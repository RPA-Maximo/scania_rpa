"""
出库单（库存使用情况）数据抓取器
从 Maximo MXAPIINVUSAGE API 抓取出库单数据
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

MR_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIINVUSAGE"
REQUEST_TIMEOUT = 120

# 从 Maximo 中选取的字段
# 主表：使用情况号、描述(领取人)、类型、仓库、地点、状态、需求日期、申请号、成本中心、发放目标
# 子表：行号、类型、项目、描述、当前余量、可用量、数量、运输日期、货柜、批号、工单、GL贷方科目、发放目标
MR_HEADER_SELECT = (
    "invusageid,usagenum,description,invuselinetype,status,"
    "storeloc,siteid,requireddate,"
    "requestnum,costcenter,chargeto,"
    "invuseline{"
    "invuselinenum,invuselinetype,itemnum,description,"
    "curbal,availbal,quantity,transdate,"
    "binnum,lotnum,wonum,conditioncode,commoditygroup,"
    "glcreditacct,chargeto,costcenter,"
    # 预留相关字段（来自 添加/修改预留项目 截图）
    "reservenum,reservetype,requestnum,requestline,requireddate,requestby"
    "}"
)


def _normalize(data: dict) -> dict:
    """移除 Maximo 返回数据中的命名空间前缀（spi: 等）"""
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


def fetch_mr_list(
    status_filter: str = "ENTERED,WAPPR",
    max_pages: int = 5,
    page_size: int = 20,
) -> List[Dict[str, Any]]:
    """
    分页抓取出库单列表（库存使用情况）

    Args:
        status_filter: 状态筛选，逗号分隔，如 "ENTERED,WAPPR"
        max_pages:     最多抓取页数
        page_size:     每页条数

    Returns:
        list: 出库单数据列表（已标准化）
    """
    print(f"[INFO] 开始抓取出库单列表 status={status_filter}")
    try:
        headers = _get_headers()
    except ValueError as e:
        print(f"[ERROR] 认证失败: {e}")
        return []

    all_data: List[Dict] = []

    for page in range(1, max_pages + 1):
        print(f"  第 {page}/{max_pages} 页...", end=" ", flush=True)

        # 构造 WHERE 条件（支持多状态）
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
        if statuses:
            where_parts = [f'status="{s}"' for s in statuses]
            where_clause = " or ".join(where_parts)
        else:
            where_clause = None

        params = {
            "oslc.select": MR_HEADER_SELECT,
            "oslc.pageSize": page_size,
            "_dropnulls": 0,
            "pageno": page,
            "oslc.orderBy": "-requireddate",
        }
        if where_clause:
            params["oslc.where"] = where_clause

        try:
            resp = requests.get(
                MR_API_URL,
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

    print(f"[INFO] 共抓取 {len(all_data)} 条出库单")
    return all_data


def fetch_mr_by_number(issue_number: str) -> Optional[Dict[str, Any]]:
    """
    根据出库单号（usagenum）查询单条出库单

    Args:
        issue_number: Maximo 使用情况号，如 '4988'

    Returns:
        dict | None
    """
    print(f"  查询出库单: {issue_number}...", end=" ", flush=True)
    try:
        headers = _get_headers()
    except ValueError:
        print("认证失败")
        return None

    params = {
        "oslc.select": MR_HEADER_SELECT,
        "oslc.where": f'usagenum="{issue_number}"',
        "_dropnulls": 0,
    }

    try:
        resp = requests.get(
            MR_API_URL,
            headers=headers,
            params=params,
            verify=VERIFY_SSL,
            proxies=settings_manager.get_proxies(),
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("member") or data.get("rdfs:member") or []
            if items:
                print("✓")
                return _normalize(items[0])
            print("未找到")
            return None
        print(f"错误 {resp.status_code}")
        return None
    except Exception as e:
        print(f"异常: {e}")
        return None


def create_remaining_usage_via_api(maximo_href: str) -> Optional[Dict]:
    """
    通过 Maximo OSLC wsmethod 触发"创建剩余余量使用情况"操作

    对应 Maximo UI 中的 更多操作 → 创建剩余余量使用情况。
    Maximo 会自动计算剩余数量（申请量 - 实际出库量）并创建新的使用情况记录。

    Args:
        maximo_href: 原出库单的 Maximo href 链接

    Returns:
        dict: 新创建的使用情况数据（含新 usagenum），失败返回 None

    注意：wsmethod 名称 'createRemaining' 为推断值，若报 400/404 需由
         Maximo 管理员在 Application Designer 中确认 Action 名称。
    """
    print(f"  调用 wsmethod:createRemaining → {maximo_href[:80]}...")
    try:
        headers = _get_headers()
    except ValueError as e:
        print(f"认证失败: {e}")
        return None

    action_url = maximo_href + "?action=wsmethod:createRemaining"
    patch_headers = {
        **headers,
        "Content-Type": "application/json",
        "x-method-override": "PATCH",
        "patchtype": "MERGE",
    }

    try:
        resp = requests.post(
            action_url,
            headers=patch_headers,
            json={},
            verify=VERIFY_SSL,
            proxies=settings_manager.get_proxies(),
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            result = resp.json()
            new_num = result.get("usagenum") or result.get("spi:usagenum") or ""
            print(f"✓ 创建剩余成功，新流水号: {new_num}")
            return _normalize(result)
        print(f"wsmethod 失败 {resp.status_code}: {resp.text[:300]}")
        return None
    except Exception as e:
        print(f"异常: {e}")
        return None


def create_mr_in_maximo(
    issue_number: str,
    warehouse: str,
    usage_type: str,
    lines: List[Dict],
) -> Optional[Dict]:
    """
    在 Maximo 创建出库单（当 WMS 出库数量未满足时，创建剩余使用情况）

    Args:
        issue_number: 原出库单号（用于关联）
        warehouse:    仓库编码
        usage_type:   使用情况类型（ISSUE）
        lines:        子表行数据列表，每行 {'itemnum', 'quantity', 'binnum', 'wonum'}

    Returns:
        dict: Maximo 响应数据（含新流水号）
    """
    print(f"  在 Maximo 创建剩余出库单 (原: {issue_number})...")
    try:
        headers = _get_headers()
    except ValueError as e:
        print(f"认证失败: {e}")
        return None

    payload = {
        "spi:invuselinetype": usage_type,
        "spi:storeloc": warehouse,
        "spi:invuseline": [
            {
                "spi:itemnum": line["itemnum"],
                "spi:quantity": line["quantity"],
                "spi:binnum": line.get("binnum", ""),
                "spi:wonum": line.get("wonum", ""),
            }
            for line in lines
        ],
    }

    headers_post = {
        **headers,
        "Content-Type": "application/json",
        "x-method-override": "PATCH",
        "patchtype": "MERGE",
    }

    try:
        resp = requests.post(
            MR_API_URL,
            headers=headers_post,
            json=payload,
            verify=VERIFY_SSL,
            proxies=settings_manager.get_proxies(),
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            result = resp.json()
            print(f"✓ 创建成功")
            return _normalize(result)
        print(f"错误 {resp.status_code}: {resp.text[:300]}")
        return None
    except Exception as e:
        print(f"异常: {e}")
        return None


def writeback_to_maximo(
    maximo_href: str,
    lines: List[Dict],
    save_and_complete: bool = True,
) -> bool:
    """
    将出库数量回传到 Maximo 并保存（可选择变更状态为完成）

    Args:
        maximo_href:       Maximo 资源 href 链接
        lines:             子表更新数据 {'maximo_lineid', 'quantity', 'binnum'}
        save_and_complete: True 则保存后将状态变更为完成

    Returns:
        bool: 是否成功
    """
    print(f"  回传 Maximo: {maximo_href}")
    try:
        headers = _get_headers()
    except ValueError:
        print("认证失败")
        return False

    payload = {
        "spi:invuseline": [
            {
                "spi:invuselinenum": line["maximo_lineid"],
                "spi:quantity": line["quantity"],
                "spi:binnum": line.get("binnum", ""),
            }
            for line in lines
        ]
    }

    patch_headers = {
        **headers,
        "Content-Type": "application/json",
        "x-method-override": "PATCH",
        "patchtype": "MERGE",
    }

    try:
        resp = requests.post(
            maximo_href,
            headers=patch_headers,
            json=payload,
            verify=VERIFY_SSL,
            proxies=settings_manager.get_proxies(),
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code in (200, 204):
            print("✓ 回传成功")
            if save_and_complete:
                return _change_status_to_complete(maximo_href, headers)
            return True
        print(f"回传失败 {resp.status_code}: {resp.text[:300]}")
        return False
    except Exception as e:
        print(f"异常: {e}")
        return False


def _change_status_to_complete(maximo_href: str, headers: dict) -> bool:
    """将使用情况状态变更为完成（COMPLETE）"""
    action_url = maximo_href + "?action=wsmethod:changeStatus"
    payload = {"spi:status": "COMPLETE"}
    patch_headers = {
        **headers,
        "Content-Type": "application/json",
        "x-method-override": "PATCH",
        "patchtype": "MERGE",
    }
    try:
        resp = requests.post(
            action_url,
            headers=patch_headers,
            json=payload,
            verify=VERIFY_SSL,
            proxies=settings_manager.get_proxies(),
            timeout=REQUEST_TIMEOUT,
        )
        ok = resp.status_code in (200, 204)
        print(f"  状态变更为完成: {'✓' if ok else f'失败 {resp.status_code}'}")
        return ok
    except Exception as e:
        print(f"  状态变更异常: {e}")
        return False
