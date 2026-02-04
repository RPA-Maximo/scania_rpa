"""
Maximo 采购订单爬虫
从 MXAPIPO API 抓取采购订单数据
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import pandas as pd
import urllib3
import json
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

# 采购订单 API 端点 (已确认可用)
PO_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIPO"

# 请求超时（网站响应较慢）
REQUEST_TIMEOUT = 120


def get_po_by_number(po_number: str):
    """
    根据采购订单号查询单个订单
    
    Args:
        po_number: 采购订单号，如 'CN5123'
    
    Returns:
        dict: 订单数据，失败返回 None
    """
    print(f"\n查询采购订单: {po_number}")
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
    
    params = {
        'oslc.select': '*',
        'oslc.where': f'ponum="{po_number}"',
        '_dropnulls': 0,
    }
    
    try:
        if PROXIES:
            print(f"使用代理: {PROXIES['https']}")
        print("请求中，请耐心等待...")
        
        start_time = time.time()
        resp = requests.get(
            PO_API_URL,
            headers=headers,
            params=params,
            verify=VERIFY_SSL,
            proxies=PROXIES,
            timeout=REQUEST_TIMEOUT
        )
        
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('member') or data.get('rdfs:member')
            
            if items:
                po = items[0]
                elapsed = time.time() - start_time
                print(f"[OK] 找到采购订单: {po_number} (耗时: {elapsed:.1f}秒)\n")
                
                # 显示关键字段
                key_fields = ['ponum', 'description', 'status', 'statusdate', 
                              'vendor', 'totalcost', 'orderdate']
                print("关键信息:")
                for field in key_fields:
                    if field in po and po[field]:
                        print(f"  {field}: {po[field]}")
                
                # 保存到 JSON
                output_file = RAW_DATA_DIR / f"po_{po_number}_detail.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(po, f, indent=2, ensure_ascii=False)
                print(f"\n完整数据已保存到: {output_file}")
                print(f"总字段数: {len(po)}")
                
                return po
            else:
                elapsed = time.time() - start_time
                print(f"[FAIL] 未找到订单: {po_number} (耗时: {elapsed:.1f}秒)")
                return None
                
        elif resp.status_code == 401:
            print("[FAIL] 认证失败，请更新 响应标头.txt")
            return None
        else:
            print(f"[FAIL] 请求失败: {resp.status_code}")
            print(f"响应: {resp.text[:200]}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"[FAIL] 请求超时 ({REQUEST_TIMEOUT}秒)")
        return None
    except Exception as e:
        print(f"[FAIL] 异常: {e}")
        return None


def scrape_po_list(
    po_numbers: list = None,
    status_filter: str = None,
    max_pages: int = 1,
    page_size: int = 20
):
    """
    抓取采购订单列表
    
    Args:
        po_numbers: 指定的订单号列表，如 ['CN5123', 'CN5121']
        status_filter: 状态筛选，如 'APPR', 'DRAFT', 'CALLOFF'
        max_pages: 最大页数
        page_size: 每页数量
    
    Returns:
        Path: 保存的文件路径，失败返回 None
    """
    print("="*60)
    print("抓取采购订单列表")
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
    
    all_data = []
    
    # 如果提供了订单号列表，逐个查询
    if po_numbers:
        print(f"查询 {len(po_numbers)} 个指定订单...\n")
        for i, po_num in enumerate(po_numbers, 1):
            print(f"[{i}/{len(po_numbers)}] 查询: {po_num}...", end=" ", flush=True)
            
            params = {
                'oslc.select': '*',
                'oslc.where': f'ponum="{po_num}"',
                '_dropnulls': 0,
            }
            
            try:
                resp = requests.get(
                    PO_API_URL,
                    headers=headers,
                    params=params,
                    verify=VERIFY_SSL,
                    proxies=PROXIES,
                    timeout=REQUEST_TIMEOUT
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get('member') or data.get('rdfs:member')
                    if items:
                        print("OK")
                        all_data.extend(items)
                    else:
                        print("未找到")
                else:
                    print(f"错误 {resp.status_code}")
                    
            except requests.exceptions.Timeout:
                print("超时")
            except Exception as e:
                print(f"{e}")
            
            time.sleep(REQUEST_DELAY)
    
    # 否则按条件分页查询
    else:
        for page in range(1, max_pages + 1):
            print(f"请求第 {page} 页...", end=" ", flush=True)
            
            params = {
                'oslc.select': '*',
                'oslc.pageSize': page_size,
                '_dropnulls': 0,
                'pageno': page,
                'oslc.orderBy': '-statusdate',  # 按状态日期降序
            }
            
            if status_filter:
                params['oslc.where'] = f'status="{status_filter}"'
                print(f"(筛选: status={status_filter})", end=" ")
            
            try:
                resp = requests.get(
                    PO_API_URL,
                    headers=headers,
                    params=params,
                    verify=VERIFY_SSL,
                    proxies=PROXIES,
                    timeout=REQUEST_TIMEOUT
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get('member') or data.get('rdfs:member')
                    
                    if items:
                        print(f"获取 {len(items)} 条")
                        all_data.extend(items)
                    else:
                        print("无数据，停止")
                        break
                else:
                    print(f"错误 {resp.status_code}")
                    break
                    
            except requests.exceptions.Timeout:
                print("超时")
                break
            except Exception as e:
                print(f"{e}")
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
        print(f"[OK] 成功保存 {len(all_data)} 条采购订单")
        print(f"文件: {filepath}")
        print(f"字段数: {len(df.columns)}")
        
        return filepath
    else:
        print("\n[FAIL] 未获取到数据")
        return None


if __name__ == "__main__":
    # 示例1: 查询单个订单
    print("\n" + "="*60)
    print("示例: 查询单个采购订单")
    print("="*60)
    
    # 使用截图中看到的订单号
    get_po_by_number("CN5123")
