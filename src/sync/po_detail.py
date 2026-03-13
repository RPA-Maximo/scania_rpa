"""
采购订单明细同步模块
负责 purchase_order_bd 明细表的数据同步
"""
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.db import generate_id
from src.utils.mapper import PO_LINE_MAPPING


def _extract_size_from_desc(desc: str):
    """
    从物料描述中提取尺寸/规格字段。

    支持两种模式：
      1. 英文部分含连字符  → 产品规格代码，如 "工具/ITB-A61-40-10" → "ITB-A61-40-10"
      2. 描述首词匹配规格模式 → 线程/螺纹尺寸，如 "M10 内六角螺栓/..." → "M10"
         规格模式：字母开头后紧跟数字（M10, M12, G1/4, NPT1 等）

    Args:
        desc: Maximo description 字段，格式通常为 "中文描述/English description"

    Returns:
        提取到的尺寸字符串，或 None
    """
    if not desc:
        return None

    if '/' in desc:
        chin_part, eng_part = desc.split('/', 1)
        eng_part = eng_part.strip()

        # 优先：英文部分含连字符 → 产品规格代码（如 "ITB-A61-40-10"）
        if '-' in eng_part:
            return eng_part

        # 次选：描述首词匹配 [字母][数字] 开头的规格模式（如 "M10", "M12", "G1"）
        chin_first = chin_part.strip().split()[0] if chin_part.strip() else ''
        if chin_first and re.match(r'^[A-Za-z]\d', chin_first):
            return chin_first

        # 也检查英文部分的首词（描述格式为 "英文/中文" 时）
        eng_first = eng_part.split()[0] if eng_part else ''
        if eng_first and re.match(r'^[A-Za-z]\d', eng_first):
            return eng_first

    else:
        # 无 "/" 时：整体首词匹配规格模式
        first_token = desc.strip().split()[0] if desc.strip() else ''
        if first_token and re.match(r'^[A-Za-z]\d', first_token):
            return first_token

    return None


def get_warehouse_id(cursor, warehouse_code: str) -> int:
    """
    根据仓库代码查询仓库ID
    
    Args:
        cursor: 数据库游标
        warehouse_code: 仓库代码（如 "518", "513A"）
        
    Returns:
        int: 仓库ID，未找到返回 None
    """
    if not warehouse_code:
        return None
    
    try:
        cursor.execute(
            "SELECT id FROM warehouse WHERE code = %s AND del_flag = 0",
            (warehouse_code,)
        )
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"  [WARN] 查询仓库信息失败 (code={warehouse_code}): {e}")
        return None


