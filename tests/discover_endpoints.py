"""
发现 Maximo 可用的 Object Structures (API 端点)
通过查询 mxapiobjectstructure 获取所有可用端点
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


def discover_endpoints(keyword: str = None):
    """
    发现可用的 Object Structures
    
    Args:
        keyword: 搜索关键词，如 'PO', 'PURCH', 'ORDER'
    """
    print("="*60)
    print("发现 Maximo Object Structures")
    print("="*60)
    
    try:
        auth = get_maximo_auth()
        print(f"✓ 认证信息已加载 (CSRF Token: {auth['csrf_token'][:20]}...)")
    except ValueError as e:
        print(f"[错误] {e}")
        return None
    
    # Object Structure 发现端点
    discovery_url = f"{MAXIMO_BASE_URL}/oslc/os/mxapiobjectstructure"
    
    headers = {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }
    
    # 查询参数
    params = {
        'oslc.select': 'objectstructure,description',
        'oslc.pageSize': 100,
        '_dropnulls': 1,
    }
    
    # 如果有关键词，添加筛选
    if keyword:
        params['oslc.where'] = f'objectstructure="%{keyword.upper()}%"'
        print(f"搜索关键词: {keyword}")
    
    print(f"请求: {discovery_url}")
    if PROXIES:
        print(f"代理: {PROXIES['https']}")
    
    try:
        resp = requests.get(
            discovery_url,
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
            
            print(f"\n找到 {len(items)} 个 Object Structures:")
            print("-"*60)
            
            # 过滤和显示
            po_related = []
            for item in items:
                name = item.get('objectstructure', '')
                desc = item.get('description', '')
                
                # 如果有关键词，高亮显示相关的
                if keyword:
                    if keyword.upper() in name.upper() or keyword.upper() in desc.upper():
                        po_related.append((name, desc))
                        print(f"  ★ {name:30s} - {desc}")
                else:
                    print(f"  {name:30s} - {desc}")
            
            if keyword and po_related:
                print(f"\n与 '{keyword}' 相关的端点: {len(po_related)} 个")
            
            return items
            
        elif resp.status_code == 401:
            print("✗ 认证失败，请更新 响应标头.txt")
            return None
        else:
            print(f"✗ 请求失败: {resp.status_code}")
            print(f"响应: {resp.text[:500]}")
            return None
            
    except Exception as e:
        print(f"✗ 异常: {e}")
        import traceback
        traceback.print_exc()
        return None


def search_po_endpoints():
    """
    搜索采购订单相关的端点
    """
    print("\n" + "="*60)
    print("搜索采购订单相关端点")
    print("="*60)
    
    try:
        auth = get_maximo_auth()
    except ValueError as e:
        print(f"[错误] {e}")
        return
    
    # 可能的搜索词
    keywords = ['PO', 'PURCH', 'ORDER', 'PR']
    
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
                for ep in found:
                    print(f"  ★ {ep['name']:30s}")
                    print(f"    描述: {ep['description']}")
                    print(f"    关键词: {ep['keyword']}")
                    print()
                
                # 推荐使用
                print("-"*60)
                print("推荐优先尝试:")
                for ep in found:
                    if 'MXAPIPO' in ep['name'].upper() or 'MXPO' in ep['name'].upper():
                        print(f"  → {ep['name']} (采购订单)")
            else:
                print("未找到相关端点")
                
        else:
            print(f"请求失败: {resp.status_code}")
            
    except Exception as e:
        print(f"异常: {e}")


if __name__ == "__main__":
    # 先搜索采购订单相关端点
    search_po_endpoints()
