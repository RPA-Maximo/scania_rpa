"""
供应商账户数据抓取器
从 Maximo MXAPICOMPANY API 拉取供应商编号和供应商名称
用于 vendor 表同步，以及 PO 头供应商/收款方字段的二次填充
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

VENDOR_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIVENDOR"

REQUEST_TIMEOUT = 120

# 供应商同步所需字段
VENDOR_SELECT = "company,name,type,status,currency,url,pluspcustomer"

# PO 头供应商/收款方二次填充所需字段
# 对应 Maximo COMPANIES 对象字段（同时覆盖供应商和收款方公司）
COMPANY_DETAIL_SELECT = (
    "company,name,"
    "address1,address2,"
    "city,stateprovince,zip,country,"
    "phone1,email1,contact"
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


def fetch_company_details_from_api(company_codes: List[str]) -> Dict[str, Any]:
    """
    从 MXAPIVENDOR 批量查询公司详细信息（名称、地址、联系方式）。
    与 fetch_item_specs() 模式相同：按批次查询，结果写入 company_cache 持久化。

    Args:
        company_codes: 公司代码列表（供应商代码 + 收款方代码混合传入均可）

    Returns:
        {company_code: {name, address1, address2, city, stateprovince,
                        zip, country, phone1, email1, contact}}
        查询失败时返回空 dict（不抛异常，只打印警告）。
    """
    if not company_codes:
        return {}

    deduped = list(dict.fromkeys(company_codes))

    try:
        headers = _get_headers()
    except ValueError as e:
        print(f"[WARN] fetch_company_details_from_api: 认证失败，跳过公司详情查询: {e}")
        return {}

    BATCH_SIZE = 20
    result: Dict[str, Any] = {}

    for i in range(0, len(deduped), BATCH_SIZE):
        batch = deduped[i: i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1

        quoted = ",".join(f'"{c}"' for c in batch)
        where_clause = f'company in [{quoted}]'

        params = {
            "oslc.select":   COMPANY_DETAIL_SELECT,
            "oslc.pageSize": len(batch),
            "_dropnulls":    0,
            "oslc.where":    where_clause,
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
            if resp.status_code != 200:
                print(
                    f"[WARN] fetch_company_details_from_api: 批次 {batch_num} "
                    f"HTTP {resp.status_code} — {resp.text[:200]}"
                )
                continue
            data = resp.json()
            members = data.get("member") or data.get("rdfs:member") or []
            if not members:
                print(f"[WARN] fetch_company_details_from_api: 批次 {batch_num} 返回 0 条（codes={batch[:3]}...）")
            for raw in members:
                item = _normalize(raw)
                code = item.get("company")
                if code:
                    result[code] = {
                        "name":          item.get("name")          or None,
                        "address1":      item.get("address1")      or None,
                        "address2":      item.get("address2")      or None,
                        "city":          item.get("city")          or None,
                        "stateprovince": item.get("stateprovince") or None,
                        "zip":           item.get("zip")           or None,
                        "country":       item.get("country")       or None,
                        "phone1":        item.get("phone1")        or None,
                        "email1":        item.get("email1")        or None,
                        "contact":       item.get("contact")       or None,
                    }
        except Exception as e:
            print(f"[WARN] fetch_company_details_from_api: 批次 {batch_num} 异常: {e}")

        time.sleep(REQUEST_DELAY)

    # 写入 company_cache，供下次直接命中
    if result:
        try:
            from src.utils.db import get_connection
            from src.sync.company_cache import upsert_company
            _conn = get_connection()
            _cur = _conn.cursor()
            try:
                for code, detail in result.items():
                    upsert_company(_cur, code, **detail)
                _conn.commit()
            finally:
                _cur.close()
                _conn.close()
            print(f"[INFO] fetch_company_details_from_api: 已缓存 {len(result)} 条公司信息")
        except Exception as e:
            print(f"[WARN] fetch_company_details_from_api: 写入 company_cache 失败: {e}")

    print(f"[INFO] fetch_company_details_from_api: 查询 {len(deduped)} 个公司，获得 {len(result)} 条")
    return result


def fetch_vendor_details(company_codes: List[str]) -> Dict[str, Any]:
    """
    加载公司详细信息（名称、地址、联系方式）。

    优先级：
      1. 本地 company_cache 表（避免重复 API 调用）
      2. MXAPIVENDOR API（缓存未命中时自动查询并回写缓存）

    Args:
        company_codes: 公司代码列表（可混合供应商代码和收款方代码）

    Returns:
        {company_code: {name, address1, address2, city, stateprovince,
                        zip, country, phone1, email1, contact}}
        失败时返回空 dict（不抛异常，只打印警告）。
    """
    if not company_codes:
        return {}

    deduped = list(dict.fromkeys(company_codes))  # 去重，保持顺序

    # 1. 从本地 company_cache 表加载
    result: Dict[str, Any] = {}
    try:
        from src.utils.db import get_connection
        from src.sync.company_cache import load_company_cache
        _cache_conn = get_connection()
        _cache_cur = _cache_conn.cursor()
        try:
            cached = load_company_cache(_cache_cur, deduped)
            result.update(cached)
        finally:
            _cache_cur.close()
            _cache_conn.close()
        print(f"[INFO] fetch_vendor_details: 本地缓存命中 {len(result)}/{len(deduped)} 条")
    except Exception as e:
        print(f"[WARN] fetch_vendor_details: 本地缓存读取失败: {e}")

    # 2. 缓存未命中：直接调 MXAPIVENDOR API（与 fetch_item_specs 模式相同）
    missing_codes = [c for c in deduped if c not in result]
    if missing_codes:
        print(f"[INFO] fetch_vendor_details: 缓存未命中 {len(missing_codes)} 条，查询 MXAPIVENDOR API")
        api_result = fetch_company_details_from_api(missing_codes)
        result.update(api_result)
        still_missing = len([c for c in missing_codes if c not in api_result])
        if still_missing:
            print(f"[INFO] fetch_vendor_details: 仍有 {still_missing} 条 API 未返回，可手动录入 /api/vendor-cache")

    return result
