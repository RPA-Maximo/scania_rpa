"""
采购订单明细同步模块
负责 purchase_order_bd 明细表的数据同步
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.db import generate_id
from src.utils.mapper import PO_LINE_MAPPING


def map_line_data(line_data: Dict, form_id: int, material_id: int) -> Dict:
    """
    将订单明细 JSON 映射到数据库字段
    
    Args:
        line_data: 明细行 JSON 数据
        form_id: 订单头ID
        material_id: 物料ID
        
    Returns:
        dict: 映射后的数据库字段
    """
    result = {
        'id': generate_id(),
        'form_id': form_id,
        'sku': material_id,  # 从 material 表查询得到的 ID
        'create_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'del_flag': 0,
    }
    
    for json_field, db_field in PO_LINE_MAPPING.items():
        value = line_data.get(json_field)
        
        # 布尔值转字符串
        if isinstance(value, bool):
            value = '是' if value else '否'
        
        # 数值转字符串或保留原值
        if db_field == 'qty':
            value = int(value) if value else 0
        elif isinstance(value, (int, float)) and db_field not in ['id', 'form_id', 'sku']:
            value = str(value)
        
        result[db_field] = value
    
    return result


def insert_po_lines(
    cursor, 
    lines: List[Dict], 
    form_id: int, 
    material_map: Dict[str, int]
) -> int:
    """
    插入订单明细
    
    Args:
        cursor: 数据库游标
        lines: 明细行列表
        form_id: 订单头ID
        material_map: 物料映射表 {物料编号: 物料ID}
        
    Returns:
        int: 成功插入的数量
    """
    inserted_count = 0
    
    for line in lines:
        item_code = line.get('itemnum')
        material_id = material_map.get(item_code)
        
        if not material_id:
            print(f"    [WARN] 跳过物料 {item_code}（找不到ID）")
            continue
        
        line_data = map_line_data(line, form_id, material_id)
        
        columns = ', '.join(line_data.keys())
        placeholders = ', '.join(['%s'] * len(line_data))
        insert_sql = f"INSERT INTO purchase_order_bd ({columns}) VALUES ({placeholders})"
        
        try:
            cursor.execute(insert_sql, list(line_data.values()))
            inserted_count += 1
        except Exception as e:
            print(f"    [ERROR] 插入明细失败: {e}")
    
    return inserted_count


def batch_insert_details(
    cursor,
    po_list: List[Dict],
    header_map: Dict[str, int],
    material_map: Dict[str, int]
) -> Dict:
    """
    批量插入订单明细
    
    Args:
        cursor: 数据库游标
        po_list: 采购订单列表
        header_map: 订单头映射表 {订单号: 订单ID}
        material_map: 物料映射表 {物料编号: 物料ID}
        
    Returns:
        dict: 统计信息
    """
    print("\n" + "="*60)
    print("步骤 3: 插入订单明细")
    print("="*60)
    
    stats = {'total_lines': 0, 'inserted': 0, 'failed': 0}
    
    for po_data in po_list:
        po_code = po_data.get('ponum')
        form_id = header_map.get(po_code)
        
        if not form_id:
            print(f"  ✗ {po_code}: 找不到订单头ID")
            continue
        
        poline = po_data.get('poline', [])
        if not poline:
            print(f"  ⊙ {po_code}: 无明细行")
            continue
        
        stats['total_lines'] += len(poline)
        
        # 插入明细
        inserted = insert_po_lines(cursor, poline, form_id, material_map)
        stats['inserted'] += inserted
        stats['failed'] += len(poline) - inserted
        
        print(f"  ✓ {po_code}: {inserted}/{len(poline)} 行")
    
    print(f"\n[INFO] 订单明细处理完成:")
    print(f"  总行数: {stats['total_lines']}")
    print(f"  成功: {stats['inserted']}")
    print(f"  失败: {stats['failed']}")
    
    return stats
