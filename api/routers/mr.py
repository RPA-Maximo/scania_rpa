"""
出库单（物料需求单）API 路由

端点列表：
  GET  /api/mr              - 主页列表（MR号、流水号、目标地址、需求日期）
  GET  /api/mr/{id}         - 出库单详情（弹窗用）
  POST /api/mr/sync         - 手动触发 Maximo 出库单同步
  PUT  /api/mr/{id}/lines/{line_id}/bin   - 修改子表行仓位
  GET  /api/mr/{id}/bins/{item_number}    - 获取货柜列表（仓位选择页）
  POST /api/mr/{id}/issue   - 执行出库（先进先出校验 + 回传 Maximo）
  POST /api/mr/{id}/writeback - 手动触发回传 Maximo 并拉取新流水号

  ── 库存货柜同步 ──
  POST /api/mr/inventory/sync   - 从 Maximo 同步库存货柜数据（初始化/增量）
  GET  /api/mr/inventory/bins   - 查询货柜库存列表
  GET  /api/mr/inventory/export - 导出货柜库存为 Excel
"""
import sys
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.responses import FileResponse
from src.utils.db import get_connection, generate_id
from src.sync.mr_sync import (
    sync_mr_from_maximo,
    get_fifo_bins,
    update_bin_location,
    update_issued_qty,
)
from src.fetcher.mr_fetcher import writeback_to_maximo, fetch_mr_by_number
from src.sync.inventory_sync import (
    sync_bin_inventory,
    export_bin_inventory_excel,
    get_bins_for_item_warehouse,
)

router = APIRouter(prefix="/api/mr", tags=["出库单 MR"])


# ── Pydantic 模型 ──────────────────────────────────────────────────────────────

class SyncRequest(BaseModel):
    status_filter: str = Field("ENTERED,WAPPR", description="Maximo 状态筛选（逗号分隔）")
    max_pages: int = Field(5, ge=1, le=50, description="最多抓取页数")
    page_size: int = Field(20, ge=1, le=100, description="每页条数")


class UpdateBinRequest(BaseModel):
    bin_location: str = Field(..., description="新仓位编码")


class IssueLineInput(BaseModel):
    line_id: int = Field(..., description="子表行 ID")
    issued_qty: float = Field(..., description="实际出库数量")
    bin_location: Optional[str] = Field(None, description="仓位（不填则使用已配置值）")


class IssueRequest(BaseModel):
    lines: List[IssueLineInput] = Field(..., description="出库行列表")
    writeback: bool = Field(True, description="是否回传 Maximo")


class WritebackRequest(BaseModel):
    new_serial: Optional[str] = Field(None, description="Maximo 新建的流水号（手动填入后写入WMS）")


class InventorySyncRequest(BaseModel):
    warehouse: Optional[str] = Field(None, description="仓库过滤（如 '518'）；None=全部仓库")
    item_numbers: Optional[List[str]] = Field(None, description="指定物料编号列表；None=全部")
    max_pages: int = Field(20, ge=1, le=200, description="最多抓取页数")
    page_size: int = Field(50, ge=1, le=200, description="每页条数")
    use_invbal_api: bool = Field(False, description="True=使用 MXAPIINVBAL 备用接口")
    full_refresh: bool = Field(False, description="True=全量刷新（先清空再写入）")


# ── 工具函数 ────────────────────────────────────────────────────────────────────

def _fetch_header(conn, header_id: int) -> dict:
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM mr_header WHERE id=%s AND del_flag=0",
        (header_id,),
    )
    row = cursor.fetchone()
    cursor.close()
    if not row:
        raise HTTPException(status_code=404, detail="出库单不存在")
    return row


def _fetch_lines(conn, header_id: int) -> list:
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM mr_detail WHERE header_id=%s AND del_flag=0 ORDER BY line_number",
        (header_id,),
    )
    rows = cursor.fetchall()
    cursor.close()
    return rows


def _serialize_row(row: dict) -> dict:
    """将数据库行转为可 JSON 序列化的字典"""
    result = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


