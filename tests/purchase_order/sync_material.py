"""
物料数据同步脚本
从 PO JSON 的 poline 同步物料到 material 表
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import mysql.connector
from config.auth import get_db_config


# poline -> material 字段映射
MATERIAL_MAPPING = {
    'itemnum': 'code',
    'description': 'name',
    'orderunit': 'ordering_unit',
    'manufacturer': 'manufacturer',
}


def generate_id() -> int:
    """生成 ID"""
    import random
    timestamp = int(datetime.now().timestamp() * 1000)
    return timestamp * 1000 + random.randint(0, 999)


def check_material_exists(cursor, code: str) -> int:
    """检查物料是否已存在，返回 ID 或 None"""
    cursor.execute(
        "SELECT id FROM material WHERE code = %s AND del_flag = 0",
        (code,)
    )
    result = cursor.fetchone()
    return result[0] if result else None


def sync_materials_from_po(po_data: Dict, skip_existing: bool = True) -> Dict:
    """
    从 PO 数据同步物料到 material 表
    
    Args:
        po_data: 完整的 PO JSON 数据
        skip_existing: 跳过已存在的物料
    
    Returns:
        dict: 统计结果 {inserted, skipped, failed}
    """
    poline = po_data.get('poline', [])
    if not poline:
        print("[FAIL] 没有 poline 数据")
        return {'inserted': 0, 'skipped': 0, 'failed': 0}
    
    po_code = po_data.get('ponum', 'Unknown')
    print(f"\n同步物料: 来自 PO {po_code}")
    print(f"共 {len(poline)} 行明细")
    print("="*60)
    
    config = get_db_config()
    conn = None
    stats = {'inserted': 0, 'skipped': 0, 'failed': 0}
    
    try:
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        for i, line in enumerate(poline, 1):
            itemnum = line.get('itemnum')
            if not itemnum:
                print(f"[{i:3}] 跳过: 无物料编号")
                stats['skipped'] += 1
                continue
            
            # 检查是否已存在
            existing_id = check_material_exists(cursor, itemnum)
            
            if existing_id:
                if skip_existing:
                    stats['skipped'] += 1
                    continue
                else:
                    # 删除旧记录
                    cursor.execute("DELETE FROM material WHERE id = %s", (existing_id,))
            
            # 构建数据
            material_data = {
                'id': generate_id(),
                'create_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'del_flag': 0,
            }
            
            for json_field, db_field in MATERIAL_MAPPING.items():
                value = line.get(json_field)
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
            except mysql.connector.Error as e:
                print(f"[{i:3}] 失败 ({itemnum}): {e}")
                stats['failed'] += 1
        
        conn.commit()
        
        print(f"\n[OK] 同步完成!")
        print(f"    插入: {stats['inserted']}")
        print(f"    跳过: {stats['skipped']} (已存在)")
        print(f"    失败: {stats['failed']}")
        
        return stats
        
    except mysql.connector.Error as e:
        print(f"[FAIL] 数据库错误: {e}")
        if conn:
            conn.rollback()
        return stats
    finally:
        if conn and conn.is_connected():
            conn.close()


def sync_from_json(json_path: str, skip_existing: bool = True) -> Dict:
    """从 JSON 文件同步物料"""
    import json
    
    if not Path(json_path).exists():
        print(f"[FAIL] 文件不存在: {json_path}")
        return {'inserted': 0, 'skipped': 0, 'failed': 0}
    
    with open(json_path, 'r', encoding='utf-8') as f:
        po_data = json.load(f)
    
    return sync_materials_from_po(po_data, skip_existing)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='从 PO 同步物料到 material 表')
    parser.add_argument('json_file', nargs='?', help='JSON 文件路径')
    parser.add_argument('--update', action='store_true', help='已存在则更新')
    
    args = parser.parse_args()
    
    # 默认测试文件
    if not args.json_file:
        default_file = PROJECT_ROOT / "data" / "raw" / "po_CN5123_detail.json"
        args.json_file = str(default_file)
    
    sync_from_json(args.json_file, skip_existing=not args.update)
