"""
PO 增量同步管理 API 路由

提供对自动同步调度器的完整控制：状态查询、手动触发、参数调整。
"""
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.sync.po_sync_service import po_sync_service, po_sync_scheduler

router = APIRouter(prefix="/api/sync/po", tags=["PO 增量同步"])


# ── 请求模型 ──────────────────────────────────────────────────────────────────

class SyncConfigRequest(BaseModel):
    status_filter: Optional[str] = Field(
        None,
        description="PO 状态筛选，如 'APPR'（已批准）、'WAPPR'（待批准）。"
                    "留空则不按状态过滤",
    )
    max_pages: Optional[int] = Field(
        None,
        description="每次同步最多抓取的页数（默认 5 页 × 每页 20 条 = 最多 100 条）",
        ge=1, le=100,
    )
    page_size: Optional[int] = Field(
        None,
        description="每页条数（默认 20）",
        ge=1, le=100,
    )
    auto_sync_materials: Optional[bool] = Field(
        None,
        description="是否自动将 Maximo 新物料同步到 WMS material 表（默认 true）",
    )


class IntervalRequest(BaseModel):
    interval_minutes: float = Field(
        ...,
        description="同步间隔（分钟）。最小 1 分钟，默认 5 分钟",
        ge=1, le=1440,
    )


# ── 端点 ──────────────────────────────────────────────────────────────────────

@router.get("/status", summary="查询同步状态")
async def get_sync_status():
    """
    返回同步服务和调度器的完整状态，包括：
    - 调度器是否运行、当前同步间隔
    - 上次同步时间、结果摘要
    - 当前同步参数配置
    """
    return {
        'scheduler': po_sync_scheduler.get_status(),
        'service': po_sync_service.get_status(),
    }


@router.post("/trigger", summary="手动触发一次同步")
async def trigger_sync():
    """
    立即执行一次增量同步（不影响自动调度计划）。

    - 若上次同步仍在运行，本次将被跳过并返回提示
    - 认证信息从 auth_manager 获取，需提前通过 `POST /api/auth/curl` 更新
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        result = await loop.run_in_executor(executor, po_sync_service.sync_once)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步执行异常: {e}")
    finally:
        executor.shutdown(wait=False)

    if not result.get('success') and not result.get('skipped'):
        raise HTTPException(status_code=500, detail=result.get('message', '同步失败'))
    return result


@router.post("/start", summary="启动自动同步调度器")
async def start_scheduler():
    """启动 5 分钟定时自动同步调度器（服务启动时已自动调用，通常无需手动操作）"""
    if po_sync_scheduler.get_status()['running']:
        return {'message': '调度器已在运行中', 'status': po_sync_scheduler.get_status()}
    po_sync_scheduler.start()
    return {'message': '调度器已启动', 'status': po_sync_scheduler.get_status()}


@router.post("/stop", summary="停止自动同步调度器")
async def stop_scheduler():
    """停止定时自动同步（不影响正在执行的同步任务）"""
    if not po_sync_scheduler.get_status()['running']:
        return {'message': '调度器未在运行', 'status': po_sync_scheduler.get_status()}
    po_sync_scheduler.stop()
    return {'message': '调度器已停止', 'status': po_sync_scheduler.get_status()}


@router.put("/config", summary="更新同步参数")
async def update_sync_config(request: SyncConfigRequest):
    """
    动态调整同步参数，立即生效（下次同步触发时使用新参数）。

    **常用配置示例：**

    只同步已批准的 PO，每次最多 200 条：
    ```json
    {"status_filter": "APPR", "max_pages": 10, "page_size": 20}
    ```

    不限状态全量扫描：
    ```json
    {"status_filter": null, "max_pages": 50}
    ```
    """
    result = po_sync_service.update_config(
        status_filter=request.status_filter,
        max_pages=request.max_pages,
        page_size=request.page_size,
        auto_sync_materials=request.auto_sync_materials,
    )
    return result


@router.put("/interval", summary="修改同步间隔")
async def update_sync_interval(request: IntervalRequest):
    """
    修改自动同步的时间间隔（分钟），立即对下次触发生效。

    默认 5 分钟。建议范围：1～60 分钟。
    """
    seconds = int(request.interval_minutes * 60)
    po_sync_scheduler.set_interval(seconds)
    return {
        'message': f'同步间隔已修改为 {request.interval_minutes} 分钟',
        'interval_seconds': seconds,
        'scheduler_status': po_sync_scheduler.get_status(),
    }
