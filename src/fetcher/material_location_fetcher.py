"""
物料默认仓位数据抓取器
从 Maximo MXAPIINVENTORY 拉取每个物料在仓库中的缺省货柜（defaultbin）字段
用于 material_location 表的自动同步
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

INVENTORY_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIINVENTORY"
REQUEST_TIMEOUT = 120

# 只取物料、仓库、地点、缺省货柜四个字段
DEFAULT_BIN_SELECT = "itemnum,storeloc,siteid,defaultbin"


def _normalize(data: dict) -> dict:
    result = {}
    for key, value in data.items():
        clean = key.split(":", 1)[1] if ":" in key else key
        result[clean] = value
    return result


def _get_headers() -> dict:
    auth = get_maximo_auth()
    return {
        **DEFAULT_HEADERS,
        "Cookie": auth["cookie"],
        "x-csrf-token": auth["csrf_token"],
    }


def fetch_default_bins(
    warehouse: Optional[str] = None,
    site_id: Optional[str] = None,
    max_pages: int = 50,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """
    从 MXAPIINVENTORY 拉取含有缺省货柜（defaultbin）的库存记录

    Args:
        warehouse:  仓库编码过滤（如 '518'）；None=全部
        site_id:    地点过滤；None=全部
        max_pages:  最多抓取页数
        page_size:  每页条数

    Returns:
        [{'item_number', 'warehouse', 'site', 'default_bin'}, ...]
        仅返回 defaultbin 非空的记录
    """
    print(f"[INFO] 开始抓取物料缺省货柜数据 (仓库={warehouse or '全部'}, max_pages={max_pages})")

    try:
        headers = _get_headers()
    except ValueError as e:
        print(f"[ERROR] 认证失败: {e}")
        return []

    all_data: List[Dict] = []

    for page in range(1, max_pages + 1):
        print(f"  第 {page}/{max_pages} 页...", end=" ", flush=True)

        where_parts = ['status!="OBSOLETE"', 'defaultbin!=""']
        if warehouse:
            where_parts.append(f'storeloc="{warehouse}"')
        if site_id:
            where_parts.append(f'siteid="{site_id}"')

        params = {
            "oslc.select":   DEFAULT_BIN_SELECT,
            "oslc.pageSize": page_size,
            "_dropnulls":    0,
            "pageno":        page,
            "oslc.orderBy":  "+itemnum",
            "oslc.where":    " and ".join(where_parts),
        }

        try:
            resp = requests.get(
                INVENTORY_API_URL,
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
                rows = [
                    {
                        "item_number": str(it.get("itemnum") or "").strip(),
                        "warehouse":   str(it.get("storeloc") or "").strip(),
                        "site":        str(it.get("siteid") or "").strip(),
                        "default_bin": str(it.get("defaultbin") or "").strip(),
                    }
                    for it in items
                    if it.get("defaultbin") and str(it.get("defaultbin")).strip()
                ]
                print(f"✓ {len(rows)} 条（含缺省货柜）")
                all_data.extend(rows)
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

    print(f"[INFO] 共抓取 {len(all_data)} 条含缺省货柜的库存记录")
    return all_data
