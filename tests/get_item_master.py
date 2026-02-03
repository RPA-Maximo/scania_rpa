"""
Maximo 物料主数据爬虫
从 MXAPIITEM API 抓取物料主数据
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

# 物料主数据 API 端点
ITEM_MASTER_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIITEM"


def scrape_item_master(
    max_pages: int = 3,
    page_size: int = 20,
    where_clause: str = None,
    order_by: str = '+itemnum'
):
    """
    抓取物料主数据
    
    Args:
        max_pages: 最大抓取页数
        page_size: 每页数据量
        where_clause: 筛选条件，例如 'status="ACTIVE"'
        order_by: 排序字段，例如 '+itemnum' (升序) 或 '-itemnum' (降序)
    """
    print(">>> 启动物料主数据爬虫...")
    print(f">>> API: {ITEM_MASTER_API_URL}")
    if PROXIES:
        print(f">>> 代理: {PROXIES['https']}")
    
    # 获取认证信息
    try:
        auth = get_maximo_auth()
    except ValueError as e:
        print(f"[错误] {e}")
        return
    
    # 构建请求头
    headers = {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }

    all_data = []
    
    for page in range(1, max_pages + 1):
        print(f"\n正在请求第 {page} 页...", end="")
        
        # 构建请求参数
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
                data_json = resp.json()
                items = data_json.get('member') or data_json.get('rdfs:member')
                
                if items:
                    print(f" 成功! 抓到 {len(items)} 条数据")
                    
                    # 显示第一条数据的关键信息
                    if page == 1 and items:
                        first_item = items[0]
                        print(f"   -> 第一条: {first_item.get('itemnum')} - {first_item.get('description')}")
                    
                    all_data.extend(items)
                else:
                    print(" 数据为空，停止抓取。")
                    break
                    
            elif resp.status_code == 401:
                print("\n[错误] Token 过期，请更新 config/响应标头.txt")
                break
            else:
                print(f"\n[失败] 状态码 {resp.status_code}")
                print(f"响应: {resp.text[:200]}")
                break
                
        except Exception as e:
            print(f"\n[异常] {e}")
            break
            
        time.sleep(REQUEST_DELAY)

    # 保存数据
    if all_data:
        df = pd.DataFrame(all_data)
        
        # 生成带时间戳的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"item_master_{timestamp}.xlsx"
        filepath = RAW_DATA_DIR / filename
        
        df.to_excel(filepath, index=False)
        
        print(f"\n{'='*60}")
        print(f"✓ 成功！")
        print(f"{'='*60}")
        print(f"保存路径: {filepath}")
        print(f"数据总量: {len(all_data)} 条")
        print(f"字段数量: {len(df.columns)} 个")
        print(f"\n主要字段:")
        key_fields = ['itemnum', 'description', 'status', 'itemtype', 'itemsetid']
        for field in key_fields:
            if field in df.columns:
                print(f"  - {field}")
        
        return filepath
    else:
        print("\n[警告] 未获取到任何数据")
        return None


def scrape_by_item_list(item_numbers: list):
    """
    根据物料编号列表抓取数据
    
    Args:
        item_numbers: 物料编号列表，例如 ['00006928', '00006929']
    """
    print(f">>> 根据物料编号列表抓取 ({len(item_numbers)} 个物料)...")
    
    # 获取认证信息
    try:
        auth = get_maximo_auth()
    except ValueError as e:
        print(f"[错误] {e}")
        return
    
    headers = {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }
    
    all_data = []
    
    for i, item_num in enumerate(item_numbers, 1):
        print(f"[{i}/{len(item_numbers)}] 查询物料: {item_num}...", end="")
        
        params = {
            'oslc.select': '*',
            'oslc.where': f'itemnum="{item_num}"',
            '_dropnulls': 0,
        }
        
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
                data_json = resp.json()
                items = data_json.get('member') or data_json.get('rdfs:member')
                
                if items:
                    print(f" ✓ 找到")
                    all_data.extend(items)
                else:
                    print(f" ✗ 未找到")
            else:
                print(f" ✗ 错误 {resp.status_code}")
                
        except Exception as e:
            print(f" ✗ 异常: {e}")
        
        time.sleep(REQUEST_DELAY)
    
    # 保存数据
    if all_data:
        df = pd.DataFrame(all_data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"item_master_list_{timestamp}.xlsx"
        filepath = RAW_DATA_DIR / filename
        df.to_excel(filepath, index=False)
        
        print(f"\n✓ 成功保存 {len(all_data)} 条数据到: {filepath}")
        return filepath
    else:
        print("\n✗ 未获取到任何数据")
        return None


if __name__ == "__main__":
    # 示例1: 抓取前3页的 ACTIVE 状态物料
    print("="*60)
    print("示例1: 抓取 ACTIVE 状态的物料")
    print("="*60)
    scrape_item_master(
        max_pages=3,
        page_size=20,
        where_clause='status="ACTIVE"',
        order_by='+itemnum'
    )
    
    # 示例2: 根据物料编号列表抓取
    # print("\n" + "="*60)
    # print("示例2: 根据物料编号列表抓取")
    # print("="*60)
    # item_list = ['00006928', '00006929', '00006930']
    # scrape_by_item_list(item_list)
