"""
PO 增量同步管理 API 路由

提供对自动同步调度器的完整控制：状态查询、手动触发、参数调整。
"""
import io
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List

from src.sync.po_sync_service import po_sync_service, po_sync_scheduler
from src.utils.db import get_connection

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


@router.get("/export", summary="导出采购订单为 Excel")
async def export_po_excel(
    limit: int = Query(1000, ge=1, le=10000, description="最多导出条数（默认 1000，最大 10000）"),
):
    """
    将数据库中已同步的采购订单导出为 Excel 文件，包含两个工作表：

    - **采购订单**：主表信息（PO 号、供应商、收货方、创建时间等）
    - **采购明细**：子表行项目（物料号、描述、数量、单价等）

    点击 Swagger UI 的 **Download file** 按钮即可保存文件。
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise HTTPException(status_code=500, detail="缺少 openpyxl 依赖，请执行: pip install openpyxl")

    try:
        conn = get_connection()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库连接失败: {e}")

    try:
        cursor = conn.cursor(dictionary=True)

        # ── 查询主表 ──────────────────────────────────────────────────────
        cursor.execute(f"""
            SELECT
                id,
                code            AS `PO号`,
                description     AS `描述`,
                status          AS `状态`,
                order_date      AS `订单日期`,
                request_date    AS `需求日期`,
                total_cost      AS `总金额`,
                currency        AS `币种`,
                supplier_name   AS `供应商名称`,
                vendor_code     AS `供应商代码`,
                supplier_address AS `供应商地址`,
                supplier_zip    AS `供应商邮政编码`,
                supplier_city   AS `供应商城市`,
                supplier_contact AS `供应商联系人`,
                supplier_phone  AS `供应商电话`,
                supplier_email  AS `供应商邮箱`,
                company_name    AS `公司名称`,
                street_address  AS `街道地址`,
                city            AS `城市`,
                postal_code     AS `邮政编码`,
                country         AS `国家`,
                create_time     AS `同步时间`
            FROM purchase_order
            WHERE del_flag = 0
            ORDER BY create_time DESC
            LIMIT {limit}
        """)
        headers = cursor.fetchall()

        # ── 查询子表 ──────────────────────────────────────────────────────
        if headers:
            po_ids = [r['id'] for r in headers]
            placeholders = ','.join(['%s'] * len(po_ids))
            cursor.execute(f"""
                SELECT
                    p.code              AS `PO号`,
                    b.number            AS `行号`,
                    COALESCE(b.item_code, m.code) AS `物料编号`,
                    b.sku_names         AS `物料名称`,
                    b.model_num         AS `型号`,
                    b.size_info         AS `尺寸`,
                    b.qty               AS `数量`,
                    b.ordering_unit     AS `订购单位`,
                    b.target_container  AS `目标货柜`,
                    w.code              AS `目标仓库`,
                    b.form_id           AS `主表ID`
                FROM purchase_order_bd b
                JOIN purchase_order p ON p.id = b.form_id
                LEFT JOIN material m ON m.id = b.sku
                LEFT JOIN warehouse w ON w.id = b.warehouse
                WHERE b.form_id IN ({placeholders})
                ORDER BY b.form_id, b.number
            """, po_ids)
            details = cursor.fetchall()
        else:
            details = []

        cursor.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询数据失败: {e}")
    finally:
        conn.close()

    # ── 生成 Excel ────────────────────────────────────────────────────────
    wb = openpyxl.Workbook()

    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def _write_sheet(ws, rows: list):
        if not rows:
            ws.append(["暂无数据"])
            return
        # 写表头（去掉内部 id/del_flag 字段）
        cols = [k for k in rows[0].keys() if k not in ('id', 'del_flag', '主表ID')]
        ws.append(cols)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center
        ws.row_dimensions[1].height = 22
        # 写数据
        for row in rows:
            ws.append([row.get(c) for c in cols])
        # 自适应列宽（最大 40）
        for col in ws.columns:
            max_len = max((len(str(c.value or '')) for c in col), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)

    ws1 = wb.active
    ws1.title = "采购订单"
    _write_sheet(ws1, headers)

    ws2 = wb.create_sheet("采购明细")
    _write_sheet(ws2, details)

    # ── 输出为字节流 ──────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"PO_Export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


class ResyncRequest(BaseModel):
    po_numbers: List[str] = Field(
        ...,
        description="要强制重同步的 PO 号列表，如 ['CN4300', 'CN5044']",
        min_items=1,
    )


@router.post("/resync", summary="强制重新同步指定PO（修复历史缺失字段）")
async def resync_specific_pos(request: ResyncRequest):
    """
    对指定 PO 号执行**强制重同步**：先删除 WMS 中已有记录，再从 Maximo 重新拉取写入。

    **适用场景：**
    - 字段结构变更后（新增 item_code / model_num / size_info / target_container），
      修复在变更前已同步的历史数据
    - 某个 PO 数据有误，需要覆盖更新

    **注意：** 同步期间该 PO 的数据会短暂不可见（删后再插）。
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        result = await loop.run_in_executor(
            executor, lambda: po_sync_service.resync_pos(request.po_numbers)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重同步执行异常: {e}")
    finally:
        executor.shutdown(wait=False)

    if not result.get('success') and not result.get('skipped'):
        raise HTTPException(status_code=500, detail=result.get('message', '重同步失败'))
    return result


@router.post("/resync-all", summary="强制重新同步数据库中所有PO（批量修复）")
async def resync_all_pos():
    """
    将数据库中**所有** PO 从 Maximo 重新拉取并覆盖写入。

    **适用场景：** 字段结构变更后，批量修复所有历史记录中的缺失字段。

    **警告：** 如果 PO 数量较多（数百条以上），此操作耗时较长，请耐心等待。
    建议先用 `/resync` 针对少量 PO 测试验证，确认正常后再执行全量重同步。

    请求超时设置为 10 分钟。
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        result = await loop.run_in_executor(
            executor, po_sync_service.resync_all_existing
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"全量重同步异常: {e}")
    finally:
        executor.shutdown(wait=False)

    if not result.get('success') and not result.get('skipped'):
        raise HTTPException(status_code=500, detail=result.get('message', '重同步失败'))
    return result


@router.get("/debug/poline/{po_number}", summary="诊断：查看指定PO的原始poline字段")
async def debug_poline_fields(po_number: str):
    """
    从 Maximo 实时抓取指定采购订单，返回原始 poline 字段列表。

    用于诊断 `newitemdesc`（尺寸）、`itemnum`（物料编号）、`orderqty`（数量）
    等字段是否被 OSLC API 正确返回。

    **使用方法：**
    - 填入一个已知有数据的 PO 号（如 `CN4300`）
    - 查看返回结果中 poline 每行实际包含的字段和值
    - 若 `newitemdesc` 字段不在返回结果中，说明 Maximo OSLC 资源未配置该字段
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from src.fetcher.po_fetcher import fetch_po_by_number

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        po_data = await loop.run_in_executor(
            executor, lambda: fetch_po_by_number(po_number, save_to_file=False)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抓取 Maximo 数据失败: {e}")
    finally:
        executor.shutdown(wait=False)

    if not po_data:
        raise HTTPException(status_code=404, detail=f"未找到 PO: {po_number}（可能认证过期或不存在）")

    poline = po_data.get('poline', [])
    if not poline:
        return {
            'po_number': po_number,
            'poline_count': 0,
            'message': '该PO无明细行',
        }

    # 返回前3行的所有字段（供诊断用）
    sample_lines = []
    for line in poline[:3]:
        sample_lines.append({
            'all_keys': sorted(line.keys()),
            'itemnum':      line.get('itemnum'),
            'description':  line.get('description'),
            'catalogcode':  line.get('catalogcode'),
            'newitemdesc':  line.get('newitemdesc'),   # 尺寸/质量
            'orderqty':     line.get('orderqty'),
            'orderunit':    line.get('orderunit'),
            'location':     line.get('location'),
            'storeloc':     line.get('storeloc'),
            'linetype':     line.get('linetype'),
        })

    return {
        'po_number': po_number,
        'poline_count': len(poline),
        'sample_lines': sample_lines,
        'diagnosis': {
            'newitemdesc_present': any(
                'newitemdesc' in line for line in poline[:10]
            ),
            'newitemdesc_has_value': any(
                line.get('newitemdesc') for line in poline[:10]
            ),
            'itemnum_present': any(
                'itemnum' in line for line in poline[:10]
            ),
        },
    }
