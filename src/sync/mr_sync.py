"""
出库单（物料需求单）同步服务
从 Maximo 抓取出库单数据并写入本地 WMS 数据库
"""
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.db import get_connection, generate_id, format_datetime
from src.sync.mr_db_init import init_mr_tables
from src.fetcher.mr_fetcher import fetch_mr_list, fetch_mr_by_number


def _collect_wo_numbers(lines: List[Dict]) -> str:
    """
    从子表行中收集所有 WO 号，去重后用 / 分隔

    WO 可能不唯一，全部拉取后去重显示。
    """
    seen = []
    for line in lines:
        wo = (line.get("wonum") or "").strip()
        if wo and wo not in seen:
            seen.append(wo)
    return " / ".join(seen) if seen else ""


def _parse_header(raw: Dict) -> Dict:
    """
    解析 Maximo 出库单主表数据

    Maximo 字段对应关系（来自分拣清单截图）：
      usagenum     → 使用数量/出库单号
      description  → 描述（领取人信息，如 "领取人：郜洁 15859365005"）
      requestnum   → 申请号（分拣清单中的"申请"列，如 10234）
      storeloc     → 原仓库（如 518）
      siteid       → 地点（如 RUGAO）
      requireddate → 需求日期
      costcenter   → 成本中心（如 36192）
      chargeto     → 发放目标（如 WYAVW6）
    """
    return {
        "issue_number":   raw.get("usagenum") or str(raw.get("invusageid") or ""),
        "request_number": raw.get("requestnum") or "",    # 申请号
        "applicant":      raw.get("description") or "",   # 描述/领取人
        "usage_type":     raw.get("invuselinetype") or "ISSUE",
        "warehouse":      raw.get("storeloc") or "",
        "site":           raw.get("siteid") or "",
        "target_address": raw.get("siteid") or "",        # 目标地址暂用地点，后续客户补充
        "required_date":  _safe_date(raw.get("requireddate")),
        "status":         raw.get("status") or "",
        "cost_center":    raw.get("costcenter") or "",    # 成本中心
        "charge_to":      raw.get("chargeto") or "",      # 发放目标
        "maximo_href":    raw.get("href") or "",
    }


def _parse_lines(raw_lines: List[Dict], header_id: int) -> List[Dict]:
    """
    解析 Maximo 出库单子表数据

    Maximo 字段对应关系（来自截图）：
      itemnum        → 项目（物料编号）
      description    → 物料名称
      curbal         → 当前余量
      availbal       → 可用量
      quantity       → 申请数量（需求数量）
      transdate      → 运输日期
      binnum         → 原货柜（仓位）
      wonum          → 工单号（WO）
      glcreditacct   → GL贷方科目（如 K-546110-36192）
      chargeto       → 发放目标（如 WYAVW6）
      costcenter     → 成本中心（如 36192）
    """
    result = []
    for line in raw_lines:
        # 跳过非物料行（SERVICE 等）
        line_type = (line.get("invuselinetype") or "").upper()
        if line_type in ("SERVICE", "STDSERVICE"):
            continue

        result.append({
            "header_id":         header_id,
            "line_number":       line.get("invuselinenum"),
            "usage_type":        line.get("invuselinetype") or "ISSUE",
            "item_number":       line.get("itemnum") or "",
            "description":       line.get("description") or "",
            "current_balance":   _safe_decimal(line.get("curbal")),
            "available_qty":     _safe_decimal(line.get("availbal")),
            "required_qty":      _safe_decimal(line.get("quantity")),
            "transport_date":    _safe_date(line.get("transdate")),
            "unit":              "PCS",
            "bin_location":      line.get("binnum") or "",
            "wo_number":         line.get("wonum") or "",
            "gl_credit_account": line.get("glcreditacct") or "",  # GL贷方科目
            "charge_to":         line.get("chargeto") or "",       # 发放目标
            "cost_center":       line.get("costcenter") or "",     # 成本中心
            "maximo_lineid":     line.get("invuselinenum"),
        })
    return result


def _safe_date(value: Any) -> Optional[str]:
    """安全提取日期字符串（取前10位）"""
    if not value:
        return None
    s = str(value)
    return s[:10] if len(s) >= 10 else s


