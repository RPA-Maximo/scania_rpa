"""
物料同步模块
负责物料数据的验证和同步
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.db import generate_id
from src.utils.mapper import MATERIAL_MAPPING


def extract_materials_from_pos(po_list: List[Dict]) -> List[str]:
    """
    从采购订单列表中提取所有唯一的物料编号
    
    Args:
        po_list: 采购订单列表
        
    Returns:
        list: 唯一的物料编号列表
    """
    material_codes = set()
    
    for po in po_list:
        poline = po.get('poline', [])
        for line in poline:
            item_code = line.get('itemnum')
            if item_code:
                material_codes.add(item_code)
    
    return sorted(list(material_codes))


def batch_validate_materials(cursor, item_codes: List[str]) -> Dict[str, int]:
    """
    批量验证物料是否存在
    
    Args:
        cursor: 数据库游标
        item_codes: 物料编号列表
        
    Returns:
        dict: {物料编号: 物料ID} 映射表
    """
    if not item_codes:
        return {}
    
    # 使用 IN 查询批量获取
    placeholders = ', '.join(['%s'] * len(item_codes))
    sql = f"SELECT code, id FROM material WHERE code IN ({placeholders}) AND del_flag = 0"
    
    cursor.execute(sql, item_codes)
    results = cursor.fetchall()
    
    # 构建映射字典
    return {code: material_id for code, material_id in results}


def get_missing_materials(item_codes: List[str], material_map: Dict[str, int]) -> List[str]:
    """
    获取缺失的物料编号
    
    Args:
        item_codes: 所有物料编号
        material_map: 已存在的物料映射
        
    Returns:
        list: 缺失的物料编号列表
    """
    return [code for code in item_codes if code not in material_map]


def sync_missing_materials(cursor, po_list: List[Dict], missing_codes: List[str]) -> Dict:
    """
    同步缺失的物料到 material 表
    
    Args:
        cursor: 数据库游标
        po_list: 采购订单列表
        missing_codes: 缺失的物料编号列表
        
    Returns:
        dict: 统计信息 {inserted, failed}
    """
    stats = {'inserted': 0, 'failed': 0}
    
    # 从 PO 中提取物料信息
    material_info = {}
    for po in po_list:
        poline = po.get('poline', [])
        for line in poline:
            item_code = line.get('itemnum')
            if item_code in missing_codes and item_code not in material_info:
                material_info[item_code] = line
    
    # 插入物料
    for item_code in missing_codes:
        line_data = material_info.get(item_code)
        if not line_data:
            print(f"  [WARN] 物料 {item_code} 无详细信息，跳过")
            stats['failed'] += 1
            continue
        
        # 构建物料数据
        material_data = {
            'id': generate_id(),
            'create_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'del_flag': 0,
        }
        
        for json_field, db_field in MATERIAL_MAPPING.items():
            value = line_data.get(json_field)
            # name 字段限制 50 字符
            if db_field == 'name' and value and len(value) > 50:
                value = value[:50]
            material_data[db_field] = value
        
        # 插入
        columns = ', '.join(material_data.keys())
        placeholders = ', '.join(['%s'] * len(material_data))
        insert_sql = f"INSERT INTO material ({columns}) VALUES ({placeholders})"
        
        try:
            cursor.execute(insert_sql, list(material_data.values()))
            stats['inserted'] += 1
            print(f"  ✓ {item_code}")
        except Exception as e:
            print(f"  ✗ {item_code}: {e}")
            stats['failed'] += 1
    
    return stats


def validate_and_sync_materials(cursor, po_list: List[Dict], auto_sync: bool = True) -> Dict[str, int]:
    """
    验证并同步物料（主函数）
    
    Args:
        cursor: 数据库游标
        po_list: 采购订单列表
        auto_sync: 是否自动同步缺失的物料
        
    Returns:
        dict: {物料编号: 物料ID} 映射表，如果有缺失且不自动同步则返回 None
    """
    print("\n" + "="*60)
    print("步骤 1: 物料验证")
    print("="*60)
    
    # 提取所有物料编号
    item_codes = extract_materials_from_pos(po_list)
    print(f"[INFO] 提取到 {len(item_codes)} 个唯一物料")
    
    # 批量验证
    material_map = batch_validate_materials(cursor, item_codes)
    print(f"[INFO] 数据库中已存在 {len(material_map)} 个物料")
    
    # 检查缺失
    missing_codes = get_missing_materials(item_codes, material_map)
    
    if missing_codes:
        print(f"[WARN] 发现 {len(missing_codes)} 个缺失物料:")
        for code in missing_codes[:10]:  # 只显示前10个
            print(f"  - {code}")
        if len(missing_codes) > 10:
            print(f"  ... 还有 {len(missing_codes) - 10} 个")
        
        if auto_sync:
            print(f"\n[INFO] 自动同步缺失物料...")
            stats = sync_missing_materials(cursor, po_list, missing_codes)
            print(f"[INFO] 同步完成: 成功 {stats['inserted']}, 失败 {stats['failed']}")
            
            # 重新查询物料映射
            material_map = batch_validate_materials(cursor, item_codes)
            
            # 再次检查是否还有缺失
            still_missing = get_missing_materials(item_codes, material_map)
            if still_missing:
                print(f"[ERROR] 仍有 {len(still_missing)} 个物料无法同步")
                return None
        else:
            print(f"[ERROR] 请先同步缺失的物料")
            return None
    
    print(f"[OK] 所有物料验证通过")
    return material_map
