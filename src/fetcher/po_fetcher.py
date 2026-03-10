"""
采购订单数据抓取器
从 Maximo API 抓取采购订单数据并保存为 JSON
"""
import sys
from pathlib import Path
import json
import time
from typing import List, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import urllib3
from config import (
    get_maximo_auth,
    DEFAULT_HEADERS,
    RAW_DATA_DIR,
)
from config.settings import MAXIMO_BASE_URL, REQUEST_DELAY, VERIFY_SSL
from config.settings_manager import settings_manager

# 禁用安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 采购订单 API 端点
PO_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIPO"
REQUEST_TIMEOUT = 120


def normalize_po_data(po_data: dict) -> dict:
    """
    标准化采购订单数据，移除命名空间前缀
    
    Args:
        po_data: 原始采购订单数据
    
    Returns:
        dict: 标准化后的数据（移除 spi: 等前缀）
    """
    normalized = {}
    
    for key, value in po_data.items():
        # 移除命名空间前缀 (spi:, rdfs: 等)
        if ':' in key:
            clean_key = key.split(':', 1)[1]
        else:
            clean_key = key
        
        # 递归处理嵌套的列表和字典
        if isinstance(value, dict):
            normalized[clean_key] = normalize_po_data(value)
        elif isinstance(value, list):
            normalized[clean_key] = [
                normalize_po_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            normalized[clean_key] = value
    
    return normalized


def fetch_po_by_number(po_number: str, save_to_file: bool = True) -> Optional[dict]:
    """
    根据采购订单号查询单个订单
    
    Args:
        po_number: 采购订单号，如 'CN5123'
        save_to_file: 是否保存到 JSON 文件
    
    Returns:
        dict: 订单数据，失败返回 None
    """
    print(f"  查询订单: {po_number}...", end=" ", flush=True)
    
    try:
        auth = get_maximo_auth()
    except ValueError as e:
        print(f"认证失败")
        return None
    
    headers = {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }
    
    params = {
        'oslc.select': (
            '*,'
            'requireddate,'
            'vendor,vendorname,'
            'venaddress1,venaddr1,'
            'venaddress2,venaddr2,'
            'venzip,venpostalcode,'
            'vencity,'
            'vencountry,vennation,'
            'vencontact,'
            'venphone,'
            'venemail,cxpoemail,'
            'billtocomp,billtoname,'
            'billtoaddress1,billtoaddr1,'
            'billtoaddress2,billtoaddr2,'
            'billtocity,'
            'billtozip,billtopostalcode,'
            'billtocountry,'
            'billtoattn,billtocontact,'
            'billtophone,'
            'billtoemail,contactemail,'
            'shiptoattn,shiptocontact,shiptocomp,'
            'buyercode,custcode,ourreference'
        ),
        'oslc.where': f'ponum="{po_number}"',
        '_dropnulls': 0,
    }
    
    try:
        start_time = time.time()
        resp = requests.get(
            PO_API_URL,
            headers=headers,
            params=params,
            verify=VERIFY_SSL,
            proxies=settings_manager.get_proxies(),
            timeout=REQUEST_TIMEOUT
        )
        
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('member') or data.get('rdfs:member')
            
            if items:
                po = items[0]
                
                # 标准化数据（移除命名空间前缀）
                po = normalize_po_data(po)
                
                elapsed = time.time() - start_time
                
                # 保存到 JSON
                if save_to_file:
                    output_file = RAW_DATA_DIR / f"po_{po_number}_detail.json"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(po, f, indent=2, ensure_ascii=False)
                
                print(f"✓ ({elapsed:.1f}s)")
                return po
            else:
                print(f"未找到")
                return None
                
        elif resp.status_code == 401:
            print(f"认证失败")
            return None
        else:
            print(f"错误 {resp.status_code}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"超时")
        return None
    except Exception as e:
        print(f"异常: {e}")
        return None


def fetch_po_list(
    po_numbers: List[str] = None,
    status_filter: str = None,
    max_pages: int = 1,
    page_size: int = 20,
    save_to_file: bool = True
) -> List[dict]:
    """
    批量抓取采购订单
    
    Args:
        po_numbers: 指定的订单号列表，如 ['CN5123', 'CN5121']
        status_filter: 状态筛选，如 'APPR', 'DRAFT', 'CALLOFF'
        max_pages: 最大页数（当 po_numbers 为 None 时有效）
        page_size: 每页数量（当 po_numbers 为 None 时有效）
        save_to_file: 是否保存到 JSON 文件
    
    Returns:
        list: 采购订单数据列表
    """
    print("\n" + "="*60)
    print("步骤 0: 从 API 抓取数据")
    print("="*60)
    
    try:
        auth = get_maximo_auth()
    except ValueError as e:
        print(f"[ERROR] 认证失败: {e}")
        return []
    
    headers = {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }
    
    all_data = []
    
    # 如果提供了订单号列表，逐个查询
    if po_numbers:
        print(f"[INFO] 查询 {len(po_numbers)} 个指定订单\n")
        
        for po_num in po_numbers:
            po_data = fetch_po_by_number(po_num, save_to_file)
            if po_data:
                all_data.append(po_data)
            time.sleep(REQUEST_DELAY)
    
    # 否则按条件分页查询
    else:
        print(f"[INFO] 分页查询订单")
        if status_filter:
            print(f"  筛选条件: status={status_filter}")
        print(f"  页数: {max_pages}, 每页: {page_size}\n")
        
        for page in range(1, max_pages + 1):
            print(f"  第 {page}/{max_pages} 页...", end=" ", flush=True)
            
            params = {
                'oslc.select': (
                    '*,'
                    'requireddate,'
                    'vendor,vendorname,'
                    'venaddress1,venaddr1,'
                    'venaddress2,venaddr2,'
                    'venzip,venpostalcode,'
                    'vencity,'
                    'vencountry,vennation,'
                    'vencontact,'
                    'venphone,'
                    'venemail,cxpoemail,'
                    'billtocomp,billtoname,'
                    'billtoaddress1,billtoaddr1,'
                    'billtoaddress2,billtoaddr2,'
                    'billtocity,'
                    'billtozip,billtopostalcode,'
                    'billtocountry,'
                    'billtoattn,billtocontact,'
                    'billtophone,'
                    'billtoemail,contactemail,'
                    'shiptoattn,shiptocontact,shiptocomp,'
                    'buyercode,custcode,ourreference'
                ),
                'oslc.pageSize': page_size,
                '_dropnulls': 0,
                'pageno': page,
                'oslc.orderBy': '-statusdate',
            }
            
            if status_filter:
                params['oslc.where'] = f'status="{status_filter}"'
            
            try:
                resp = requests.get(
                    PO_API_URL,
                    headers=headers,
                    params=params,
                    verify=VERIFY_SSL,
                    proxies=settings_manager.get_proxies(),
                    timeout=REQUEST_TIMEOUT
                )
                
                if resp.status_code == 200:
                    if not resp.content:
                        print("认证过期（空响应）")
                        break
                    try:
                        data = resp.json()
                    except Exception:
                        print(f"非JSON响应（认证可能已过期），内容: {resp.text[:100]!r}")
                        break
                    items = data.get('member') or data.get('rdfs:member')
                    
                    if items:
                        # 标准化所有订单数据
                        items = [normalize_po_data(item) for item in items]
                        
                        print(f"✓ {len(items)} 条")
                        all_data.extend(items)
                        
                        # 保存每个订单到单独的 JSON 文件
                        if save_to_file:
                            for item in items:
                                po_num = item.get('ponum')
                                if po_num:
                                    output_file = RAW_DATA_DIR / f"po_{po_num}_detail.json"
                                    with open(output_file, 'w', encoding='utf-8') as f:
                                        json.dump(item, f, indent=2, ensure_ascii=False)
                    else:
                        print("无数据")
                        break
                else:
                    print(f"错误 {resp.status_code}")
                    break
                    
            except requests.exceptions.Timeout:
                print("超时")
                break
            except Exception as e:
                print(f"异常: {e}")
                break
            
            time.sleep(REQUEST_DELAY)
    
    print(f"\n[INFO] 成功抓取 {len(all_data)} 个采购订单")
    return all_data
