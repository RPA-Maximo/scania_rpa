"""
验证数据库中采购订单明细的仓库信息
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import mysql.connector
from config.auth import get_db_config


def verify_warehouse_data():
    """验证采购订单明细表中的仓库信息"""
    config = get_db_config()
    
    print(">>> 验证采购订单明细仓库信息")
    print("="*60)
    
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
            cursor = conn.cursor()
            
            # 查询明细表中的仓库信息
            print("\n查询采购订单明细的仓库分布:\n")
            
            sql = """
            SELECT 
                w.code AS 仓库代码,
                w.name AS 仓库名称,
                COUNT(bd.id) AS 明细行数
            FROM purchase_order_bd bd
            LEFT JOIN warehouse w ON bd.warehouse = w.id
            WHERE bd.del_flag = 0
            GROUP BY w.code, w.name
            ORDER BY COUNT(bd.id) DESC
            """
            
            cursor.execute(sql)
            results = cursor.fetchall()
            
            print(f"{'仓库代码':<15} {'仓库名称':<40} {'明细行数':<10}")
            print("-" * 70)
            
            total_lines = 0
            for row in results:
                code = row[0] or 'NULL'
                name = row[1] or '(无仓库)'
                count = row[2]
                total_lines += count
                print(f"{code:<15} {name:<40} {count:<10}")
            
            print("-" * 70)
            print(f"{'总计':<55} {total_lines:<10}")
            
            # 查看具体订单的仓库信息
            print("\n" + "="*60)
            print("查看 CN5123 订单的仓库信息（前5行）:")
            print("="*60)
            
            sql = """
            SELECT 
                po.code AS 订单号,
                bd.number AS 行号,
                bd.sku_names AS 物料描述,
                w.code AS 仓库代码,
                w.name AS 仓库名称
            FROM purchase_order_bd bd
            JOIN purchase_order po ON bd.form_id = po.id
            LEFT JOIN warehouse w ON bd.warehouse = w.id
            WHERE po.code = 'CN5123' AND bd.del_flag = 0
            ORDER BY bd.number
            LIMIT 5
            """
            
            cursor.execute(sql)
            results = cursor.fetchall()
            
            print(f"\n{'行号':<10} {'仓库代码':<15} {'物料描述':<50}")
            print("-" * 80)
            for row in results:
                line_num = row[1] or 'N/A'
                wh_code = row[3] or 'NULL'
                desc = (row[2] or 'N/A')[:47] + '...' if row[2] and len(row[2]) > 50 else (row[2] or 'N/A')
                print(f"{line_num:<10} {wh_code:<15} {desc:<50}")
            
            # 验证仓库ID是否正确
            print("\n" + "="*60)
            print("验证仓库ID的正确性:")
            print("="*60)
            
            sql = """
            SELECT 
                bd.warehouse AS warehouse_id,
                w.code AS warehouse_code,
                w.name AS warehouse_name,
                COUNT(*) AS count
            FROM purchase_order_bd bd
            LEFT JOIN warehouse w ON bd.warehouse = w.id
            WHERE bd.del_flag = 0 AND bd.warehouse IS NOT NULL
            GROUP BY bd.warehouse, w.code, w.name
            """
            
            cursor.execute(sql)
            results = cursor.fetchall()
            
            print(f"\n{'仓库ID':<20} {'代码':<10} {'名称':<40} {'数量'}")
            print("-" * 80)
            for row in results:
                print(f"{row[0]:<20} {row[1]:<10} {row[2]:<40} {row[3]}")
            
            if results:
                print("\n✓ 仓库ID映射正确!")
            else:
                print("\n⚠️  没有找到仓库信息")
            
    except mysql.connector.Error as e:
        print(f"[FAIL] 数据库操作失败: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()
            print("\n>>> 数据库连接已关闭。")


if __name__ == "__main__":
    verify_warehouse_data()
