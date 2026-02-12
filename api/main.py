"""
Maximo RPA API 主入口
通过 subprocess 调用 RPA 脚本，避免事件循环冲突
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import subprocess
import json
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

app = FastAPI(
    title="Maximo RPA API",
    description="Maximo 入库操作自动化 API 服务",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        "service": "maximo-rpa-api"
    }


@app.post("/api/receipt", response_model=ReceiptResponse)
async def create_receipt(request: ReceiptRequest):
    """
    创建入库单
    
    通过 subprocess 调用 RPA 脚本批量处理入库操作
    支持按 PO 行号或项目号查找
    """
    try:
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
        
        # 调用 RPA 服务脚本
        rpa_service_path = PROJECT_ROOT / "api" / "rpa_service.py"
        
        # 使用 subprocess 调用
        result = subprocess.run(
            [sys.executable, str(rpa_service_path)],
            input=json.dumps(rpa_input),
            capture_output=True,
            text=True,
            timeout=180,  # 3分钟超时
            cwd=str(PROJECT_ROOT)
        )
        
        if result.returncode != 0:
            # 脚本执行失败
            error_msg = result.stderr or result.stdout or "RPA 脚本执行失败"
            raise HTTPException(
                status_code=500,
                detail=f"RPA 执行失败: {error_msg}"
            )
        
        # 解析输出
        try:
            rpa_result = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=500,
                detail=f"无法解析 RPA 输出: {result.stdout}"
            )
        
        # 构造响应
        return ReceiptResponse(
            success=rpa_result.get('success', False),
            message="入库完成" if rpa_result.get('success') else "入库失败",
            po_number=request.po_number,
            total=rpa_result.get('total', 0),
            processed=rpa_result.get('processed', 0),
            failed=rpa_result.get('failed', 0),
            saved=rpa_result.get('saved'),
            details=rpa_result.get('results', [])
        )
        
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="RPA 执行超时（超过180秒）"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"入库操作失败: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
