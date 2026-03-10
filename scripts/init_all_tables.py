"""
数据库全量建表脚本
==================
一次性创建 Maximo 同步所需的所有数据库表：

  1. material            物料主数据
  2. purchase_order       采购订单主表
  3. purchase_order_bd    采购订单明细表
  4. mr_header            出库单主表（物料需求单）
  5. mr_detail            出库单明细表
  6. bin_inventory        货柜库存表（FIFO 先进先出）
  7. material_location    物料默认仓位映射表
  8. vendor               供应商账户表
  9. warehouse            仓库主数据表
  10. warehouse_bin        仓库-仓位关联表

用法：
    python scripts/init_all_tables.py
    python scripts/init_all_tables.py --check   # 仅检查表是否存在，不创建
"""

import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.db import get_connection


# ─────────────────────────────────────────────────────────────────────────────
# 建表 DDL
# ─────────────────────────────────────────────────────────────────────────────

DDL_STATEMENTS = {

    # ── 1. 物料主数据 ─────────────────────────────────────────────────────────
    "material": """
        CREATE TABLE IF NOT EXISTS `material` (
            `id`                BIGINT          NOT NULL PRIMARY KEY         COMMENT '主键ID（雪花ID）',
            `code`              VARCHAR(50)     NOT NULL                     COMMENT '物料编号（Maximo itemnum）',
            `name`              VARCHAR(200)    NULL                         COMMENT '物料名称/描述',
            `ordering_unit`     VARCHAR(50)     NULL                         COMMENT '订购单位（orderunit）',
            `issuing_unit`      VARCHAR(50)     NULL                         COMMENT '发放单位（issueunit）',
            `status`            VARCHAR(50)     NULL                         COMMENT '状态（ACTIVE/INACTIVE）',
            `batch_type`        VARCHAR(50)     NULL                         COMMENT '批次类型（lottype）',
            `unit_cost`         DECIMAL(18,4)   NULL                         COMMENT '物料单价（来自 Maximo invcost）',
            `avg_cost`          DECIMAL(18,4)   NULL                         COMMENT '平均成本（avgcost）',
            `last_cost`         DECIMAL(18,4)   NULL                         COMMENT '最近成本（lastcost）',
            `cost_date`         DATETIME        NULL                         COMMENT '成本日期',
            `cost_sync_time`    DATETIME        NULL                         COMMENT '单价最近同步时间',
            `maximo_changedate` DATETIME        NULL                         COMMENT 'Maximo 物料最近更新时间（增量同步依据）',
            `sync_time`         DATETIME        NULL                         COMMENT 'WMS 最近同步时间',
            `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `last_update_time`  DATETIME        NULL     ON UPDATE CURRENT_TIMESTAMP COMMENT '最近更新时间',
            `del_flag`          TINYINT         NOT NULL DEFAULT 0           COMMENT '软删除（0=正常，1=删除）',
            UNIQUE KEY `uq_material_code` (`code`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='物料主数据（来自 Maximo MXAPIITEM）'
    """,

    # ── 2. 采购订单主表 ──────────────────────────────────────────────────────
    "purchase_order": """
        CREATE TABLE IF NOT EXISTS `purchase_order` (
            `id`                  BIGINT        NOT NULL PRIMARY KEY         COMMENT '主键ID（雪花ID）',
            `code`                VARCHAR(50)   NOT NULL                     COMMENT 'PO单号（Maximo ponum）',
            `description`         VARCHAR(500)  NULL                         COMMENT '描述/用户单号',
            `user_code`           VARCHAR(100)  NULL                         COMMENT '采购员（purchaseagent）',
            `location`            VARCHAR(50)   NULL                         COMMENT '地点（siteid）',
            `status`              VARCHAR(50)   NULL                         COMMENT 'PO状态（APPR/WAPPR等）',
            `status_date`         DATETIME      NULL                         COMMENT '状态日期',
            `order_date`          DATETIME      NULL                         COMMENT '订单日期',
            `request_date`        VARCHAR(100)  NULL                         COMMENT '需求日期',
            `total_cost`          VARCHAR(50)   NULL                         COMMENT '总金额',
            `currency`            VARCHAR(20)   NULL                         COMMENT '币种',
            `revision`            VARCHAR(20)   NULL                         COMMENT '修订号',
            `type`                VARCHAR(20)   NULL                         COMMENT 'PO类型',
            `supplier_name`       VARCHAR(200)  NULL                         COMMENT '供应商名称（vendorname）',
            `owner_dept_id`       BIGINT        NULL                         COMMENT '供应商ID（关联 sys_department）',
            `vendor_code`         VARCHAR(50)   NULL                         COMMENT '供应商编号',
            `supplier_address`    VARCHAR(500)  NULL                         COMMENT '供应商地址',
            `supplier_zip`        VARCHAR(20)   NULL                         COMMENT '供应商邮政编码',
            `supplier_city`       VARCHAR(100)  NULL                         COMMENT '供应商城市',
            `supplier_contact`    VARCHAR(100)  NULL                         COMMENT '供应商联系人',
            `supplier_phone`      VARCHAR(50)   NULL                         COMMENT '供应商电话',
            `supplier_email`      VARCHAR(200)  NULL                         COMMENT '供应商邮箱',
            `scania_customer_code` VARCHAR(50)  NULL                         COMMENT '斯堪尼亚客户代码',
            `company_name`        VARCHAR(200)  NULL                         COMMENT '收款方公司名称',
            `street_address`      VARCHAR(500)  NULL                         COMMENT '收款方街道地址',
            `city`                VARCHAR(100)  NULL                         COMMENT '收款方城市',
            `postal_code`         VARCHAR(20)   NULL                         COMMENT '收款方邮政编码',
            `country`             VARCHAR(100)  NULL                         COMMENT '收款方国家',
            `contact_person`      VARCHAR(100)  NULL                         COMMENT '联系人',
            `contact_phone`       VARCHAR(50)   NULL                         COMMENT '联系电话',
            `contact_email`       VARCHAR(200)  NULL                         COMMENT '联系邮箱',
            `receiver`            VARCHAR(100)  NULL                         COMMENT '接收人',
            `create_time`         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '同步时间',
            `del_flag`            TINYINT       NOT NULL DEFAULT 0           COMMENT '软删除',
            UNIQUE KEY `uq_po_code` (`code`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='采购订单主表（来自 Maximo MXAPIPO）'
    """,

    # ── 3. 采购订单明细表 ────────────────────────────────────────────────────
    "purchase_order_bd": """
        CREATE TABLE IF NOT EXISTS `purchase_order_bd` (
            `id`              BIGINT        NOT NULL PRIMARY KEY         COMMENT '主键ID（雪花ID）',
            `form_id`         BIGINT        NOT NULL                     COMMENT '主表ID（关联 purchase_order.id）',
            `sku`             BIGINT        NULL                         COMMENT '物料ID（关联 material.id）',
            `warehouse`       BIGINT        NULL                         COMMENT '仓库ID（关联 warehouse.id）',
            `number`          VARCHAR(20)   NULL                         COMMENT '行号（polinenum）',
            `sku_names`       VARCHAR(500)  NULL                         COMMENT '物料名称/描述',
            `qty`             INT           NOT NULL DEFAULT 0           COMMENT '订购数量',
            `receive_status`  VARCHAR(20)   NULL                         COMMENT '接收状态（receiptscomplete）',
            `ordering_unit`   VARCHAR(50)   NULL                         COMMENT '订购单位',
            `unit_cost`       VARCHAR(50)   NULL                         COMMENT '单价',
            `line_cost`       VARCHAR(50)   NULL                         COMMENT '行金额',
            `model_num`       VARCHAR(200)  NULL                         COMMENT '型号（catalogcode）',
            `size_info`       VARCHAR(500)  NULL                         COMMENT '尺寸/规格（newitemdesc）',
            `target_container` VARCHAR(100) NULL                         COMMENT '目标货柜（location）',
            `create_time`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '同步时间',
            `del_flag`        TINYINT       NOT NULL DEFAULT 0           COMMENT '软删除',
            KEY `idx_po_bd_form` (`form_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='采购订单明细表（来自 Maximo MXAPIPO poline）'
    """,

    # ── 4. 出库单主表 ────────────────────────────────────────────────────────
    "mr_header": """
        CREATE TABLE IF NOT EXISTS `mr_header` (
            `id`              BIGINT        NOT NULL PRIMARY KEY         COMMENT '主键ID',
            `issue_number`    VARCHAR(50)   NOT NULL                     COMMENT '出库单号（Maximo usagenum）',
            `request_number`  VARCHAR(50)   NULL                         COMMENT '申请号',
            `mr_number`       VARCHAR(200)  NULL                         COMMENT 'MR号（发放目标）',
            `applicant`       VARCHAR(500)  NULL                         COMMENT '描述/领取人信息',
            `usage_type`      VARCHAR(20)   NULL                         COMMENT '使用情况类型（ISSUE）',
            `warehouse`       VARCHAR(100)  NULL                         COMMENT '出库仓库',
            `site`            VARCHAR(50)   NULL                         COMMENT '地点（siteid）',
            `target_address`  VARCHAR(500)  NULL                         COMMENT '目标地址',
            `required_date`   DATE          NULL                         COMMENT '需求日期',
            `status`          VARCHAR(50)   NULL                         COMMENT '状态（ENTERED/COMPLETE等）',
            `cost_center`     VARCHAR(100)  NULL                         COMMENT '成本中心',
            `charge_to`       VARCHAR(200)  NULL                         COMMENT '发放目标',
            `wo_numbers`      VARCHAR(1000) NULL                         COMMENT 'WO号（用 / 分隔）',
            `maximo_href`     VARCHAR(1000) NULL                         COMMENT 'Maximo 资源链接',
            `create_time`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '同步时间',
            `update_time`     DATETIME      NULL     ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            `del_flag`        TINYINT       NOT NULL DEFAULT 0           COMMENT '软删除',
            UNIQUE KEY `uq_issue_number` (`issue_number`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='出库单主表（物料需求单，来自 Maximo MXAPIINVUSE）'
    """,

    # ── 5. 出库单明细表 ──────────────────────────────────────────────────────
    "mr_detail": """
        CREATE TABLE IF NOT EXISTS `mr_detail` (
            `id`                BIGINT         NOT NULL PRIMARY KEY      COMMENT '主键ID',
            `header_id`         BIGINT         NOT NULL                  COMMENT '主表ID（关联 mr_header.id）',
            `line_number`       INT            NULL                      COMMENT '行号',
            `usage_type`        VARCHAR(20)    NULL                      COMMENT '使用情况类型',
            `item_number`       VARCHAR(100)   NULL                      COMMENT '物料编号',
            `description`       VARCHAR(500)   NULL                      COMMENT '物料名称/描述',
            `current_balance`   DECIMAL(15,2)  NULL                      COMMENT '当前余量',
            `available_qty`     DECIMAL(15,2)  NULL                      COMMENT '可用量',
            `required_qty`      DECIMAL(15,2)  NULL                      COMMENT '需求数量',
            `delivered_qty`     DECIMAL(15,2)  NULL                      COMMENT '交货数量',
            `transport_date`    DATE           NULL                      COMMENT '运输日期',
            `unit`              VARCHAR(20)    NOT NULL DEFAULT 'PCS'    COMMENT '单位',
            `bin_location`      VARCHAR(100)   NULL                      COMMENT '仓位（可修改）',
            `wo_number`         VARCHAR(500)   NULL                      COMMENT '工单号',
            `gl_credit_account` VARCHAR(200)   NULL                      COMMENT 'GL贷方科目',
            `charge_to`         VARCHAR(200)   NULL                      COMMENT '发放目标',
            `cost_center`       VARCHAR(100)   NULL                      COMMENT '成本中心',
            `reserve_num`       VARCHAR(50)    NULL                      COMMENT '预留号',
            `reserve_type`      VARCHAR(20)    NULL                      COMMENT '预留类型（APHARD/SOFT等）',
            `line_request_num`  VARCHAR(50)    NULL                      COMMENT '行级申请号',
            `request_line`      INT            NULL                      COMMENT '申请行号',
            `required_date`     DATE           NULL                      COMMENT '行级需求日期',
            `requester`         VARCHAR(100)   NULL                      COMMENT '请求者',
            `issued_qty`        DECIMAL(15,2)  NULL                      COMMENT '实际出库数量（WMS确认）',
            `is_satisfied`      TINYINT        NOT NULL DEFAULT 0        COMMENT '数量是否满足',
            `maximo_lineid`     INT            NULL                      COMMENT 'Maximo 行号',
            `create_time`       DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '同步时间',
            `update_time`       DATETIME       NULL     ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            `del_flag`          TINYINT        NOT NULL DEFAULT 0        COMMENT '软删除',
            KEY `idx_mr_detail_header` (`header_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='出库单明细表（来自 Maximo MXAPIINVUSE invuseline）'
    """,

    # ── 6. 货柜库存表（FIFO 先进先出）────────────────────────────────────────
    "bin_inventory": """
        CREATE TABLE IF NOT EXISTS `bin_inventory` (
            `id`           BIGINT        NOT NULL PRIMARY KEY         COMMENT '主键ID',
            `item_number`  VARCHAR(100)  NOT NULL                     COMMENT '物料编号',
            `bin_code`     VARCHAR(100)  NOT NULL                     COMMENT '货柜编号',
            `bin_name`     VARCHAR(100)  NULL                         COMMENT '货柜名称',
            `warehouse`    VARCHAR(100)  NULL                         COMMENT '仓库编码',
            `batch_number` VARCHAR(100)  NULL                         COMMENT '批次号',
            `lot_number`   VARCHAR(100)  NULL                         COMMENT '批号',
            `quantity`     DECIMAL(15,2) NULL                         COMMENT '当前库存数量',
            `receipt_date` DATE          NULL                         COMMENT '入库日期（先进先出依据）',
            `create_time`  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '同步时间',
            `update_time`  DATETIME      NULL     ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            `del_flag`     TINYINT       NOT NULL DEFAULT 0           COMMENT '软删除',
            KEY `idx_bin_inv_item_wh` (`item_number`, `warehouse`),
            KEY `idx_bin_inv_code`    (`bin_code`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='货柜库存表（FIFO 先进先出，来自 Maximo MXAPIINVENTORY）'
    """,

    # ── 7. 物料默认仓位映射表 ────────────────────────────────────────────────
    "material_location": """
        CREATE TABLE IF NOT EXISTS `material_location` (
            `id`            BIGINT        NOT NULL PRIMARY KEY         COMMENT '主键ID',
            `item_number`   VARCHAR(100)  NOT NULL                     COMMENT '物料编号',
            `item_name`     VARCHAR(200)  NULL                         COMMENT '物料名称（冗余）',
            `warehouse`     VARCHAR(100)  NULL                         COMMENT '默认仓库（由货柜推导）',
            `bin_code`      VARCHAR(100)  NOT NULL                     COMMENT '默认货柜编号',
            `bin_name`      VARCHAR(200)  NULL                         COMMENT '货柜名称',
            `remark`        VARCHAR(500)  NULL                         COMMENT '备注',
            `import_time`   DATETIME      NULL                         COMMENT '最近导入/同步时间',
            `import_source` VARCHAR(20)   NOT NULL DEFAULT 'excel'     COMMENT '数据来源：excel=手工导入（优先），maximo=Maximo同步',
            `create_time`   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `update_time`   DATETIME      NULL     ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            `del_flag`      TINYINT       NOT NULL DEFAULT 0           COMMENT '软删除',
            UNIQUE KEY `uq_mat_loc_item` (`item_number`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='物料默认仓库仓位映射（Excel导入/Maximo同步维护）'
    """,

    # ── 8. 供应商账户表 ──────────────────────────────────────────────────────
    "vendor": """
        CREATE TABLE IF NOT EXISTS `vendor` (
            `id`          BIGINT        NOT NULL PRIMARY KEY         COMMENT '主键ID',
            `vendor_code` VARCHAR(50)   NOT NULL                     COMMENT '供应商编号（Maximo company）',
            `vendor_name` VARCHAR(200)  NULL                         COMMENT '供应商名称',
            `vendor_type` VARCHAR(20)   NULL                         COMMENT '供应商类型',
            `status`      VARCHAR(20)   NULL                         COMMENT '状态',
            `currency`    VARCHAR(10)   NULL                         COMMENT '币种',
            `sync_time`   DATETIME      NULL                         COMMENT '最近同步时间',
            `create_time` DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `update_time` DATETIME      NULL     ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            `del_flag`    TINYINT       NOT NULL DEFAULT 0           COMMENT '软删除',
            UNIQUE KEY `uq_vendor_code` (`vendor_code`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='供应商账户表（来自 Maximo MXAPICOMPANY）'
    """,

    # ── 9. 仓库主数据表 ──────────────────────────────────────────────────────
    "warehouse": """
        CREATE TABLE IF NOT EXISTS `warehouse` (
            `id`            BIGINT        NOT NULL PRIMARY KEY         COMMENT '主键ID',
            `code`          VARCHAR(50)   NOT NULL                     COMMENT '仓库编号（Maximo location）',
            `name`          VARCHAR(200)  NULL                         COMMENT '仓库名称（description）',
            `site`          VARCHAR(50)   NULL                         COMMENT '地点（siteid）',
            `org`           VARCHAR(50)   NULL                         COMMENT '组织（orgid）',
            `location_type` VARCHAR(30)   NULL                         COMMENT '位置类型',
            `status`        VARCHAR(20)   NULL                         COMMENT '状态',
            `sync_time`     DATETIME      NULL                         COMMENT '最近同步时间',
            `create_time`   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `update_time`   DATETIME      NULL     ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            `del_flag`      TINYINT       NOT NULL DEFAULT 0           COMMENT '软删除',
            UNIQUE KEY `uq_warehouse_code` (`code`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仓库主数据（来自 Maximo MXAPILOCATION）'
    """,

    # ── 10. 仓库-仓位关联表 ──────────────────────────────────────────────────
    "warehouse_bin": """
        CREATE TABLE IF NOT EXISTS `warehouse_bin` (
            `id`           BIGINT        NOT NULL PRIMARY KEY         COMMENT '主键ID',
            `warehouse`    VARCHAR(50)   NOT NULL                     COMMENT '仓库编号',
            `bin_code`     VARCHAR(100)  NOT NULL                     COMMENT '仓位编号',
            `bin_name`     VARCHAR(200)  NULL                         COMMENT '仓位名称',
            `site`         VARCHAR(50)   NULL                         COMMENT '地点（siteid）',
            `remark`       VARCHAR(500)  NULL                         COMMENT '备注',
            `sync_source`  VARCHAR(20)   NOT NULL DEFAULT 'maximo'    COMMENT '数据来源（maximo/import）',
            `create_time`  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `update_time`  DATETIME      NULL     ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            `del_flag`     TINYINT       NOT NULL DEFAULT 0           COMMENT '软删除',
            UNIQUE KEY `uq_wh_bin` (`warehouse`, `bin_code`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仓库-仓位关联表（来自 Maximo MXAPIINVENTORY 提取）'
    """,
}

