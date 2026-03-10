"""
数据库表结构初始化
安全地为 purchase_order 和 purchase_order_bd 添加新字段（如已存在则跳过）
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
    确保 purchase_order 主表有采购订单主子表明细所需的全部字段
    """
    # ── purchase_order 主表新增字段 ─────────────────────────────────────

    # 供应商信息
    _add_column_if_not_exists(cursor, 'purchase_order', 'vendor_code',
                              "VARCHAR(50) NULL COMMENT '供应商编号'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_address',
                              "VARCHAR(500) NULL COMMENT '供应商地址'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_zip',
                              "VARCHAR(20) NULL COMMENT '供应商邮政编码'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_city',
                              "VARCHAR(100) NULL COMMENT '供应商城市'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_country',
                              "VARCHAR(100) NULL COMMENT '供应商国家'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_contact',
                              "VARCHAR(100) NULL COMMENT '供应商联系人'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_phone',
                              "VARCHAR(50) NULL COMMENT '供应商联系电话'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'supplier_email',
                              "VARCHAR(200) NULL COMMENT '供应商电子邮件'")

    # 收货方信息
    _add_column_if_not_exists(cursor, 'purchase_order', 'scania_customer_code',
                              "VARCHAR(50) NULL COMMENT '斯堪尼亚客户代码'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'company_name',
                              "VARCHAR(200) NULL COMMENT '公司名称'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'street_address',
                              "VARCHAR(500) NULL COMMENT '街道地址'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'postal_code',
                              "VARCHAR(20) NULL COMMENT '邮政编码'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'city',
                              "VARCHAR(100) NULL COMMENT '城市'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'country',
                              "VARCHAR(100) NULL COMMENT '国家'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'contact_person',
                              "VARCHAR(100) NULL COMMENT '联系人'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'contact_phone',
                              "VARCHAR(50) NULL COMMENT '联系电话'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'contact_email',
                              "VARCHAR(200) NULL COMMENT '电子邮件'")
    _add_column_if_not_exists(cursor, 'purchase_order', 'receiver',
                              "VARCHAR(100) NULL COMMENT '接收人'")

    # ── purchase_order_bd 子表新增字段 ─────────────────────────────────

    _add_column_if_not_exists(cursor, 'purchase_order_bd', 'model_num',
                              "VARCHAR(200) NULL COMMENT '型号'")
    _add_column_if_not_exists(cursor, 'purchase_order_bd', 'size_info',
                              "VARCHAR(500) NULL COMMENT '尺寸/规格'")
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
