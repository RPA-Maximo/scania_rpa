"""
测试采购订单主表映射和插入功能
验证完整的 JSON -> purchase_order 表的数据流
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
import mysql.connector
from config.auth import get_db_config
from src.sync.po_header import map_header_data, get_supplier_info


def test_po_header_mapping():
    """测试采购订单头映射功能"""
    config = get_db_config()
    
    print(">>> 测试采购订单主表字段映射")
    print("="*60)
    
    # 加载测试数据
    json_file = PROJECT_ROOT / "data" / "raw" / "po_CN5123_detail.json"
    with open(json_file, 'r', encoding='utf-8') as f:
        po_data = json.load(f)
    
    print(f"\n加载测试数据: {json_file.name}")
    print(f"订单号: {po_data.get('ponum')}")
    print(f"供应商代码: {po_data.get('vendor')}")
    
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
            
            # 测试供应商信息查询
            print("\n" + "-"*60)
            print("步骤 1: 查询供应商信息")
            print("-"*60)
            vendor_code = po_data.get('vendor')
            supplier_id, supplier_name = get_supplier_info(cursor, vendor_code)
            
            if supplier_id and supplier_name:
                print(f"  ✓ 供应商查询成功")
                print(f"    代码: {vendor_code}")
                print(f"    ID: {supplier_id}")
                print(f"    名称: {supplier_name}")
            else:
                print(f"  ✗ 未找到供应商信息 (code={vendor_code})")
            
            # 测试字段映射
            print("\n" + "-"*60)
            print("步骤 2: 执行字段映射")
            print("-"*60)
            
            header_data = map_header_data(cursor, po_data)
            
            print(f"\n映射结果 (共 {len(header_data)} 个字段):\n")
            
            # 分类显示
            print("【自动生成字段】")
            for key in ['id', 'create_time', 'del_flag']:
                if key in header_data:
                    print(f"  {key:<20} = {header_data[key]}")
            
            print("\n【基础映射字段】")
            basic_fields = ['code', 'description', 'user_code', 'location', 'status', 
                          'status_date', 'order_date', 'total_cost', 'currency', 
                          'revision', 'type', 'request_date']
            for key in basic_fields:
                if key in header_data:
                    value = header_data[key]
                    if value and len(str(value)) > 50:
                        value = str(value)[:50] + "..."
                    print(f"  {key:<20} = {value}")
            
            print("\n【供应商信息字段】")
            for key in ['owner_dept_id', 'supplier_name']:
                if key in header_data:
                    print(f"  {key:<20} = {header_data[key]}")
            
            # 验证关键字段
            print("\n" + "-"*60)
            print("步骤 3: 验证关键字段")
            print("-"*60)
            
            checks = [
                ('订单号', 'code', po_data.get('ponum')),
                ('供应商ID', 'owner_dept_id', supplier_id),
                ('供应商名称', 'supplier_name', supplier_name),
                ('状态', 'status', po_data.get('status')),
            ]
            
            all_passed = True
            for name, field, expected in checks:
                actual = header_data.get(field)
                if actual == expected:
                    print(f"  ✓ {name}: {actual}")
                else:
                    print(f"  ✗ {name}: 期望 {expected}, 实际 {actual}")
                    all_passed = False
            
            if all_passed:
                print("\n[SUCCESS] 所有验证通过!")
            else:
                print("\n[FAIL] 部分验证失败")
            
    except mysql.connector.Error as e:
        print(f"[FAIL] 数据库操作失败: {e}")
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn and conn.is_connected():
            conn.close()
            print("\n>>> 数据库连接已关闭。")


if __name__ == "__main__":
    test_po_header_mapping()
