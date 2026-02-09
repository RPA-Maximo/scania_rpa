"""
测试 MXAPIPO 的 PATCH 能力 - 尝试更新 poline 来记录接收
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


def get_api_yaml():
    """获取 MXAPIPO 的 OpenAPI/YAML 文档"""
    print("=" * 60)
    print("1. 获取 MXAPIPO API 文档")
    print("=" * 60)
    
    headers, _ = get_auth_headers()
    
    url = f'{MAXIMO_BASE_URL}/oslc/yaml/mxapipo'
    print(f'请求: {url}')
    
    resp = requests.get(url, headers=headers, verify=False, proxies=PROXIES, timeout=60)
    print(f'状态码: {resp.status_code}')
    
    if resp.status_code == 200:
        output = RAW_DATA_DIR / 'mxapipo_api.yaml'
        with open(output, 'w', encoding='utf-8') as f:
            f.write(resp.text)
        print(f'已保存到: {output}')
        
        # 搜索 receipt 相关内容
        if 'receipt' in resp.text.lower():
            print('\n✓ 发现 receipt 相关内容!')
        if 'POST' in resp.text or 'PATCH' in resp.text:
            print('✓ API 支持 POST/PATCH 方法!')
            
        return resp.text
    else:
        print(f'失败: {resp.text[:200]}')
        return None


def check_po_actions():
    """检查 MXAPIPO 的可用动作"""
    print("\n" + "=" * 60)
    print("2. 检查 MXAPIPO 支持的动作/方法")
    print("=" * 60)
    
    headers, _ = get_auth_headers()
    
    # 检查端点支持的HTTP方法
    url = f'{MAXIMO_BASE_URL}/oslc/os/MXAPIPO'
    resp = requests.options(url, headers=headers, verify=False, proxies=PROXIES, timeout=30)
    print(f'OPTIONS 状态码: {resp.status_code}')
    
    allow = resp.headers.get('Allow', '')
    if allow:
        print(f'Allow: {allow}')
    
    # 检查 CORS headers
    methods = resp.headers.get('access-control-allow-methods', '')
    print(f'Access-Control-Allow-Methods: {methods}')


def get_po_schema():
    """获取 MXAPIPO 的 JSON Schema - 了解可写字段"""
    print("\n" + "=" * 60)
    print("3. 获取 MXAPIPO JSON Schema")
    print("=" * 60)
    
    headers, _ = get_auth_headers()
    
    url = f'{MAXIMO_BASE_URL}/oslc/jsonschemas/mxapipo'
    print(f'请求: {url}')
    
    resp = requests.get(url, headers=headers, verify=False, proxies=PROXIES, timeout=60)
    print(f'状态码: {resp.status_code}')
    
    if resp.status_code == 200:
        output = RAW_DATA_DIR / 'mxapipo_schema.json'
        with open(output, 'w', encoding='utf-8') as f:
            f.write(resp.text)
        print(f'已保存到: {output}')
        
        # 解析并检查 poline 相关的属性
        try:
            schema = resp.json()
            if 'properties' in schema:
                props = list(schema.get('properties', {}).keys())
                print(f'根属性数: {len(props)}')
                
                # 查找 poline 相关
                poline_props = [p for p in props if 'poline' in p.lower() or 'receipt' in p.lower()]
                if poline_props:
                    print(f'poline/receipt 相关属性: {poline_props}')
        except:
            pass
        
        return resp.text
    else:
        print(f'失败: {resp.text[:200]}')
        return None


def test_patch_simulation():
    """测试 PATCH 请求更新 poline 的 receivedqty (模拟/不实际执行)"""
    print("\n" + "=" * 60)
    print("4. 准备 PATCH 请求 (仅模拟)")
    print("=" * 60)
    
    # 从之前保存的 PO 数据获取信息
    po_file = RAW_DATA_DIR / 'po_with_receipts.json'
    if not po_file.exists():
        print(f'文件不存在: {po_file}')
        return
    
    with open(po_file, 'r', encoding='utf-8') as f:
        po_data = json.load(f)
    
    po_href = po_data.get('href', '')
    ponum = po_data.get('ponum', '')
    poline = po_data.get('poline', [])
    
    print(f'PO号: {ponum}')
    print(f'PO href: {po_href}')
    print(f'行数: {len(poline)}')
    
    # 找一个未完成接收的行
    pending_lines = [p for p in poline if not p.get('receiptscomplete', True)]
    print(f'待接收行数: {len(pending_lines)}')
    
    if pending_lines:
        line = pending_lines[0]
        print(f'\n选择行 {line.get("polinenum")}:')
        print(f'  物料: {line.get("itemnum")}')
        print(f'  描述: {line.get("description", "")[:40]}...')
        print(f'  订购数量: {line.get("orderqty")}')
        print(f'  已接收: {line.get("receivedqty", 0)}')
        print(f'  localref: {line.get("localref")}')
        
        # 模拟 PATCH 请求体
        patch_url = f'{MAXIMO_BASE_URL}/{line.get("localref")}'
        patch_body = {
            'receivedqty': line.get('orderqty', 0),  # 设置为全部接收
        }
        
        print(f'\n模拟 PATCH:')
        print(f'  URL: {patch_url}')
        print(f'  Body: {json.dumps(patch_body, indent=2)}')
        print('\n⚠️ 这是模拟请求，未实际发送')
        print('如需实际测试，请取消下面代码的注释')


if __name__ == "__main__":
    # 1. 获取API文档
    get_api_yaml()
    
    # 2. 检查支持的方法
    check_po_actions()
    
    # 3. 获取schema
    get_po_schema()
    
    # 4. 准备PATCH测试
    test_patch_simulation()
    
    print("\n" + "=" * 60)
    print("完成! 请查看输出文件了解API能力")
    print("=" * 60)
