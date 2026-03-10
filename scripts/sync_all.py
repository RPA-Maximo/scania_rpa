"""
Maximo 全量数据同步脚本
=======================
按正确顺序从 Maximo 拉取所有业务数据到本地数据库：

  步骤 1  建表初始化（确保所有表存在）
  步骤 2  供应商账户        MXAPICOMPANY  → vendor
  步骤 3  仓库主数据        MXAPILOCATION → warehouse
  步骤 4  仓库仓位          MXAPIINVENTORY→ warehouse_bin
  步骤 5  物料主数据        MXAPIITEM     → material
  步骤 6  物料货值/单价     MXAPIINVENTORY→ material.unit_cost / avg_cost
  步骤 7  物料仓位映射      MXAPIINVENTORY→ material_location
  步骤 8  采购订单主子表    MXAPIPO       → purchase_order / purchase_order_bd
  步骤 9  出库单主子表      MXAPIINVUSE   → mr_header / mr_detail
  步骤 10 货柜库存（FIFO）  MXAPIINVENTORY→ bin_inventory

用法：
    python scripts/sync_all.py                   # 全量同步所有模块
    python scripts/sync_all.py --skip-po         # 跳过 PO 同步
    python scripts/sync_all.py --skip-mr         # 跳过出库单同步
    python scripts/sync_all.py --only vendor warehouse material  # 仅同步指定模块
    python scripts/sync_all.py --dry-run         # 演习模式（只建表，不拉数据）

注意：
    运行前需保证 Maximo 认证有效（config/响应标头.txt 或 config/.env 中有 MAXIMO_COOKIE）
"""

import sys
import time
import argparse
import traceback
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

_steps = []   # (name, ok, elapsed, detail)


def _start(name: str):
    print(f"\n{'─' * 65}")
    print(f"  {name}")
    print(f"{'─' * 65}")
    return time.time()


def _done(name: str, t0: float, ok: bool, detail: str = ""):
    elapsed = time.time() - t0
    mark = "✓" if ok else "✗"
    msg = f"  [{mark}] {name}  ({elapsed:.1f}s)"
    if detail:
        msg += f"  →  {detail}"
    print(msg)
    _steps.append((name, ok, elapsed, detail))


def _summary():
    total = len(_steps)
    passed = sum(1 for _, ok, _, _ in _steps if ok)
    print(f"\n{'=' * 65}")
    print(f"  同步总结：{passed}/{total} 步成功")
    print(f"{'=' * 65}")
    for name, ok, elapsed, detail in _steps:
        mark = "✓" if ok else "✗"
        line = f"  [{mark}] {name:<30} {elapsed:>6.1f}s"
        if detail:
            line += f"  {detail}"
        print(line)
    print()


def _should_run(module: str, only: list, skip: list) -> bool:
    if only:
        return module in only
    return module not in skip


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 1：建表初始化
# ─────────────────────────────────────────────────────────────────────────────

def step_init_tables():
    name = "步骤1  建表初始化"
    t0 = _start(name)
    try:
        from scripts.init_all_tables import init_all_tables
        init_all_tables(check_only=False)
        _done(name, t0, True, "所有表已就绪")
        return True
    except SystemExit as e:
        _done(name, t0, e.code == 0, "建表失败，请检查数据库连接")
        return e.code == 0
    except Exception as e:
        _done(name, t0, False, str(e))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 2：供应商账户
# ─────────────────────────────────────────────────────────────────────────────

def step_vendor(max_pages: int = 50, page_size: int = 100):
    name = "步骤2  供应商账户（MXAPICOMPANY → vendor）"
    t0 = _start(name)
    try:
        from src.sync.vendor_sync import sync_vendors
        stats = sync_vendors(max_pages=max_pages, page_size=page_size)
        detail = f"新增={stats.get('inserted',0)}, 更新={stats.get('updated',0)}, 跳过={stats.get('skipped',0)}"
        _done(name, t0, True, detail)
        return True
    except Exception as e:
        _done(name, t0, False, str(e))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 3：仓库主数据
