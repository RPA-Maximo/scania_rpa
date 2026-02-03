"""
查询单个物料的详细信息
对照页面显示的所有字段
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import json
import urllib3
from config import get_maximo_auth, VERIFY_SSL, PROXIES
from config.settings import MAXIMO_BASE_URL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ITEM_MASTER_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIITEM"


def get_item_detail(item_number: str):
    """
    获取单个物料的详细信息
    
    Args:
        item_number: 物料编号，例如 '00050421'
    """
    print(f"查询物料: {item_number}")
    print("="*80)
    
    try:
        auth = get_maximo_auth()
    except ValueError as e:
        print(f"[错误] {e}")
        return None
    
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }
    
    # 查询参数 - 获取所有字段
    params = {
        'oslc.select': '*',
        'oslc.where': f'itemnum="{item_number}"',
        '_dropnulls': 0,  # 不删除空值，显示所有字段
    }
    
    try:
        if PROXIES:
            print(f"使用代理: {PROXIES['https']}\n")
        
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
            
            if not items:
                print(f"✗ 未找到物料: {item_number}")
                return None
            
            item = items[0]
            print(f"✓ 找到物料信息\n")
            
            # 对照页面字段显示
            print("="*80)
            print("物料基本信息")
            print("="*80)
            
            # 从截图中看到的字段
            field_mapping = {
                '物料编号 (Item)': 'itemnum',
                '物料名称': 'description',
                'SAP Material': 'sap_material',  # 可能的字段名
                '★PackIT Item': 'packit_item',  # 可能的字段名
                'EN Description': 'description_longdescription',
                'Type Designation': 'cxtypedsg',
                'Dimension / Quality': 'cxdimensionquality',
                'Additional Data': 'cxadditionaldata',
                'Manufacturer': 'manufacturer',
                'Manufacturer Product Number': 'cxmfprodnum',
                '★Commodity Group': 'commoditygroup',
                'Commodity Code': 'commodity',
                'Order Unit': 'orderunit',
                'Issue Unit': 'issueunit',
                'MSDS': 'msds',
                
                # 右侧字段
                'Status': 'status',
                'Preparation Status': 'cxprepstatus',
                'Item Set': 'itemsetid',
                'Rotating?': 'rotating',
                'Condition Enabled?': 'conditionenabled',
                'Kit?': 'iskit',
                'Capitalized?': 'capitalized',
                'Inspect on Receipt?': 'inspectionrequired',
                'Tax Exempt?': 'taxexempt',
                'Send to ARTHUR?': 'cxsendarthur',
                'Alter Type': 'lottype',
                'Product Owner': 'cxproductowner',
                'Product Code': 'cxproductcode',
                'Item Class': 'cxitemclass',
            }
            
            # 显示字段值
            found_fields = []
            missing_fields = []
            
            for display_name, api_field in field_mapping.items():
                value = item.get(api_field)
                
                if value is not None and value != '':
                    found_fields.append((display_name, api_field, value))
                    # 特殊标记的字段用 ★ 标注
                    marker = "★" if display_name.startswith('★') else " "
                    print(f"{marker} {display_name:35s} = {str(value)[:60]}")
                else:
                    missing_fields.append((display_name, api_field))
            
            # 显示未找到的字段
            if missing_fields:
                print(f"\n{'='*80}")
                print("未找到的字段 (可能使用了不同的字段名)")
                print(f"{'='*80}")
                for display_name, api_field in missing_fields:
                    print(f"  ✗ {display_name:35s} (尝试字段: {api_field})")
            
            # 搜索可能的字段
            print(f"\n{'='*80}")
            print("搜索可能相关的字段")
            print(f"{'='*80}")
            
            keywords = {
                'SAP': ['sap', 'erp'],
                'PackIT': ['pack', 'packit'],
                'MSDS': ['msds', 'safety'],
                'Product': ['product', 'prod'],
                'Manufacturer': ['manufacturer', 'vendor', 'mfr', 'mf'],
                'Additional': ['additional', 'add', 'extra'],
            }
            
            for category, search_terms in keywords.items():
                matching = []
                for field_name in item.keys():
                    for term in search_terms:
                        if term.lower() in field_name.lower():
                            value = item[field_name]
                            if value is not None and value != '':
                                matching.append((field_name, value))
                            break
                
                if matching:
                    print(f"\n{category} 相关字段:")
                    for field_name, value in matching:
                        print(f"  - {field_name:30s} = {str(value)[:50]}")
            
            # 保存完整数据到 JSON
            output_file = PROJECT_ROOT / "data" / "raw" / f"item_{item_number}_detail.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(item, f, indent=2, ensure_ascii=False)
            
            print(f"\n{'='*80}")
            print(f"完整数据已保存到: {output_file}")
            print(f"总字段数: {len(item)}")
            print(f"已匹配字段: {len(found_fields)}")
            print(f"未匹配字段: {len(missing_fields)}")
            
            return item
            
        elif resp.status_code == 401:
            print("✗ 认证失败，请更新 Cookie")
            return None
        else:
            print(f"✗ 请求失败: {resp.status_code}")
            print(f"响应: {resp.text[:200]}")
            return None
            
    except Exception as e:
        print(f"✗ 异常: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # 从截图中看到的物料编号
    item_number = "00050421"  # ALARGADOR CONICO
    
    print("="*80)
    print("物料详细信息查询工具")
    print("="*80)
    print()
    
    get_item_detail(item_number)
