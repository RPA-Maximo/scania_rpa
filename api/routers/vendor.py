"""
供应商账户同步 API 路由

端点：
  POST /api/vendor/sync          手动触发供应商同步
  GET  /api/vendor               分页查询供应商列表
  GET  /api/vendor/export        导出 Excel（供客户导入）
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.sync.vendor_sync import sync_vendors, export_vendors_excel
from src.utils.db import get_connection

router = APIRouter(prefix="/api/vendor", tags=["供应商账户同步"])


class VendorSyncRequest(BaseModel):
    vendor_type: Optional[str] = None
    """供应商类型过滤（如 'V'=Vendor）；None=不过滤"""
    max_pages: int = 50
    page_size: int = 100


@router.post("/sync", summary="手动触发供应商同步")
def trigger_vendor_sync(req: VendorSyncRequest):
    """
    从 Maximo MXAPICOMPANY 同步供应商编号和供应商名称到本地 vendor 表。
    """
    try:
        stats = sync_vendors(
            vendor_type=req.vendor_type,
            max_pages=req.max_pages,
            page_size=req.page_size,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"供应商同步失败: {e}")

    return {
        "success": True,
        "stats":   stats,
        "message": (
            f"同步完成：新增 {stats['inserted']} 条，"
            f"更新 {stats['updated']} 条，"
            f"跳过 {stats['skipped']} 条"
        ),
    }


@router.get("", summary="查询供应商列表")
def list_vendors(
    keyword:   Optional[str] = Query(None, description="供应商编号或名称关键字"),
    page:      int           = Query(1,    ge=1),
    page_size: int           = Query(20,   ge=1, le=200),
):
    """分页查询本地 vendor 表"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        where  = ["del_flag=0"]
        params = []
        if keyword:
            where.append("(vendor_code LIKE %s OR vendor_name LIKE %s)")
            params += [f"%{keyword}%", f"%{keyword}%"]

        w_sql  = " AND ".join(where)
        offset = (page - 1) * page_size

        cursor.execute(f"SELECT COUNT(*) AS total FROM vendor WHERE {w_sql}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"""SELECT vendor_code, vendor_name, vendor_type, status, currency, sync_time
                FROM vendor WHERE {w_sql}
                ORDER BY vendor_code
                LIMIT %s OFFSET %s""",
            params + [page_size, offset],
        )
        rows = cursor.fetchall()
        for r in rows:
            if r.get("sync_time") and not isinstance(r["sync_time"], str):
                r["sync_time"] = r["sync_time"].strftime("%Y-%m-%d %H:%M:%S")

        return {"total": total, "page": page, "page_size": page_size, "items": rows}
    finally:
        cursor.close()
        conn.close()


@router.get("/export", summary="导出供应商账户 Excel")
def export_vendors(
    keyword: Optional[str] = Query(None, description="供应商编号或名称关键字过滤"),
):
    """
    将本地 vendor 表中的供应商编号和名称导出为 Excel，供客户系统导入。

    Excel 列：供应商编号、供应商名称、供应商类型、状态、币种、同步时间
    """
    try:
        data = export_vendors_excel(keyword=keyword)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")

    if not data:
        raise HTTPException(status_code=404, detail="暂无供应商数据，请先执行同步")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=vendors_{ts}.xlsx"},
    )