# 建表顺序（有外键依赖关系时保证先后）
TABLE_ORDER = [
    "material",
    "vendor",
    "warehouse",
    "warehouse_bin",
    "purchase_order",
    "purchase_order_bd",
    "mr_header",
    "mr_detail",
    "bin_inventory",
    "material_location",
]


# ─────────────────────────────────────────────────────────────────────────────
# 核心函数
# ─────────────────────────────────────────────────────────────────────────────

def check_tables(cursor) -> dict:
    """返回 {table_name: exists_bool}"""
    cursor.execute("SHOW TABLES")
    existing = {row[0].lower() for row in cursor.fetchall()}
    return {t: t.lower() in existing for t in TABLE_ORDER}


def init_all_tables(check_only: bool = False):
    print("\n" + "=" * 65)
    print("  Maximo 同步数据库建表初始化")
    print("=" * 65)

    try:
        conn = get_connection()
    except Exception as e:
        print(f"\n[ERROR] 数据库连接失败: {e}")
        print("  请检查 config/.env 中的 DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME")
        sys.exit(1)

    cursor = conn.cursor()

    # ── 检查当前状态 ──────────────────────────────────────────────────────────
    status = check_tables(cursor)
    print(f"\n{'表名':<22} {'状态':>10}")
    print("-" * 35)
    for table, exists in status.items():
        mark = "✓ 已存在" if exists else "○ 待创建"
        print(f"  {table:<20} {mark}")

    if check_only:
        cursor.close()
        conn.close()
        missing = [t for t, e in status.items() if not e]
        print(f"\n共 {len(TABLE_ORDER)} 张表，缺少 {len(missing)} 张。")
        if missing:
            print("  缺少：" + ", ".join(missing))
        return

    # ── 执行建表 ─────────────────────────────────────────────────────────────
    print("\n开始建表...\n")
    created, skipped, failed = 0, 0, 0

    for table in TABLE_ORDER:
        if status.get(table):
            print(f"  [跳过] {table}（已存在）")
            skipped += 1
            continue
        try:
            cursor.execute(DDL_STATEMENTS[table])
            conn.commit()
            print(f"  [创建] {table} ✓")
            created += 1
        except Exception as e:
            conn.rollback()
            print(f"  [失败] {table}: {e}")
            failed += 1

    cursor.close()
    conn.close()

    print(f"\n{'=' * 65}")
    print(f"  完成：创建 {created} 张 | 已存在 {skipped} 张 | 失败 {failed} 张")
    print(f"{'=' * 65}\n")

    if failed:
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Maximo 同步数据库建表初始化")
    parser.add_argument("--check", action="store_true",
                        help="仅检查表是否存在，不执行建表")
    args = parser.parse_args()
    init_all_tables(check_only=args.check)
