"""
测试可能用于入库操作的 API 端点
"""
import sys
import json
sys.path.insert(0, '.')
import requests
import urllib3
from config import get_maximo_auth, DEFAULT_HEADERS, PROXIES
from config.settings import MAXIMO_BASE_URL, RAW_DATA_DIR

urllib3.disable_warnings()


def test_receipt_endpoints():
    """测试可能用于入库的端点"""
    auth = get_maximo_auth()
    headers = {
        **DEFAULT_HEADERS, 
        'Cookie': auth['cookie'], 
        'x-csrf-token': auth['csrf_token']
    }
    
    # 潜在的入库相关端点
    endpoints = [
        'OSLCMATRECTRANS',
        'REP_RECEIPT', 
        'CXAPIMATUSETRANS',
        'CXMATUSETRANS',
        'MXAPIINVRES',
        'CXAPIINVENTORY',
        'MXL_INVTRANS',
    ]
    
    print("=" * 60)
    print("测试入库相关端点")
    print("=" * 60)
    
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
                count = data.get('responseInfo', {}).get('totalCount', 'N/A')
                member = data.get('member', [])
                print(f'\n✓ {ep}: {count} 条记录')
                if member:
                    keys = list(member[0].keys())[:15]
                    print(f'  字段: {keys}')
                    # 保存样例数据
                    output = RAW_DATA_DIR / f'{ep.lower()}_sample.json'
                    with open(output, 'w', encoding='utf-8') as f:
                        json.dump(member[0], f, ensure_ascii=False, indent=2)
                    print(f'  已保存样例到: {output.name}')
            elif resp.status_code == 400:
                err = resp.json() if resp.text else {}
                msg = err.get('Error', {}).get('message', resp.text[:100])
                print(f'\n✗ {ep}: 400 - {msg}')
            else:
                print(f'\n✗ {ep}: {resp.status_code}')
                
        except Exception as e:
            print(f'\n! {ep}: 异常 - {str(e)[:50]}')


def test_po_actions():
    """测试 PO 上可用的 actions"""
    auth = get_maximo_auth()
    headers = {
        **DEFAULT_HEADERS, 
        'Cookie': auth['cookie'], 
        'x-csrf-token': auth['csrf_token'],
        'Content-Type': 'application/json'
    }
    
    print("\n" + "=" * 60)
    print("测试 PO 上可调用的 Actions")
    print("=" * 60)
    
    # 获取一个待接收的 PO
    po_url = f'{MAXIMO_BASE_URL}/oslc/os/MXAPIPO'
    params = {
        'lean': 1,
        'oslc.where': 'receipts="NONE" or receipts="PARTIAL"',
        'oslc.select': 'ponum,status,receipts,href',
        'oslc.pageSize': 1
    }
    
    resp = requests.get(po_url, headers=headers, params=params, 
                       verify=False, proxies=PROXIES, timeout=30)
    
    if resp.status_code == 200:
        data = resp.json()
        if data.get('member'):
            po = data['member'][0]
            print(f"测试 PO: {po.get('ponum')}, 状态: {po.get('status')}, 接收: {po.get('receipts')}")
            
            # 尝试获取 PO 的 schema 看有没有 actions
            po_href = po.get('href', '').replace('http://childkey#', '')
            if po_href:
                schema_url = f'{MAXIMO_BASE_URL}/{po_href}?oslc.properties=*&oslc.meta=true'
                resp = requests.get(schema_url, headers=headers, 
                                   verify=False, proxies=PROXIES, timeout=30)
                if resp.status_code == 200:
                    po_data = resp.json()
                    action_keys = [k for k in po_data.keys() if 'action' in k.lower()]
                    if action_keys:
                        print(f"  发现 action 相关字段: {action_keys}")
                    
                    # 保存完整数据
                    output = RAW_DATA_DIR / 'po_with_actions.json'
                    with open(output, 'w', encoding='utf-8') as f:
                        json.dump(po_data, f, ensure_ascii=False, indent=2)
                    print(f"  已保存到: {output}")
    else:
        print(f"获取 PO 失败: {resp.status_code}")


def test_script_actions():
    """测试系统中可用的脚本/actions"""
    auth = get_maximo_auth()
    headers = {
        **DEFAULT_HEADERS, 
        'Cookie': auth['cookie'], 
        'x-csrf-token': auth['csrf_token']
    }
    
    print("\n" + "=" * 60)
    print("搜索 REST API 可调用的业务逻辑")
    print("=" * 60)
    
    # 尝试获取 OSLC Service Provider
    urls = [
        f'{MAXIMO_BASE_URL}/oslc/sp',
        f'{MAXIMO_BASE_URL}/oslc/os/MXAPIPO/meta/actions',
        f'{MAXIMO_BASE_URL}/oslc/script',
    ]
    
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, 
                               verify=False, proxies=PROXIES, timeout=20)
            print(f"\n{url.split('/maximo')[1]}:")
            print(f"  状态码: {resp.status_code}")
            if resp.status_code == 200 and resp.text:
                # 保存响应
                name = url.split('/')[-1] or 'sp'
                output = RAW_DATA_DIR / f'oslc_{name}.json'
                try:
                    data = resp.json()
                    with open(output, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f"  已保存到: {output.name}")
                except:
                    print(f"  响应: {resp.text[:200]}")
        except Exception as e:
            print(f"  异常: {str(e)[:50]}")


if __name__ == '__main__':
    test_receipt_endpoints()
    test_po_actions()
    test_script_actions()
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
