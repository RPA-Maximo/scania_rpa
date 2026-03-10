"""
物料库存成本（单价）抓取器
从 Maximo MXAPIINVENTORY（含 invcost 子集）拉取物料单价

对应 Maximo 界面：Inventory LIFO/FIFO Costs
字段：unitcost（单价）、costdate（成本日期）、quantity（数量）
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

# 同时获取物料基础信息 + invcost 子集（单价/成本）
INVCOST_SELECT = (
    "itemnum,storeloc,siteid,description,"
    "avgcost,stdcost,lastcost,"
    "invcost{unitcost,costdate,quantity,conditioncode}"
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


def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def fetch_invcost(
    item_numbers: Optional[List[str]] = None,
    warehouse: Optional[str] = None,
    max_pages: int = 100,
    page_size: int = 50,
) -> List[Dict[str, Any]]:
    """
    从 MXAPIINVENTORY 拉取物料库存成本数据（含 LIFO/FIFO 单价）

    Args:
        item_numbers: 指定物料编号列表；None=全部
        warehouse:    仓库过滤；None=全部
        max_pages:    最多抓取页数
        page_size:    每页条数

    Returns:
        扁平化后的成本行列表，每项含：
          item_number, warehouse, site,
          unit_cost（取最新 invcost 行的 unitcost，或 avgcost 作为兜底）,
          avg_cost, last_cost,
          cost_date, cost_quantity
    """
    print(f"[INFO] 开始抓取物料单价 (warehouse={warehouse or '全部'}, max_pages={max_pages})")

    try:
        headers = _get_headers()
    except ValueError as e:
        print(f"[ERROR] 认证失败: {e}")
        return []

    all_data: List[Dict] = []

    for page in range(1, max_pages + 1):
        print(f"  第 {page}/{max_pages} 页...", end=" ", flush=True)

        where_parts = ['status!="OBSOLETE"']
        if warehouse:
            where_parts.append(f'storeloc="{warehouse}"')
        if item_numbers:
            clause = " or ".join(f'itemnum="{n}"' for n in item_numbers)
            where_parts.append(f"({clause})")

        params = {
            "oslc.select":   INVCOST_SELECT,
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
                    print(f"非JSON: {resp.text[:100]!r}")
                    break
                items = data.get("member") or data.get("rdfs:member") or []
                if not items:
                    print("无数据")
                    break
                items = [_normalize(i) for i in items]
                print(f"✓ {len(items)} 条")

                for inv in items:
                    item_num  = str(inv.get("itemnum") or "").strip()
                    wh        = str(inv.get("storeloc") or "").strip()
                    site      = str(inv.get("siteid") or "").strip()
                    avg_cost  = _safe_float(inv.get("avgcost"))
                    last_cost = _safe_float(inv.get("lastcost"))

                    # invcost 子集：取最新的（按 costdate 降序第1条）
                    invcost_list = inv.get("invcost") or []
                    if isinstance(invcost_list, dict):
                        invcost_list = [invcost_list]

                    if invcost_list:
                        # 按 costdate 找最新一条
                        def _cd(x):
                            return str(x.get("costdate") or "")
                        latest = max(invcost_list, key=_cd)
                        unit_cost   = _safe_float(latest.get("unitcost"))
                        cost_date   = str(latest.get("costdate") or "")[:19]
                        cost_qty    = _safe_float(latest.get("quantity"))
                    else:
                        # 没有 invcost 子集，用 avgcost 作为兜底
                        unit_cost   = avg_cost
                        cost_date   = None
                        cost_qty    = None

                    if not item_num:
                        continue

                    all_data.append({
                        "item_number":  item_num,
                        "warehouse":    wh,
                        "site":         site,
                        "unit_cost":    unit_cost,
                        "avg_cost":     avg_cost,
                        "last_cost":    last_cost,
                        "cost_date":    cost_date,
                        "cost_quantity": cost_qty,
                    })

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

    print(f"[INFO] 共抓取 {len(all_data)} 条库存成本记录")
    return all_data
