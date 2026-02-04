"""
测试供应商信息查询逻辑
验证从 sys_department 表查询供应商信息的功能
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import mysql.connector
from config.auth import get_db_config
from src.sync.po_header import get_supplier_info


def test_supplier_lookup():
    """测试供应商查询功能"""
    config = get_db_config()
    
    print(">>> 测试供应商信息查询")
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
            
            # 测试用例1: 查询存在的供应商
            test_vendor_code = "9209701"
            print(f"\n测试 1: 查询供应商代码 '{test_vendor_code}'")
            supplier_id, supplier_name = get_supplier_info(cursor, test_vendor_code)
            
            if supplier_id and supplier_name:
                print(f"  ✓ 查询成功!")
                print(f"    supplier_id (owner_dept_id): {supplier_id}")
                print(f"    supplier_name: {supplier_name}")
            else:
                print(f"  ✗ 未找到供应商信息")
            
            # 测试用例2: 查询不存在的供应商
            test_vendor_code_2 = "NOTEXIST"
            print(f"\n测试 2: 查询不存在的供应商代码 '{test_vendor_code_2}'")
            supplier_id_2, supplier_name_2 = get_supplier_info(cursor, test_vendor_code_2)
            
            if supplier_id_2 is None and supplier_name_2 is None:
                print(f"  ✓ 正确返回 None")
            else:
                print(f"  ✗ 应该返回 None，但返回了: {supplier_id_2}, {supplier_name_2}")
            
            # 测试用例3: 查看 sys_department 表中的所有供应商
            print(f"\n测试 3: 查看 sys_department 表中的前10个部门")
            cursor.execute(
                "SELECT id, code, name FROM sys_department WHERE del_flag = 0 LIMIT 10"
            )
            departments = cursor.fetchall()
            
            print(f"\n  共找到 {len(departments)} 个部门:")
            print(f"  {'ID':<10} {'代码':<15} {'名称'}")
            print("  " + "-"*60)
            for dept in departments:
                print(f"  {dept[0]:<10} {dept[1]:<15} {dept[2]}")
            
    except mysql.connector.Error as e:
        print(f"[FAIL] 数据库操作失败: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()
            print("\n>>> 数据库连接已关闭。")


if __name__ == "__main__":
    test_supplier_lookup()
