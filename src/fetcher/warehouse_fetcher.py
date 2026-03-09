"""
仓库和仓位数据抓取器
从 Maximo MXAPILOCATION API 拉取仓库（storeroom）和仓位信息
用于 warehouse / warehouse_bin 表同步
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

# 仓库（Storeroom）API
LOCATION_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPILOCATION"

REQUEST_TIMEOUT = 120

# 仓库主数据字段
LOCATION_SELECT = (
    "location,description,type,siteid,orgid,status,"
    "useinpopr,useinwo"
)


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


def fetch_warehouses(
    site_id: Optional[str] = None,
    location_codes: Optional[List[str]] = None,
    location_type: str = "STOREROOM",
    max_pages: int = 20,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """
    从 MXAPILOCATION 拉取仓库（storeroom）数据

    Args:
        site_id:        地点过滤
        location_codes: 指定仓库编号列表
        location_type:  位置类型，默认 STOREROOM
        max_pages:      最多抓取页数
        page_size:      每页条数

    Returns:
        标准化后的仓库列表
    """
    print(f"[INFO] 开始抓取仓库数据 (type={location_type}, max_pages={max_pages})")

    try:
        headers = _get_headers()
    except ValueError as e:
        print(f"[ERROR] 认证失败: {e}")
        return []

    all_data: List[Dict] = []

    for page in range(1, max_pages + 1):
        print(f"  第 {page}/{max_pages} 页...", end=" ", flush=True)

        where_parts = [f'type="{location_type}"', 'status!="INACTIVE"']
        if site_id:
            where_parts.append(f'siteid="{site_id}"')
        if location_codes:
            clause = " or ".join(f'location="{c}"' for c in location_codes)
            where_parts.append(f"({clause})")

        params = {
            "oslc.select":   LOCATION_SELECT,
            "oslc.pageSize": page_size,
            "_dropnulls":    0,
            "pageno":        page,
            "oslc.orderBy":  "+location",
            "oslc.where":    " and ".join(where_parts),
        }

        try:
            resp = requests.get(
                LOCATION_API_URL,
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

    print(f"[INFO] 共抓取 {len(all_data)} 条仓库记录")
    return all_data


def fetch_bins_from_inventory(
    warehouse: Optional[str] = None,
    site_id: Optional[str] = None,
    max_pages: int = 50,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """
    从 MXAPIINVBAL（货柜级库存）提取仓位（bin）信息

    通过库存数据中的 binnum 字段获取各仓库下的仓位列表，
    是从 Maximo 获取仓位信息最可靠的方式。

    Returns:
        去重后的仓位列表 [{'warehouse', 'site', 'bin_code'}, ...]
    """
    from config.settings import MAXIMO_BASE_URL

    INVBAL_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIINVBAL"
    BIN_SELECT = "storeloc,siteid,binnum"

    print(f"[INFO] 开始从库存数据提取仓位信息 (warehouse={warehouse or '全部'})")

    try:
        headers = _get_headers()
    except ValueError as e:
        print(f"[ERROR] 认证失败: {e}")
        return []

    seen = set()
    all_bins: List[Dict] = []

    for page in range(1, max_pages + 1):
        print(f"  仓位抓取第 {page}/{max_pages} 页...", end=" ", flush=True)

        where_parts = ['binnum!=""']
        if warehouse:
            where_parts.append(f'storeloc="{warehouse}"')
        if site_id:
            where_parts.append(f'siteid="{site_id}"')

        params = {
            "oslc.select":   BIN_SELECT,
            "oslc.pageSize": page_size,
            "_dropnulls":    0,
            "pageno":        page,
            "oslc.orderBy":  "+storeloc,+binnum",
            "oslc.where":    " and ".join(where_parts),
        }

        try:
            resp = requests.get(
                INVBAL_URL,
                headers=headers,
                params=params,
                verify=VERIFY_SSL,
                proxies=settings_manager.get_proxies(),
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                if not resp.content:
                    print("空响应")
                    break
                try:
                    data = resp.json()
                except Exception:
                    print(f"非JSON: {resp.text[:80]!r}")
                    break
                items = data.get("member") or data.get("rdfs:member") or []
                if not items:
                    print("无数据")
                    break
                items = [_normalize(i) for i in items]
                added = 0
                for it in items:
                    wh  = str(it.get("storeloc") or "").strip()
                    bin = str(it.get("binnum") or "").strip()
                    if wh and bin:
                        key = (wh, bin)
                        if key not in seen:
                            seen.add(key)
                            all_bins.append({
                                "warehouse": wh,
                                "site":      str(it.get("siteid") or "").strip(),
                                "bin_code":  bin,
                            })
                            added += 1
                print(f"✓ 新增 {added} 个仓位")
                if len(items) < page_size:
                    break
            elif resp.status_code == 401:
                print("认证过期")
                break
            else:
                print(f"错误 {resp.status_code}")
                break
        except requests.exceptions.Timeout:
            print("超时")
            break
        except Exception as e:
            print(f"异常: {e}")
            break

        time.sleep(REQUEST_DELAY)

    print(f"[INFO] 共提取 {len(all_bins)} 个唯一仓位")
    return all_bins
