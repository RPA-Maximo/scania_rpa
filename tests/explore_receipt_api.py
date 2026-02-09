"""
深度探索 Maximo REST API
1. 使用 apimeta 端点发现可用API
2. 测试 MXAPIPO 中的物料接收相关操作
3. 尝试直接 POST 到 MXAPIRECEIPT
"""
import sys
import json
sys.path.insert(0, '.')
import requests
import urllib3
from config import get_maximo_auth, DEFAULT_HEADERS, PROXIES
from config.settings import MAXIMO_BASE_URL, RAW_DATA_DIR

urllib3.disable_warnings()


def get_auth_headers():
    auth = get_maximo_auth()
    return {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token']
    }, auth['csrf_token']


def test_api_meta():
    """测试 /oslc/apimeta 端点 - 获取所有可用API列表"""
    print("=" * 60)
    print("1. 测试 /oslc/apimeta 端点")
    print("=" * 60)
    
    headers, _ = get_auth_headers()
    url = f'{MAXIMO_BASE_URL}/oslc/apimeta'
    
    print(f'请求: {url}')
    resp = requests.get(url, headers=headers, verify=False, proxies=PROXIES, timeout=60)
    print(f'状态码: {resp.status_code}')
    
    if resp.status_code == 200:
        data = resp.json()
        # 保存完整数据
        output = RAW_DATA_DIR / 'apimeta.json'
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'已保存到: {output}')
        
        # 分析响应结构
        if isinstance(data, dict):
            print(f'\n响应字段: {list(data.keys())}')
            
            # 搜索 receipt 相关
            receipt_apis = []
            for key, value in data.items():
                if 'receipt' in str(key).lower() or 'receipt' in str(value).lower():
                    receipt_apis.append((key, value))
            
            if receipt_apis:
                print(f'\n找到 {len(receipt_apis)} 个 receipt 相关 API:')
                for k, v in receipt_apis[:10]:
                    print(f'  {k}: {str(v)[:100]}')
        
        return data
    else:
        print(f'失败: {resp.text[:300]}')
        return None


def test_po_receipt_operations():
    """测试通过 MXAPIPO 获取接收相关信息"""
    print("\n" + "=" * 60)
    print("2. 测试 MXAPIPO 中的接收相关字段")
    print("=" * 60)
    
    headers, _ = get_auth_headers()
    
    # 获取一个PO的详细信息，包括接收相关字段
    url = f'{MAXIMO_BASE_URL}/oslc/os/MXAPIPO'
    params = {
        'lean': 1,
        'oslc.select': 'ponum,status,receipts,matrectrans,poline',
        'oslc.pageSize': 1,
        'oslc.where': 'status="APPR"'  # 只看已批准的PO
    }
    
    print(f'请求: {url}')
    resp = requests.get(url, headers=headers, params=params, verify=False, proxies=PROXIES, timeout=60)
    print(f'状态码: {resp.status_code}')
    
    if resp.status_code == 200:
        data = resp.json()
        members = data.get('member', [])
        if members:
            print(f'\n找到 {len(members)} 个PO')
            po = members[0]
            print(f'PO字段: {list(po.keys())}')
            
            # 保存详情
            output = RAW_DATA_DIR / 'po_with_receipts.json'
            with open(output, 'w', encoding='utf-8') as f:
                json.dump(po, f, ensure_ascii=False, indent=2)
            print(f'已保存到: {output}')
            
            return po
    else:
        print(f'失败: {resp.text[:300]}')
    return None


def test_more_endpoints():
    """测试更多可能的端点"""
    print("\n" + "=" * 60)
    print("3. 测试更多可能的 Object Structures")
    print("=" * 60)
    
    headers, _ = get_auth_headers()
    
    endpoints = [
        'MXAPIMATRECTRANS',   # Material Receipt Transaction
        'MXMATRECTRANS',      # Mat Rec Trans (非API版)
        'MXAPIPORECEIPT',     # PO Receipt
        'MXAPIRECEIVING',     # Receiving
        'MXAPIPUR',           # Purchasing
        'MXAPIPOLINE',        # PO Line
        'MXAPIINVTRANS',      # Inventory Transaction
        'MXAPIITEM',          # Item Master
    ]
    
    results = []
    for ep in endpoints:
        url = f'{MAXIMO_BASE_URL}/oslc/os/{ep}'
        try:
            resp = requests.get(
                url, 
                headers=headers, 
                params={'lean': 1, 'oslc.pageSize': 1},
                verify=False, 
                proxies=PROXIES, 
                timeout=30
            )
            
            if resp.status_code == 200:
                data = resp.json()
                count = data.get('responseInfo', {}).get('totalCount', 0)
                print(f'  ✓ {ep:25s} 可用 (数据: {count} 条)')
                results.append({'endpoint': ep, 'status': 'ok', 'count': count})
            elif resp.status_code == 404:
                print(f'  ✗ {ep:25s} 不存在')
            else:
                print(f'  ? {ep:25s} {resp.status_code}')
                
        except Exception as e:
            print(f'  ! {ep:25s} 异常: {str(e)[:30]}')
    
    return results


def try_post_receipt():
    """尝试 POST 到 MXAPIRECEIPT 创建接收"""
    print("\n" + "=" * 60)
    print("4. 尝试 POST 创建接收单 (测试)")
    print("=" * 60)
    
    headers, csrf = get_auth_headers()
    headers['Content-Type'] = 'application/json'
    
    url = f'{MAXIMO_BASE_URL}/oslc/os/MXAPIRECEIPT'
    
    # 最小化的 POST 请求体 (用于探测API是否支持创建)
    # 这个请求会失败,但错误信息可以告诉我们需要什么字段
    test_payload = {
        'ponum': 'TEST123',
        'siteid': 'CN'
    }
    
    print(f'POST: {url}')
    print(f'Payload: {test_payload}')
    
    try:
        resp = requests.post(
            url,
            headers=headers,
            json=test_payload,
            params={'lean': 1},
            verify=False,
            proxies=PROXIES,
            timeout=30
        )
        
        print(f'状态码: {resp.status_code}')
        print(f'响应: {resp.text[:500]}')
        
        # 即使失败,错误信息也很有价值
        if resp.status_code in [400, 500]:
            print('\n分析错误信息可能告诉我们需要哪些字段...')
            
    except Exception as e:
        print(f'异常: {e}')


if __name__ == "__main__":
    # 1. 获取API元数据
    test_api_meta()
    
    # 2. 测试PO中的接收字段
    test_po_receipt_operations()
    
    # 3. 测试更多端点
    test_more_endpoints()
    
    # 4. 尝试POST (注释掉避免意外创建数据)
    # try_post_receipt()
    
    print("\n" + "=" * 60)
    print("探索完成! 请查看 data/raw/ 目录下的输出文件")
    print("=" * 60)
