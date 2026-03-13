"""
供应商/公司信息 RPA 抓取模块

功能：
- 从 Maximo Companies 页面（浏览器 UI）抓取公司详情
- 作为 MXAPIVENDOR API 权限不足时的备用数据源（Stage 3 fallback）
- 批量抓取多个公司代码，结果自动写入 company_cache 表

用法：
    from rpa.vendor_operations import rpa_fetch_vendor_details
    result = rpa_fetch_vendor_details(['8970301', 'BILLTOCHINA'])
    # result = {'8970301': {'name': ..., 'address1': ..., ...}, ...}

LLM 提示：
- Maximo Companies 应用 URL: {base}/ui/?event=loadapp&value=COMPANIES
- QBE 搜索参数: additionalevent=useqbe&additionaleventvalue=company%3D"CODE"
- 字段 ID 模式: [session_hash]_[fieldname]_txt-tb (部分 ID 匹配)
"""
import asyncio
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import Frame, Page

from .browser import connect_to_browser, _find_main_frame
from .logger import logger

# Maximo Companies 应用名称
COMPANIES_APP = "COMPANIES"

# 等待时间（秒）
_WAIT_LOAD = 4.0       # 页面加载等待
_WAIT_SHORT = 1.0      # 短等待

# 需要提取的字段及其在 Maximo 页面中的 ID 关键字
# 格式: {db字段名: [ID关键词列表，优先级从高到低]}
_FIELD_ID_KEYWORDS: Dict[str, List[str]] = {
    "name":          ["_name_", "compname"],
    "address1":      ["_address1_", "_addr1_"],
    "address2":      ["_address2_", "_addr2_"],
    "city":          ["_city_"],
    "stateprovince": ["_stateprovince_", "_state_", "_province_"],
    "zip":           ["_zip_", "_postalcode_", "_postal_"],
    "country":       ["_country_"],
    "phone1":        ["_phone1_", "_phone_"],
    "email1":        ["_email1_", "_email_"],
    "contact":       ["_contact_"],
}


# ── 工具函数 ────────────────────────────────────────────────────────────────


def _get_maximo_base_url(page_url: str) -> Optional[str]:
    """从当前 URL 提取 Maximo base URL"""
    match = re.match(r"(https?://[^/]+/maximo)", page_url)
    return match.group(1) if match else None


async def _wait_for_companies_page(frame: Frame, timeout: float = 10.0) -> bool:
    """
    轮询等待 Companies 详情页加载完成。
    判断依据：页面中存在 company 字段的 input 元素。
    """
    interval = 0.5
    waited = 0.0
    while waited < timeout:
        found = await frame.evaluate("""
            () => {
                // 检查是否有 company 相关的 input 元素（详情页标志）
                const inputs = document.querySelectorAll('input[type="text"], input[role="textbox"]');
                for (const inp of inputs) {
                    const id = (inp.id || '').toLowerCase();
                    if (id.includes('company') || id.includes('compobj') || id.includes('_c_co')) {
                        return true;
                    }
                }
                // 也接受只读 span 形式（某些字段只读时以 span 渲染）
                const spans = document.querySelectorAll('span[id*="company"]');
                return spans.length > 0;
            }
        """)
        if found:
            return True
        await asyncio.sleep(interval)
        waited += interval
    return False


async def _navigate_to_company_qbe(page: Page, maximo_base: str, company_code: str) -> Frame:
    """
    使用 QBE URL 导航到指定公司代码的详情页。
    返回更新后的 main_frame（页面跳转后 frame 引用会更新）。

    QBE URL 格式：
      {base}/ui/?event=loadapp&value=COMPANIES
             &additionalevent=useqbe
             &additionaleventvalue=company%3D"CODE"
    """
    encoded_code = quote(f'"{company_code}"', safe="")
    target_url = (
        f"{maximo_base}/ui/"
        f"?event=loadapp&value={COMPANIES_APP}"
        f"&additionalevent=useqbe"
        f"&additionaleventvalue=company%3D{encoded_code}"
    )
    logger.debug(f"导航到 Companies QBE: {company_code} -> {target_url}")
    await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(_WAIT_LOAD)
    return _find_main_frame(page)