# ─────────────────────────────────────────────────────────────────────────────

def step_warehouse(max_pages: int = 20, page_size: int = 100):
    name = "步骤3  仓库主数据（MXAPILOCATION → warehouse）"
    t0 = _start(name)
    try:
        from src.sync.warehouse_sync import sync_warehouses
        stats = sync_warehouses(max_pages=max_pages, page_size=page_size)
        detail = f"新增={stats.get('inserted',0)}, 更新={stats.get('updated',0)}, 跳过={stats.get('skipped',0)}"
        _done(name, t0, True, detail)
        return True
    except Exception as e:
        _done(name, t0, False, str(e))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 4：仓库仓位
# ─────────────────────────────────────────────────────────────────────────────

def step_warehouse_bins(max_pages: int = 50, page_size: int = 100):
    name = "步骤4  仓库仓位（MXAPIINVENTORY → warehouse_bin）"
    t0 = _start(name)
    try:
        from src.sync.warehouse_sync import sync_warehouse_bins
        stats = sync_warehouse_bins(max_pages=max_pages, page_size=page_size)
        detail = f"新增={stats.get('inserted',0)}, 跳过={stats.get('skipped',0)}"
        _done(name, t0, True, detail)
        return True
    except Exception as e:
        _done(name, t0, False, str(e))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 5：物料主数据（全量）
# ─────────────────────────────────────────────────────────────────────────────

def step_items(max_pages: int = 200, page_size: int = 100):
    name = "步骤5  物料主数据全量（MXAPIITEM → material）"
    t0 = _start(name)
    try:
        from src.sync.item_sync import sync_items_from_maximo
        # full_no_filter=True: 不限时间过滤，全量拉取
        stats = sync_items_from_maximo(
            since_date=None,
            max_pages=max_pages,
            page_size=page_size,
        )
        detail = f"新增={stats.get('inserted',0)}, 更新={stats.get('updated',0)}, 跳过={stats.get('skipped',0)}"
        _done(name, t0, True, detail)
        return True
    except Exception as e:
        _done(name, t0, False, str(e))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 6：物料货值/单价
# ─────────────────────────────────────────────────────────────────────────────

def step_invcost(max_pages: int = 100, page_size: int = 50):
    name = "步骤6  物料货值/单价（MXAPIINVENTORY → material.unit_cost）"
    t0 = _start(name)
    try:
        from src.sync.invcost_sync import sync_invcost
        stats = sync_invcost(max_pages=max_pages, page_size=page_size)
        detail = f"更新={stats.get('updated',0)}, 跳过={stats.get('skipped',0)}"
        _done(name, t0, True, detail)
        return True
    except Exception as e:
        _done(name, t0, False, str(e))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 7：物料仓位映射
# ─────────────────────────────────────────────────────────────────────────────

def step_material_location(max_pages: int = 100, page_size: int = 50):
    name = "步骤7  物料仓位映射（MXAPIINVENTORY → material_location）"
    t0 = _start(name)
    try:
        from src.sync.material_location_sync import sync_material_locations
        stats = sync_material_locations(max_pages=max_pages, page_size=page_size)
        detail = f"新增={stats.get('inserted',0)}, 跳过={stats.get('skipped',0)}"
        _done(name, t0, True, detail)
        return True
    except Exception as e:
        _done(name, t0, False, str(e))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 8：采购订单主子表
# ─────────────────────────────────────────────────────────────────────────────

def step_po(max_pages: int = 50, page_size: int = 20):
    name = "步骤8  采购订单（MXAPIPO → purchase_order / purchase_order_bd）"
    t0 = _start(name)
    try:
        from src.sync.po_sync_service import po_sync_service
        result = po_sync_service.sync_once()
        ok = result.get("success", False) or result.get("skipped", False)
        detail = result.get("message", "")
        if result.get("stats"):
            s = result["stats"]
            detail = f"新增={s.get('inserted',0)}, 更新={s.get('updated',0)}, 跳过={s.get('skipped',0)}"
        _done(name, t0, ok, detail)
        return ok
    except Exception as e:
        _done(name, t0, False, str(e))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 9：出库单主子表
