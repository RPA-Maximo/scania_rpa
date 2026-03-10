"""
库存货柜数据同步服务
将 Maximo 库存数据写入 bin_inventory 表（先进先出基础数据）

数据来源：
  - 主要：MXAPIINVENTORY（含 invbalance 货柜明细子集）
  - 备用：MXAPIINVBAL（直接货柜级库存）

表：bin_inventory
字段：物料编号、仓库、仓位(货柜)、批次号、数量、入库日期（先进先出依据）
化学品批次信息：待客户补充具体字段
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.db import get_connection, generate_id
from src.fetcher.inventory_fetcher import (
    fetch_inventory_with_bins,
    fetch_invbal_direct,
    flatten_to_bin_rows,
)


def sync_bin_inventory(
    warehouse: Optional[str] = None,
    item_numbers: Optional[List[str]] = None,
    max_pages: int = 20,
    page_size: int = 50,
    use_invbal_api: bool = False,
    full_refresh: bool = False,
) -> Dict[str, int]:
    """
    从 Maximo 同步库存货柜数据到 bin_inventory 表

    Args:
        warehouse:       仓库过滤（如 '518'）；None 抓全部
        item_numbers:    指定物料编号列表；None 抓全部
        max_pages:       最多抓取页数
        page_size:       每页条数
        use_invbal_api:  True=使用 MXAPIINVBAL 直接接口（备用方案）
        full_refresh:    True=先清空指定仓库数据再写入（全量刷新）

    Returns:
        {'inserted': N, 'updated': N, 'skipped': N, 'deleted': N}
    """
    # 1. 拉取 Maximo 数据
    if use_invbal_api:
        raw_items = fetch_invbal_direct(
            warehouse=warehouse,
            max_pages=max_pages,
            page_size=page_size,
        )
        # MXAPIINVBAL 返回的已经是货柜级别
        bin_rows = [
            {
                "item_number":    r.get("itemnum") or "",
                "warehouse":      r.get("storeloc") or "",
                "site":           r.get("siteid") or "",
                "bin_code":       r.get("binnum") or "",
                "lot_number":     r.get("lotnum") or "",
                "quantity":       _safe_float(r.get("curbal")),
                "receipt_date":   _safe_date(r.get("receiptdate")),
                "issue_date":     _safe_date(r.get("issuedate")),
                "condition_code": r.get("conditioncode") or "",
            }
            for r in raw_items
        ]
    else:
        raw_items = fetch_inventory_with_bins(
            warehouse=warehouse,
            item_numbers=item_numbers,
            max_pages=max_pages,
            page_size=page_size,
        )
        bin_rows = flatten_to_bin_rows(raw_items)

    if not bin_rows:
        print("[WARN] 未获取到任何库存数据")
        return {"inserted": 0, "updated": 0, "skipped": 0, "deleted": 0}

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "deleted": 0}

    try:
        # 全量刷新：清空指定仓库的旧数据
        if full_refresh:
            if warehouse:
                cursor.execute(
                    "UPDATE bin_inventory SET del_flag=1 WHERE warehouse=%s",
                    (warehouse,),
                )
            else:
                cursor.execute("UPDATE bin_inventory SET del_flag=1")
            stats["deleted"] = cursor.rowcount
            print(f"[INFO] 已标记 {stats['deleted']} 条旧数据为删除")

        for row in bin_rows:
            item_num  = row["item_number"]
            bin_code  = row["bin_code"]
            wh        = row["warehouse"]
            qty       = row["quantity"]

            if not item_num:
                stats["skipped"] += 1
                continue

            # 查询是否已存在（以 item+bin+warehouse 为唯一键）
            cursor.execute(
                """SELECT id FROM bin_inventory
                   WHERE item_number=%s AND bin_code=%s AND warehouse=%s""",
                (item_num, bin_code, wh),
            )
            existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    """UPDATE bin_inventory SET
                        quantity=%s, lot_number=%s, receipt_date=%s,
                        batch_number=%s, del_flag=0, update_time=NOW()
                       WHERE id=%s""",
                    (
                        qty,
                        row["lot_number"],
                        row["receipt_date"],
                        row["lot_number"],   # batch_number 暂用 lot_number
                        existing["id"],
                    ),
                )
                stats["updated"] += 1
            else:
                cursor.execute(
                    """INSERT INTO bin_inventory
                        (id, item_number, bin_code, bin_name, warehouse,
                         batch_number, lot_number, quantity, receipt_date,
                         create_time, del_flag)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),0)""",
                    (
                        generate_id(),
                        item_num,
                        bin_code,
                        bin_code,            # bin_name 暂用 bin_code，货柜名称后续补充
                        wh,
                        row["lot_number"],   # batch_number
                        row["lot_number"],   # lot_number
                        qty,
                        row["receipt_date"],
                    ),
                )
                stats["inserted"] += 1

        conn.commit()
        print(f"[OK] 库存同步完成: {stats}")
        return stats

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 库存同步失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def export_bin_inventory_excel(
    warehouse: Optional[str] = None,
    item_number: Optional[str] = None,
) -> str:
    """
    导出 bin_inventory 表数据为 Excel 文件

    Args:
        warehouse:   仓库过滤
        item_number: 物料编号过滤

    Returns:
        文件路径
    """
    import pandas as pd

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        where = ["del_flag=0"]
        params = []
        if warehouse:
            where.append("warehouse=%s")
            params.append(warehouse)
        if item_number:
            where.append("item_number LIKE %s")
            params.append(f"%{item_number}%")

        cursor.execute(
            f"""SELECT
                item_number   AS 物料编号,
                warehouse     AS 仓库,
                bin_code      AS 货柜编号,
                bin_name      AS 货柜名称,
                lot_number    AS 批次号,
                batch_number  AS 批号,
                quantity      AS 当前库存,
                receipt_date  AS 入库日期,
                update_time   AS 更新时间
               FROM bin_inventory WHERE {" AND ".join(where)}
               ORDER BY item_number, receipt_date, bin_code""",
            params,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if not rows:
        return ""

    df = pd.DataFrame(rows)

    from config.settings import RAW_DATA_DIR
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    wh_tag = f"_{warehouse}" if warehouse else ""
    out_path = RAW_DATA_DIR / f"bin_inventory{wh_tag}_{ts}.xlsx"
    df.to_excel(str(out_path), index=False)
    print(f"[OK] 导出完成: {out_path}，共 {len(rows)} 行")
    return str(out_path)


def get_bins_for_item_warehouse(
    item_number: str,
    warehouse: str,
) -> List[Dict]:
    """
    查询指定物料+仓库的所有货柜（按先进先出顺序）
    供 WMS 货柜选择页使用

    Returns:
        [{'bin_code','bin_name','quantity','lot_number','receipt_date'}, ...]
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT bin_code, bin_name, quantity, lot_number,
                      batch_number, receipt_date
               FROM bin_inventory
               WHERE item_number=%s AND warehouse=%s
                 AND del_flag=0 AND quantity > 0
               ORDER BY receipt_date ASC, bin_code ASC""",
            (item_number, warehouse),
        )
        rows = cursor.fetchall()
        return [
            {
                "bin_code":     r["bin_code"],
                "bin_name":     r["bin_name"] or r["bin_code"],
                "quantity":     float(r["quantity"] or 0),
                "lot_number":   r["lot_number"] or "",
                "batch_number": r["batch_number"] or "",
                "receipt_date": str(r["receipt_date"]) if r["receipt_date"] else "",
            }
            for r in rows
        ]
    finally:
        cursor.close()
        conn.close()


def _safe_float(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_date(v) -> Optional[str]:
    if not v:
        return None
    s = str(v)
    return s[:10] if len(s) >= 10 else s
