"""
直接测试常见的接收单API端点
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


# 常见的 Maximo 接收单相关 Object Structures
RECEIPT_ENDPOINTS = [
    # OSLC API 标准端点
    "MXAPIMATRECTRANS",      # Material Receipt Transaction
    "MXAPIRECEIPT",          # Receipt
    "MXAPIMATRECEIPT",       # Material Receipt
    "MXMATRECTRANS",         # Material Receipt Trans (非API版)
    "MXRECEIPT",
    "MXAPIPORECEIPT",        # PO Receipt
    "MXAPIRECEIVING",        # Receiving
    # 库存相关
    "MXAPIINVENTORY",        # Inventory (已知可用)
    "MXAPIINVBALANCES",      # Inventory Balances
    # 采购订单行
    "MXAPIPOLINE",           # PO Line
    "MXAPIPOLINECOST",       # PO Line Cost
]


def test_endpoint(endpoint_name: str):
    """测试单个端点"""
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
        'oslc.pageSize': 1,
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
            count = len(items)
            if items:
                # 获取字段列表
                fields = [k for k in items[0].keys() if not k.startswith('_')]
                return {
                    'status': 'OK',
                    'count': count,
                    'fields': fields[:10],  # 只显示前10个字段
                    'sample': {k: v for k, v in list(items[0].items())[:5]}
                }
            else:
                return {'status': 'OK (空)', 'count': 0}
        elif resp.status_code == 404:
            return {'status': '不存在'}
        elif resp.status_code == 401:
            return {'status': '401认证失败'}
        else:
            return {'status': f'错误 {resp.status_code}'}
            
    except Exception as e:
        return {'status': f'异常: {str(e)[:30]}'}


def main():
    print("=" * 70)
    print("Maximo 接收单相关 API 端点测试")
    print("=" * 70)
    print()
    
    results = []
    
    for endpoint in RECEIPT_ENDPOINTS:
        print(f"测试 {endpoint:25s} ... ", end="", flush=True)
        result = test_endpoint(endpoint)
        
        if result:
            status = result.get('status', '未知')
            if status == 'OK':
                count = result.get('count', 0)
                fields = result.get('fields', [])
                print(f"✓ {status} (数据: {count} 条)")
                print(f"    字段: {', '.join(fields[:5])}...")
                results.append({
                    'endpoint': endpoint,
                    'available': True,
                    **result
                })
            elif status == 'OK (空)':
                print(f"✓ {status}")
                results.append({
                    'endpoint': endpoint,
                    'available': True,
                    **result
                })
            else:
                print(f"✗ {status}")
    
    # 总结
    print()
    print("=" * 70)
    print("可用端点总结")
    print("=" * 70)
    
    available = [r for r in results if r.get('available')]
    if available:
        print(f"\n找到 {len(available)} 个可用端点:\n")
        for ep in available:
            print(f"  ★ {ep['endpoint']}")
            if ep.get('fields'):
                print(f"    字段: {', '.join(ep['fields'])}")
    else:
        print("\n未找到可用的接收单端点")
        print("\n建议:")
        print("  1. 检查 Maximo 是否开放了接收单的 OSLC API")
        print("  2. 联系管理员获取可用的 Object Structure 名称")
        print("  3. 使用浏览器开发者工具抓取实际的 API 请求")


if __name__ == "__main__":
    main()
