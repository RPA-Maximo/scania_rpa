"""
数据库连接探测脚本
验证与 MySQL 数据库的连接，并确认业务表的可访问性。
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import mysql.connector
from config.auth import get_db_config

def test_connection():
    """测试数据库连接并检查表结构"""
    config = get_db_config()
    
    print(">>> 正在尝试连接数据库...")
    print(f"    Host: {config['host']}")
    print(f"    Port: {config['port']}")
    print(f"    User: {config['user']}")
    print(f"    DB:   {config['database']}")
    
    # 待验证的表列表
    required_tables = [
        "Material", "PurchaseOrder", "PurchaseOrderBd", 
        "PurchaseReceiving", "Warehouse", "WarehouseBin",
        "PurchaseReceivingBd", "DeliveryNote", "DeliveryNoteBd",
        "TransferHd", "TransferBd"
    ]
    
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
            print("\n✅ 数据库连接成功！")
            cursor = conn.cursor()
            
            # 1. 获取所有现有的表
            cursor.execute("SHOW TABLES")
            existing_tables = [t[0].lower() for t in cursor.fetchall()]
            
            print("\n>>> 正在验证核心业务表...")
            found_count = 0
            for table in required_tables:
                if table.lower() in existing_tables:
                    print(f"  [OK] 发现表: {table}")
                    found_count += 1
                    
                    # 打印前 5 个字段作为结构参考
                    cursor.execute(f"DESCRIBE {table}")
                    columns = cursor.fetchall()
                    col_names = [c[0] for c in columns[:5]]
                    print(f"       示例字段: {', '.join(col_names)}...")
                else:
                    print(f"  [!!] 缺失表: {table}")
            
            print(f"\n>>> 验证结果: 发现 {found_count}/{len(required_tables)} 个目标表")
            
    except mysql.connector.Error as e:
        print(f"\n❌ 数据库连接失败: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()
            print("\n>>> 数据库连接已关闭。")

if __name__ == "__main__":
    test_connection()
