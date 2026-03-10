"""
采购单详情字段补填脚本
======================
针对数据库中已存在但缺少详情字段（供应商地址/联系方式/收款方信息等）
的 PO 记录，从 Maximo API 重新拉取并 UPDATE 补全，不影响主子表结构。

用法：
    python scripts/resync_po_details.py              # 补填全部字段为空的 PO
    python scripts/resync_po_details.py --all        # 强制刷新所有 PO（不管字段是否为空）
    python scripts/resync_po_details.py --po CN5128 CN5026  # 指定 PO 号
    python scripts/resync_po_details.py --limit 100  # 最多处理 100 条
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetcher.po_fetcher import fetch_po_by_number
from src.sync.po_header import map_header_data
from src.utils.db import get_connection

# 需要补填的字段（只 UPDATE 这些，不碰 PO 号 / 状态 / 订单日期等核心字段）
UPDATE_FIELDS = [
    'supplier_name',
    'vendor_code',
    'supplier_address',
    'supplier_zip',
    'supplier_city',
    'supplier_country',
    'supplier_contact',
    'supplier_phone',
    'supplier_email',
    'scania_customer_code',
    'company_name',
    'street_address',
    'city',
    'postal_code',
    'country',
    'contact_person',
    'contact_phone',
    'contact_email',
    'receiver',
]

# 判断"字段缺失"的条件：只要以下任一字段为空，就认为需要补填
MISSING_INDICATOR_FIELDS = [
    'supplier_address',
    'supplier_city',
    'company_name',
    'contact_person',
    'supplier_country',
]


def get_pos_to_update(cursor, force_all: bool = False, limit: int = None) -> list:
    """
    从数据库查询需要补填详情的 PO 号列表

    Args:
        force_all: True=全部 PO，False=只取有空字段的 PO
        limit: 最多返回条数

    Returns:
        list[str]: PO 号列表
    """
    if force_all:
        sql = "SELECT code FROM purchase_order WHERE del_flag = 0 ORDER BY create_time DESC"
    else:
        # 任一指示字段为 NULL 或空字符串
        conditions = " OR ".join(
            f"({f} IS NULL OR {f} = '')" for f in MISSING_INDICATOR_FIELDS
        )
        sql = f"""
            SELECT code FROM purchase_order
            WHERE del_flag = 0 AND ({conditions})
            ORDER BY create_time DESC
        """

    if limit:
        sql += f" LIMIT {limit}"

    cursor.execute(sql)
    return [row[0] for row in cursor.fetchall()]


def update_po_header(cursor, po_code: str, mapped: dict) -> bool:
    """
    只 UPDATE UPDATE_FIELDS 中定义的字段（不碰其他字段）

    Returns:
        bool: 是否实际执行了更新
    """
    # 只取 UPDATE_FIELDS 里有值的字段
    to_update = {f: mapped.get(f) for f in UPDATE_FIELDS if f in mapped}
    if not to_update:
        return False

    set_clause = ", ".join(f"`{k}` = %s" for k in to_update)
    values = list(to_update.values()) + [po_code]
    sql = f"UPDATE purchase_order SET {set_clause} WHERE code = %s AND del_flag = 0"
    cursor.execute(sql, values)
    return cursor.rowcount > 0


def resync_po_details(
    po_codes: list = None,
    force_all: bool = False,
    limit: int = None,
    delay: float = 0.5,
):
    print("\n" + "=" * 65)
    print(f"  采购单详情补填  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    conn = get_connection()
    cursor = conn.cursor()

    # ── 确定要处理的 PO 列表 ────────────────────────────────────────────────
    if po_codes:
        targets = po_codes
        print(f"  模式：指定 PO（{len(targets)} 条）")
    else:
        targets = get_pos_to_update(cursor, force_all=force_all, limit=limit)
        mode = "全部" if force_all else "字段缺失"
        print(f"  模式：{mode}（共 {len(targets)} 条需要处理）")

    if not targets:
        print("\n  无需处理，退出。")
        cursor.close()
        conn.close()
        return

    print()

    # ── 逐条处理 ─────────────────────────────────────────────────────────────
    success, skipped, failed = 0, 0, 0

    for i, po_code in enumerate(targets, 1):
        print(f"  [{i:>4}/{len(targets)}] {po_code} ", end="", flush=True)

        # 从 Maximo API 拉取
        po_data = fetch_po_by_number(po_code, save_to_file=False)
        if not po_data:
            print("→ ✗ API 返回空（认证过期或 PO 不存在）")
            failed += 1
            continue

        # 映射字段
        try:
            mapped = map_header_data(cursor, po_data)
        except Exception as e:
            print(f"→ ✗ 映射失败: {e}")
            failed += 1
            continue

        # UPDATE 数据库
        try:
            updated = update_po_header(cursor, po_code, mapped)
            conn.commit()
            if updated:
                # 显示本次填入的关键字段值
                vendor = mapped.get('supplier_name') or mapped.get('vendor_code') or '-'
                city = mapped.get('supplier_city') or '-'
                print(f"→ ✓  供应商={vendor[:30]}, 城市={city}")
                success += 1
            else:
                print("→ ○ 无变化")
                skipped += 1
        except Exception as e:
            conn.rollback()
            print(f"→ ✗ 写入失败: {e}")
            failed += 1

        time.sleep(delay)

    cursor.close()
    conn.close()

    print(f"\n{'=' * 65}")
    print(f"  完成：更新 {success} 条 | 无变化 {skipped} 条 | 失败 {failed} 条")
    print(f"{'=' * 65}\n")


def main():
    parser = argparse.ArgumentParser(description="采购单详情字段补填")
    parser.add_argument("--all",   action="store_true",
                        help="强制刷新所有 PO（包括字段已有值的）")
    parser.add_argument("--po",    nargs="+", metavar="PONUM",
                        help="指定 PO 号列表，如 --po CN5128 CN5026")
    parser.add_argument("--limit", type=int, default=None,
                        help="最多处理条数（默认不限）")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="每条请求间隔秒数（默认 0.5s，避免 API 限流）")
    args = parser.parse_args()

    resync_po_details(
        po_codes=args.po,
        force_all=args.all,
        limit=args.limit,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
