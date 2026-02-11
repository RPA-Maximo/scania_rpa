"""
测试 MXAPIPO 的 wsmethod actions
Maximo REST API 支持通过 ?action=wsmethod:XXX 调用业务方法
"""
import sys
import json
sys.path.insert(0, '.')
import requests
import urllib3
from config import get_maximo_auth, DEFAULT_HEADERS, PROXIES
from config.settings import MAXIMO_BASE_URL, RAW_DATA_DIR

urllib3.disable_warnings()


def get_headers():
    auth = get_maximo_auth()
    return {
        **DEFAULT_HEADERS, 
        'Cookie': auth['cookie'], 
        'x-csrf-token': auth['csrf_token'],
        'Content-Type': 'application/json',
        'x-method-override': 'PATCH'
    }


def get_test_po():
    """获取一个可以测试的PO"""
    headers = get_headers()
    
    # 获取 CN5123 的详情
    url = f'{MAXIMO_BASE_URL}/oslc/os/MXAPIPO'
    params = {
        'lean': 1,
        'oslc.where': 'ponum="CN5123"',
        'oslc.select': 'ponum,status,receipts,href,poid,poline{polinenum,itemnum,orderqty,receivedqty,receiptscomplete,polineid}'
    }
    
    resp = requests.get(url, headers=headers, params=params, 
                       verify=False, proxies=PROXIES, timeout=30)
    
    if resp.status_code == 200:
        data = resp.json()
        if data.get('member'):
            return data['member'][0]
    return None


def test_wsmethod_actions():
    """测试可能的 wsmethod actions"""
    headers = get_headers()
    po = get_test_po()
    
    if not po:
        print("无法获取测试 PO")
        return
    
    print("=" * 60)
    print(f"测试 PO: {po.get('ponum')}")
    print(f"状态: {po.get('status')}, 接收: {po.get('receipts')}")
    print("=" * 60)
    
    # 找到未完成接收的行
    pending_lines = [
        line for line in po.get('poline', [])
        if not line.get('receiptscomplete')
    ]
    
    print(f"\n待接收行数: {len(pending_lines)}")
    for line in pending_lines[:3]:
        print(f"  行 {line.get('polinenum')}: {line.get('itemnum')} - 订购 {line.get('orderqty')}, 已收 {line.get('receivedqty', 0)}")
    
    po_href = po.get('href', '')
    po_url = f'{MAXIMO_BASE_URL}/{po_href}'
    
    # 常见的 Maximo PO actions
    actions = [
        'RECEIVE',          # 接收
        'CANCELRECEIPT',    # 取消接收
        'APPROVERECEIVE',   # 批准接收
        'CREATERECEIPT',    # 创建接收
        'PORECEIPT',        # PO接收
        'ADDRECEIPT',       # 添加接收
        'SETRECEIPT',       # 设置接收
        'ENTERRECEIPTS',    # 输入接收
    ]
    
    print("\n" + "=" * 60)
    print("测试 wsmethod actions (仅检测是否可用)")
    print("=" * 60)
    
    for action in actions:
        action_url = f'{po_url}?action=wsmethod:{action}'
        
        # 使用 OPTIONS 请求测试
        try:
            resp = requests.options(action_url, headers=headers,
                                   verify=False, proxies=PROXIES, timeout=20)
            print(f"\nOPTIONS wsmethod:{action}: {resp.status_code}")
            if resp.status_code == 200:
                print(f"  Headers: {dict(resp.headers)}")
        except Exception as e:
            print(f"\nOPTIONS wsmethod:{action}: 异常 - {str(e)[:50]}")


def test_bulk_receive_endpoint():
    """测试批量接收相关端点"""
    headers = get_headers()
    
    print("\n" + "=" * 60)
    print("测试批量接收相关端点")
    print("=" * 60)
    
    # 测试 /oslc/action 端点
    endpoints = [
        '/oslc/action/RECEIVE',
        '/oslc/action/CREATERECEIPT',
        '/oslc/bulk/MXAPIPO',
        '/oslc/script/RECEIVING',
    ]
    
    for ep in endpoints:
        url = f'{MAXIMO_BASE_URL}{ep}'
        try:
            # 尝试 GET
            resp = requests.get(url, headers=headers,
                               verify=False, proxies=PROXIES, timeout=20)
            print(f"\nGET {ep}:")
            print(f"  状态码: {resp.status_code}")
            if resp.status_code < 500 and resp.text:
                print(f"  响应: {resp.text[:200]}")
        except Exception as e:
            print(f"\nGET {ep}: 异常 - {str(e)[:50]}")


def explore_po_operations():
    """探索 PO 上支持的操作"""
    headers = get_headers()
    po = get_test_po()
    
    if not po:
        print("无法获取测试 PO")
        return
    
    print("\n" + "=" * 60)
    print("探索 PO 支持的 HTTP 方法")
    print("=" * 60)
    
    po_href = po.get('href', '')
    po_url = f'{MAXIMO_BASE_URL}/{po_href}'
    
    # OPTIONS 请求
    resp = requests.options(po_url, headers=headers,
                           verify=False, proxies=PROXIES, timeout=20)
    print(f"\nOPTIONS {po_href}:")
    print(f"  状态码: {resp.status_code}")
    print(f"  Allow: {resp.headers.get('Allow', 'N/A')}")
    
    # 尝试 SYNC 操作 (Maximo 7.6.1+)
    sync_url = f'{po_url}?action=system:sync'
    resp = requests.post(sync_url, headers=headers, json={},
                        verify=False, proxies=PROXIES, timeout=20)
    print(f"\nPOST action=system:sync:")
    print(f"  状态码: {resp.status_code}")
    if resp.text:
        print(f"  响应: {resp.text[:300]}")


if __name__ == '__main__':
    test_wsmethod_actions()
    test_bulk_receive_endpoint()
    explore_po_operations()
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
