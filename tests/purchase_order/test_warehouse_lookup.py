"""
测试仓库信息查询逻辑
验证从 warehouse 表查询仓库信息的功能
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import mysql.connector
from config.auth import get_db_config
from src.sync.po_detail import get_warehouse_id


def test_warehouse_lookup():
    """测试仓库查询功能"""
    config = get_db_config()
    
    print(">>> 测试仓库信息查询")
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
            
            # 测试用例1: 查询存在的仓库 518
            test_warehouse_code = "518"
            print(f"\n测试 1: 查询仓库代码 '{test_warehouse_code}'")
            warehouse_id = get_warehouse_id(cursor, test_warehouse_code)
            
            if warehouse_id:
                print(f"  ✓ 查询成功!")
                print(f"    warehouse_id: {warehouse_id}")
                
                # 验证查询结果
                cursor.execute(
                    "SELECT id, code, name FROM warehouse WHERE id = %s",
                    (warehouse_id,)
                )
                result = cursor.fetchone()
                if result:
                    print(f"    code: {result[1]}")
                    print(f"    name: {result[2]}")
            else:
                print(f"  ✗ 未找到仓库信息")
            
            # 测试用例2: 查询存在的仓库 513A
            test_warehouse_code_2 = "513A"
            print(f"\n测试 2: 查询仓库代码 '{test_warehouse_code_2}'")
            warehouse_id_2 = get_warehouse_id(cursor, test_warehouse_code_2)
            
            if warehouse_id_2:
                print(f"  ✓ 查询成功!")
                print(f"    warehouse_id: {warehouse_id_2}")
            else:
                print(f"  ✗ 未找到仓库信息")
            
            # 测试用例3: 查询不存在的仓库
            test_warehouse_code_3 = "NOTEXIST"
            print(f"\n测试 3: 查询不存在的仓库代码 '{test_warehouse_code_3}'")
            warehouse_id_3 = get_warehouse_id(cursor, test_warehouse_code_3)
            
            if warehouse_id_3 is None:
                print(f"  ✓ 正确返回 None")
            else:
                print(f"  ✗ 应该返回 None，但返回了: {warehouse_id_3}")
            
            # 测试用例4: 查看 warehouse 表中的所有仓库
            print(f"\n测试 4: 查看 warehouse 表中的所有仓库")
            cursor.execute(
                "SELECT id, code, name FROM warehouse WHERE del_flag = 0 ORDER BY code"
            )
            warehouses = cursor.fetchall()
            
            print(f"\n  共找到 {len(warehouses)} 个仓库:")
            print(f"  {'ID':<20} {'代码':<10} {'名称'}")
            print("  " + "-"*60)
            for wh in warehouses:
                print(f"  {wh[0]:<20} {wh[1]:<10} {wh[2]}")
            
    except mysql.connector.Error as e:
        print(f"[FAIL] 数据库操作失败: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()
            print("\n>>> 数据库连接已关闭。")


if __name__ == "__main__":
    test_warehouse_lookup()