def _safe_decimal(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sync_mr_from_maximo(
    status_filter: str = "ENTERED,WAPPR",
    max_pages: int = 5,
    page_size: int = 20,
) -> Dict[str, int]:
    """
    从 Maximo 拉取出库单并同步到本地数据库

    Returns:
        {'inserted': N, 'updated': N, 'skipped': N}
    """
    conn = get_connection()
    try:
        # 确保表结构存在
        init_mr_tables(conn)

        raw_list = fetch_mr_list(
            status_filter=status_filter,
            max_pages=max_pages,
            page_size=page_size,
        )

        stats = {"inserted": 0, "updated": 0, "skipped": 0}
        cursor = conn.cursor(dictionary=True)

        for raw in raw_list:
            header = _parse_header(raw)
            issue_number = header["issue_number"]
            if not issue_number:
                stats["skipped"] += 1
                continue

            # 检查是否已存在
            cursor.execute(
                "SELECT id FROM mr_header WHERE issue_number=%s AND del_flag=0",
                (issue_number,),
            )
            existing = cursor.fetchone()

            if existing:
                # 更新主表（状态、WO 等可能变化）
                raw_lines = raw.get("invuseline") or []
                wo_numbers = _collect_wo_numbers(raw_lines)
                cursor.execute(
                    """UPDATE mr_header SET
                        status=%s, wo_numbers=%s, required_date=%s,
                        target_address=%s, applicant=%s, request_number=%s,
                        cost_center=%s, charge_to=%s, update_time=NOW()
                       WHERE id=%s""",
                    (
                        header["status"],
                        wo_numbers,
                        header["required_date"],
                        header["target_address"],
                        header["applicant"],
                        header["request_number"],
                        header["cost_center"],
                        header["charge_to"],
                        existing["id"],
                    ),
                )
                stats["updated"] += 1
            else:
                # 插入主表
                header_id = generate_id()
                raw_lines = raw.get("invuseline") or []
                wo_numbers = _collect_wo_numbers(raw_lines)

                cursor.execute(
                    """INSERT INTO mr_header
                        (id, issue_number, request_number, applicant,
                         usage_type, warehouse, site, target_address,
                         required_date, status, cost_center, charge_to,
                         wo_numbers, maximo_href, create_time)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                    (
                        header_id,
                        issue_number,
                        header["request_number"],
                        header["applicant"],
                        header["usage_type"],
                        header["warehouse"],
                        header["site"],
                        header["target_address"],
                        header["required_date"],
                        header["status"],
                        header["cost_center"],
                        header["charge_to"],
                        wo_numbers,
                        header["maximo_href"],
                    ),
                )

                # 插入子表行
                lines = _parse_lines(raw_lines, header_id)
                for line in lines:
                    line_id = generate_id()
                    cursor.execute(
                        """INSERT INTO mr_detail
                            (id, header_id, line_number, usage_type, item_number,
                             description, current_balance, available_qty, required_qty,
                             transport_date, unit, bin_location, wo_number,
                             gl_credit_account, charge_to, cost_center,
                             maximo_lineid, create_time)
                           VALUES
                            (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                        (
                            line_id,
                            line["header_id"],
                            line["line_number"],
                            line["usage_type"],
                            line["item_number"],
                            line["description"],
                            line["current_balance"],
                            line["available_qty"],
                            line["required_qty"],
                            line["transport_date"],
                            line["unit"],
                            line["bin_location"],
                            line["wo_number"],
                            line["gl_credit_account"],
                            line["charge_to"],
                            line["cost_center"],
                            line["maximo_lineid"],
                        ),
                    )

                stats["inserted"] += 1

        conn.commit()
        cursor.close()
        print(f"[OK] 同步完成: {stats}")
        return stats

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 同步出库单失败: {e}")
        raise
    finally:
        conn.close()


def get_fifo_bins(
    item_number: str,
    warehouse: str,
    required_qty: float,
) -> Dict[str, Any]:
    """
    根据先进先出原则为物料推荐货柜

    逻辑：
    1. 查询该物料在指定仓库的所有货柜（按入库日期正序 = 先进先出）
    2. 优先找单个货柜能满足数量的 → 返回该货柜，is_satisfied=True
    3. 全部货柜都不够 → 返回批次号最小的货柜，is_satisfied=False（触发警告）

    Returns:
        {
          'recommended_bin': str,   # 推荐仓位编码
          'is_satisfied': bool,     # 数量是否满足
          'bins': [                 # 可选货柜列表（用于货柜选择页）
              {'bin_code': ..., 'bin_name': ..., 'quantity': ..., 'receipt_date': ...}
          ]
        }
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT bin_code, bin_name, quantity, batch_number, receipt_date
               FROM bin_inventory
               WHERE item_number=%s AND warehouse=%s AND del_flag=0
                 AND quantity > 0
               ORDER BY receipt_date ASC, batch_number ASC""",
            (item_number, warehouse),
        )
        bins = cursor.fetchall()

        if not bins:
            return {
                "recommended_bin": "",
                "is_satisfied": False,
                "bins": [],
            }

        # 找第一个能满足数量的货柜（先进先出顺序）
        for b in bins:
            if (b["quantity"] or 0) >= required_qty:
                return {
                    "recommended_bin": b["bin_code"],
                    "is_satisfied": True,
                    "bins": _format_bins(bins),
                }

        # 没有单个能满足 → 返回批次最小（最老的），并标记 is_satisfied=False
        return {
            "recommended_bin": bins[0]["bin_code"],
            "is_satisfied": False,
            "bins": _format_bins(bins),
        }

    finally:
        cursor.close()
        conn.close()


def _format_bins(bins: list) -> list:
    return [
        {
            "bin_code":     b["bin_code"],
            "bin_name":     b["bin_name"] or b["bin_code"],
            "quantity":     float(b["quantity"] or 0),
            "batch_number": b["batch_number"] or "",
            "receipt_date": str(b["receipt_date"]) if b["receipt_date"] else "",
        }
        for b in bins
    ]


def update_bin_location(detail_id: int, bin_location: str) -> bool:
    """更新子表行的仓位"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE mr_detail SET bin_location=%s, update_time=NOW() WHERE id=%s AND del_flag=0",
            (bin_location, detail_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception:
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def update_issued_qty(detail_id: int, issued_qty: float) -> bool:
    """更新子表行的已出库数量，并标记是否满足"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT required_qty FROM mr_detail WHERE id=%s AND del_flag=0",
            (detail_id,),
        )
        row = cursor.fetchone()
        if not row:
            return False
        required = float(row["required_qty"] or 0)
        satisfied = 1 if issued_qty >= required else 0

        cursor.execute(
            """UPDATE mr_detail
               SET issued_qty=%s, is_satisfied=%s, update_time=NOW()
               WHERE id=%s AND del_flag=0""",
            (issued_qty, satisfied, detail_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def sync_bin_inventory_from_maximo(bin_data_list: List[Dict]) -> int:
    """
    将从 Maximo 抓取的货柜库存数据写入 bin_inventory 表

    Args:
        bin_data_list: 标准化后的货柜数据列表

    Returns:
        写入数量
    """
    if not bin_data_list:
        return 0

    conn = get_connection()
    cursor = conn.cursor()
    count = 0
    try:
        for item in bin_data_list:
            item_number = item.get("itemnum") or ""
            bin_code = item.get("binnum") or ""
            warehouse = item.get("storeloc") or ""
            if not (item_number and bin_code):
                continue

            # 检查是否已存在
            cursor.execute(
                """SELECT id FROM bin_inventory
                   WHERE item_number=%s AND bin_code=%s AND warehouse=%s AND del_flag=0""",
                (item_number, bin_code, warehouse),
            )
            existing = cursor.fetchone()
            qty = _safe_decimal(item.get("curbal") or item.get("quantity"))
            receipt_date = _safe_date(item.get("receiptdate") or item.get("statusdate"))
            batch = item.get("lotnum") or item.get("conditioncode") or ""

            if existing:
                cursor.execute(
                    """UPDATE bin_inventory
                       SET quantity=%s, batch_number=%s, receipt_date=%s, update_time=NOW()
                       WHERE id=%s""",
                    (qty, batch, receipt_date, existing[0]),
                )
            else:
                cursor.execute(
                    """INSERT INTO bin_inventory
                        (id, item_number, bin_code, bin_name, warehouse,
                         batch_number, quantity, receipt_date, create_time)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                    (
                        generate_id(),
                        item_number,
                        bin_code,
                        item.get("binnum") or bin_code,
                        warehouse,
                        batch,
                        qty,
                        receipt_date,
                    ),
                )
                count += 1

        conn.commit()
        return count
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 同步货柜库存失败: {e}")
        return 0
    finally:
        cursor.close()
        conn.close()
