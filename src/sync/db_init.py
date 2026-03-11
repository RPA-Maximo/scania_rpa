"""
数据库表结构初始化
安全地为 purchase_order 和 purchase_order_bd 添加新字段（如已存在则跳过）

字段取舍依据（见字段映射表）：
  - 供应商国家      → 不抓（供应商国家不拉）
  - 斯堪尼亚客户代码 → 不填
  - 联系人/联系电话/电子邮件/接收人 → 不抓默认表信息
  以上字段不在此处建列；历史数据库中若已存在这些列，保留为 NULL 即可。
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _add_column_if_not_exists(cursor, table: str, column: str, definition: str):
    """
    安全地为表添加列（不存在时添加，已存在时跳过）
    兼容 MySQL 5.7 及以上版本
    """
    try:
        cursor.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,))
        if cursor.fetchone() is None:
            cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}")
    except Exception as e:
        print(f"  [WARN] 添加列 {table}.{column} 失败: {e}")


def ensure_po_columns(cursor):
    """
    确保 purchase_order 主表和 purchase_order_bd 子表拥有字段映射所需的全部列。

    主表字段（必须抓取）：
      供应商：vendor_code / supplier_name / supplier_address / supplier_address2 /
              supplier_zip / supplier_city / supplier_state /
              supplier_contact / supplier_phone / supplier_email
      收货方：company_name / street_address / postal_code / city / country

    子表字段：
      item_code / model_num / size_info / discount_pct / currency / target_container
    """

    # ── purchase_order 主表 ──────────────────────────────────────────────

    # 供应商信息
    _add_column_if_not_exists(cursor, 'purchase_order', 'vendor_code',
                              "VARCHAR(50) NULL COMMENT '供应商编号'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_address',
                              "VARCHAR(500) NULL COMMENT '供应商地址1'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_address2',
                              "VARCHAR(500) NULL COMMENT '供应商地址2'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_zip',
                              "VARCHAR(20) NULL COMMENT '供应商邮政编码'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_city',
                              "VARCHAR(100) NULL COMMENT '供应商城市'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_state',
                              "VARCHAR(100) NULL COMMENT '供应商省/区'")
    # supplier_country → 不抓，不建列
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_contact',
                              "VARCHAR(100) NULL COMMENT '供应商联系人'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_phone',
                              "VARCHAR(50) NULL COMMENT '供应商联系电话（含区号，如 +86...）'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_email',
                              "VARCHAR(200) NULL COMMENT '供应商电子邮件'")

    # 收货方信息（不填/不抓的字段不建列）
    # scania_customer_code → 不填，不建列
    _add_column_if_not_exists(cursor, 'purchase_order', 'company_name',
                              "VARCHAR(200) NULL COMMENT '公司名称'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'street_address',
                              "VARCHAR(500) NULL COMMENT '街道地址（address1, address2 合并）'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'postal_code',
                              "VARCHAR(20) NULL COMMENT '邮政编码'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'city',
                              "VARCHAR(100) NULL COMMENT '城市'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'country',
                              "VARCHAR(100) NULL COMMENT '国家'")
    # contact_person / contact_phone / contact_email / receiver → 不抓，不建列

    # ── purchase_order_bd 子表 ──────────────────────────────────────────

    _add_column_if_not_exists(cursor, 'purchase_order_bd', 'item_code',
                              "VARCHAR(50) NULL COMMENT '物料编号（原始）'")
    _add_column_if_not_exists(cursor, 'purchase_order_bd', 'model_num',
                              "VARCHAR(200) NULL COMMENT '型号'")
    _add_column_if_not_exists(cursor, 'purchase_order_bd', 'size_info',
                              "VARCHAR(500) NULL COMMENT '尺寸/规格'")
    _add_column_if_not_exists(cursor, 'purchase_order_bd', 'discount_pct',
                              "VARCHAR(20) NULL COMMENT '折扣%'")
    _add_column_if_not_exists(cursor, 'purchase_order_bd', 'currency',
                              "VARCHAR(10) NULL COMMENT '订单货币'")
    _add_column_if_not_exists(cursor, 'purchase_order_bd', 'target_container',
                              "VARCHAR(100) NULL COMMENT '目标货柜'")


def init_schema(conn):
    """
    执行数据库 schema 初始化（添加缺失字段）

    Args:
        conn: MySQL 连接对象（调用方负责打开和关闭）
    """
    cursor = conn.cursor()
    try:
        ensure_po_columns(cursor)
        conn.commit()
    finally:
        cursor.close()
