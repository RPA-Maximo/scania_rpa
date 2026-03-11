"""
出库单（物料需求单）数据库表结构初始化
创建 mr_header、mr_detail、bin_inventory 三张表，并补齐新增字段
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _add_col(cursor, table: str, col: str, definition: str):
    """不存在则添加列，已存在则跳过（兼容 MySQL 5.7+）"""
    cursor.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (col,))
    if cursor.fetchone() is None:
        cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {definition}")


def init_mr_tables(conn):
    """
    创建或更新出库单相关表

    表：
        mr_header    - 出库单主表
        mr_detail    - 出库单子表
        bin_inventory - 货柜库存表（先进先出推荐用）
    """
    cursor = conn.cursor()
    try:
        # ── 出库单主表 ─────────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS `mr_header` (
                `id`              BIGINT        NOT NULL PRIMARY KEY COMMENT '主键ID',
                `issue_number`    VARCHAR(50)   NOT NULL COMMENT '出库单号(Maximo使用情况号/usagenum)',
                `request_number`  VARCHAR(50)   NULL     COMMENT '申请号(Maximo申请字段)',
                `mr_number`       VARCHAR(200)  NULL     COMMENT 'MR号(发放目标/WYAVW6等)',
                `applicant`       VARCHAR(500)  NULL     COMMENT '描述/领取人信息',
                `usage_type`      VARCHAR(20)   NULL     COMMENT '使用情况类型(ISSUE)',
                `warehouse`       VARCHAR(100)  NULL     COMMENT '出库仓库(不可修改)',
                `site`            VARCHAR(50)   NULL     COMMENT '地点(siteid)',
                `target_address`  VARCHAR(500)  NULL     COMMENT '目标地址',
                `required_date`   DATE          NULL     COMMENT '需求日期',
                `status`          VARCHAR(50)   NULL     COMMENT '状态(ENTERED/COMPLETE等)',
                `cost_center`     VARCHAR(100)  NULL     COMMENT '成本中心',
                `charge_to`       VARCHAR(200)  NULL     COMMENT '发放目标(发放到)',
                `wo_numbers`      VARCHAR(1000) NULL     COMMENT 'WO号(去重后用 / 分隔)',
                `maximo_href`     VARCHAR(1000) NULL     COMMENT 'Maximo资源链接',
                `create_time`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `update_time`     DATETIME      NULL     ON UPDATE CURRENT_TIMESTAMP,
                `del_flag`        TINYINT       NOT NULL DEFAULT 0,
                UNIQUE KEY `uq_issue_number` (`issue_number`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='出库单主表'
        """)

        # 已有旧表时补充新字段
        _add_col(cursor, 'mr_header', 'request_number',
                 "VARCHAR(50) NULL COMMENT '申请号'")
        _add_col(cursor, 'mr_header', 'applicant',
                 "VARCHAR(500) NULL COMMENT '描述/领取人信息'")
        _add_col(cursor, 'mr_header', 'site',
                 "VARCHAR(50) NULL COMMENT '地点'")
        _add_col(cursor, 'mr_header', 'cost_center',
                 "VARCHAR(100) NULL COMMENT '成本中心'")
        _add_col(cursor, 'mr_header', 'charge_to',
                 "VARCHAR(200) NULL COMMENT '发放目标'")

        # ── 出库单子表 ─────────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS `mr_detail` (
                `id`                BIGINT         NOT NULL PRIMARY KEY COMMENT '主键ID',
                `header_id`         BIGINT         NOT NULL COMMENT '主表ID',
                `line_number`       INT            NULL     COMMENT '行号',
                `usage_type`        VARCHAR(20)    NULL     COMMENT '使用情况类型',
                `item_number`       VARCHAR(100)   NULL     COMMENT '项目(物料编号)',
                `description`       VARCHAR(500)   NULL     COMMENT '物料名称/描述',
                `current_balance`   DECIMAL(15,2)  NULL     COMMENT '当前余量',
                `available_qty`     DECIMAL(15,2)  NULL     COMMENT '可用量',
                `required_qty`      DECIMAL(15,2)  NULL     COMMENT '需求数量(申请数量)',
                `delivered_qty`     DECIMAL(15,2)  NULL     COMMENT '交货数量',
                `transport_date`    DATE           NULL     COMMENT '运输日期',
                `unit`              VARCHAR(20)    NOT NULL DEFAULT 'PCS' COMMENT '单位',
                `bin_location`      VARCHAR(100)   NULL     COMMENT '仓位(可修改)',
                `wo_number`         VARCHAR(500)   NULL     COMMENT '工单号',
                `gl_credit_account` VARCHAR(200)   NULL     COMMENT 'GL贷方科目',
                `charge_to`         VARCHAR(200)   NULL     COMMENT '发放目标',
                `cost_center`       VARCHAR(100)   NULL     COMMENT '成本中心',
                `issued_qty`        DECIMAL(15,2)  NULL     COMMENT '实际出库数量(WMS确认)',
                `is_satisfied`      TINYINT        NOT NULL DEFAULT 0 COMMENT '数量是否满足',
                `maximo_lineid`     INT            NULL     COMMENT 'Maximo行号',
                `create_time`       DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `update_time`       DATETIME       NULL     ON UPDATE CURRENT_TIMESTAMP,
                `del_flag`          TINYINT        NOT NULL DEFAULT 0,
                KEY `idx_header_id` (`header_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='出库单子表'
        """)

        # 已有旧表时补充新字段
        _add_col(cursor, 'mr_detail', 'delivered_qty',
                 "DECIMAL(15,2) NULL COMMENT '交货数量'")
        _add_col(cursor, 'mr_detail', 'gl_credit_account',
                 "VARCHAR(200) NULL COMMENT 'GL贷方科目(如K-546110-36192)'")
        _add_col(cursor, 'mr_detail', 'charge_to',
                 "VARCHAR(200) NULL COMMENT '发放目标(如WYAVW6)'")
        _add_col(cursor, 'mr_detail', 'cost_center',
                 "VARCHAR(100) NULL COMMENT '成本中心'")
        # 商品组（化学品识别：39000000=化学品，需特殊处理）
        _add_col(cursor, 'mr_detail', 'commodity_group',
                 "VARCHAR(100) NULL COMMENT '商品组(39000000=化学品)'")
        # 预留相关字段（来自 添加/修改预留项目 截图）
        _add_col(cursor, 'mr_detail', 'reserve_num',
                 "VARCHAR(50) NULL COMMENT '预留号(如24948819)'")
        _add_col(cursor, 'mr_detail', 'reserve_type',
                 "VARCHAR(20) NULL COMMENT '预留类型(APHARD/SOFT等)'")
        _add_col(cursor, 'mr_detail', 'line_request_num',
                 "VARCHAR(50) NULL COMMENT '行级申请号(invusage行的requestnum)'")
        _add_col(cursor, 'mr_detail', 'request_line',
                 "INT NULL COMMENT '申请行号(requestline,如5)'")
        _add_col(cursor, 'mr_detail', 'required_date',
                 "DATE NULL COMMENT '行级需求日期(来自预留项目要求的日期)'")
        _add_col(cursor, 'mr_detail', 'requester',
                 "VARCHAR(100) NULL COMMENT '请求者(requestby,如SANTBM)'")

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

        # ── 物料默认仓库仓位关联表（Excel 导入 / Maximo 同步维护）────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS `material_location` (
                `id`            BIGINT        NOT NULL PRIMARY KEY COMMENT '主键ID',
                `item_number`   VARCHAR(100)  NOT NULL COMMENT '物料编号',
                `item_name`     VARCHAR(200)  NULL     COMMENT '物料名称(冗余，方便查询)',
                `warehouse`     VARCHAR(100)  NULL     COMMENT '默认仓库(由货柜推导)',
                `bin_code`      VARCHAR(100)  NOT NULL COMMENT '默认货柜编号',
                `bin_name`      VARCHAR(200)  NULL     COMMENT '货柜名称',
                `remark`        VARCHAR(500)  NULL     COMMENT '备注',
                `import_time`   DATETIME      NULL     COMMENT '最近导入/同步时间',
                `import_source` VARCHAR(20)   NOT NULL DEFAULT 'excel'
                                              COMMENT '数据来源: excel=手工导入(优先), maximo=Maximo同步',
                `create_time`   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `update_time`   DATETIME      NULL     ON UPDATE CURRENT_TIMESTAMP,
                `del_flag`      TINYINT       NOT NULL DEFAULT 0,
                UNIQUE KEY `uq_item_number` (`item_number`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='物料默认仓库仓位关联表'
        """)
        # 为已存在的旧表补充 import_source 列
        _add_col(cursor, 'material_location', 'import_source',
                 "VARCHAR(20) NOT NULL DEFAULT 'excel' COMMENT '数据来源: excel/maximo'")

        conn.commit()
        print("[OK] 出库单表结构初始化/更新完成")
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 出库单表结构初始化失败: {e}")
        raise
    finally:
        cursor.close()
