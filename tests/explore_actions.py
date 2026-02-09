"""
探索 MXAPIPO 的 Actions 和 MATRECTRANS 相关
看能否找到接收操作的API入口
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


def test_mxapipo_actions():
    """测试 MXAPIPO 的可用 actions"""
    print("=" * 60)
    print("1. 查询 MXAPIPO 的可用 Actions")
    print("=" * 60)
    
    headers, _ = get_auth_headers()
    
    # 获取PO的详情，看是否有 _action 字段
    po_file = RAW_DATA_DIR / 'po_with_receipts.json'
    with open(po_file, 'r', encoding='utf-8') as f:
        po_data = json.load(f)
    
    po_href = po_data.get('href', '')
    print(f'PO href: {po_href}')
    
    # 尝试获取 PO 的 actions
    po_url = f'{MAXIMO_BASE_URL}/{po_href}'
    params = {'lean': 1}
    
    # 1. 先获取完整的PO数据看是否有action属性
    resp = requests.get(po_url, headers=headers, params=params, verify=False, proxies=PROXIES, timeout=30)
    print(f'GET PO 状态码: {resp.status_code}')
    
    if resp.status_code == 200:
        data = resp.json()
        # 查找 action 相关的字段
        action_fields = [k for k in data.keys() if 'action' in k.lower() or 'rel' in k.lower()]
        print(f'action相关字段: {action_fields}')
        
        # 保存完整数据
        output = RAW_DATA_DIR / 'po_full_detail.json'
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'已保存到: {output}')
    else:
        print(f'失败: {resp.text[:300]}')


def test_actions_endpoint():
    """测试 /oslc/actions 端点"""
    print("\n" + "=" * 60)
    print("2. 查询 /oslc/actions 端点")
    print("=" * 60)
    
    headers, _ = get_auth_headers()
    
    url = f'{MAXIMO_BASE_URL}/oslc/actions'
    print(f'请求: {url}')
    
    resp = requests.get(url, headers=headers, verify=False, proxies=PROXIES, timeout=30)
    print(f'状态码: {resp.status_code}')
    
    if resp.status_code == 200:
        data = resp.json()
        output = RAW_DATA_DIR / 'oslc_actions.json'
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'已保存到: {output}')
        
        # 搜索 receipt 相关
        text = json.dumps(data)
        if 'receipt' in text.lower():
            print('✓ 发现 receipt 相关 action!')
    else:
        print(f'响应 ({resp.status_code}): {resp.text[:300]}')


def test_matrectrans():
    """测试 MATRECTRANS 相关端点"""
    print("\n" + "=" * 60)
    print("3. 测试 MATRECTRANS 相关端点")
    print("=" * 60)
    
    headers, _ = get_auth_headers()
    
    # 尝试不同的端点名称
    endpoints = [
        'MXMATRECTRANS',
        'MATRECTRANS',
        'MX_MATRECTRANS',
        'MXAPIMATRECTRANS',
        'MXAPITRANSACTION',
        'MXINVTRANS',
        'MX_INVTRANS',
    ]
    
    for ep in endpoints:
        url = f'{MAXIMO_BASE_URL}/oslc/os/{ep}'
        try:
            resp = requests.get(
                url, 
                headers=headers, 
                params={'lean': 1, 'oslc.pageSize': 1},
                verify=False, 
                proxies=PROXIES, 
                timeout=20
            )
            
            if resp.status_code == 200:
                data = resp.json()
                count = data.get('responseInfo', {}).get('totalCount', 0)
                print(f'  ✓ {ep:25s} 可用 (数据: {count} 条)')
            elif resp.status_code == 404:
                print(f'  ✗ {ep:25s} 不存在')
            else:
                print(f'  ? {ep:25s} {resp.status_code}')
                
        except Exception as e:
            print(f'  ! {ep:25s} 异常: {str(e)[:30]}')


def search_apimeta_for_trans():
    """在 apimeta 中搜索 transaction 相关"""
    print("\n" + "=" * 60)
    print("4. 在 apimeta 中搜索 transaction 相关")
    print("=" * 60)
    
    apimeta_file = RAW_DATA_DIR / 'apimeta.json'
    with open(apimeta_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 搜索 trans, inv, rec 相关
    keywords = ['trans', 'inv', 'rec', 'mat']
    
    results = []
    for item in data:
        name = item.get('osName', '')
        title = item.get('title', '')
        for kw in keywords:
            if kw in name.lower() or kw in title.lower():
                results.append((name, title))
                break
    
    print(f'找到 {len(results)} 个相关 API:')
    for name, title in results[:15]:
        print(f'  {name:30s} - {title}')


def test_invoke_action():
    """尝试对 PO 调用 action"""
    print("\n" + "=" * 60)
    print("5. 尝试调用 PO 上的 Action")
    print("=" * 60)
    
    headers, _ = get_auth_headers()
    
    po_file = RAW_DATA_DIR / 'po_with_receipts.json'
    with open(po_file, 'r', encoding='utf-8') as f:
        po_data = json.load(f)
    
    po_href = po_data.get('href', '')
    
    # 尝试 OPTIONS 请求看支持哪些方法
    po_url = f'{MAXIMO_BASE_URL}/{po_href}'
    
    # 尝试 POST 到 PO 看需要什么参数
    print(f'测试 POST 到: {po_url}')
    
    # 添加 x-method-override 头来模拟不同的 action
    test_headers = {**headers, 'Content-Type': 'application/json'}
    
    # 不实际执行，只打印信息
    print('\n按照 Maximo REST API 规范:')
    print('  - 执行 action 需要 POST 到 resource + action 参数')
    print('  - 格式: POST /oslc/os/MXAPIPO/{id}?action=wsmethod:RECEIVE')
    print('  - 或者 POST 请求体中包含 _action 字段')


if __name__ == "__main__":
    test_mxapipo_actions()
    test_actions_endpoint()
    test_matrectrans()
    search_apimeta_for_trans()
    test_invoke_action()
    
    print("\n" + "=" * 60)
    print("探索完成!")
    print("=" * 60)
