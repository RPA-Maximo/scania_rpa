"""
库存货柜数据抓取器
从 Maximo MXAPIINVENTORY API 抓取库存数据（含货柜/批次明细）
用于 bin_inventory 表初始化与增量同步，支撑先进先出推荐
"""
import sys
from pathlib import Path
import time
from typing import List, Optional, Dict, Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import urllib3
from config import get_maximo_auth, DEFAULT_HEADERS
from config.settings import MAXIMO_BASE_URL, REQUEST_DELAY, VERIFY_SSL
from config.settings_manager import settings_manager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Maximo 库存 API（物料+货柜级库存）
INVENTORY_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIINVENTORY"

# 货柜级库存 API（按 binnum 独立查询，部分 Maximo 版本支持）
INVBAL_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIINVBAL"

REQUEST_TIMEOUT = 120

# 从 MXAPIINVENTORY 获取的字段
# invbalance 子集 = 货柜级别的库存明细（每个货柜的数量、批号、入库日期等）
INVENTORY_SELECT = (
    "itemnum,storeloc,siteid,description,orderunit,status,"
    "curbal,availbal,"
    "invbalance{"
    "binnum,curbal,lotnum,conditioncode,receiptdate,"
    "issuedate,physcnt,physcntdate"
    # 化学品批次信息（待客户补充具体字段）
    # "hazardous,shelflife,expirationdate"
    "}"
)

# 从 MXAPIINVBAL 获取的字段（若 MXAPIINVENTORY 不支持 invbalance 展开时备用）
INVBAL_SELECT = (
    "itemnum,storeloc,siteid,binnum,lotnum,curbal,"
    "conditioncode,receiptdate,issuedate"
)


def _normalize(data: dict) -> dict:
    """移除 Maximo 命名空间前缀"""
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


def fetch_inventory_with_bins(
    warehouse: Optional[str] = None,
    item_numbers: Optional[List[str]] = None,
    max_pages: int = 20,
    page_size: int = 50,
) -> List[Dict[str, Any]]:
    """
    从 MXAPIINVENTORY 分页拉取库存数据（含货柜明细）

    Args:
        warehouse:    仓库编码过滤（如 '518'）；None 表示全部
        item_numbers: 指定物料编号列表；None 表示全部
        max_pages:    最多抓取页数
        page_size:    每页条数

    Returns:
        标准化后的库存列表，每项含 invbalance（货柜明细）
    """
    print(f"[INFO] 开始抓取库存货柜数据 (仓库={warehouse}, max_pages={max_pages})")
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
            # Maximo OSLC 用 "or" 连接多个 itemnum
            item_clause = " or ".join(f'itemnum="{n}"' for n in item_numbers)
            where_parts.append(f"({item_clause})")

        params = {
            "oslc.select":  INVENTORY_SELECT,
            "oslc.pageSize": page_size,
            "_dropnulls":   0,
            "pageno":       page,
            "oslc.orderBy": "+itemnum",
            "oslc.where":   " and ".join(where_parts),
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
                print(f"✓ {len(items)} 条")
                all_data.extend(items)
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

    print(f"[INFO] 共抓取 {len(all_data)} 条物料库存记录")
    return all_data


def fetch_invbal_direct(
    warehouse: Optional[str] = None,
    item_number: Optional[str] = None,
    max_pages: int = 50,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """
    备用方案：直接从 MXAPIINVBAL 拉取货柜级库存
    （当 MXAPIINVENTORY invbalance 子集不可用时使用）

    Args:
        warehouse:   仓库过滤
        item_number: 物料编号过滤
        max_pages:   最多抓取页数
        page_size:   每页条数
    """
    print(f"[INFO] 从 MXAPIINVBAL 直接拉取货柜库存 (仓库={warehouse})")
    try:
        headers = _get_headers()
    except ValueError as e:
        print(f"[ERROR] 认证失败: {e}")
        return []

    all_data: List[Dict] = []
    where_parts = []
    if warehouse:
        where_parts.append(f'storeloc="{warehouse}"')
    if item_number:
        where_parts.append(f'itemnum="{item_number}"')

    for page in range(1, max_pages + 1):
        print(f"  第 {page}/{max_pages} 页...", end=" ", flush=True)
        params = {
            "oslc.select":  INVBAL_SELECT,
            "oslc.pageSize": page_size,
            "_dropnulls":   0,
            "pageno":       page,
            "oslc.orderBy": "+itemnum,+binnum",
        }
        if where_parts:
            params["oslc.where"] = " and ".join(where_parts)

        try:
            resp = requests.get(
                INVBAL_API_URL,
                headers=headers,
                params=params,
                verify=VERIFY_SSL,
                proxies=settings_manager.get_proxies(),
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                if not resp.content:
                    print("认证过期")
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
                all_data.extend(items)
            elif resp.status_code == 404:
                print("MXAPIINVBAL 端点不存在，请改用 fetch_inventory_with_bins()")
                break
            else:
                print(f"错误 {resp.status_code}")
                break
        except Exception as e:
            print(f"异常: {e}")
            break

        time.sleep(REQUEST_DELAY)

    print(f"[INFO] 共抓取 {len(all_data)} 条货柜库存记录")
    return all_data


def flatten_to_bin_rows(inventory_items: List[Dict]) -> List[Dict]:
    """
    将 MXAPIINVENTORY 返回的物料级数据展开为货柜级别行

    输入：每个 item 含 invbalance 列表
    输出：每行对应一个 (物料, 货柜) 组合

    Returns:
        [{
          'item_number', 'warehouse', 'site',
          'bin_code', 'lot_number', 'quantity',
          'receipt_date', 'issue_date',
          'condition_code',
        }, ...]
    """
    rows = []
    for item in inventory_items:
        item_num  = item.get("itemnum") or ""
        warehouse = item.get("storeloc") or ""
        site      = item.get("siteid") or ""
        bal_list  = item.get("invbalance") or []

        if not bal_list:
            # 无货柜明细 → 仍记录物料总库存（bin_code 留空）
            rows.append({
                "item_number":    item_num,
                "warehouse":      warehouse,
                "site":           site,
                "bin_code":       "",
                "lot_number":     "",
                "quantity":       _safe_float(item.get("curbal")),
                "receipt_date":   None,
                "issue_date":     None,
                "condition_code": "",
            })
        else:
            for bal in bal_list:
                rows.append({
                    "item_number":    item_num,
                    "warehouse":      warehouse,
                    "site":           site,
                    "bin_code":       bal.get("binnum") or "",
                    "lot_number":     bal.get("lotnum") or "",
                    "quantity":       _safe_float(bal.get("curbal")),
                    "receipt_date":   _safe_date(bal.get("receiptdate")),
                    "issue_date":     _safe_date(bal.get("issuedate")),
                    "condition_code": bal.get("conditioncode") or "",
                })
    return rows


def _safe_float(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_date(v) -> Optional[str]:
    if not v:
        return None
    s = str(v)
    return s[:10] if len(s) >= 10 else s
