"""
物料默认仓库仓位同步服务

从 Maximo MXAPIINVENTORY 的 defaultbin（缺省货柜）字段同步到 material_location 表。
仓库由货柜编号自动推导（查 bin_inventory → 回查 warehouse_bin）。
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetcher.material_location_fetcher import fetch_default_bins
from src.utils.db import get_connection, generate_id


def _derive_warehouse(cursor, bin_code: str) -> Optional[str]:
    """
    按货柜编号推导仓库编码，查询顺序：
      1. bin_inventory（含实时库存的货柜）
      2. warehouse_bin （所有已同步的仓位关联，无论有无库存）
    """
    if not bin_code:
        return None
    # 优先查 bin_inventory（含仓库字段的库存记录）
    cursor.execute(
        """SELECT warehouse FROM bin_inventory
           WHERE bin_code=%s AND del_flag=0
             AND warehouse IS NOT NULL AND warehouse!=''
           LIMIT 1""",
        (bin_code,),
    )
    row = cursor.fetchone()
    if row:
        return row["warehouse"]
    # 回查 warehouse_bin（Maximo 仓位主数据，无库存时仍有记录）
    cursor.execute(
        """SELECT warehouse FROM warehouse_bin
           WHERE bin_code=%s AND del_flag=0
           LIMIT 1""",
        (bin_code,),
    )
    row = cursor.fetchone()
    return row["warehouse"] if row else None


def _derive_bin_name(cursor, bin_code: str) -> Optional[str]:
    """从 warehouse_bin 查货柜名称，无则从 bin_inventory 查"""
    if not bin_code:
        return None
    cursor.execute(
        "SELECT bin_name FROM warehouse_bin WHERE bin_code=%s AND del_flag=0 LIMIT 1",
        (bin_code,),
    )
    row = cursor.fetchone()
    if row and row["bin_name"]:
        return row["bin_name"]
    cursor.execute(
        "SELECT bin_name FROM bin_inventory WHERE bin_code=%s AND del_flag=0 LIMIT 1",
        (bin_code,),
    )
    row = cursor.fetchone()
    return row["bin_name"] if row else None


def _derive_item_name(cursor, item_number: str) -> Optional[str]:
    if not item_number:
        return None
    cursor.execute(
        "SELECT name FROM material WHERE code=%s AND del_flag=0 LIMIT 1",
        (item_number,),
    )
    row = cursor.fetchone()
    return row["name"] if row else None


def sync_material_locations(
    warehouse: Optional[str] = None,
    site_id: Optional[str] = None,
    max_pages: int = 50,
    page_size: int = 100,
) -> Dict[str, int]:
    """
    从 Maximo 同步物料缺省货柜数据到 material_location 表

    业务规则：
    - 以 item_number 为唯一键（每个物料只保留一条默认仓位记录）
    - defaultbin 为空的物料跳过
    - 仓库由货柜编号自动推导
    - Excel 手动导入的记录不被覆盖（import_source='excel' 优先保留）
      → 若已有 Excel 导入记录则跳过，仅当 import_source='maximo' 或新记录时写入

    Args:
        warehouse:  仓库过滤
        site_id:    地点过滤
        max_pages:  最多抓取页数
        page_size:  每页条数

    Returns:
        {'inserted': N, 'updated': N, 'skipped': N, 'no_warehouse': N}
    """
    rows = fetch_default_bins(
        warehouse=warehouse,
        site_id=site_id,
        max_pages=max_pages,
        page_size=page_size,
    )

    if not rows:
        print("[WARN] 未获取到任何缺省货柜数据")
        return {"inserted": 0, "updated": 0, "skipped": 0, "no_warehouse": 0}

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "no_warehouse": 0}
    now = datetime.now()

    try:
        for row in rows:
            item_number = row["item_number"]
            bin_code    = row["default_bin"]

            if not item_number or not bin_code:
                stats["skipped"] += 1
                continue

            # 推导仓库
            warehouse_code = _derive_warehouse(cursor, bin_code)
            if not warehouse_code:
                stats["no_warehouse"] += 1
                print(f"  [WARN] 物料 {item_number} 货柜 {bin_code} 未找到对应仓库，已写入但仓库留空")

            bin_name  = _derive_bin_name(cursor, bin_code)
            item_name = _derive_item_name(cursor, item_number)

            cursor.execute(
                "SELECT id, import_source FROM material_location WHERE item_number=%s AND del_flag=0",
                (item_number,),
            )
            existing = cursor.fetchone()

            if existing:
                # Excel 导入的记录具有更高优先级，Maximo 同步不覆盖
                if existing.get("import_source") == "excel":
                    stats["skipped"] += 1
                    continue
                cursor.execute(
                    """UPDATE material_location SET
                        item_name=%s, warehouse=%s, bin_code=%s, bin_name=%s,
                        import_time=%s, import_source='maximo',
                        update_time=%s, del_flag=0
                       WHERE id=%s""",
                    (item_name, warehouse_code, bin_code, bin_name, now, now, existing["id"]),
                )
                stats["updated"] += 1
            else:
                cursor.execute(
                    """INSERT INTO material_location
                        (id, item_number, item_name, warehouse, bin_code, bin_name,
                         import_time, import_source, create_time, del_flag)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,'maximo',%s,0)""",
                    (generate_id(), item_number, item_name, warehouse_code,
                     bin_code, bin_name, now, now),
                )
                stats["inserted"] += 1

        conn.commit()
        print(f"[OK] 物料缺省货柜同步完成: {stats}")
        return stats

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 物料缺省货柜同步失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()
