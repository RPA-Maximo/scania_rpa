"""
Maximo 库存数据爬虫 - 数据探索脚本
从 Maximo API 抓取库存数据，支持分页、排序和筛选
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径，以便导入 config 模块
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import pandas as pd
import urllib3
import time
from datetime import datetime

from config import (
    get_maximo_auth,
    MAXIMO_API_URL,
    DEFAULT_HEADERS,
    API_PARAMS,
    REQUEST_DELAY,
    VERIFY_SSL,
    RAW_DATA_DIR
)

# 禁用安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def run_scraper_sorted(max_pages: int = 3):
    """
    执行带筛选和排序的抓取任务
    
    Args:
        max_pages: 最大抓取页数
    """
    print(">>> 启动【筛选+排序】抓取脚本...")
    
    # 从配置模块获取认证信息
    try:
        auth = get_maximo_auth()
    except ValueError as e:
        print(f"[错误] {e}")
        print("请复制 config/.env.example 为 config/.env 并填入认证信息")
        return
    
    # 构建请求头
    headers = {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }

    all_data = []
    
    for page in range(1, max_pages + 1):
        print(f"正在请求第 {page} 页 (带筛选!=OBSOLETE, 按编号排序)...", end="")
        
        # 构建请求参数
        params = {
            **API_PARAMS,
            'pageno': page,
        }
        
        try:
            resp = requests.get(
                MAXIMO_API_URL, 
                headers=headers, 
                params=params, 
                verify=VERIFY_SSL
            )
            
            if resp.status_code == 200:
                data_json = resp.json()
                items = data_json.get('member') or data_json.get('rdfs:member')
                
                if items:
                    print(f" 成功! 抓到 {len(items)} 条数据")
                    # 打印第一条看看是不是 20326793
                    if page == 1:
                        first_item = items[0].get('itemnum')
                        print(f"   -> 第1页第1条数据编号是: {first_item} (应该等于 20326793)")
                    all_data.extend(items)
                else:
                    print(" 数据为空，停止抓取。")
                    break
            elif resp.status_code == 401:
                print("\n[错误] Token 似乎过期了，请去浏览器刷新页面重新复制 Cookie。")
                print("然后更新 config/.env 文件中的 MAXIMO_COOKIE 和 MAXIMO_CSRF_TOKEN")
                break
            else:
                print(f"\n[失败] 状态码 {resp.status_code}: {resp.text[:200]}")
                break
                
        except Exception as e:
            print(f"\n[异常] {e}")
            break
            
        time.sleep(REQUEST_DELAY)

    # 保存文件到统一的数据目录
    if all_data:
        df = pd.DataFrame(all_data)
        df = df.astype(str)
        
        # 生成带时间戳的文件名，保存到 data/raw 目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"inventory_{timestamp}.xlsx"
        filepath = RAW_DATA_DIR / filename
        
        df.to_excel(filepath, index=False)
        print(f"\n>>> 成功！已保存到 {filepath}")
        print(f">>> 共获取 {len(all_data)} 条数据")


if __name__ == "__main__":
    run_scraper_sorted()