def map_line_data(
    line_data: Dict,
    form_id: int,
    material_id: int = None,
    warehouse_id: int = None,
    header_currency: str = None,
    item_spec_map: Dict = None,
) -> Dict:
    """
    将订单明细 JSON 映射到数据库字段

    Args:
        line_data: 明细行 JSON 数据
        form_id: 订单头ID
        material_id: 物料ID（可选，对于非标准物料可以为 None）
        warehouse_id: 仓库ID（可选）
        header_currency: PO 头货币代码（poline 无行级货币时的 fallback）

    Returns:
        dict: 映射后的数据库字段
    """
    result = {
        'id': generate_id(),
        'form_id': form_id,
        'sku': material_id,  # 可以为 None（非标准物料）
        'warehouse': warehouse_id,  # 仓库ID
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
            # 保留小数精度（Maximo 可能返回非整数数量）
            try:
                value = float(value) if value is not None else 0
            except (TypeError, ValueError):
                value = 0
        elif isinstance(value, (int, float)) and db_field not in ['id', 'form_id', 'sku', 'warehouse']:
            value = str(value)

        result[db_field] = value

    # 货币：优先取行级 currency，fallback 到 PO 头 currencycode
    result['currency'] = (
        line_data.get('currency') or line_data.get('currencycode') or header_currency or None
    )

    # model_num / size_info：
    # poline 中 catalogcode/newitemdesc 均为 null 或不存在（Maximo 实测），
    # 从 MXAPIITEM 读取规格数据，再回退到 poline 自身的 description 字段：
    #
    #   model_num  ← MXAPIITEM.cxtypedsg（型号，UI 验证字段）
    #   size_info  ← 优先级：
    #     1. MXAPIITEM.catalogcode（规格代码，若有值直接使用）
    #     2. MXAPIITEM.description 解析（含 "-" 的英文产品代码 或 M10/M12 等规格前缀）
    #     3. poline 自身 description 解析（同上规则，作为最终兜底）
    if item_spec_map:
        item_num = line_data.get('itemnum')
        if item_num:
            spec = item_spec_map.get(item_num, {})
            if not result.get('model_num'):
                result['model_num'] = spec.get('cxtypedsg') or None

            if not result.get('size_info'):
                # 1. MXAPIITEM.catalogcode
                size = spec.get('catalogcode') or None
                # 2. MXAPIITEM.description 解析
                if not size:
                    size = _extract_size_from_desc(spec.get('description') or '')
                result['size_info'] = size or None

    # 3. 最终兜底：poline 自身 description 字段解析
    if not result.get('size_info'):
        poline_desc = line_data.get('description') or ''
        result['size_info'] = _extract_size_from_desc(poline_desc) or None

    return result


def insert_po_lines(
    cursor,
    lines: List[Dict],
    form_id: int,
    material_map: Dict[str, int],
    header_currency: str = None,
    item_spec_map: Dict = None,
) -> Dict:
    """
    插入订单明细
    
    Args:
        cursor: 数据库游标
        lines: 明细行列表
        form_id: 订单头ID
        material_map: 物料映射表 {物料编号: 物料ID}
        
    Returns:
        dict: 统计信息
    """
    stats = {
        'inserted': 0,
        'inserted_no_sku': 0,      # 插入成功（sku=NULL：无物料编号或 material 表中找不到）
        'skipped_service': 0,      # 跳过：服务类
        'failed': 0                # 失败：插入错误
    }
    
    # 缓存仓库ID查询结果
    warehouse_cache = {}
    
    for line in lines:
        item_code = line.get('itemnum')
        line_type = line.get('linetype', 'UNKNOWN')
        
        # 服务类订单行：跳过（不插入到明细表）
        if line_type in ['SERVICE', 'STDSERVICE']:
            stats['skipped_service'] += 1
            continue
        
        # 物料类订单行：查找物料ID；找不到时 sku=NULL 但 item_code 仍会保留
        material_id = material_map.get(item_code) if item_code else None
        if item_code and not material_id:
            print(f"    [INFO] 物料 {item_code} 未在 material 表中，sku 置 NULL")
        
        # 查询仓库ID
        warehouse_code = line.get('storeloc')
        warehouse_id = None
        
        if warehouse_code:
            # 使用缓存避免重复查询
            if warehouse_code in warehouse_cache:
                warehouse_id = warehouse_cache[warehouse_code]
            else:
                warehouse_id = get_warehouse_id(cursor, warehouse_code)
                warehouse_cache[warehouse_code] = warehouse_id
                
                if not warehouse_id:
                    print(f"    [WARN] 仓库 {warehouse_code} 在 warehouse 表中找不到ID")
        
        # 映射并插入数据
        line_data = map_line_data(line, form_id, material_id, warehouse_id, header_currency, item_spec_map)
        
        columns = ', '.join(line_data.keys())
        placeholders = ', '.join(['%s'] * len(line_data))
        insert_sql = f"INSERT INTO purchase_order_bd ({columns}) VALUES ({placeholders})"
        
        try:
            cursor.execute(insert_sql, list(line_data.values()))
            if material_id:
                stats['inserted'] += 1
            else:
                stats['inserted_no_sku'] += 1
        except Exception as e:
            desc = line.get('description', 'N/A')[:30]
            print(f"    [ERROR] 插入明细失败 ({desc}...): {e}")
            stats['failed'] += 1
    
    return stats


def batch_map_details(
    cursor,
    po_list: List[Dict],
    header_map: Dict[str, int],
    material_map: Dict[str, int],
    item_spec_map: Dict[str, Dict] = None,
) -> Dict[str, List[Dict]]:
    """
    批量清洗订单明细数据（只读 DB 做仓库查询，不写入）

    Args:
        cursor: 数据库游标
        po_list: 采购订单列表
        header_map: {ponum: form_id}（由 batch_map_headers 预生成）
        material_map: {物料编号: 物料ID}

    Returns:
        {ponum: [cleaned_line_data, ...]}
    """
    print("\n" + "="*60)
    print("步骤 3a: 清洗订单明细数据")
    print("="*60)

    result: Dict[str, List[Dict]] = {}
    warehouse_cache: Dict[str, int] = {}
    total_lines = 0

    for po_data in po_list:
        po_code = po_data.get('ponum')
        form_id = header_map.get(po_code)
        if not form_id:
            continue

        header_currency = po_data.get('currencycode') or None
        poline = po_data.get('poline', [])
        cleaned_lines = []

        for line in poline:
            item_code = line.get('itemnum')
            line_type = line.get('linetype', 'UNKNOWN')

            if line_type in ['SERVICE', 'STDSERVICE']:
                continue

            material_id = material_map.get(item_code) if item_code else None

            warehouse_code = line.get('storeloc')
            warehouse_id = None
            if warehouse_code:
                if warehouse_code not in warehouse_cache:
                    warehouse_cache[warehouse_code] = get_warehouse_id(cursor, warehouse_code)
                warehouse_id = warehouse_cache[warehouse_code]

            cleaned_lines.append(map_line_data(line, form_id, material_id, warehouse_id, header_currency, item_spec_map))

        result[po_code] = cleaned_lines
        total_lines += len(cleaned_lines)
        print(f"  ✓ {po_code}: {len(cleaned_lines)} 行")

    print(f"\n[INFO] 清洗完成: 共 {total_lines} 行明细")
    return result


def batch_insert_details(
    cursor,
    po_list: List[Dict],
    header_map: Dict[str, int],
    material_map: Dict[str, int],
    pre_mapped: Dict[str, List[Dict]] = None,
) -> Dict:
    """
    批量插入订单明细

    Args:
        cursor: 数据库游标
        po_list: 采购订单列表
        header_map: 订单头映射表 {订单号: 订单ID}
        material_map: 物料映射表 {物料编号: 物料ID}
        pre_mapped: 预清洗数据 {ponum: [line_data, ...]}，不为 None 时跳过 map 步骤

    Returns:
        dict: 统计信息
    """
    print("\n" + "="*60)
    print("步骤 3b: 插入订单明细")
    print("="*60)

    total_stats = {
        'total_lines': 0,
        'inserted': 0,
        'inserted_no_sku': 0,
        'skipped_service': 0,
        'failed': 0
    }

    for po_data in po_list:
        po_code = po_data.get('ponum')
        form_id = header_map.get(po_code)

        if not form_id:
            print(f"  ✗ {po_code}: 找不到订单头ID")
            continue

        # 使用预清洗数据或实时 map
        if pre_mapped is not None:
            cleaned_lines = pre_mapped.get(po_code, [])
            total_stats['total_lines'] += len(cleaned_lines)

            for line_data in cleaned_lines:
                columns = ', '.join(line_data.keys())
                placeholders = ', '.join(['%s'] * len(line_data))
                insert_sql = f"INSERT INTO purchase_order_bd ({columns}) VALUES ({placeholders})"
                try:
                    cursor.execute(insert_sql, list(line_data.values()))
                    if line_data.get('sku'):
                        total_stats['inserted'] += 1
                    else:
                        total_stats['inserted_no_sku'] += 1
                except Exception as e:
                    print(f"    [ERROR] 插入明细失败: {e}")
                    total_stats['failed'] += 1

            total_inserted = total_stats['inserted'] + total_stats['inserted_no_sku']
            print(f"  ✓ {po_code}: {len(cleaned_lines)} 行")
        else:
            poline = po_data.get('poline', [])
            if not poline:
                print(f"  ⊙ {po_code}: 无明细行")
                continue

            total_stats['total_lines'] += len(poline)
            line_stats = insert_po_lines(cursor, poline, form_id, material_map)

            for key in line_stats:
                total_stats[key] += line_stats[key]

            total_inserted = line_stats['inserted'] + line_stats['inserted_no_sku']
            msg = f"  ✓ {po_code}: {total_inserted}/{len(poline)} 行"
            details = []
            if line_stats['inserted_no_sku'] > 0:
                details.append(f"{line_stats['inserted_no_sku']} 非标准物料")
            if line_stats['skipped_service'] > 0:
                details.append(f"{line_stats['skipped_service']} 服务类")
            if details:
                msg += f" ({', '.join(details)})"
            print(msg)

    total_inserted = total_stats['inserted'] + total_stats['inserted_no_sku']
    print(f"\n[INFO] 订单明细处理完成:")
    print(f"  总行数: {total_stats['total_lines']}")
    print(f"  成功插入: {total_inserted} (含 {total_stats['inserted_no_sku']} 条 sku=NULL)")
    if total_stats['skipped_service'] > 0:
        print(f"  跳过（服务类）: {total_stats['skipped_service']}")
    if total_stats['failed'] > 0:
        print(f"  失败: {total_stats['failed']}")

    return total_stats