# ─────────────────────────────────────────────────────────────────────────────

def step_mr(status_filter: str = "ENTERED,WAPPR", max_pages: int = 10, page_size: int = 20):
    name = "步骤9  出库单（MXAPIINVUSE → mr_header / mr_detail）"
    t0 = _start(name)
    try:
        from src.sync.mr_sync import sync_mr_from_maximo
        stats = sync_mr_from_maximo(
            status_filter=status_filter,
            max_pages=max_pages,
            page_size=page_size,
        )
        detail = f"主表 新增={stats.get('headers_inserted',0)}, 更新={stats.get('headers_updated',0)}; 子表 新增={stats.get('details_inserted',0)}"
        _done(name, t0, True, detail)
        return True
    except Exception as e:
        _done(name, t0, False, str(e))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 10：货柜库存（FIFO 先进先出）
# ─────────────────────────────────────────────────────────────────────────────

def step_bin_inventory(max_pages: int = 50, page_size: int = 50):
    name = "步骤10 货柜库存（MXAPIINVENTORY → bin_inventory）"
    t0 = _start(name)
    try:
        from src.sync.inventory_sync import sync_bin_inventory
        stats = sync_bin_inventory(max_pages=max_pages, page_size=page_size)
        detail = f"新增={stats.get('inserted',0)}, 更新={stats.get('updated',0)}, 跳过={stats.get('skipped',0)}"
        _done(name, t0, True, detail)
        return True
    except Exception as e:
        _done(name, t0, False, str(e))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────

MODULE_FUNCS = {
    "vendor":             step_vendor,
    "warehouse":          step_warehouse,
    "warehouse_bin":      step_warehouse_bins,
    "item":               step_items,
    "invcost":            step_invcost,
    "material_location":  step_material_location,
    "po":                 step_po,
    "mr":                 step_mr,
    "bin_inventory":      step_bin_inventory,
}


def main():
    parser = argparse.ArgumentParser(description="Maximo 全量数据同步")
    parser.add_argument("--skip-po",  action="store_true", help="跳过采购订单同步")
    parser.add_argument("--skip-mr",  action="store_true", help="跳过出库单同步")
    parser.add_argument("--dry-run",  action="store_true", help="演习模式：仅建表，不拉数据")
    parser.add_argument("--only", nargs="+",
                        choices=list(MODULE_FUNCS.keys()),
                        help="仅同步指定模块（多个用空格分隔）")
    args = parser.parse_args()

    print("\n" + "=" * 65)
    print(f"  Maximo 全量数据同步  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    if args.dry_run:
        print("  [演习模式] 仅执行建表初始化，跳过数据拉取")

    # ── 步骤 1：建表（总是执行）──────────────────────────────────────────────
    ok = step_init_tables()
    if not ok:
        print("\n[ERROR] 建表失败，终止同步")
        sys.exit(1)

    if args.dry_run:
        _summary()
        return

    # ── 构建跳过列表 ─────────────────────────────────────────────────────────
    skip = []
    if args.skip_po:
        skip.append("po")
    if args.skip_mr:
        skip.append("mr")

    # ── 按顺序执行各同步步骤 ─────────────────────────────────────────────────
    ordered_modules = [
        "vendor",
        "warehouse",
        "warehouse_bin",
        "item",
        "invcost",
        "material_location",
        "po",
        "mr",
        "bin_inventory",
    ]

    for module in ordered_modules:
        if not _should_run(module, args.only, skip):
            print(f"\n  [跳过] {module}")
            continue
        MODULE_FUNCS[module]()

    _summary()


if __name__ == "__main__":
    main()
