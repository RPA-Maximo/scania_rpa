"""
供应商账户数据抓取器
从 Maximo MXAPICOMPANY API 拉取供应商编号和供应商名称
用于 vendor 表同步
"""
import sys
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import urllib3
from config import get_maximo_auth, DEFAULT_HEADERS
from config.settings import MAXIMO_BASE_URL, REQUEST_DELAY, VERIFY_SSL
from config.settings_manager import settings_manager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

VENDOR_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPICOMPANY"

REQUEST_TIMEOUT = 120

# 供应商同步所需字段
VENDOR_SELECT = "company,name,type,status,currency,url,pluspcustomer"


def _normalize(data: dict) -> dict:
    result = {}
    for key, value in data.items():
        clean = key.split(":", 1)[1] if ":" in key else key
        if isinstance(value, dict):
            result[clean] = _normalize(value)
        elif isinstance(value, list):
            result[clean] = [_normalize(i) if isinstance(i, dict) else i for i in value]
        else:
            result[clean] = value
    return result


def _get_headers() -> dict:
    auth = get_maximo_auth()
    return {
        **DEFAULT_HEADERS,
        "Cookie": auth["cookie"],
        "x-csrf-token": auth["csrf_token"],
    }


def fetch_vendors(
    vendor_numbers: Optional[List[str]] = None,
    vendor_type: Optional[str] = None,
    max_pages: int = 50,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """
    从 MXAPICOMPANY 分页拉取供应商数据

    Args:
        vendor_numbers: 指定供应商编号列表；None 表示全部
        vendor_type:    供应商类型过滤（如 'V' 代表 Vendor）；None 不过滤
        max_pages:      最多抓取页数
        page_size:      每页条数

    Returns:
        标准化后的供应商列表，每项含 company（编号）和 name（名称）
    """
    print(f"[INFO] 开始抓取供应商数据 (max_pages={max_pages})")

    try:
        headers = _get_headers()
    except ValueError as e:
        print(f"[ERROR] 认证失败: {e}")
        return []

    all_data: List[Dict] = []

    for page in range(1, max_pages + 1):
        print(f"  第 {page}/{max_pages} 页...", end=" ", flush=True)

        where_parts = ['status!="INACTIVE"']
        if vendor_type:
            where_parts.append(f'type="{vendor_type}"')
        if vendor_numbers:
            clause = " or ".join(f'company="{n}"' for n in vendor_numbers)
            where_parts.append(f"({clause})")

        params = {
            "oslc.select":   VENDOR_SELECT,
            "oslc.pageSize": page_size,
            "_dropnulls":    0,
            "pageno":        page,
            "oslc.orderBy":  "+company",
            "oslc.where":    " and ".join(where_parts),
        }

        try:
            resp = requests.get(
                VENDOR_API_URL,
                headers=headers,
                params=params,
                verify=VERIFY_SSL,
                proxies=settings_manager.get_proxies(),
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                if not resp.content:
                    print("认证过期（空响应）")
                    break
                try:
                    data = resp.json()
                except Exception:
                    print(f"非JSON响应: {resp.text[:100]!r}")
                    break
                items = data.get("member") or data.get("rdfs:member") or []
                if not items:
                    print("无数据")
                    break
                items = [_normalize(i) for i in items]
                print(f"✓ {len(items)} 条")
                all_data.extend(items)
                if len(items) < page_size:
                    break
            elif resp.status_code == 401:
                print("认证过期")
                break
            else:
                print(f"错误 {resp.status_code}: {resp.text[:200]}")
                break
        except requests.exceptions.Timeout:
            print("超时")
            break
        except Exception as e:
            print(f"异常: {e}")
            break

        time.sleep(REQUEST_DELAY)

    print(f"[INFO] 共抓取 {len(all_data)} 条供应商记录")
    return all_data