# ── 路由 ────────────────────────────────────────────────────────────────────────

@router.get("", summary="出库单列表（主页）")
def list_mr(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: Optional[str] = Query(None, description="状态筛选"),
    keyword: Optional[str] = Query(None, description="关键字（MR号/出库单号）"),
):
    """
    主页展示：MR号、流水号（出库单号）、目标地址、需求日期、WO号
    点击详情按钮弹出弹窗查看完整信息
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        where = ["del_flag=0"]
        params = []

        if status:
            where.append("status=%s")
            params.append(status)

        if keyword:
            where.append("(issue_number LIKE %s OR mr_number LIKE %s OR wo_numbers LIKE %s)")
            like = f"%{keyword}%"
            params.extend([like, like, like])

        where_sql = " AND ".join(where)
        offset = (page - 1) * page_size

        # 总数
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM mr_header WHERE {where_sql}", params)
        total = cursor.fetchone()["cnt"]

        # 数据（列表页展示：出库单号、申请号、描述/领取人、发放目标、仓库、需求日期、WO号、状态）
        cursor.execute(
            f"""SELECT id, issue_number AS serial_number,
                       request_number, applicant, charge_to,
                       warehouse, required_date, status, wo_numbers
                FROM mr_header WHERE {where_sql}
                ORDER BY required_date DESC, id DESC
                LIMIT %s OFFSET %s""",
            [*params, page_size, offset],
        )
        rows = [_serialize_row(r) for r in cursor.fetchall()]

        return {"total": total, "page": page, "page_size": page_size, "items": rows}
    finally:
        cursor.close()
        conn.close()


@router.get("/{header_id}", summary="出库单详情（弹窗）")
def get_mr_detail(header_id: int):
    """
    返回出库单主表 + 子表明细，用于弹窗展示
    """
    conn = get_connection()
    try:
        header = _serialize_row(_fetch_header(conn, header_id))
        lines = [_serialize_row(l) for l in _fetch_lines(conn, header_id)]

        # 汇总：哪些行数量未满足
        unsatisfied = [
            {"line_id": l["id"], "item_number": l["item_number"],
             "required_qty": l["required_qty"], "available_qty": l["available_qty"]}
            for l in lines
            if not l["is_satisfied"] and l.get("issued_qty") is None
        ]

        return {
            "header": header,
            "lines": lines,
            "unsatisfied_count": len(unsatisfied),
            "unsatisfied_lines": unsatisfied,
        }
    finally:
        conn.close()


@router.post("/sync", summary="手动同步出库单")
def sync_mr(req: SyncRequest):
    """从 Maximo 拉取出库单并写入本地数据库"""
    try:
        stats = sync_mr_from_maximo(
            status_filter=req.status_filter,
            max_pages=req.max_pages,
            page_size=req.page_size,
        )
        return {"success": True, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{header_id}/lines/{line_id}/bin", summary="修改子表行仓位")
def update_line_bin(header_id: int, line_id: int, req: UpdateBinRequest):
    """
    仓位允许修改（仓库在主表不允许修改）
    修改后重新判断先进先出满足情况
    """
    ok = update_bin_location(line_id, req.bin_location)
    if not ok:
        raise HTTPException(status_code=404, detail="子表行不存在")
    return {"success": True, "bin_location": req.bin_location}


@router.get("/{header_id}/bins/{item_number}", summary="获取货柜列表（仓位选择）")
def get_bins_for_item(header_id: int, item_number: str):
    """
    货柜选择页：
    - 只显示该物料所在货柜
    - 根据 MR 表头仓库进行筛选
    - 默认值基于先进先出：能满足数量优先，否则批次号最小优先
    - 返回该子表行的需求数量，前端可显示数量不足警告
    """
    conn = get_connection()
    try:
        header = _fetch_header(conn, header_id)
        warehouse = header["warehouse"]

        # 获取该行的需求数量
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT required_qty FROM mr_detail WHERE header_id=%s AND item_number=%s AND del_flag=0 LIMIT 1",
            (header_id, item_number),
        )
        line_row = cursor.fetchone()
        cursor.close()
        required_qty = float(line_row["required_qty"] or 0) if line_row else 0.0

        result = get_fifo_bins(item_number, warehouse, required_qty)
        result["required_qty"] = required_qty
        result["warehouse"] = warehouse
        result["item_number"] = item_number

        return result
    finally:
        conn.close()


@router.post("/{header_id}/issue", summary="执行出库（先进先出校验）")
def execute_issue(header_id: int, req: IssueRequest):
    """
    执行出库操作：
    1. 更新每行的实际出库数量和仓位
    2. 校验先进先出：能满足则无提醒，不满足则在响应中标记警告
    3. 若设置 writeback=True，则将数量回传 Maximo 并保存
    4. 如果 WMS 出库数量 < Maximo 需求数量，Maximo 端创建剩余使用情况

    返回：
      - lines_result: 每行处理结果
      - has_warning: 是否存在数量不满足的行（前端在右上角显示提示）
      - unsatisfied_lines: 未满足行列表
    """
    conn = get_connection()
    try:
        header = _fetch_header(conn, header_id)
        all_lines = {l["id"]: l for l in _fetch_lines(conn, header_id)}
    finally:
        conn.close()

    lines_result = []
    unsatisfied = []
    writeback_lines = []

    for line_input in req.lines:
        line_id = line_input.line_id
        line = all_lines.get(line_id)
        if not line:
            lines_result.append({"line_id": line_id, "success": False, "error": "行不存在"})
            continue

        # 更新仓位（如果提供了新仓位）
        if line_input.bin_location:
            update_bin_location(line_id, line_input.bin_location)

        # 更新已出库数量
        update_issued_qty(line_id, line_input.issued_qty)

        required = float(line["required_qty"] or 0)
        issued = line_input.issued_qty
        satisfied = issued >= required

        result_item = {
            "line_id": line_id,
            "item_number": line["item_number"],
            "required_qty": required,
            "issued_qty": issued,
            "is_satisfied": satisfied,
            "bin_location": line_input.bin_location or line["bin_location"],
        }
        lines_result.append(result_item)

        if not satisfied:
            unsatisfied.append(result_item)

        # 准备回传 Maximo 的数据
        writeback_lines.append({
            "maximo_lineid": line["maximo_lineid"],
            "quantity": issued,
            "binnum": line_input.bin_location or line["bin_location"] or "",
        })

    # 回传 Maximo
    writeback_ok = False
    if req.writeback and header.get("maximo_href"):
        writeback_ok = writeback_to_maximo(
            maximo_href=header["maximo_href"],
            lines=writeback_lines,
            save_and_complete=(len(unsatisfied) == 0),  # 全部满足才变完成状态
        )

    return {
        "success": True,
        "has_warning": len(unsatisfied) > 0,
        "unsatisfied_lines": unsatisfied,
        "lines_result": lines_result,
        "writeback_ok": writeback_ok,
        "message": (
            f"出库完成，{len(unsatisfied)} 行数量未满足，请注意右上角提示"
            if unsatisfied
            else "出库完成，所有数量已满足"
        ),
    }


@router.post("/{header_id}/writeback", summary="手动回传 Maximo 并写入新流水号")
def writeback_and_update_serial(header_id: int, req: WritebackRequest):
    """
    当出库数量未满足时：
    1. Maximo 创建剩余使用情况，生成新流水号
    2. 调用此端点将新流水号写入 WMS 对应出库单
    3. 前端在 WMS 界面点击"回传"按钮后调用此端点

    如果 req.new_serial 为空，则从 Maximo 重新拉取该单，获取最新状态
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 如果传入了新流水号，直接写入
        if req.new_serial:
            cursor.execute(
                """UPDATE mr_header
                   SET wo_numbers=CONCAT(IFNULL(wo_numbers,''), IF(wo_numbers IS NULL OR wo_numbers='', '', ' / '), %s),
                       update_time=NOW()
                   WHERE id=%s AND del_flag=0""",
                (req.new_serial, header_id),
            )
            conn.commit()
            return {"success": True, "new_serial": req.new_serial, "message": "新流水号已写入 WMS"}

        # 否则从 Maximo 拉取最新数据，更新主表状态
        header = _fetch_header(conn, header_id)
        issue_number = header["issue_number"]
        raw = fetch_mr_by_number(issue_number)
        if not raw:
            raise HTTPException(status_code=404, detail="Maximo 中未找到该出库单")

        new_status = raw.get("status") or ""
        cursor.execute(
            "UPDATE mr_header SET status=%s, update_time=NOW() WHERE id=%s",
            (new_status, header_id),
        )
        conn.commit()

        return {
            "success": True,
            "issue_number": issue_number,
            "status": new_status,
            "message": "已从 Maximo 刷新状态",
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


# ── 库存货柜同步 API ────────────────────────────────────────────────────────────

@router.post("/inventory/sync", summary="同步库存货柜数据（初始化/增量）")
def sync_inventory(req: InventorySyncRequest):
    """
    从 Maximo MXAPIINVENTORY（含 invbalance 货柜明细）同步库存到 bin_inventory 表。

    用途：
    - 初次使用：full_refresh=True 全量写入
    - 日常增量：full_refresh=False 仅更新变化数据
    - 按仓库：warehouse='518' 只同步指定仓库
    - 备用接口：use_invbal_api=True（当主接口 invbalance 子集不可用时）

    化学品批次信息字段待客户确认后补充到 oslc.select 中。
    """
    try:
        stats = sync_bin_inventory(
            warehouse=req.warehouse,
            item_numbers=req.item_numbers,
            max_pages=req.max_pages,
            page_size=req.page_size,
            use_invbal_api=req.use_invbal_api,
            full_refresh=req.full_refresh,
        )
        return {"success": True, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/bins", summary="查询货柜库存列表")
def list_bins(
    warehouse: Optional[str] = Query(None, description="仓库过滤"),
    item_number: Optional[str] = Query(None, description="物料编号过滤"),
    bin_code: Optional[str] = Query(None, description="货柜编号过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """
    查询 bin_inventory 表中的货柜库存，按先进先出顺序（receipt_date ASC）排序
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        where = ["del_flag=0", "quantity > 0"]
        params = []
        if warehouse:
            where.append("warehouse=%s"); params.append(warehouse)
        if item_number:
            where.append("item_number LIKE %s"); params.append(f"%{item_number}%")
        if bin_code:
            where.append("bin_code LIKE %s"); params.append(f"%{bin_code}%")

        where_sql = " AND ".join(where)
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM bin_inventory WHERE {where_sql}", params)
        total = cursor.fetchone()["cnt"]

        offset = (page - 1) * page_size
        cursor.execute(
            f"""SELECT id, item_number, warehouse, bin_code, bin_name,
                       lot_number, batch_number, quantity, receipt_date, update_time
                FROM bin_inventory WHERE {where_sql}
                ORDER BY item_number, receipt_date ASC, bin_code
                LIMIT %s OFFSET %s""",
            [*params, page_size, offset],
        )
        rows = [_serialize_row(r) for r in cursor.fetchall()]
        return {"total": total, "page": page, "page_size": page_size, "items": rows}
    finally:
        cursor.close()
        conn.close()


@router.get("/inventory/export", summary="导出货柜库存为 Excel")
def export_inventory(
    warehouse: Optional[str] = Query(None, description="仓库过滤"),
    item_number: Optional[str] = Query(None, description="物料编号过滤"),
):
    """
    将 bin_inventory 表按先进先出顺序导出为 Excel 文件
    包含字段：物料编号、仓库、货柜、批次号、数量、入库日期
    （化学品批次信息待客户补充字段后扩展）
    """
    try:
        path = export_bin_inventory_excel(warehouse=warehouse, item_number=item_number)
        if not path:
            raise HTTPException(status_code=404, detail="无库存数据可导出")
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"bin_inventory_{warehouse or 'all'}.xlsx",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
