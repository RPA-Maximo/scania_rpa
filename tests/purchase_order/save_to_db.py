"""
采购订单数据入库脚本
将从 Maximo API 抓取的 JSON 数据保存到 MySQL 数据库
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import mysql.connector
from config.auth import get_db_config


# JSON 字段 -> 数据库字段映射 (订单头)
PO_HEADER_MAPPING = {
    'ponum': 'code',
    'description': 'description',
    'purchaseagent': 'user_code',
    'siteid': 'location',
    'status': 'status',
    'vendor': 'supplier_name',
    'statusdate': 'status_date',
    'orderdate': 'order_date',
    'totalcost': 'total_cost',
    'currencycode': 'currency',
    'revisionnum': 'revision',
    'potype': 'type',
    'requireddate': 'request_date',
}

# JSON 字段 -> 数据库字段映射 (订单明细)
PO_LINE_MAPPING = {
    'polinenum': 'number',
    'description': 'sku_names',  # 物料名称描述
    'orderqty': 'qty',
    'receiptscomplete': 'receive_status',
    'orderunit': 'ordering_unit',
    'unitcost': 'unit_cost',
    'linecost': 'line_cost',
    # 'itemnum' 需要通过查询 material 表获取 id，映射到 'sku'
}


def generate_id() -> int:
    """生成雪花 ID (简化版: 时间戳 + 随机数)"""
    import random
    timestamp = int(datetime.now().timestamp() * 1000)
    return timestamp * 1000 + random.randint(0, 999)


def format_datetime(dt_str: str) -> str:
    """格式化日期时间字符串"""
    if not dt_str:
        return None
    # 处理 ISO 格式: 2025-12-25T07:33:49+00:00
    try:
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str.replace('+00:00', '+0000').replace('Z', '+0000'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        return dt_str
    except:
        return dt_str


def map_header_data(po_data: Dict) -> Dict:
    """将 JSON 数据映射到数据库字段"""
    result = {
        'id': generate_id(),
        'create_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'del_flag': 0,
    }
    
    for json_field, db_field in PO_HEADER_MAPPING.items():
        value = po_data.get(json_field)
        
        # 日期时间格式化
        if 'date' in json_field.lower() and value:
            value = format_datetime(value)
        
        # 数值转字符串 (数据库字段是 varchar)
        if isinstance(value, (int, float)) and db_field not in ['id']:
            value = str(value)
        
        result[db_field] = value
    
    return result


def map_line_data(line_data: Dict, form_id: int, material_id: int) -> Dict:
    """将订单明细 JSON 映射到数据库字段"""
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


def check_po_exists(cursor, po_code: str) -> int:
    """检查订单是否已存在，返回 ID 或 None"""
    cursor.execute(
        "SELECT id FROM purchase_order WHERE code = %s AND del_flag = 0",
        (po_code,)
    )
    result = cursor.fetchone()
    return result[0] if result else None


def batch_get_material_ids(cursor, item_codes: List[str]) -> Dict[str, int]:
    """
    批量查询物料ID
    
    Args:
        cursor: 数据库游标
        item_codes: 物料编号列表
    
    Returns:
        Dict[物料编号, 物料ID]
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


def save_po_to_db(po_data: Dict, update_if_exists: bool = False) -> bool:
    """
    将采购订单数据保存到数据库
    
    Args:
        po_data: 完整的 PO JSON 数据
        update_if_exists: 如果订单已存在是否更新
    
    Returns:
        bool: 是否成功
    """
    po_code = po_data.get('ponum')
    if not po_code:
        print("[FAIL] 缺少 ponum 字段")
        return False
    
    print(f"\n保存订单: {po_code}")
    print("="*60)
    
    config = get_db_config()
    conn = None
    
    try:
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        # 检查是否已存在
        existing_id = check_po_exists(cursor, po_code)
        
        if existing_id:
            if update_if_exists:
                print(f"[INFO] 订单 {po_code} 已存在 (ID: {existing_id})，将更新")
                # 删除旧的明细
                cursor.execute(
                    "DELETE FROM purchase_order_bd WHERE form_id = %s",
                    (existing_id,)
                )
                # 删除旧的主表记录
                cursor.execute(
                    "DELETE FROM purchase_order WHERE id = %s",
                    (existing_id,)
                )
            else:
                print(f"[SKIP] 订单 {po_code} 已存在 (ID: {existing_id})，跳过")
                return True
        
        # 获取所有明细行
        poline = po_data.get('poline', [])
        if not poline:
            print("[WARN] 订单没有明细行")
        
        # 1. 批量验证物料是否存在
        item_codes = [line.get('itemnum') for line in poline if line.get('itemnum')]
        
        if item_codes:
            print(f"[INFO] 验证 {len(item_codes)} 个物料...")
            material_id_map = batch_get_material_ids(cursor, item_codes)
            
            # 检查是否有物料找不到
            missing_items = [code for code in item_codes if code not in material_id_map]
            
            if missing_items:
                print(f"[FAIL] 以下物料在 material 表中找不到:")
                for item_code in missing_items:
                    print(f"  - {item_code}")
                print(f"[FAIL] 订单 {po_code} 导入失败，整批数据不插入")
                return False
            
            print(f"[OK] 所有物料验证通过")
        
        # 2. 映射主表数据
        header_data = map_header_data(po_data)
        header_id = header_data['id']
        
        # 3. 插入主表
        columns = ', '.join(header_data.keys())
        placeholders = ', '.join(['%s'] * len(header_data))
        insert_sql = f"INSERT INTO purchase_order ({columns}) VALUES ({placeholders})"
        
        cursor.execute(insert_sql, list(header_data.values()))
        print(f"[OK] 主表插入成功 (ID: {header_id})")
        
        # 4. 插入明细
        if poline:
            inserted_count = 0
            for line in poline:
                item_code = line.get('itemnum')
                material_id = material_id_map.get(item_code)
                
                if not material_id:
                    # 理论上不会到这里，因为前面已经验证过
                    print(f"[WARN] 跳过物料 {item_code}（找不到ID）")
                    continue
                
                line_data = map_line_data(line, header_id, material_id)
                
                columns = ', '.join(line_data.keys())
                placeholders = ', '.join(['%s'] * len(line_data))
                insert_sql = f"INSERT INTO purchase_order_bd ({columns}) VALUES ({placeholders})"
                
                cursor.execute(insert_sql, list(line_data.values()))
                inserted_count += 1
            
            print(f"[OK] 明细插入成功 ({inserted_count} 条)")
        
        conn.commit()
        print(f"\n[OK] 订单 {po_code} 保存完成!")
        return True
        
    except mysql.connector.Error as e:
        print(f"[FAIL] 数据库错误: {e}")
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        print(f"[FAIL] 异常: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def save_po_from_json(json_path: str, update_if_exists: bool = False) -> bool:
    """从 JSON 文件导入订单"""
    import json
    
    if not Path(json_path).exists():
        print(f"[FAIL] 文件不存在: {json_path}")
        return False
    
    with open(json_path, 'r', encoding='utf-8') as f:
        po_data = json.load(f)
    
    return save_po_to_db(po_data, update_if_exists)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='采购订单数据入库')
    parser.add_argument('json_file', nargs='?', help='JSON 文件路径')
    parser.add_argument('--update', action='store_true', help='如果已存在则更新')
    
    args = parser.parse_args()
    
    # 默认测试文件
    if not args.json_file:
        default_file = PROJECT_ROOT / "data" / "raw" / "po_CN5123_detail.json"
        args.json_file = str(default_file)
    
    success = save_po_from_json(args.json_file, args.update)
    sys.exit(0 if success else 1)
