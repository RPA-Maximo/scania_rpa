"""
发现 Maximo 接收单相关的 Object Structures (API 端点)
用于入库自动化
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import urllib3
from config import get_maximo_auth, DEFAULT_HEADERS, VERIFY_SSL, PROXIES
from config.settings import MAXIMO_BASE_URL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def search_receipt_endpoints():
    """
    搜索接收单相关的端点
    """
    print("=" * 70)
    print("搜索 Maximo 接收单 (Receipts) 相关 API 端点")
    print("=" * 70)
    
    try:
        auth = get_maximo_auth()
        print(f"✓ 认证信息已加载 (CSRF Token: {auth['csrf_token'][:20]}...)")
    except ValueError as e:
        print(f"[错误] {e}")
        return
    
    # 可能的搜索词
    # RECEIPT = 接收
    # MATREC = Material Receipt (物料接收)
    # INV = Inventory (库存)
    # POR = PO Receipt
    keywords = ['RECEIPT', 'MATREC', 'RECV', 'RECEIVING', 'INV', 'POR']
    
    discovery_url = f"{MAXIMO_BASE_URL}/oslc/os/mxapiobjectstructure"
    
    headers = {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }
    
    # 获取所有 Object Structures
    params = {
        'oslc.select': 'objectstructure,description',
        'oslc.pageSize': 500,
        '_dropnulls': 1,
    }
    
    try:
        print(f"请求: {discovery_url}")
        resp = requests.get(
            discovery_url,
            headers=headers,
            params=params,
            verify=VERIFY_SSL,
            proxies=PROXIES,
            timeout=60
        )
        
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('member') or data.get('rdfs:member') or []
            
            print(f"共有 {len(items)} 个 Object Structures\n")
            
            # 搜索相关端点
            found = []
            for item in items:
                name = item.get('objectstructure', '').upper()
                desc = item.get('description', '').upper()
                
                for kw in keywords:
                    if kw in name or kw in desc:
                        found.append({
                            'name': item.get('objectstructure'),
                            'description': item.get('description'),
                            'keyword': kw
                        })
                        break
            
            if found:
                print(f"找到 {len(found)} 个相关端点:\n")
                # 按关键词分组
                by_keyword = {}
                for ep in found:
                    kw = ep['keyword']
                    if kw not in by_keyword:
                        by_keyword[kw] = []
                    by_keyword[kw].append(ep)
                
                for kw, eps in by_keyword.items():
                    print(f"【{kw}】")
                    for ep in eps:
                        print(f"  ★ {ep['name']:35s}")
                        print(f"    描述: {ep['description']}")
                    print()
                
                # 推荐使用
                print("-" * 70)
                print("推荐优先尝试:")
                priority_keywords = ['MATREC', 'RECEIPT', 'RECV']
                for ep in found:
                    for pk in priority_keywords:
                        if pk in ep['name'].upper():
                            print(f"  → {ep['name']} ({ep['description']})")
                            break
                
                return found
            else:
                print("未找到相关端点")
                print("\n建议手动搜索以下关键词:")
                for kw in keywords:
                    print(f"  - {kw}")
                return []
                
        elif resp.status_code == 401:
            print("✗ 认证失败，请更新 config/响应标头.txt")
            return None
        else:
            print(f"请求失败: {resp.status_code}")
            return None
            
    except Exception as e:
        print(f"异常: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_receipt_endpoint(endpoint_name: str, po_number: str = None):
    """
    测试指定的接收单端点
    
    Args:
        endpoint_name: API端点名称
        po_number: 可选，采购订单号筛选
    """
    print(f"\n{'=' * 70}")
    print(f"测试端点: {endpoint_name}")
    print(f"{'=' * 70}")
    
    try:
        auth = get_maximo_auth()
    except ValueError as e:
        print(f"[错误] {e}")
        return None
    
    api_url = f"{MAXIMO_BASE_URL}/oslc/os/{endpoint_name}"
    
    headers = {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }
    
    params = {
        'oslc.select': '*',
        'oslc.pageSize': 5,
        '_dropnulls': 0,
    }
    
    # 如果指定了PO号, 添加筛选
    if po_number:
        params['oslc.where'] = f'ponum="{po_number}"'
        print(f"查询条件: ponum={po_number}")
    
    try:
        print(f"请求: {api_url}")
        resp = requests.get(
            api_url,
            headers=headers,
            params=params,
            verify=VERIFY_SSL,
            proxies=PROXIES,
            timeout=60
        )
        
        print(f"状态码: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('member') or data.get('rdfs:member') or []
            
            if items:
                print(f"✓ 成功！找到 {len(items)} 条数据\n")
                
                # 显示第一条数据
                item = items[0]
                print("第一条数据字段:")
                for key, value in list(item.items())[:20]:
                    if not key.startswith('_'):
                        print(f"  {key}: {value}")
                
                if len(item) > 20:
                    print(f"  ... 还有 {len(item) - 20} 个字段")
                
                return {
                    'endpoint': endpoint_name,
                    'success': True,
                    'count': len(items),
                    'fields': list(item.keys()),
                    'sample': item
                }
            else:
                print("✗ 端点可用，但未找到数据")
                return {
                    'endpoint': endpoint_name,
                    'success': True,
                    'count': 0
                }
        
        elif resp.status_code == 404:
            print("✗ 端点不存在")
            return None
        elif resp.status_code == 401:
            print("✗ 认证失败")
            return None
        else:
            print(f"✗ 请求失败: {resp.text[:200]}")
            return None
            
    except Exception as e:
        print(f"✗ 异常: {e}")
        return None


if __name__ == "__main__":
    # 1. 先发现相关端点
    endpoints = search_receipt_endpoints()
    
    if endpoints:
        print("\n" + "=" * 70)
        print("测试优先端点")
        print("=" * 70)
        
        # 2. 自动测试找到的端点
        priority = ['MXAPIMATRECTRANS', 'MXAPIRECEIPT', 'MXMATRECTRANS']
        for ep in endpoints:
            if any(p in ep['name'].upper() for p in priority):
                test_receipt_endpoint(ep['name'])
                break
