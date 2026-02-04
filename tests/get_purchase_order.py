"""
Maximo 采购订单爬虫
从 MXAPIPO API 抓取采购订单数据
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import pandas as pd
import urllib3
import time
from datetime import datetime

from config import (
    get_maximo_auth,
    DEFAULT_HEADERS,
    REQUEST_DELAY,
    VERIFY_SSL,
    RAW_DATA_DIR,
    PROXIES
)
from config.settings import MAXIMO_BASE_URL

# 禁用安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 采购订单 API 端点 (可能的端点名称)
POSSIBLE_ENDPOINTS = [
    "MXAPIPO",           # Purchase Order
    "MXPO",              # PO 简写
    "MXAPIPR",           # Purchase Requisition
    "MXAPIPURCHORDER",   # 完整命名
]


def test_po_endpoints():
    """
    测试可能的采购订单 API 端点
    """
    print("="*60)
    print("测试 Purchase Order API 端点")
    print("="*60)
    
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
    
    working_endpoints = []
    
    for endpoint in POSSIBLE_ENDPOINTS:
        api_url = f"{MAXIMO_BASE_URL}/oslc/os/{endpoint}"
        print(f"\n测试端点: {endpoint}")
        print(f"  URL: {api_url}")
        
        params = {
            'oslc.select': '*',
            'oslc.pageSize': 3,
            '_dropnulls': 0,
        }
        
        try:
            resp = requests.get(
                api_url,
                headers=headers,
                params=params,
                verify=VERIFY_SSL,
                proxies=PROXIES,
                timeout=30
            )
            
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('member') or data.get('rdfs:member') or []
                
                if items:
                    print(f"  ✓ 成功! 找到 {len(items)} 条数据")
                    
                    # 显示第一条数据的关键字段
                    first = items[0]
                    print(f"  第一条数据:")
                    
                    # 尝试显示常见的 PO 字段
                    po_fields = ['ponum', 'description', 'status', 'statusdate', 
                                 'orderdate', 'vendor', 'totalcost']
                    for field in po_fields:
                        if field in first:
                            print(f"    - {field}: {first[field]}")
                    
                    working_endpoints.append({
                        'endpoint': endpoint,
                        'url': api_url,
                        'sample': items[0]
                    })
                else:
                    print(f"  ✗ 无数据")
                    
            elif resp.status_code == 404:
                print(f"  ✗ 端点不存在")
            elif resp.status_code == 401:
                print(f"  ✗ 认证失败，请更新 Cookie")
                break
            else:
                print(f"  ✗ 错误 {resp.status_code}")
                
        except Exception as e:
            print(f"  ✗ 异常: {e}")
        
        time.sleep(0.5)
    
    return working_endpoints


def get_po_by_number(po_number: str, endpoint: str = "MXAPIPO"):
    """
    根据采购订单号查询单个订单
    
    Args:
        po_number: 采购订单号，如 'CN5123'
        endpoint: API 端点名称
    """
    print(f"\n查询采购订单: {po_number}")
    print("="*60)
    
    try:
        auth = get_maximo_auth()
    except ValueError as e:
        print(f"[错误] {e}")
        return None
    
    api_url = f"{MAXIMO_BASE_URL}/oslc/os/{endpoint}"
    
    headers = {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }
    
    params = {
        'oslc.select': '*',
        'oslc.where': f'ponum="{po_number}"',
        '_dropnulls': 0,
    }
    
    try:
        if PROXIES:
            print(f"使用代理: {PROXIES['https']}")
        
        resp = requests.get(
            api_url,
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
                po = items[0]
                print(f"✓ 找到采购订单\n")
                
                # 显示所有字段
                print("订单字段:")
                for key, value in po.items():
                    if value is not None and value != '' and not key.startswith('_'):
                        print(f"  {key}: {value}")
                
                return po
            else:
                print(f"✗ 未找到订单: {po_number}")
                return None
                
        elif resp.status_code == 401:
            print("✗ 认证失败，请更新 Cookie")
            return None
        else:
            print(f"✗ 请求失败: {resp.status_code}")
            print(f"响应: {resp.text[:200]}")
            return None
            
    except Exception as e:
        print(f"✗ 异常: {e}")
        return None


def scrape_po_list(
    po_numbers: list = None,
    status_filter: str = None,
    max_pages: int = 1,
    page_size: int = 20,
    endpoint: str = "MXAPIPO"
):
    """
    抓取采购订单列表
    
    Args:
        po_numbers: 指定的订单号列表，如 ['CN5123', 'CN5121']
        status_filter: 状态筛选，如 'APPR' 或 'DRAFT'
        max_pages: 最大页数
        page_size: 每页数量
        endpoint: API 端点
    """
    print("="*60)
    print("抓取采购订单列表")
    print("="*60)
    
    try:
        auth = get_maximo_auth()
    except ValueError as e:
        print(f"[错误] {e}")
        return None
    
    api_url = f"{MAXIMO_BASE_URL}/oslc/os/{endpoint}"
    
    headers = {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }
    
    all_data = []
    
    # 如果提供了订单号列表，逐个查询
    if po_numbers:
        print(f"查询 {len(po_numbers)} 个指定订单...")
        for i, po_num in enumerate(po_numbers, 1):
            print(f"[{i}/{len(po_numbers)}] 查询: {po_num}...", end="")
            
            params = {
                'oslc.select': '*',
                'oslc.where': f'ponum="{po_num}"',
                '_dropnulls': 0,
            }
            
            try:
                resp = requests.get(
                    api_url,
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
                        print(f" ✓")
                        all_data.extend(items)
                    else:
                        print(f" ✗ 未找到")
                else:
                    print(f" ✗ 错误 {resp.status_code}")
                    
            except Exception as e:
                print(f" ✗ {e}")
            
            time.sleep(REQUEST_DELAY)
    
    # 否则按条件分页查询
    else:
        for page in range(1, max_pages + 1):
            print(f"请求第 {page} 页...", end="")
            
            params = {
                'oslc.select': '*',
                'oslc.pageSize': page_size,
                '_dropnulls': 0,
                'pageno': page,
                'oslc.orderBy': '-statusdate',  # 按状态日期降序
            }
            
            if status_filter:
                params['oslc.where'] = f'status="{status_filter}"'
            
            try:
                resp = requests.get(
                    api_url,
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
                        print(f" ✓ 获取 {len(items)} 条")
                        all_data.extend(items)
                    else:
                        print(" 无数据，停止")
                        break
                else:
                    print(f" ✗ 错误 {resp.status_code}")
                    break
                    
            except Exception as e:
                print(f" ✗ {e}")
                break
            
            time.sleep(REQUEST_DELAY)
    
    # 保存数据
    if all_data:
        df = pd.DataFrame(all_data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"purchase_orders_{timestamp}.xlsx"
        filepath = RAW_DATA_DIR / filename
        df.to_excel(filepath, index=False)
        
        print(f"\n{'='*60}")
        print(f"✓ 成功保存 {len(all_data)} 条采购订单")
        print(f"文件: {filepath}")
        print(f"字段数: {len(df.columns)}")
        
        return filepath
    else:
        print("\n✗ 未获取到数据")
        return None


if __name__ == "__main__":
    # 第一步：测试 API 端点
    print("\n" + "="*60)
    print("步骤1: 测试可用的 API 端点")
    print("="*60)
    
    endpoints = test_po_endpoints()
    
    if endpoints:
        print(f"\n✓ 找到 {len(endpoints)} 个可用端点")
        recommended = endpoints[0]['endpoint']
        print(f"推荐使用: {recommended}")
        
        # 第二步：查询特定订单 (从截图中的订单号)
        print("\n" + "="*60)
        print("步骤2: 查询特定采购订单")
        print("="*60)
        
        # 使用截图中看到的订单号测试
        test_po = "CN5123"
        get_po_by_number(test_po, endpoint=recommended)
        
    else:
        print("\n✗ 未找到可用的端点")
        print("请在浏览器 F12 中查找包含 'oslc/os/' 的请求来确定正确的端点名称")
