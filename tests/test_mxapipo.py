"""
专门测试 MXAPIPO 端点（增加超时时间）
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

def test_mxapipo():
    """测试 MXAPIPO 端点，超时时间 120 秒"""
    print("="*60)
    print("测试 MXAPIPO 端点 (超时: 120秒)")
    print("="*60)
    
    try:
        auth = get_maximo_auth()
        print(f"✓ 认证信息已加载")
    except ValueError as e:
        print(f"[错误] {e}")
        return
    
    api_url = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIPO"
    
    headers = {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }
    
    params = {
        'oslc.select': 'ponum,description,status,statusdate',
        'oslc.pageSize': 3,
        '_dropnulls': 1,
    }
    
    print(f"请求: {api_url}")
    if PROXIES:
        print(f"代理: {PROXIES['https']}")
    print("请耐心等待...")
    
    try:
        resp = requests.get(
            api_url,
            headers=headers,
            params=params,
            verify=VERIFY_SSL,
            proxies=PROXIES,
            timeout=120  # 增加到 120 秒
        )
        
        print(f"\n状态码: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('member') or data.get('rdfs:member') or []
            
            print(f"✓ 成功! 获取到 {len(items)} 条数据\n")
            
            for i, item in enumerate(items, 1):
                print(f"订单 {i}:")
                for key, value in item.items():
                    if not key.startswith('_') and not key.startswith('href'):
                        print(f"  {key}: {value}")
                print()
                
            print("="*60)
            print("MXAPIPO 端点可用！")
            print("="*60)
            
        else:
            print(f"✗ 失败: {resp.status_code}")
            print(f"响应: {resp.text[:500]}")
            
    except requests.exceptions.Timeout:
        print("✗ 请求超时 (120秒)")
    except Exception as e:
        print(f"✗ 异常: {e}")


if __name__ == "__main__":
    test_mxapipo()
