"""
采购订单表头同步模块
负责 purchase_order 主表的数据同步
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.db import generate_id, format_datetime
from src.utils.mapper import PO_HEADER_MAPPING, VENDOR_FIELD_CANDIDATES, SHIPTO_FIELD_CANDIDATES


def _first_nonempty(data: dict, keys: list) -> str:
    """从 data 中按 keys 列表顺序取第一个非空值"""
    for k in keys:
        v = data.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return ''


def get_supplier_info(cursor, vendor_code: str) -> Tuple[Optional[int], Optional[str]]:
    """
    根据供应商代码查询供应商信息
    
    Args:
        cursor: 数据库游标
        vendor_code: 供应商代码 (JSON中的vendor字段)
        
    Returns:
        tuple: (supplier_id, supplier_name) 如果未找到返回 (None, None)
    """
    if not vendor_code:
        return None, None
    
    try:
        cursor.execute(
            "SELECT id, name FROM sys_department WHERE code = %s AND del_flag = 0",
            (vendor_code,)
        )
        result = cursor.fetchone()
        if result:
            return result[0], result[1]  # (id, name)
        return None, None
    except Exception as e:
        print(f"  [WARN] 查询供应商信息失败 (code={vendor_code}): {e}")
        return None, None


def map_header_data(cursor, po_data: Dict) -> Dict:
    """
    将 JSON 数据映射到数据库字段
    
    Args:
        cursor: 数据库游标
        po_data: 采购订单 JSON 数据
        
    Returns:
        dict: 映射后的数据库字段
    """
    result = {
        'id': generate_id(),
        'create_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'del_flag': 0,
    }
    
    # 基础字段映射
    for json_field, db_field in PO_HEADER_MAPPING.items():
        # 跳过 vendor 字段，后面单独处理
        if json_field == 'vendor':
            continue
            
        value = po_data.get(json_field)
        
        # 日期时间格式化
        if 'date' in json_field.lower() and value:
            value = format_datetime(value)
        
        # 数值转字符串 (数据库字段是 varchar)
        if isinstance(value, (int, float)) and db_field not in ['id']:
            value = str(value)
        
        result[db_field] = value
    
    # 处理供应商信息：从 sys_department 表查询
    vendor_code = po_data.get('vendor')
    if vendor_code:
        supplier_id, supplier_name = get_supplier_info(cursor, vendor_code)
        result['owner_dept_id'] = supplier_id
        result['supplier_name'] = supplier_name
    else:
        result['owner_dept_id'] = None
        result['supplier_name'] = None

    # ── 供应商扩展信息（来自 Maximo PO 供应商字段）────────────────────────
    vc = VENDOR_FIELD_CANDIDATES
    result['vendor_code']      = _first_nonempty(po_data, vc['vendor_code']) or None
    result['supplier_address'] = _first_nonempty(po_data, vc['supplier_address']) or None
    result['supplier_zip']     = _first_nonempty(po_data, vc['supplier_zip']) or None
    result['supplier_city']    = _first_nonempty(po_data, vc['supplier_city']) or None
    # supplier_country: 业务要求不抓，留空
    result['supplier_contact'] = _first_nonempty(po_data, vc['supplier_contact']) or None
    result['supplier_phone']   = _first_nonempty(po_data, vc['supplier_phone']) or None
    result['supplier_email']   = _first_nonempty(po_data, vc['supplier_email']) or None

    # ── 收货方信息（shipto）───────────────────────────────────────────────
    sc = SHIPTO_FIELD_CANDIDATES
    result['company_name'] = _first_nonempty(po_data, sc['company_name']) or None

    # 街道地址：合并 address1 和 address2
    addr1 = _first_nonempty(po_data, sc['street_address_1'])
    addr2 = _first_nonempty(po_data, sc['street_address_2'])
    result['street_address'] = ' '.join(filter(None, [addr1, addr2])) or None

    result['postal_code'] = _first_nonempty(po_data, sc['postal_code']) or None
    result['city']        = _first_nonempty(po_data, sc['city']) or None
    result['country']     = 'China'  # 固定值

    # 联系人、联系电话、电子邮件、接收人：业务要求不抓，留空
    result['contact_person'] = None
    result['contact_phone']  = None
    result['contact_email']  = None
    result['receiver']       = None

    # 斯堪尼亚客户代码：业务要求不填，留空
    result['scania_customer_code'] = None

    return result


def check_po_exists(cursor, po_code: str) -> Optional[int]:
    """
    检查订单是否已存在
    
    Args:
        cursor: 数据库游标
        po_code: 订单号
        
    Returns:
        int: 订单ID，不存在返回 None
    """
    cursor.execute(
        "SELECT id FROM purchase_order WHERE code = %s AND del_flag = 0",
        (po_code,)
    )
    result = cursor.fetchone()
    return result[0] if result else None


def delete_existing_po(cursor, po_id: int):
    """
    删除已存在的订单（包括明细）
    
    Args:
        cursor: 数据库游标
        po_id: 订单ID
    """
    # 删除明细
    cursor.execute("DELETE FROM purchase_order_bd WHERE form_id = %s", (po_id,))
    # 删除主表
    cursor.execute("DELETE FROM purchase_order WHERE id = %s", (po_id,))


def insert_po_header(cursor, header_data: Dict) -> int:
    """
    插入订单头
    
    Args:
        cursor: 数据库游标
        header_data: 订单头数据
        
    Returns:
        int: 插入的订单ID
    """
    columns = ', '.join(header_data.keys())
    placeholders = ', '.join(['%s'] * len(header_data))
    insert_sql = f"INSERT INTO purchase_order ({columns}) VALUES ({placeholders})"
    
    cursor.execute(insert_sql, list(header_data.values()))
    return header_data['id']


def batch_insert_headers(
    cursor, 
    po_list: List[Dict], 
    update_existing: bool = False
) -> Dict[str, int]:
    """
    批量插入订单头
    
    Args:
        cursor: 数据库游标
        po_list: 采购订单列表
        update_existing: 是否更新已存在的订单
        
    Returns:
        dict: {订单号: 订单ID} 映射表
    """
    print("\n" + "="*60)
    print("步骤 2: 插入订单头")
    print("="*60)
    
    header_map = {}
    stats = {'inserted': 0, 'updated': 0, 'skipped': 0, 'failed': 0}
    
    for po_data in po_list:
        po_code = po_data.get('ponum')
        if not po_code:
            print(f"  ✗ 跳过: 缺少 ponum")
            stats['failed'] += 1
            continue
        
        try:
            # 检查是否已存在
            existing_id = check_po_exists(cursor, po_code)
            
            if existing_id:
                if update_existing:
                    delete_existing_po(cursor, existing_id)
                    header_data = map_header_data(cursor, po_data)
                    header_id = insert_po_header(cursor, header_data)
                    header_map[po_code] = header_id
                    stats['updated'] += 1
                    print(f"  ↻ {po_code} (更新)")
                else:
                    header_map[po_code] = existing_id
                    stats['skipped'] += 1
                    print(f"  ⊙ {po_code} (已存在)")
            else:
                header_data = map_header_data(cursor, po_data)
                header_id = insert_po_header(cursor, header_data)
                header_map[po_code] = header_id
                stats['inserted'] += 1
                print(f"  ✓ {po_code}")
                
        except Exception as e:
            print(f"  ✗ {po_code}: {e}")
            stats['failed'] += 1
    
    print(f"\n[INFO] 订单头处理完成:")
    print(f"  新增: {stats['inserted']}")
    print(f"  更新: {stats['updated']}")
    print(f"  跳过: {stats['skipped']}")
    print(f"  失败: {stats['failed']}")
    
    return header_map
