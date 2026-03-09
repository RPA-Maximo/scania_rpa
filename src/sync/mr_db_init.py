"""
出库单（物料需求单）数据库表结构初始化
创建 mr_header、mr_detail、bin_inventory 三张表
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def init_mr_tables(conn):
    """
    创建出库单相关表（不存在则创建，已存在则跳过）

    表结构：
        mr_header    - 出库单主表
        mr_detail    - 出库单子表
        bin_inventory - 货柜库存表（用于先进先出推荐）
    """
    cursor = conn.cursor()
    try:
        # ── 出库单主表 ─────────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS `mr_header` (
                `id`             BIGINT        NOT NULL PRIMARY KEY COMMENT '主键ID',
                `issue_number`   VARCHAR(50)   NOT NULL COMMENT '出库单号(Maximo使用情况号)',
                `mr_number`      VARCHAR(50)   NULL     COMMENT 'MR号/申请号',
                `usage_type`     VARCHAR(20)   NULL     COMMENT '使用情况类型(ISSUE)',
                `warehouse`      VARCHAR(100)  NULL     COMMENT '出库仓库(不可修改)',
                `target_address` VARCHAR(500)  NULL     COMMENT '目标地址',
                `required_date`  DATE          NULL     COMMENT '需求日期',
                `status`         VARCHAR(50)   NULL     COMMENT '状态(ENTERED/COMPLETE等)',
                `wo_numbers`     VARCHAR(1000) NULL     COMMENT '工单号(去重后用/分隔)',
                `maximo_href`    VARCHAR(1000) NULL     COMMENT 'Maximo资源链接',
                `create_time`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `update_time`    DATETIME      NULL     ON UPDATE CURRENT_TIMESTAMP,
                `del_flag`       TINYINT       NOT NULL DEFAULT 0,
                UNIQUE KEY `uq_issue_number` (`issue_number`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='出库单主表'
        """)

        # ── 出库单子表 ─────────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS `mr_detail` (
                `id`              BIGINT         NOT NULL PRIMARY KEY COMMENT '主键ID',
                `header_id`       BIGINT         NOT NULL COMMENT '主表ID',
                `line_number`     INT            NULL     COMMENT '行号',
                `usage_type`      VARCHAR(20)    NULL     COMMENT '使用情况类型',
                `item_number`     VARCHAR(100)   NULL     COMMENT '项目(物料编号)',
                `description`     VARCHAR(500)   NULL     COMMENT '描述',
                `current_balance` DECIMAL(15,2)  NULL     COMMENT '当前余量',
                `available_qty`   DECIMAL(15,2)  NULL     COMMENT '可用量',
                `required_qty`    DECIMAL(15,2)  NULL     COMMENT '需求数量(出库数量)',
                `transport_date`  DATE           NULL     COMMENT '运输日期',
                `unit`            VARCHAR(20)    NULL     DEFAULT 'PCS' COMMENT '单位',
                `bin_location`    VARCHAR(100)   NULL     COMMENT '仓位(可修改)',
                `wo_number`       VARCHAR(500)   NULL     COMMENT '工单号(原始)',
                `issued_qty`      DECIMAL(15,2)  NULL     COMMENT '已实际出库数量',
                `is_satisfied`    TINYINT        NOT NULL DEFAULT 0 COMMENT '数量是否满足(0否1是)',
                `maximo_lineid`   BIGINT         NULL     COMMENT 'Maximo行ID',
                `create_time`     DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `update_time`     DATETIME       NULL     ON UPDATE CURRENT_TIMESTAMP,
                `del_flag`        TINYINT        NOT NULL DEFAULT 0,
                KEY `idx_header_id` (`header_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='出库单子表'
        """)

        # ── 货柜库存表（先进先出基础数据）─────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS `bin_inventory` (
                `id`           BIGINT        NOT NULL PRIMARY KEY COMMENT '主键ID',
                `item_number`  VARCHAR(100)  NOT NULL COMMENT '物料编号',
                `bin_code`     VARCHAR(100)  NOT NULL COMMENT '货柜编号',
                `bin_name`     VARCHAR(100)  NULL     COMMENT '货柜名称',
                `warehouse`    VARCHAR(100)  NULL     COMMENT '仓库编码',
                `batch_number` VARCHAR(100)  NULL     COMMENT '批次号',
                `lot_number`   VARCHAR(100)  NULL     COMMENT '批号',
                `quantity`     DECIMAL(15,2) NULL     COMMENT '当前库存数量',
                `receipt_date` DATE          NULL     COMMENT '入库日期(先进先出依据)',
                `create_time`  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `update_time`  DATETIME      NULL     ON UPDATE CURRENT_TIMESTAMP,
                `del_flag`     TINYINT       NOT NULL DEFAULT 0,
                KEY `idx_item_wh` (`item_number`, `warehouse`),
                KEY `idx_bin_code` (`bin_code`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='货柜库存表(先进先出)'
        """)

        conn.commit()
        print("[OK] 出库单表结构初始化完成")
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 出库单表结构初始化失败: {e}")
        raise
    finally:
        cursor.close()
