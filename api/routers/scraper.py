"""
爬虫 API 路由

通过 API 触发 Maximo 数据抓取，支持自定义参数。
认证信息从内存中的 auth_manager 获取，无需手动修改文件。
"""
import sys
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import urllib3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.auth_manager import auth_manager
from config.settings import (
    MAXIMO_BASE_URL,
    MAXIMO_API_URL,
    DEFAULT_HEADERS,
    VERIFY_SSL,
    PROXIES,
    RAW_DATA_DIR,
    REQUEST_DELAY,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(prefix="/api/scraper", tags=["爬虫"])

# 线程池：运行同步 requests 代码，避免阻塞事件循环
_executor = ThreadPoolExecutor(max_workers=2)

PO_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIPO"
REQUEST_TIMEOUT = 120


# ------------------------------------------------------------------
# 请求模型
# ------------------------------------------------------------------

class POScrapeRequest(BaseModel):
    po_numbers: Optional[List[str]] = Field(
        None,
        description="指定查询的订单号列表，如 ['CN5123', 'CN5121']。"
                    "为空则按 status_filter / max_pages 分页查询",
    )
    status_filter: Optional[str] = Field(
        None,
        description="按状态筛选（分页查询时有效），如 'APPR'、'DRAFT'、'CALLOFF'",
    )
    max_pages: int = Field(1, description="最大查询页数（分页查询时有效）", ge=1, le=50)
    page_size: int = Field(20, description="每页条数", ge=1, le=100)


class InventoryScrapeRequest(BaseModel):
    max_pages: int = Field(3, description="最大抓取页数", ge=1, le=50)
    page_size: int = Field(20, description="每页条数", ge=1, le=100)
    status_filter: Optional[str] = Field(
        None,
        description="状态筛选。为空时自动排除 OBSOLETE 状态",
    )
    item_num_min: Optional[str] = Field(
        None,
        description="物料编号起始值筛选，如 '20326793'",
    )
    order_by: str = Field(
        "+itemnum",
        description="排序字段。前缀 + 升序，- 降序，如 '+itemnum'、'-statusdate'",
    )


# ------------------------------------------------------------------
# 同步爬虫函数（在线程池中执行）
# ------------------------------------------------------------------

def _make_headers() -> dict:
    """构建带认证信息的请求头"""
    auth = auth_manager.get_auth()
    return {
        **DEFAULT_HEADERS,
        'Cookie': auth['cookie'],
        'x-csrf-token': auth['csrf_token'],
    }


def _run_po_scraper(req: POScrapeRequest) -> dict:
    """采购订单爬虫（同步）"""
    import requests
    import pandas as pd

    try:
        headers = _make_headers()
    except ValueError as e:
        return {'success': False, 'message': str(e)}

    all_data = []

    if req.po_numbers:
        # 按订单号逐个查询
        for po_num in req.po_numbers:
            params = {
                'oslc.select': '*',
                'oslc.where': f'ponum="{po_num}"',
                '_dropnulls': 0,
            }
            try:
                resp = requests.get(
                    PO_API_URL,
                    headers=headers,
                    params=params,
                    verify=VERIFY_SSL,
                    proxies=PROXIES,
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code == 200:
                    items = resp.json().get('member') or resp.json().get('rdfs:member') or []
                    all_data.extend(items)
                elif resp.status_code == 401:
                    return {
                        'success': False,
                        'message': '认证失败（401），请通过 POST /api/auth/curl 更新认证信息',
                    }
            except requests.exceptions.Timeout:
                return {'success': False, 'message': f'请求超时（>{REQUEST_TIMEOUT}s）'}
            except Exception as e:
                return {'success': False, 'message': f'请求异常: {e}'}
            time.sleep(REQUEST_DELAY)

    else:
        # 分页查询
        for page in range(1, req.max_pages + 1):
            params = {
                'oslc.select': '*',
                'oslc.pageSize': req.page_size,
                '_dropnulls': 0,
                'pageno': page,
                'oslc.orderBy': '-statusdate',
            }
            if req.status_filter:
                params['oslc.where'] = f'status="{req.status_filter}"'

            try:
                resp = requests.get(
                    PO_API_URL,
                    headers=headers,
                    params=params,
                    verify=VERIFY_SSL,
                    proxies=PROXIES,
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code == 200:
                    items = resp.json().get('member') or resp.json().get('rdfs:member') or []
                    if not items:
                        break
                    all_data.extend(items)
                elif resp.status_code == 401:
                    return {
                        'success': False,
                        'message': '认证失败（401），请通过 POST /api/auth/curl 更新认证信息',
                    }
                else:
                    return {'success': False, 'message': f'请求失败: HTTP {resp.status_code}'}
            except requests.exceptions.Timeout:
                return {'success': False, 'message': f'请求超时（>{REQUEST_TIMEOUT}s）'}
            except Exception as e:
                return {'success': False, 'message': f'请求异常: {e}'}
            time.sleep(REQUEST_DELAY)

    if not all_data:
        return {'success': False, 'message': '未获取到数据，请检查查询条件或认证信息'}

    import pandas as pd
    df = pd.DataFrame(all_data)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = RAW_DATA_DIR / f"purchase_orders_{timestamp}.xlsx"
    df.to_excel(filepath, index=False)

    return {
        'success': True,
        'total': len(all_data),
        'file': str(filepath),
        'message': f'共获取 {len(all_data)} 条采购订单，已保存到 {filepath}',
    }


def _run_inventory_scraper(req: InventoryScrapeRequest) -> dict:
    """库存数据爬虫（同步）"""
    import requests
    import pandas as pd

    try:
        headers = _make_headers()
    except ValueError as e:
        return {'success': False, 'message': str(e)}

    # 构建 OSLC where 条件
    where_parts = []
    if req.status_filter:
        where_parts.append(f'status="{req.status_filter}"')
    else:
        where_parts.append('status!="OBSOLETE"')
    if req.item_num_min:
        where_parts.append(f'itemnum>="{req.item_num_min}"')

    all_data = []
    for page in range(1, req.max_pages + 1):
        params = {
            'oslc.select': '*',
            'oslc.pageSize': req.page_size,
            '_dropnulls': 1,
            'pageno': page,
            'oslc.orderBy': req.order_by,
            'oslc.where': ' and '.join(where_parts),
        }
        try:
            resp = requests.get(
                MAXIMO_API_URL,
                headers=headers,
                params=params,
                verify=VERIFY_SSL,
                proxies=PROXIES,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                items = resp.json().get('member') or resp.json().get('rdfs:member') or []
                if not items:
                    break
                all_data.extend(items)
            elif resp.status_code == 401:
                return {
                    'success': False,
                    'message': '认证失败（401），请通过 POST /api/auth/curl 更新认证信息',
                }
            else:
                return {'success': False, 'message': f'请求失败: HTTP {resp.status_code}'}
        except requests.exceptions.Timeout:
            return {'success': False, 'message': f'请求超时（>{REQUEST_TIMEOUT}s）'}
        except Exception as e:
            return {'success': False, 'message': f'请求异常: {e}'}
        time.sleep(REQUEST_DELAY)

    if not all_data:
        return {'success': False, 'message': '未获取到数据，请检查查询条件或认证信息'}

    df = pd.DataFrame(all_data).astype(str)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = RAW_DATA_DIR / f"inventory_{timestamp}.xlsx"
    df.to_excel(filepath, index=False)

    return {
        'success': True,
        'total': len(all_data),
        'file': str(filepath),
        'message': f'共获取 {len(all_data)} 条库存数据，已保存到 {filepath}',
    }


# ------------------------------------------------------------------
# API 端点
# ------------------------------------------------------------------

@router.post("/po", summary="抓取采购订单")
async def scrape_purchase_orders(request: POScrapeRequest):
    """
    抓取 Maximo 采购订单数据并保存为 Excel。

    **两种模式：**
    - 提供 `po_numbers`：按订单号批量精确查询
    - 不提供 `po_numbers`：按 `status_filter` 分页查询，最多 `max_pages` 页

    认证信息自动从内存获取，若未配置请先调用 `POST /api/auth/curl`。
    """
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, _run_po_scraper, request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"爬虫异常: {e}")
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('message', '爬虫失败'))
    return result


@router.post("/inventory", summary="抓取库存数据")
async def scrape_inventory(request: InventoryScrapeRequest):
    """
    抓取 Maximo 库存数据并保存为 Excel。

    **可配置参数：**
    - `max_pages`：最大页数
    - `page_size`：每页条数
    - `status_filter`：状态筛选（不填则自动排除 OBSOLETE）
    - `item_num_min`：物料编号起始值
    - `order_by`：排序字段（`+itemnum`、`-statusdate` 等）

    认证信息自动从内存获取，若未配置请先调用 `POST /api/auth/curl`。
    """
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, _run_inventory_scraper, request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"爬虫异常: {e}")
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('message', '爬虫失败'))
    return result
