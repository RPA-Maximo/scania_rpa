"""
测试不同的 Maximo API 端点
用于找到正确的物料主数据 API
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import urllib3
from config import get_maximo_auth, VERIFY_SSL, PROXIES
from config.settings import MAXIMO_BASE_URL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# 可能的 Item Master API 端点
POSSIBLE_ENDPOINTS = [
    "MXAPIITEM",           # 物料主数据
    "MXITEM",              # 物料
    "MXAPIITEMMASTER",     # 物料主数据（另一种命名）
    "MXAPIINVENTORY",      # 库存（已知可用）
]


def test_endpoint(endpoint_name, item_number="00006928"):
    """
    测试指定的 API 端点
    
    Args:
        endpoint_name: API 端点名称
        item_number: 要查询的物料编号（从页面上看到的）
    """
    print(f"\n{'='*60}")
    print(f"测试端点: {endpoint_name}")
    print(f"{'='*60}")
    
    try:
        auth = get_maximo_auth()
    except ValueError as e:
        print(f"[错误] {e}")
        return None
    
    # 构建 API URL
    api_url = f"{MAXIMO_BASE_URL}/oslc/os/{endpoint_name}"
    
    # 构建请求头
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }
    
    # 构建查询参数
    params = {
        'oslc.select': '*',
        'oslc.pageSize': 5,
        '_dropnulls': 0,
        'oslc.where': f'itemnum="{item_number}"',  # 查询特定物料
    }
    
    try:
        print(f"请求 URL: {api_url}")
        print(f"查询条件: itemnum={item_number}")
        if PROXIES:
            print(f"使用代理: {PROXIES['https']}")
        
        resp = requests.get(
            api_url,
            headers=headers,
            params=params,
            verify=VERIFY_SSL,
            proxies=PROXIES,
            timeout=30
        )
        
        print(f"状态码: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            
            # 获取数据
            items = data.get('member') or data.get('rdfs:member') or []
            
            if items:
                print(f"✓ 成功！找到 {len(items)} 条数据")
                print(f"\n第一条数据:")
                item = items[0]
                
                # 显示关键字段
                print(f"  物料编号: {item.get('itemnum', 'N/A')}")
                print(f"  描述: {item.get('description', 'N/A')}")
                print(f"  状态: {item.get('status', 'N/A')}")
                
                # 显示所有字段名
                print(f"\n  可用字段 ({len(item)} 个):")
                fields = list(item.keys())[:20]  # 只显示前20个
                for field in fields:
                    print(f"    - {field}")
                if len(item) > 20:
                    print(f"    ... 还有 {len(item) - 20} 个字段")
                
                return {
                    'endpoint': endpoint_name,
                    'success': True,
                    'data': items
                }
            else:
                print(f"✗ 未找到数据")
                print(f"响应内容: {data}")
                return None
                
        elif resp.status_code == 404:
            print(f"✗ 端点不存在")
            return None
        elif resp.status_code == 401:
            print(f"✗ 认证失败，请更新 Cookie")
            return None
        else:
            print(f"✗ 请求失败")
            print(f"响应: {resp.text[:200]}")
            return None
            
    except Exception as e:
        print(f"✗ 异常: {e}")
        return None


def compare_with_page_data():
    """
    对比 API 数据和页面数据
    """
    print(f"\n{'='*60}")
    print("对比页面数据")
    print(f"{'='*60}")
    
    # 从页面上看到的数据
    page_data = {
        'itemnum': '00006928',
        'description': 'PAPEL VCI    1240 X 800MM',
        'status': 'ACTIVE'
    }
    
    print("\n页面显示的数据:")
    for key, value in page_data.items():
        print(f"  {key}: {value}")
    
    return page_data


def main():
    """
    主函数：测试所有可能的端点
    """
    print("="*60)
    print("Maximo API 端点测试工具")
    print("="*60)
    
    # 先显示页面数据
    page_data = compare_with_page_data()
    
    # 测试所有端点
    results = []
    for endpoint in POSSIBLE_ENDPOINTS:
        result = test_endpoint(endpoint, page_data['itemnum'])
        if result:
            results.append(result)
    
    # 总结
    print(f"\n{'='*60}")
    print("测试总结")
    print(f"{'='*60}")
    
    if results:
        print(f"\n✓ 找到 {len(results)} 个可用端点:")
        for result in results:
            print(f"  - {result['endpoint']}")
        
        print(f"\n推荐使用: {results[0]['endpoint']}")
    else:
        print("\n✗ 未找到可用的端点")
        print("\n可能的原因:")
        print("  1. API 端点名称不在测试列表中")
        print("  2. 需要特殊的权限或参数")
        print("  3. 使用的是定制化的 API")
        print("\n建议:")
        print("  1. 在浏览器中查找包含 'oslc/os/' 的请求")
        print("  2. 或者使用 HTML 解析方案")


if __name__ == "__main__":
    main()