async def _extract_field_value(frame: Frame, field_keywords: List[str]) -> Optional[str]:
    """
    按关键词列表尝试从 Maximo 页面提取字段值。
    支持 input（可编辑/只读）和 span（只读显示）两种渲染方式。

    Args:
        frame:          当前 Playwright frame
        field_keywords: 部分 ID 匹配关键词，优先级从高到低

    Returns:
        字段值字符串，未找到返回 None
    """
    keywords_json = str(field_keywords).replace("'", '"')
    value = await frame.evaluate(f"""
        (keywords) => {{
            for (const kw of keywords) {{
                // 1. 优先找可编辑 input（value 属性）
                const inputs = document.querySelectorAll('input[type="text"], input[role="textbox"]');
                for (const inp of inputs) {{
                    if ((inp.id || '').toLowerCase().includes(kw.toLowerCase())) {{
                        const val = (inp.value || '').trim();
                        if (val) return val;
                    }}
                }}
                // 2. 只读 input（readonly 属性）
                const readonlyInputs = document.querySelectorAll('input[readonly]');
                for (const inp of readonlyInputs) {{
                    if ((inp.id || '').toLowerCase().includes(kw.toLowerCase())) {{
                        const val = (inp.value || '').trim();
                        if (val) return val;
                    }}
                }}
                // 3. span 元素（只读文本渲染）
                const spans = document.querySelectorAll('span[id]');
                for (const span of spans) {{
                    if ((span.id || '').toLowerCase().includes(kw.toLowerCase())) {{
                        const val = (span.textContent || '').trim();
                        if (val && val !== '\\u00a0') return val;  // 排除 &nbsp;
                    }}
                }}
            }}
            return null;
        }},
        {keywords_json}
    """)
    return value if value else None


async def _extract_company_detail(frame: Frame, company_code: str) -> Dict[str, Optional[str]]:
    """
    从当前页面的 Companies 详情提取所有字段值。

    Returns:
        {field_name: value_or_None}
    """
    result: Dict[str, Optional[str]] = {}
    for field_name, keywords in _FIELD_ID_KEYWORDS.items():
        value = await _extract_field_value(frame, keywords)
        result[field_name] = value
        if value:
            logger.debug(f"  {company_code}.{field_name} = {value!r}")

    return result


async def _is_no_result_page(frame: Frame, company_code: str) -> bool:
    """
    判断页面是否为空结果页（未找到该公司代码）。
    Maximo 无结果时通常显示 "No records found" 或类似消息。
    """
    text = await frame.evaluate("""
        () => document.body ? document.body.innerText : ''
    """)
    text_lower = (text or "").lower()
    # 常见的无结果提示
    no_result_signals = [
        "no records found",
        "bmxaa1081e",   # Maximo 无记录错误码
        "0 of 0",
        "没有记录",
        "无记录",
    ]
    return any(sig in text_lower for sig in no_result_signals)


async def _check_record_list_and_click(frame: Frame, company_code: str) -> bool:
    """
    如果 QBE 返回了多条记录（列表视图），点击匹配 company_code 的记录。
    Returns True if clicked successfully, False if already on detail page or not found.
    """
    clicked = await frame.evaluate(f"""
        (code) => {{
            // 在列表中找与 company_code 完全匹配的 span/a 元素
            const spans = document.querySelectorAll('span[mxevent="click"], a[mxevent="click"]');
            for (const el of spans) {{
                if (el.textContent.trim() === code) {{
                    el.click();
                    return true;
                }}
            }}
            // 也检查 td 中的文本
            const tds = document.querySelectorAll('td');
            for (const td of tds) {{
                if (td.textContent.trim() === code) {{
                    const link = td.querySelector('a, span[mxevent]');
                    if (link) {{
                        link.click();
                        return true;
                    }}
                    td.click();
                    return true;
                }}
            }}
            return false;
        }},
        "{company_code}"
    """)
    if clicked:
        await asyncio.sleep(_WAIT_LOAD)
        logger.debug(f"点击了列表中的 {company_code} 记录")
    return clicked


# ── 核心批量抓取函数 ──────────────────────────────────────────────────────


