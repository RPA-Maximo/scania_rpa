"""
物料主数据抓取器
从 Maximo MXAPIITEM API 拉取物料信息
用于 material 表增量/全量同步
"""
import sys
from pathlib import Path
import time
from datetime import datetime
from typing import List, Optional, Dict, Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import urllib3
from config import get_maximo_auth, DEFAULT_HEADERS
from config.settings import MAXIMO_BASE_URL, REQUEST_DELAY, VERIFY_SSL
from config.settings_manager import settings_manager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ITEM_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIITEM"

REQUEST_TIMEOUT = 120

# 同步所需字段（客户后续补充时在此追加）
# changedate = Maximo 物料最近更新时间，用于增量过滤
ITEM_SELECT = (
    "itemnum,description,orderunit,"
    "issueunit,status,lottype,"
    "changedate"
    # 待客户补充字段，例如：
    # ",cxsapmat,manufacturer,commoditygroup"
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


def fetch_items(
    since_date: Optional[datetime] = None,
    item_numbers: Optional[List[str]] = None,
    max_pages: int = 100,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """
    从 MXAPIITEM 分页拉取物料主数据

    Args:
        since_date:    增量起始时间（筛选 changedate >= since_date）；None 表示全量
        item_numbers:  指定物料编号列表；None 表示全部
        max_pages:     最多抓取页数
        page_size:     每页条数

    Returns:
        标准化后的物料列表
    """
    since_str = since_date.strftime("%Y-%m-%dT%H:%M:%S+00:00") if since_date else None
    print(
        f"[INFO] 开始抓取物料主数据 "
        f"(since={since_str or '全量'}, max_pages={max_pages})"
    )

    try:
        headers = _get_headers()
    except ValueError as e:
        print(f"[ERROR] 认证失败: {e}")
        return []

    all_data: List[Dict] = []

    for page in range(1, max_pages + 1):
        print(f"  第 {page}/{max_pages} 页...", end=" ", flush=True)

        where_parts = ['status!="OBSOLETE"']
        if since_date:
            where_parts.append(f'changedate>="{since_str}"')
        if item_numbers:
            item_clause = " or ".join(f'itemnum="{n}"' for n in item_numbers)
            where_parts.append(f"({item_clause})")

        params = {
            "oslc.select":   ITEM_SELECT,
            "oslc.pageSize": page_size,
            "_dropnulls":    0,
            "pageno":        page,
            "oslc.orderBy":  "+itemnum",
            "oslc.where":    " and ".join(where_parts),
        }

        try:
            resp = requests.get(
                ITEM_API_URL,
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

                # 如果返回条数少于 page_size，说明已是最后一页
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

    print(f"[INFO] 共抓取 {len(all_data)} 条物料记录")
    return all_data
