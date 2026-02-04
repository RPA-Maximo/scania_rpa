"""
查看数据库中物料表的结构
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import mysql.connector
from config import get_db_config


def check_table_structure():
    """查看物料表结构"""
    print("="*80)
    print("连接数据库...")
    print("="*80)
    
    try:
        db_config = get_db_config()
        print(f"数据库: {db_config['host']}:{db_config['port']}/{db_config['database']}")
        
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # 查看所有表
        print("\n查询所有表...")
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        
        print(f"\n数据库中的表 ({len(tables)} 个):")
        for i, (table_name,) in enumerate(tables, 1):
            print(f"  {i}. {table_name}")
        
        # 查找物料相关的表
        print("\n" + "="*80)
        print("查找物料相关的表...")
        print("="*80)
        
        item_tables = [t[0] for t in tables if 'item' in t[0].lower() or 'material' in t[0].lower() or '物料' in t[0]]
        
        if item_tables:
            print(f"\n找到 {len(item_tables)} 个可能的物料表:")
            for table in item_tables:
                print(f"\n表名: {table}")
                print("-"*80)
                
                # 查看表结构
                cursor.execute(f"DESCRIBE `{table}`")
                columns = cursor.fetchall()
                
                print(f"字段数: {len(columns)}")
                print(f"\n{'字段名':<30} {'类型':<20} {'允许NULL':<10} {'键':<10} {'默认值':<15}")
                print("-"*80)
                
                for col in columns:
                    field, type_, null, key, default, extra = col
                    print(f"{field:<30} {type_:<20} {null:<10} {key:<10} {str(default):<15}")
                
                # 查看数据量
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                count = cursor.fetchone()[0]
                print(f"\n当前数据量: {count} 条")
                
                # 查看示例数据
                if count > 0:
                    cursor.execute(f"SELECT * FROM `{table}` LIMIT 1")
                    sample = cursor.fetchone()
                    print(f"\n示例数据 (第一条):")
                    col_names = [desc[0] for desc in cursor.description]
                    for col_name, value in zip(col_names, sample):
                        print(f"  {col_name}: {value}")
        else:
            print("\n未找到物料相关的表")
            print("请手动指定表名")
        
        cursor.close()
        conn.close()
        
        print("\n" + "="*80)
        print("✓ 查询完成")
        print("="*80)
        
    except mysql.connector.Error as e:
        print(f"\n✗ 数据库错误: {e}")
    except Exception as e:
        print(f"\n✗ 异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_table_structure()
