"""
物料数据导入脚本
API → 内存 → 数据库 (同时保存CSV备份)
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import pandas as pd
import mysql.connector
import urllib3
import time
from datetime import datetime

from config import (
    get_maximo_auth,
    get_db_config,
    DEFAULT_HEADERS,
    REQUEST_DELAY,
    VERIFY_SSL,
    PROXIES,
    RAW_DATA_DIR
)
from config.settings import MAXIMO_BASE_URL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ITEM_MASTER_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIITEM"


def fetch_items_from_api(max_pages=5, page_size=20, where_clause=None, order_by='+itemnum'):
    """
    从 API 获取物料数据
    
    Returns:
        list: 物料数据列表
    """
    print("="*80)
    print("步骤 1: 从 API 获取数据")
    print("="*80)
    
    try:
        auth = get_maximo_auth()
    except ValueError as e:
        print(f"[错误] {e}")
        return None
    
    headers = {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }
    
    all_items = []
    
    for page in range(1, max_pages + 1):
        print(f"正在请求第 {page}/{max_pages} 页...", end="")
        
        params = {
            'oslc.select': '*',
            'oslc.pageSize': page_size,
            '_dropnulls': 0,
            'pageno': page,
        }
        
        if where_clause:
            params['oslc.where'] = where_clause
        if order_by:
            params['oslc.orderBy'] = order_by
        
        try:
            resp = requests.get(
                ITEM_MASTER_API_URL,
                headers=headers,
                params=params,
                verify=VERIFY_SSL,
                proxies=PROXIES,
                timeout=30
            )
            
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('member') or data.get('rdfs:member')
                
                if items:
                    print(f" ✓ {len(items)} 条")
                    all_items.extend(items)
                else:
                    print(" 无数据")
                    break
            else:
                print(f" ✗ 错误 {resp.status_code}")
                break
                
        except Exception as e:
            print(f" ✗ 异常: {e}")
            break
        
        time.sleep(REQUEST_DELAY)
    
    print(f"\n✓ 共获取 {len(all_items)} 条数据")
    return all_items


def transform_item_to_db_format(item):
    """
    将 API 数据转换为数据库格式
    
    Args:
        item: API 返回的物料数据
        
    Returns:
        dict: 数据库格式的数据
    """
    # 处理命名空间前缀
    def get_value(field_name):
        """获取字段值，处理可能的命名空间前缀"""
        value = item.get(field_name)
        if value is None:
            value = item.get(f'spi:{field_name}')
        return value
    
    # 提取英文描述
    en_description = None
    itemchangestatus = get_value('itemchangestatus')
    if itemchangestatus and isinstance(itemchangestatus, list) and len(itemchangestatus) > 0:
        en_description = itemchangestatus[0].get('description_longdescription')
        # 截断到1500字符
        if en_description and len(en_description) > 1500:
            en_description = en_description[:1500]
    
    # 布尔值转换
    def bool_to_str(value):
        if value is None:
            return None
        if isinstance(value, bool):
            return 'YES' if value else 'NO'
        if isinstance(value, str):
            return 'YES' if value.lower() in ['true', 'yes', '1'] else 'NO'
        return 'NO'
    
    # 字符串截断函数
    def truncate(value, max_length):
        if value is None:
            return None
        value_str = str(value)
        return value_str[:max_length] if len(value_str) > max_length else value_str
    
    return {
        'code': truncate(get_value('itemnum'), 50),
        'name': truncate(get_value('description'), 50),
        'description': get_value('description'),  # longtext 不需要截断
        'sap_material': truncate(get_value('cxsapmat'), 255),
        'status': truncate(get_value('status'), 255),
        'pack_item': truncate(get_value('cxpackit'), 255),
        'readiness': truncate(get_value('cxprepstatus'), 255),
        'english_description': en_description,
        'program_portfolio': None,  # API 中未找到
        'model': truncate(get_value('cxtypedsg'), 255),
        'turnover': None,  # API 中未找到 (盾线)
        'size': truncate(get_value('cxdimensionquality'), 255),
        'condition': truncate(bool_to_str(get_value('conditionenabled')), 255),
        'additional': truncate(get_value('cxadditionaldata'), 255),
        'toolkit': truncate(bool_to_str(get_value('iskit')), 255),
        'manufacturer': truncate(get_value('cxmanufct'), 255),
        'capitalization': truncate(bool_to_str(get_value('capitalized')), 255),
        'order_number': truncate(get_value('cxmfprodnum'), 255),
        'cheek': truncate(bool_to_str(get_value('inspectionrequired')), 255),
        'identifier': truncate(get_value('commoditygroup'), 255),
        'identifier_name': None,  # 需要查询商品表
        'duty_free': truncate(bool_to_str(get_value('taxexempt')), 255),
        'product_code': truncate(get_value('cxprodcode'), 255),
        'send_authentication': truncate(bool_to_str(get_value('cxsendarthur')), 255),
        'ordering_unit': truncate(get_value('orderunit'), 255),
        'batch_type': truncate(get_value('lottype'), 255),
        'issuing_unit': truncate(get_value('issueunit'), 255),
        'product_series': truncate(get_value('cxprodfam'), 255),
        'msds': truncate(get_value('msdsnum'), 255),
        'prcode': None,  # API 中未找到
        'material_category': truncate(get_value('cxitemclass'), 255),
        # 系统字段
        'create_time': datetime.now(),
        'create_user': 1,  # 系统用户
        'last_update_time': datetime.now(),
        'last_update_user': 1,
        'del_flag': 0,
    }


def save_to_csv(items, filename=None):
    """
    保存数据到 CSV 备份
    
    Args:
        items: 转换后的数据列表
        filename: 文件名
        
    Returns:
        Path: CSV 文件路径
    """
    print("\n" + "="*80)
    print("步骤 2: 保存 CSV 备份")
    print("="*80)
    
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"materials_import_{timestamp}.csv"
    
    filepath = RAW_DATA_DIR / filename
    
    df = pd.DataFrame(items)
    df.to_csv(filepath, index=False, encoding='utf-8-sig')
    
    print(f"✓ CSV 备份已保存: {filepath}")
    print(f"  行数: {len(df)}")
    print(f"  列数: {len(df.columns)}")
    
    return filepath


def insert_to_database(items, batch_size=100):
    """
    批量插入数据到数据库
    
    Args:
        items: 转换后的数据列表
        batch_size: 批量插入大小
        
    Returns:
        int: 成功插入的数量
    """
    print("\n" + "="*80)
    print("步骤 3: 导入数据库")
    print("="*80)
    
    try:
        db_config = get_db_config()
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # 获取当前最大 ID
        cursor.execute("SELECT COALESCE(MAX(id), 0) FROM `material`")
        max_id = cursor.fetchone()[0]
        print(f"当前最大 ID: {max_id}")
        
        # 准备 INSERT 语句 (包含 id)
        fields = [
            'id', 'code', 'name', 'description', 'sap_material', 'status', 'pack_item',
            'readiness', 'english_description', 'program_portfolio', 'model',
            'turnover', 'size', 'condition', 'additional', 'toolkit',
            'manufacturer', 'capitalization', 'order_number', 'cheek',
            'identifier', 'identifier_name', 'duty_free', 'product_code',
            'send_authentication', 'ordering_unit', 'batch_type', 'issuing_unit',
            'product_series', 'msds', 'prcode', 'material_category',
            'create_time', 'create_user', 'last_update_time', 'last_update_user', 'del_flag'
        ]
        
        placeholders = ', '.join(['%s'] * len(fields))
        field_names = ', '.join([f'`{f}`' for f in fields])
        
        # 使用 ON DUPLICATE KEY UPDATE 处理重复的 code
        update_fields = ', '.join([f'`{f}` = VALUES(`{f}`)' for f in fields if f not in ['id', 'code', 'create_time', 'create_user']])
        
        insert_sql = f"""
            INSERT INTO `material` ({field_names})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE
                {update_fields}
        """
        
        # 批量插入
        success_count = 0
        error_count = 0
        current_id = max_id
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i+batch_size]
            batch_data = []
            
            for item in batch:
                current_id += 1
                # 添加 ID 到数据中
                item_with_id = {'id': current_id, **item}
                row = tuple(item_with_id.get(f) for f in fields)
                batch_data.append(row)
            
            try:
                cursor.executemany(insert_sql, batch_data)
                conn.commit()
                success_count += len(batch)
                print(f"  批次 {i//batch_size + 1}: ✓ 插入 {len(batch)} 条 (ID: {current_id - len(batch) + 1} - {current_id})")
            except mysql.connector.Error as e:
                error_count += len(batch)
                print(f"  批次 {i//batch_size + 1}: ✗ 错误 - {e}")
                conn.rollback()
                # 回滚 ID
                current_id -= len(batch)
        
        cursor.close()
        conn.close()
        
        print(f"\n✓ 导入完成")
        print(f"  成功: {success_count} 条")
        print(f"  失败: {error_count} 条")
        
        return success_count
        
    except mysql.connector.Error as e:
        print(f"\n✗ 数据库错误: {e}")
        return 0
    except Exception as e:
        print(f"\n✗ 异常: {e}")
        import traceback
        traceback.print_exc()
        return 0


def main():
    """主函数"""
    print("="*80)
    print("物料数据导入工具")
    print("="*80)
    print()
    
    # 配置
    MAX_PAGES = 5
    PAGE_SIZE = 20
    WHERE_CLAUSE = 'status!="OBSOLETE" and itemnum>="00050102"'
    ORDER_BY = '+itemnum'
    
    print("导入配置:")
    print(f"  筛选条件: {WHERE_CLAUSE}")
    print(f"  排序: {ORDER_BY}")
    print(f"  页数: {MAX_PAGES}")
    print(f"  每页: {PAGE_SIZE} 条")
    print()
    
    # 步骤 1: 获取数据
    api_items = fetch_items_from_api(
        max_pages=MAX_PAGES,
        page_size=PAGE_SIZE,
        where_clause=WHERE_CLAUSE,
        order_by=ORDER_BY
    )
    
    if not api_items:
        print("\n✗ 未获取到数据，退出")
        return
    
    # 转换数据
    print("\n转换数据格式...")
    db_items = [transform_item_to_db_format(item) for item in api_items]
    print(f"✓ 转换完成: {len(db_items)} 条")
    
    # 步骤 2: 保存 CSV 备份
    csv_file = save_to_csv(db_items)
    
    # 步骤 3: 导入数据库
    success_count = insert_to_database(db_items, batch_size=50)
    
    # 总结
    print("\n" + "="*80)
    print("导入总结")
    print("="*80)
    print(f"API 获取: {len(api_items)} 条")
    print(f"数据转换: {len(db_items)} 条")
    print(f"CSV 备份: {csv_file}")
    print(f"数据库导入: {success_count} 条")
    print("="*80)


if __name__ == "__main__":
    main()
