"""
验证数据库中采购订单的供应商信息是否正确
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import mysql.connector
from config.auth import get_db_config


def verify_supplier_data():
    """验证采购订单表中的供应商信息"""
    config = get_db_config()
    
    print(">>> 验证采购订单供应商信息")
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
            
            # 查询最近的采购订单
            print("\n查询最近的采购订单及其供应商信息:\n")
            
            sql = """
            SELECT 
                po.code AS 订单号,
                po.supplier_name AS 供应商名称,
                po.owner_dept_id AS 供应商部门ID,
                sd.code AS 部门代码,
                sd.name AS 部门名称,
                po.status AS 状态,
                po.create_time AS 创建时间
            FROM purchase_order po
            LEFT JOIN sys_department sd ON po.owner_dept_id = sd.id
            WHERE po.del_flag = 0
            ORDER BY po.create_time DESC
            LIMIT 10
            """
            
            cursor.execute(sql)
            orders = cursor.fetchall()
            
            if not orders:
                print("  没有找到采购订单")
                return
            
            print(f"{'订单号':<15} {'供应商名称':<40} {'部门代码':<15} {'状态':<10}")
            print("-" * 100)
            
            for order in orders:
                po_code = order[0] or 'NULL'
                supplier_name = order[1] or 'NULL'
                owner_dept_id = order[2]
                dept_code = order[3] or 'NULL'
                dept_name = order[4] or 'NULL'
                status = order[5] or 'NULL'
                create_time = order[6]
                
                # 截断过长的字段
                if len(supplier_name) > 38:
                    supplier_name = supplier_name[:35] + "..."
                
                print(f"{po_code:<15} {supplier_name:<40} {dept_code:<15} {status:<10}")
                
                # 验证一致性
                if supplier_name != 'NULL' and dept_name != 'NULL':
                    if supplier_name != dept_name:
                        print(f"  ⚠️  警告: supplier_name 与 sys_department.name 不一致!")
                        print(f"      purchase_order.supplier_name: {supplier_name}")
                        print(f"      sys_department.name: {dept_name}")
            
            # 特别检查 CN5123 订单
            print("\n" + "="*60)
            print("详细检查订单 CN5123:")
            print("="*60)
            
            sql = """
            SELECT 
                po.code,
                po.supplier_name,
                po.owner_dept_id,
                sd.code AS dept_code,
                sd.name AS dept_name
            FROM purchase_order po
            LEFT JOIN sys_department sd ON po.owner_dept_id = sd.id
            WHERE po.code = 'CN5123' AND po.del_flag = 0
            """
            
            cursor.execute(sql)
            result = cursor.fetchone()
            
            if result:
                print(f"\n订单号: {result[0]}")
                print(f"purchase_order.supplier_name: {result[1]}")
                print(f"purchase_order.owner_dept_id: {result[2]}")
                print(f"sys_department.code: {result[3]}")
                print(f"sys_department.name: {result[4]}")
                
                if result[1] == result[4]:
                    print("\n✓ 供应商信息一致性验证通过!")
                else:
                    print("\n✗ 供应商信息不一致!")
            else:
                print("\n未找到订单 CN5123")
            
    except mysql.connector.Error as e:
        print(f"[FAIL] 数据库操作失败: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()
            print("\n>>> 数据库连接已关闭。")


if __name__ == "__main__":
    verify_supplier_data()
