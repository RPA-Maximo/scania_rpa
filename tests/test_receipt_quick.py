"""获取接收单完整字段 - 使用列表查询方式"""
import sys
import json
sys.path.insert(0, '.')
import requests
import urllib3
from config import get_maximo_auth, DEFAULT_HEADERS, PROXIES
from config.settings import MAXIMO_BASE_URL, RAW_DATA_DIR

urllib3.disable_warnings()

auth = get_maximo_auth()
print(f'CSRF Token: {auth["csrf_token"]}')

# 使用列表请求,但带上 oslc.select=* 获取所有字段
url = f'{MAXIMO_BASE_URL}/oslc/os/MXAPIRECEIPT'
headers = {
    **DEFAULT_HEADERS, 
    'Cookie': auth['cookie'], 
    'x-csrf-token': auth['csrf_token']
}
params = {
    'lean': 1,
    'oslc.select': '*',  # 选择所有字段
    'oslc.pageSize': 1
}

print(f'请求: {url}')
resp = requests.get(url, headers=headers, params=params, verify=False, proxies=PROXIES, timeout=60)
print(f'状态码: {resp.status_code}')

if resp.status_code == 200:
    data = resp.json()
    members = data.get('member', [])
    
    if members:
        print(f'\n找到 {len(members)} 条记录!')
        first = members[0]
        
        # 保存完整数据
        output_file = RAW_DATA_DIR / 'mxapireceipt_detail.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(first, f, ensure_ascii=False, indent=2)
        print(f'已保存到: {output_file}')
        
        # 打印所有字段
        print('\n' + '='*60)
        print('接收单字段:')
        print('='*60)
        
        public_fields = {k: v for k, v in first.items() if not k.startswith('_')}
        print(f'共 {len(public_fields)} 个字段:\n')
        
        for k, v in sorted(public_fields.items()):
            val_str = str(v)[:80] + "..." if len(str(v)) > 80 else str(v)
            print(f'  {k:30s} = {val_str}')
    else:
        print('响应中没有member数据')
        print(f'响应: {resp.text[:500]}')
else:
    print(f'请求失败: {resp.text}')
