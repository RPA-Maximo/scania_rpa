"""
检查采购订单相关数据库表结构
PurchaseOrder (采购订单主表)
PurchaseOrderBd (采购订单明细表)
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import mysql.connector
from config.auth import get_db_config


def check_po_tables():
    """检查采购订单相关表的字段结构"""
    config = get_db_config()
    
    print(">>> 连接数据库...")
    print(f"    Host: {config['host']}:{config['port']}")
    print(f"    Database: {config['database']}")
    
    conn = None
    try:
        conn = mysql.connector.connect(
            host=config['host'],
            port=config['port'],
            user=config['user'],
            password=config['password'],
            database=config['database']
        )
        
        if conn.is_connected():
            print("[OK] 数据库连接成功!\n")
            cursor = conn.cursor()
            
            # 检查两个表 (小写蛇形命名)
            tables = ['purchase_order', 'purchase_order_bd']
            
            for table in tables:
                print("="*60)
                print(f"表: {table}")
                print("="*60)
                
                try:
                    cursor.execute(f"DESCRIBE {table}")
                    columns = cursor.fetchall()
                    
                    print(f"共 {len(columns)} 个字段:\n")
                    print(f"{'序号':<4} {'字段名':<25} {'类型':<20} {'可空':<6} {'键':<6} {'默认值'}")
                    print("-"*80)
                    
                    for i, col in enumerate(columns, 1):
                        name = col[0]
                        col_type = col[1]
                        nullable = col[2]
                        key = col[3] if col[3] else ''
                        default = col[4] if col[4] else ''
                        print(f"{i:<4} {name:<25} {col_type:<20} {nullable:<6} {key:<6} {default}")
                    
                    print()
                    
                    # 查看表中的数据量
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    print(f"当前数据量: {count} 条\n")
                    
                except mysql.connector.Error as e:
                    print(f"[FAIL] 查询表 {table} 失败: {e}\n")
            
    except mysql.connector.Error as e:
        print(f"[FAIL] 数据库连接失败: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()
            print(">>> 数据库连接已关闭。")


if __name__ == "__main__":
    check_po_tables()