async def fetch_company_details_via_rpa(
    company_codes: List[str],
    cdp_url: Optional[str] = None,
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    通过 Playwright 浏览器 RPA 批量抓取公司详情。

    Args:
        company_codes: 公司代码列表（供应商代码 + billto 代码）
        cdp_url:       Chrome DevTools Protocol URL（None 时使用配置文件中的值）

    Returns:
        {company_code: {name, address1, address2, city, stateprovince,
                        zip, country, phone1, email1, contact}}
        失败的代码不会出现在结果中。
    """
    if not company_codes:
        return {}

    from config.browser import CDP_URL as _CDP_URL
    cdp_url = cdp_url or _CDP_URL

    result: Dict[str, Dict[str, Optional[str]]] = {}
    failed_codes: List[str] = []

    try:
        p, browser, page, frame = await connect_to_browser(cdp_url)
    except Exception as e:
        logger.warning(f"[RPA] 无法连接浏览器，跳过公司信息抓取: {e}")
        return {}

    try:
        maximo_base = _get_maximo_base_url(page.url)
        if not maximo_base:
            logger.warning("[RPA] 无法获取 Maximo base URL，跳过公司信息抓取")
            return {}

        logger.info(f"[RPA] 开始抓取 {len(company_codes)} 个公司信息: {company_codes}")

        for company_code in company_codes:
            logger.info(f"[RPA] 抓取公司: {company_code}")
            try:
                # 1. 通过 QBE URL 导航到该公司
                frame = await _navigate_to_company_qbe(page, maximo_base, company_code)

                # 2. 检查是否无结果
                if await _is_no_result_page(frame, company_code):
                    logger.warning(f"[RPA] 公司 {company_code} 无记录")
                    failed_codes.append(company_code)
                    continue

                # 3. 如果是列表视图（多条记录），点击目标记录
                on_detail = await _wait_for_companies_page(frame, timeout=2.0)
                if not on_detail:
                    clicked = await _check_record_list_and_click(frame, company_code)
                    if clicked:
                        # 重新获取 frame（页面可能刷新）
                        frame = _find_main_frame(page)
                        on_detail = await _wait_for_companies_page(frame, timeout=_WAIT_LOAD)

                if not on_detail:
                    logger.warning(f"[RPA] 公司 {company_code} 页面未能加载详情")
                    failed_codes.append(company_code)
                    continue

                # 4. 提取字段值
                detail = await _extract_company_detail(frame, company_code)
                found_count = sum(1 for v in detail.values() if v)
                logger.info(f"[RPA] {company_code}: 获取到 {found_count}/{len(_FIELD_ID_KEYWORDS)} 个字段")

                result[company_code] = detail

            except Exception as e:
                logger.warning(f"[RPA] 抓取公司 {company_code} 失败: {e}")
                failed_codes.append(company_code)

            # 短暂等待，避免请求过快
            await asyncio.sleep(_WAIT_SHORT)

    finally:
        try:
            await p.stop()
        except Exception:
            pass

    if failed_codes:
        logger.warning(f"[RPA] 以下公司未能抓取: {failed_codes}")

    logger.info(f"[RPA] 共抓取 {len(result)}/{len(company_codes)} 个公司")
    return result


# ── 同步包装器（供非异步调用方使用）────────────────────────────────────────


def rpa_fetch_vendor_details(
    company_codes: List[str],
    write_to_cache: bool = True,
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    同步入口：通过 RPA 批量抓取公司详情，结果自动写入 company_cache。

    Args:
        company_codes:  公司代码列表
        write_to_cache: 是否将结果写入 company_cache 表（默认 True）

    Returns:
        {company_code: {name, address1, address2, city, stateprovince,
                        zip, country, phone1, email1, contact}}
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("event loop is closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            fetch_company_details_via_rpa(company_codes)
        )
    except Exception as e:
        logger.warning(f"[RPA] 同步包装器异常: {e}")
        return {}

    # 将结果写入 company_cache（避免下次重复抓取）
    if write_to_cache and result:
        try:
            from src.utils.db import get_connection
            from src.sync.company_cache import upsert_company
            conn = get_connection()
            cur = conn.cursor()
            try:
                for code, detail in result.items():
                    upsert_company(cur, code, **{k: v for k, v in detail.items() if v is not None})
                conn.commit()
                logger.info(f"[RPA] 已将 {len(result)} 条公司信息写入 company_cache")
            finally:
                cur.close()
                conn.close()
        except Exception as e:
            logger.warning(f"[RPA] 写入 company_cache 失败: {e}")

    return result
