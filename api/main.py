"""
Maximo RPA API 主入口
通过 subprocess 调用 RPA 脚本，避免事件循环冲突
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import subprocess
import json
import sys
import time
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from rpa.keepalive import KeepaliveManager
from api.routers.auth import router as auth_router
from api.routers.scraper import router as scraper_router
from api.routers.settings import router as settings_router
from api.routers.sync import router as sync_router
from api.routers.mr import router as mr_router
from api.routers.items import router as items_router
from api.routers.material_location import router as material_location_router
from src.sync.po_sync_service import po_sync_scheduler
from src.sync.item_sync import item_sync_scheduler

# 保活管理器（全局单例）
keepalive_manager = KeepaliveManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动/停止保活定时器和 PO 增量同步调度器"""
    keepalive_manager.start()
    po_sync_scheduler.start()     # 启动 5 分钟 PO 增量同步
    item_sync_scheduler.start()   # 启动每日凌晨物料全量同步
    yield
    item_sync_scheduler.stop()
    po_sync_scheduler.stop()
    keepalive_manager.stop()


app = FastAPI(
    title="Maximo RPA API",
    description="Maximo 入库操作自动化 API 服务",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 注册路由
app.include_router(auth_router)
app.include_router(scraper_router)
app.include_router(settings_router)
app.include_router(sync_router)
app.include_router(mr_router)
app.include_router(items_router)
app.include_router(material_location_router)

# 静态文件（前端页面）
_static_dir = PROJECT_ROOT / "api" / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/mr", include_in_schema=False)
async def mr_wms_page():
    """出库单 WMS 前端页面"""
    return FileResponse(str(_static_dir / "mr_wms.html"))

import logging

# API 请求日志
api_logger = logging.getLogger("api")
api_logger.setLevel(logging.INFO)
if not api_logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    api_logger.addHandler(_handler)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志中间件"""
    start = time.time()
    response = await call_next(request)
    elapsed = (time.time() - start) * 1000  # 毫秒
    api_logger.info(
        f"API: {request.method} {request.url.path} → "
        f"{response.status_code} ({elapsed:.0f}ms)"
    )
    return response


# 数据模型
class ReceiptItem(BaseModel):
    """入库项"""
    po_line: Optional[str] = Field(None, description="PO 行号（与 item_num 二选一）")
    item_num: Optional[str] = Field(None, description="项目号（与 item_num 二选一）")
    quantity: float = Field(..., description="入库数量（支持小数）", example=2.5)
    remark: Optional[str] = Field(None, description="备注", example="自动入库")


class ReceiptRequest(BaseModel):
    """入库请求"""
    po_number: str = Field(..., description="采购单号", example="CN5123")
    items: List[ReceiptItem] = Field(
        ..., 
        description="入库项列表",
        example=[
            {
                "item_num": "20326862",
                "quantity": 2.0,
                "remark": "这是一个备注"
            },
            {
                "item_num": "20346794",
                "quantity": 3.5,
                "remark": "rpa自动处理"
            }
        ]
    )
    auto_save: bool = Field(False, description="是否自动保存（false 表示仅填写不保存）")


class ReceiptResponse(BaseModel):
    """入库响应"""
    success: bool
    message: str
    po_number: str
    total: int
    processed: int
    failed: int
    saved: Optional[bool] = None
    details: Optional[List[dict]] = None


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "Maximo RPA API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "service": "maximo-rpa-api",
        "keepalive": keepalive_manager.get_status()
    }


@app.get("/api/keepalive")
async def trigger_keepalive():
    """
    手动触发保活
    
    返回保活结果和当前会话状态
    """
    result = keepalive_manager.trigger_keepalive()
    return result


@app.get("/api/keepalive/status")
async def keepalive_status():
    """
    查询保活状态（不触发保活操作）
    """
    return keepalive_manager.get_status()


@app.post("/api/receipt", response_model=ReceiptResponse)
async def create_receipt(request: ReceiptRequest):
    """
    创建入库单
    
    通过 subprocess 调用 RPA 脚本批量处理入库操作
    支持按 PO 行号或项目号查找
    """
    # 获取保活锁（暂停保活定时器）
    keepalive_manager.acquire()
    
    try:
        return await _execute_receipt(request)
    finally:
        # 释放保活锁（恢复保活定时器 + 重新倒计时）
        keepalive_manager.release()


async def _execute_receipt(request: ReceiptRequest) -> ReceiptResponse:
    """实际执行入库操作（内部方法）"""
    print("\n" + "=" * 80)
    print("FastAPI: 收到入库请求")
    print("=" * 80)
    
    try:
        print(f"\n[1/5] 请求参数:")
        print(f"  - PO 单号: {request.po_number}")
        print(f"  - 自动保存: {request.auto_save}")
        print(f"  - 入库项数量: {len(request.items)}")
        for idx, item in enumerate(request.items, 1):
            print(f"    {idx}. PO行={item.po_line}, 项目号={item.item_num}, 数量={item.quantity}, 备注={item.remark}")
        
        # 转换数据格式（将 float 转为字符串格式）
        po_lines_data = [
            {
                'po_line': item.po_line,
                'item_num': item.item_num,
                'quantity': f"{item.quantity:.2f}",  # 转换为两位小数的字符串
                'remark': item.remark or ''
            }
            for item in request.items
        ]
        
        # 准备调用参数
        rpa_input = {
            'po_number': request.po_number,
            'po_lines_data': po_lines_data,
            'auto_save': request.auto_save
        }
        
        print(f"\n[2/5] 准备调用 RPA 服务:")
        print(f"  输入数据: {json.dumps(rpa_input, ensure_ascii=False, indent=2)}")
        
        # 调用 RPA 服务脚本
        rpa_service_path = PROJECT_ROOT / "api" / "rpa_service.py"
        print(f"  RPA 脚本路径: {rpa_service_path}")
        print(f"  Python 解释器: {sys.executable}")
        print(f"  工作目录: {PROJECT_ROOT}")
        
        # 使用 subprocess 调用
        print(f"\n[3/5] 执行 RPA 脚本...")
        result = subprocess.run(
            [sys.executable, str(rpa_service_path)],
            input=json.dumps(rpa_input),
            capture_output=True,
            text=True,
            timeout=180,  # 3分钟超时
            cwd=str(PROJECT_ROOT)
        )
        
        print(f"\n[4/5] RPA 脚本执行完成:")
        print(f"  返回码: {result.returncode}")
        print(f"  标准输出长度: {len(result.stdout)} 字符")
        print(f"  标准错误长度: {len(result.stderr)} 字符")
        
        if result.stderr:
            print(f"\n  标准错误输出 (stderr):")
            print("  " + "-" * 76)
            for line in result.stderr.split('\n'):
                print(f"  {line}")
            print("  " + "-" * 76)
        
        if result.returncode != 0:
            # 脚本执行失败
            error_msg = result.stderr or result.stdout or "RPA 脚本执行失败"
            print(f"\n✗ RPA 脚本执行失败 (返回码 {result.returncode})")
            raise HTTPException(
                status_code=500,
                detail=f"RPA 执行失败: {error_msg}"
            )
        
        # 解析输出
        print(f"\n  标准输出 (stdout):")
        print(f"  {result.stdout[:500]}..." if len(result.stdout) > 500 else f"  {result.stdout}")
        
        try:
            rpa_result = json.loads(result.stdout)
            print(f"\n  解析后的结果:")
            print(f"  {json.dumps(rpa_result, ensure_ascii=False, indent=2)}")
        except json.JSONDecodeError as e:
            print(f"\n✗ 无法解析 RPA 输出: {e}")
            print(f"  原始输出: {result.stdout}")
            raise HTTPException(
                status_code=500,
                detail=f"无法解析 RPA 输出: {result.stdout}"
            )
        
        # 构造响应
        print(f"\n[5/5] 构造响应:")
        response = ReceiptResponse(
            success=rpa_result.get('success', False),
            message="入库完成" if rpa_result.get('success') else "入库失败",
            po_number=request.po_number,
            total=rpa_result.get('total', 0),
            processed=rpa_result.get('processed', 0),
            failed=rpa_result.get('failed', 0),
            saved=rpa_result.get('saved'),
            details=rpa_result.get('results', [])
        )
        print(f"  响应: {response.model_dump()}")
        print("\n" + "=" * 80)
        print("FastAPI: 请求处理完成")
        print("=" * 80 + "\n")
        
        return response
        
    except subprocess.TimeoutExpired:
        print(f"\n✗ RPA 执行超时（超过180秒）")
        raise HTTPException(
            status_code=504,
            detail="RPA 执行超时（超过180秒）"
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"\n✗ 发生异常: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"入库操作失败: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
