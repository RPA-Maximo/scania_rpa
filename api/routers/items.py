"""
物料主数据 API 路由

端点：
  POST /api/items/sync          手动触发物料同步
  GET  /api/items/sync/status   查看同步服务状态（含下次定时执行时间）
  GET  /api/items               分页查询物料列表
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.sync.item_sync import item_sync_service, item_sync_scheduler
from src.utils.db import get_connection

router = APIRouter(prefix="/api/items", tags=["items"])


# ── 请求/响应模型 ─────────────────────────────────────────────────────────────


class ItemSyncRequest(BaseModel):
    """手动触发同步参数"""
    since_date: Optional[str] = None
    """增量起点（ISO格式 如 '2024-06-01T00:00:00'）；
       None = 昨天00:00；full_no_filter=true 时忽略此字段"""

    full_no_filter: bool = False
    """True = 完全不加时间过滤，拉取所有非 OBSOLETE 物料（量大，慎用）"""

    max_pages: int = 100
    page_size: int = 100


# ── 端点 ──────────────────────────────────────────────────────────────────────


@router.post("/sync", summary="手动触发物料同步")
def trigger_item_sync(req: ItemSyncRequest):
    """
    手动触发从 Maximo 同步物料主数据到 material 表。

    - 不传 since_date：默认增量，只同步昨天00:00以后更新的物料
    - 传 since_date：从指定时间起增量同步
    - full_no_filter=true：全量（不加时间过滤，拉取所有物料，量大慎用）
    """
    since_dt: Optional[datetime] = None
    if not req.full_no_filter and req.since_date:
        try:
            since_dt = datetime.fromisoformat(req.since_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"since_date 格式错误: {req.since_date}")

    # 动态更新 page 配置
    item_sync_service.update_config(
        max_pages=req.max_pages,
        page_size=req.page_size,
    )

    result = item_sync_service.sync_once(
        since_date=since_dt,
        full_no_filter=req.full_no_filter,
    )
    return result


@router.get("/sync/status", summary="查看同步服务状态")
def get_sync_status():
    """返回同步服务状态和每日定时调度器下次执行时间"""
    return {
        "service":   item_sync_service.get_status(),
        "scheduler": item_sync_scheduler.get_status(),
    }


@router.get("", summary="查询物料列表")
def list_items(
    keyword: Optional[str] = Query(None, description="物料编号或名称关键字"),
    page:     int          = Query(1,    ge=1,  description="页码"),
    page_size: int         = Query(20,   ge=1, le=200, description="每页条数"),
):
    """
    分页查询 material 表中的物料列表

    支持按物料编号（code）或名称（name）关键字搜索。
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        where = ["del_flag=0"]
        params: list = []

        if keyword:
            where.append("(code LIKE %s OR name LIKE %s)")
            params += [f"%{keyword}%", f"%{keyword}%"]

        where_sql = " AND ".join(where)
        offset = (page - 1) * page_size

        cursor.execute(
            f"SELECT COUNT(*) AS total FROM material WHERE {where_sql}",
            params,
        )
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"""SELECT
                    code          AS item_number,
                    name          AS item_name,
                    ordering_unit,
                    issuing_unit,
                    status,
                    batch_type    AS lot_type,
                    maximo_changedate,
                    sync_time
                FROM material
                WHERE {where_sql}
                ORDER BY code
                LIMIT %s OFFSET %s""",
            params + [page_size, offset],
        )
        rows = cursor.fetchall()

        # datetime → str
        for r in rows:
            for f in ("maximo_changedate", "sync_time"):
                if r.get(f) and not isinstance(r[f], str):
                    r[f] = r[f].strftime("%Y-%m-%d %H:%M:%S")

        return {
            "total":     total,
            "page":      page,
            "page_size": page_size,
            "items":     rows,
        }
    finally:
        cursor.close()
        conn.close()
