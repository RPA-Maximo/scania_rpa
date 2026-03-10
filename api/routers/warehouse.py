"""
仓库信息同步 API 路由

端点：
  POST /api/warehouse/sync        同步仓库主数据（Maximo MXAPILOCATION）
  POST /api/warehouse/sync/bins   同步仓位信息（Maximo MXAPIINVBAL）
  GET  /api/warehouse             查询仓库列表
  GET  /api/warehouse/bins        查询仓位列表
  GET  /api/warehouse/export      导出仓库+仓位 Excel
  POST /api/warehouse/import      Excel 导入仓库-仓位关联
  GET  /api/warehouse/template    下载导入模板
"""
import io
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import openpyxl
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.sync.warehouse_sync import (
    sync_warehouses,
    sync_warehouse_bins,
    export_warehouse_excel,
    import_warehouse_bins_excel,
)
from src.utils.db import get_connection

router = APIRouter(prefix="/api/warehouse", tags=["仓库信息同步"])


class WHSyncRequest(BaseModel):
    site_id:   Optional[str] = None
    max_pages: int = 20
    page_size: int = 100


class BinSyncRequest(BaseModel):
    warehouse: Optional[str] = None
    site_id:   Optional[str] = None
    max_pages: int = 50
    page_size: int = 100


@router.post("/sync", summary="同步仓库主数据")
def trigger_warehouse_sync(req: WHSyncRequest):
    """从 Maximo MXAPILOCATION 同步仓库（Storeroom）主数据。"""
    try:
        stats = sync_warehouses(
            site_id=req.site_id,
            max_pages=req.max_pages,
            page_size=req.page_size,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"仓库同步失败: {e}")

    return {
        "success": True,
        "stats":   stats,
        "message": f"新增 {stats['inserted']}，更新 {stats['updated']}，跳过 {stats['skipped']}",
    }


@router.post("/sync/bins", summary="同步仓位信息")
def trigger_bin_sync(req: BinSyncRequest):
    """
    从 Maximo 库存数据（MXAPIINVBAL）提取仓位编号，
    写入 warehouse_bin 关联表。
    """
    try:
        stats = sync_warehouse_bins(
            warehouse=req.warehouse,
            site_id=req.site_id,
            max_pages=req.max_pages,
            page_size=req.page_size,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"仓位同步失败: {e}")

    return {
        "success": True,
        "stats":   stats,
        "message": f"新增 {stats['inserted']}，更新 {stats['updated']}，跳过 {stats['skipped']}",
    }


@router.get("", summary="查询仓库列表")
def list_warehouses(
    keyword:   Optional[str] = Query(None, description="仓库编号或名称关键字"),
    page:      int           = Query(1,    ge=1),
    page_size: int           = Query(20,   ge=1, le=200),
):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        where  = ["del_flag=0"]
        params = []
        if keyword:
            where.append("(code LIKE %s OR name LIKE %s)")
            params += [f"%{keyword}%", f"%{keyword}%"]

        w_sql  = " AND ".join(where)
        offset = (page - 1) * page_size

        cursor.execute(f"SELECT COUNT(*) AS total FROM warehouse WHERE {w_sql}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"""SELECT code, name, site, org, location_type, status, sync_time
                FROM warehouse WHERE {w_sql}
                ORDER BY code LIMIT %s OFFSET %s""",
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


@router.get("/bins", summary="查询仓位列表")
def list_bins(
    warehouse: Optional[str] = Query(None, description="仓库编号过滤"),
    keyword:   Optional[str] = Query(None, description="仓位编号或名称关键字"),
    page:      int           = Query(1,    ge=1),
    page_size: int           = Query(20,   ge=1, le=200),
):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        where  = ["del_flag=0"]
        params = []
        if warehouse:
            where.append("warehouse=%s")
            params.append(warehouse)
        if keyword:
            where.append("(bin_code LIKE %s OR bin_name LIKE %s)")
            params += [f"%{keyword}%", f"%{keyword}%"]

        w_sql  = " AND ".join(where)
        offset = (page - 1) * page_size

        cursor.execute(
            f"SELECT COUNT(*) AS total FROM warehouse_bin WHERE {w_sql}", params
        )
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"""SELECT warehouse, bin_code, bin_name, site, remark, sync_source
                FROM warehouse_bin WHERE {w_sql}
                ORDER BY warehouse, bin_code LIMIT %s OFFSET %s""",
            params + [page_size, offset],
        )
        rows = cursor.fetchall()
        return {"total": total, "page": page, "page_size": page_size, "items": rows}
    finally:
        cursor.close()
        conn.close()


@router.get("/export", summary="导出仓库+仓位 Excel")
def export_warehouse(
    warehouse: Optional[str] = Query(None, description="仓库过滤；None=全部"),
    include_bins: bool = Query(True, description="是否包含仓位关联工作表"),
):
    """
    导出 Excel 文件，包含两个工作表：
    - **仓库信息**：仓库编号、名称、地点、状态等
    - **仓库-仓位关联**：仓库与仓位的关联关系（include_bins=true 时）
    """
    try:
        data = export_warehouse_excel(include_bins=include_bins, warehouse=warehouse)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=warehouse_{ts}.xlsx"},
    )


@router.post("/import", summary="Excel 导入仓库-仓位关联")
async def import_warehouse_bins(file: UploadFile = File(...)):
    """
    上传 Excel 文件批量导入仓库-仓位关联关系。

    **Excel 格式：**
    - 列：仓库编号、仓位编号、仓位名称（可选）、备注（可选）
    - 以 仓库编号+仓位编号 为唯一键，已存在则更新，不存在则插入
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 文件")

    content = await file.read()
    try:
        stats = import_warehouse_bins_excel(content)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")

    return {
        "success":  True,
        "inserted": stats["inserted"],
        "updated":  stats["updated"],
        "skipped":  stats["skipped"],
        "warnings": stats.get("warnings", []),
        "message":  (
            f"导入完成：新增 {stats['inserted']} 条，"
            f"更新 {stats['updated']} 条，"
            f"跳过 {stats['skipped']} 条"
        ),
    }


@router.get("/template", summary="下载仓库-仓位导入模板")
def download_template():
    """下载 Excel 导入模板（含列标题和示例数据）"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "仓库-仓位关联导入"
    ws.append(["仓库编号", "仓位编号", "仓位名称", "备注"])
    ws.append(["518", "CVC4802A", "A区货架01", "示例数据"])
    ws.append(["518", "CVC4803B", "",           ""])
    for col, w in zip("ABCD", [15, 20, 25, 30]):
        ws.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=warehouse_bin_template.xlsx"},
    )
