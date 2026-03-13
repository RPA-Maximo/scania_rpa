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
from src.utils.mapper import PO_HEADER_MAPPING, VENDOR_FIELD_CANDIDATES, BILLTO_FIELD_CANDIDATES  # noqa: E501


def _first_nonempty(data: dict, keys: list) -> str:
    """从 data 中按 keys 列表顺序取第一个非空值，始终返回字符串"""
    for k in keys:
        v = data.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ''


def _safe_phone(value: str) -> Optional[str]:
    """
    电话号码安全处理：
    - 保留 + 前缀（避免被数值化后丢失）
    - 去除首尾空格
    - 空值返回 None
    """
    if not value:
        return None
    s = str(value).strip()
    return s if s else None


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


def map_header_data(cursor, po_data: Dict, vendor_detail_map: Dict = None) -> Dict:
    """
    将 JSON 数据映射到数据库字段

    Args:
        cursor:            数据库游标
        po_data:           采购订单 JSON 数据
        vendor_detail_map: 公司详情字典 {company_code: {name, address1, city, ...}}
                           由 fetch_vendor_details 返回；为 None 时跳过二次填充

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
        value = po_data.get(json_field)
        
        # 日期时间格式化
        if 'date' in json_field.lower() and value:
            value = format_datetime(value)
        
        # 数值转字符串 (数据库字段是 varchar)
        if isinstance(value, (int, float)) and db_field not in ['id']:
            value = str(value)
        
        result[db_field] = value
    
    # 供应商名称：直接使用 Maximo vendorname 字段，不依赖 sys_department 查表
    result['supplier_name'] = po_data.get('vendorname') or None

    # owner_dept_id：仍通过 sys_department 查询（用于部门关联）
    vendor_code = po_data.get('vendor')
    if vendor_code:
        supplier_id, _ = get_supplier_info(cursor, vendor_code)
        result['owner_dept_id'] = supplier_id
    else:
        result['owner_dept_id'] = None

    # ── 供应商扩展信息（来自 Maximo PO 供应商字段）────────────────────────
    vc = VENDOR_FIELD_CANDIDATES
    result['vendor_code']        = _first_nonempty(po_data, vc['vendor_code']) or None
    result['supplier_address']   = _first_nonempty(po_data, vc['supplier_address']) or None
    result['supplier_address2']  = _first_nonempty(po_data, vc['supplier_address2']) or None
    result['supplier_zip']       = _first_nonempty(po_data, vc['supplier_zip']) or None
    result['supplier_city']      = _first_nonempty(po_data, vc['supplier_city']) or None
    result['supplier_state']     = _first_nonempty(po_data, vc['supplier_state']) or None
    # supplier_country 不抓（供应商国家不拉）
    result['supplier_contact']   = _first_nonempty(po_data, vc['supplier_contact']) or None
    result['supplier_phone']     = _safe_phone(_first_nonempty(po_data, vc['supplier_phone']))
    result['supplier_email']     = _first_nonempty(po_data, vc['supplier_email']) or None

    # ── 收款方信息（billto）+ 内部买方信息 ────────────────────────────────
    bc = BILLTO_FIELD_CANDIDATES
    result['company_name'] = _first_nonempty(po_data, bc['company_name']) or None

    # 街道地址：合并 address1 + address2（address2 为空时不加分隔符）
    addr1 = _first_nonempty(po_data, bc['street_address_1'])
    addr2 = _first_nonempty(po_data, bc['street_address_2'])
    result['street_address'] = ', '.join(filter(None, [addr1, addr2])) or None

    result['postal_code']    = _first_nonempty(po_data, bc['postal_code']) or None
    result['city']           = _first_nonempty(po_data, bc['city']) or None
    result['country']        = _first_nonempty(po_data, bc['country']) or None
    result['contact_person'] = _first_nonempty(po_data, bc['contact_person']) or None
    result['contact_phone']  = _safe_phone(_first_nonempty(po_data, bc['contact_phone']))
    result['contact_email']  = _first_nonempty(po_data, bc['contact_email']) or None
    result['receiver']       = _first_nonempty(po_data, bc['receiver']) or None
    # scania_customer_code 无对应 Maximo 字段，保持空值

    # ── 二次填充：从 MXAPICOMPANY 查询结果补充空字段 ─────────────────────────
    # 与 model_num/size_info 的子表修复逻辑完全一致：
    #   MXAPIPO 本身的 ven*/billto* 字段若为空（Maximo 权限限制），
    #   从 fetch_vendor_details 返回的公司详情字典中读取并回填。
    if vendor_detail_map:
        vendor_code = po_data.get('vendor')
        billto_code = po_data.get('billto')

        # 供应商字段 fallback
        if vendor_code:
            vd = vendor_detail_map.get(vendor_code, {})
            if not result.get('supplier_name'):
                result['supplier_name']   = vd.get('name')
            if not result.get('vendor_code'):
                result['vendor_code']     = vendor_code
            if not result.get('supplier_address'):
                result['supplier_address'] = vd.get('address1')
            if not result.get('supplier_address2'):
                result['supplier_address2'] = vd.get('address2')
            if not result.get('supplier_zip'):
                result['supplier_zip']    = vd.get('zip')
            if not result.get('supplier_city'):
                result['supplier_city']   = vd.get('city')
            if not result.get('supplier_state'):
                result['supplier_state']  = vd.get('stateprovince')
            if not result.get('supplier_contact'):
                result['supplier_contact'] = vd.get('contact')
            if not result.get('supplier_phone'):
                result['supplier_phone']  = _safe_phone(vd.get('phone1') or '')
            if not result.get('supplier_email'):
                result['supplier_email']  = vd.get('email1')

        # 收款方（billto）字段 fallback
        if billto_code:
            bd = vendor_detail_map.get(billto_code, {})
            if not result.get('company_name'):
                result['company_name']    = bd.get('name')
            if not result.get('street_address'):
                addr1 = bd.get('address1') or ''
                addr2 = bd.get('address2') or ''
                merged = ', '.join(filter(None, [addr1, addr2]))
                result['street_address']  = merged or None
            if not result.get('postal_code'):
                result['postal_code']     = bd.get('zip')
            if not result.get('city'):
                result['city']            = bd.get('city')
            if not result.get('country'):
                result['country']         = bd.get('country')
            if not result.get('contact_person'):
                result['contact_person']  = bd.get('contact')
            if not result.get('contact_phone'):
                result['contact_phone']   = _safe_phone(bd.get('phone1') or '')
            if not result.get('contact_email'):
                result['contact_email']   = bd.get('email1')

    # ── 国家默认值：billto 国家为空时默认"中国" ────────────────────────────
    if not result.get('country'):
        result['country'] = '中国'

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


def batch_map_headers(
    cursor,
    po_list: List[Dict],
    vendor_detail_map: Dict = None,
) -> Tuple[Dict[str, Dict], Dict[str, int]]:
    """
    批量清洗订单头数据（只读 DB 做查询，不写入）

    Args:
        cursor:            数据库游标
        po_list:           采购订单列表
        vendor_detail_map: 公司详情字典 {company_code: {...}}
                           由 fetch_vendor_details 返回；为 None 时跳过二次填充

    Returns:
        (cleaned_map, header_id_map):
            cleaned_map    = {ponum: header_data_dict}
            header_id_map  = {ponum: id}  （id 由 generate_id() 预生成）
    """
    print("\n" + "="*60)
    print("步骤 2a: 清洗订单头数据")
    print("="*60)

    cleaned_map: Dict[str, Dict] = {}
    header_id_map: Dict[str, int] = {}
    failed = 0

    for po_data in po_list:
        po_code = po_data.get('ponum')
        if not po_code:
            print(f"  ✗ 跳过: 缺少 ponum")
            failed += 1
            continue
        try:
            header_data = map_header_data(cursor, po_data, vendor_detail_map)
            cleaned_map[po_code] = header_data
            header_id_map[po_code] = header_data['id']
            print(f"  ✓ {po_code}")
        except Exception as e:
            print(f"  ✗ {po_code}: {e}")
            failed += 1

    print(f"\n[INFO] 清洗完成: 成功 {len(cleaned_map)}, 失败 {failed}")
    return cleaned_map, header_id_map


def batch_insert_headers(
    cursor,
    po_list: List[Dict],
    update_existing: bool = False,
    pre_mapped: Dict[str, Dict] = None,
) -> Dict[str, int]:
    """
    批量插入订单头

    Args:
        cursor: 数据库游标
        po_list: 采购订单列表
        update_existing: 是否更新已存在的订单
        pre_mapped: 预清洗数据 {ponum: header_data}，不为 None 时跳过 map 步骤

    Returns:
        dict: {订单号: 订单ID} 映射表
    """
    print("\n" + "="*60)
    print("步骤 2b: 插入订单头")
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
            existing_id = check_po_exists(cursor, po_code)

            if existing_id:
                if update_existing:
                    delete_existing_po(cursor, existing_id)
                    header_data = (
                        pre_mapped[po_code]
                        if pre_mapped and po_code in pre_mapped
                        else map_header_data(cursor, po_data)
                    )
                    header_id = insert_po_header(cursor, header_data)
                    header_map[po_code] = header_id
                    stats['updated'] += 1
                    print(f"  ↻ {po_code} (更新)")
                else:
                    header_map[po_code] = existing_id
                    stats['skipped'] += 1
                    print(f"  ⊙ {po_code} (已存在)")
            else:
                header_data = (
                    pre_mapped[po_code]
                    if pre_mapped and po_code in pre_mapped
                    else map_header_data(cursor, po_data)
                )
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
