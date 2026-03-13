"""
从 Maximo 采购单页面通过 RPA 抓取供应商/收款方信息

数据来源（对应截图）：
  - PO 标签页 → 供应商信息区：公司名、地址、城市、邮编、电话
  - 收货方/收款人 标签页 → 收款方区：公司名、地址、城市、邮编

使用方式：
    from rpa.po_vendor_scraper import rpa_scrape_vendor_from_po
    result = rpa_scrape_vendor_from_po(
        vendor_po_map  = {'8970301': 'CN5074', ...},
        billto_po_map  = {'BILLTOCHINA': 'CN5074', ...},
    )
    # result = {
    #   '8970301':    {'name': 'ATLAS COPCO ...', 'address1': 'BUILDING 26', ...},
    #   'BILLTOCHINA': {'name': 'Scania Production ...', 'city': 'Rugao City', ...},
    # }
"""
import asyncio
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import Frame, Page

from .browser import connect_to_browser, _find_main_frame
from .logger import logger

# 等待时间
_WAIT_PAGE = 4.0
_WAIT_TAB  = 2.0

# ── PO 标签页：供应商信息字段 ID 关键词 ─────────────────────────────────────
# Maximo PO 页面供应商字段的部分 ID 关键词（不含 hash 前缀）
_SUPPLIER_FIELDS: Dict[str, List[str]] = {
    "name":     ["_vendorname_", "_venname_", "venname"],
    "address1": ["_venaddress1_", "_venaddr1_"],
    "address2": ["_venaddress2_", "_venaddr2_"],
    "city":     ["_vencity_"],
    "zip":      ["_venzip_", "_venpostalcode_"],
    "phone1":   ["_venphone_", "_venphone1_"],
    "contact":  ["_vencontact_"],
    "email1":   ["_venemail_", "_venemail1_"],
}

# ── 收货方/收款人 标签页：收款方字段 ID 关键词 ──────────────────────────────
_BILLTO_FIELDS: Dict[str, List[str]] = {
    "name":     ["_billtocomp_", "_billtoname_"],
    "address1": ["_billtoaddress1_", "_billtoaddr1_"],
    "address2": ["_billtoaddress2_", "_billtoaddr2_"],
    "city":     ["_billtocity_"],
    "zip":      ["_billtozip_", "_billtopostalcode_"],
    "contact":  ["_billtocontact_"],
    "phone1":   ["_billtophone_"],
}


def _get_maximo_base(url: str) -> Optional[str]:
    m = re.match(r"(https?://[^/]+/maximo)", url)
    return m.group(1) if m else None


async def _navigate_to_po(page: Page, maximo_base: str, po_number: str) -> Frame:
    """导航到指定采购单的详情页（PO 标签页）。"""
    encoded = quote(f'"{po_number}"', safe="")
    url = (
        f"{maximo_base}/ui/"
        f"?event=loadapp&value=PO"
        f"&additionalevent=useqbe"
        f"&additionaleventvalue=ponum%3D{encoded}"
    )
    logger.debug(f"[PO抓取] 导航到采购单: {po_number}")
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(_WAIT_PAGE)
    return _find_main_frame(page)


async def _read_field(frame: Frame, keywords: List[str]) -> Optional[str]:
    """按关键词列表从页面提取字段值（input/span 两种渲染均支持）。"""
    kw_json = str(keywords).replace("'", '"')
    value = await frame.evaluate(f"""
        (keywords) => {{
            for (const kw of keywords) {{
                const kl = kw.toLowerCase();
                // 可编辑 input
                for (const el of document.querySelectorAll('input[type="text"], input[role="textbox"]')) {{
                    if ((el.id || '').toLowerCase().includes(kl)) {{
                        const v = (el.value || '').trim();
                        if (v) return v;
                    }}
                }}
                // 只读 input
                for (const el of document.querySelectorAll('input[readonly]')) {{
                    if ((el.id || '').toLowerCase().includes(kl)) {{
                        const v = (el.value || '').trim();
                        if (v) return v;
                    }}
                }}
                // span 文本
                for (const el of document.querySelectorAll('span[id]')) {{
                    if ((el.id || '').toLowerCase().includes(kl)) {{
                        const v = (el.textContent || '').trim().replace(/\\u00a0/g, '');
                        if (v) return v;
                    }}
                }}
            }}
            return null;
        }},
        {kw_json}
    """)
    return value or None


async def _click_tab(frame: Frame, tab_keywords: List[str]) -> bool:
    """点击页面顶部指定标签页（通过文本/ID 匹配）。"""
    clicked = await frame.evaluate(f"""
        (keywords) => {{
            const candidates = document.querySelectorAll(
                'button[role="tab"], a[role="tab"], li[role="tab"], [class*="tab"]'
            );
            for (const el of candidates) {{
                const text = (el.textContent || el.innerText || '').trim();
                const id   = (el.id || '').toLowerCase();
                for (const kw of keywords) {{
                    if (text.includes(kw) || id.includes(kw.toLowerCase())) {{
                        el.click();
                        return true;
                    }}
                }}
            }}
            // fallback: any clickable element containing the keyword text
            for (const kw of keywords) {{
                const xpath = `//*[contains(text(),'${{kw}}')]`;
                const result = document.evaluate(xpath, document, null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                const node = result.singleNodeValue;
                if (node) {{ node.click(); return true; }}
            }}
            return false;
        }},
        {str(tab_keywords).replace("'", '"')}
    """)
    if clicked:
        await asyncio.sleep(_WAIT_TAB)
    return bool(clicked)


async def _scrape_po_supplier(frame: Frame) -> Dict[str, Optional[str]]:
    """从 PO 标签页抓取供应商信息。"""
    result = {}
    for field, keywords in _SUPPLIER_FIELDS.items():
        result[field] = await _read_field(frame, keywords)
    return result


async def _scrape_po_billto(frame: Frame) -> Dict[str, Optional[str]]:
    """切换到收货方/收款人标签页，抓取收款方（billto）信息。"""
    # 尝试点击"收货方/收款人"标签
    clicked = await _click_tab(frame, ["收货方", "收款人", "shipbill", "ShipBill"])
    if not clicked:
        logger.warning("[PO抓取] 未找到收货方/收款人标签页")

    result = {}
    for field, keywords in _BILLTO_FIELDS.items():
        result[field] = await _read_field(frame, keywords)
    return result


# ── 核心批量抓取 ─────────────────────────────────────────────────────────────

async def _fetch_all(
    vendor_po_map: Dict[str, str],
    billto_po_map: Dict[str, str],
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    异步核心：遍历 PO，抓取供应商 + 收款方信息。

    Args:
        vendor_po_map:  {vendor_code: po_number}  — 每个供应商代码找一张代表 PO
        billto_po_map:  {billto_code:  po_number}  — 每个收款方代码找一张代表 PO

    Returns:
        {company_code: {name, address1, address2, city, zip, phone1, contact, email1}}
    """
    from config.browser import CDP_URL
    try:
        p, browser, page, frame = await connect_to_browser(CDP_URL)
    except Exception as e:
        logger.warning(f"[PO抓取] 浏览器未启动，跳过供应商信息抓取: {e}")
        return {}

    result: Dict[str, Dict] = {}
    maximo_base = _get_maximo_base(page.url)
    if not maximo_base:
        logger.warning("[PO抓取] 无法获取 Maximo base URL")
        await p.stop()
        return {}

    # ── 供应商（PO 标签页）─────────────────────────────────
    for vendor_code, po_num in vendor_po_map.items():
        try:
            frame = await _navigate_to_po(page, maximo_base, po_num)
            detail = await _scrape_po_supplier(frame)
            found = sum(1 for v in detail.values() if v)
            logger.info(f"[PO抓取] 供应商 {vendor_code} 从 {po_num}: {found} 个字段")
            if found:
                result[vendor_code] = {**detail, "stateprovince": None, "country": None}
        except Exception as e:
            logger.warning(f"[PO抓取] 供应商 {vendor_code} 失败: {e}")
        await asyncio.sleep(0.5)

    # ── 收款方（收货方/收款人 标签页）─────────────────────────
    for billto_code, po_num in billto_po_map.items():
        if billto_code in result:
            continue  # 已经抓过（billto 可能与某个 vendor 代码相同）
        try:
            frame = await _navigate_to_po(page, maximo_base, po_num)
            detail = await _scrape_po_billto(frame)
            found = sum(1 for v in detail.values() if v)
            logger.info(f"[PO抓取] 收款方 {billto_code} 从 {po_num}: {found} 个字段")
            if found:
                result[billto_code] = {**detail, "stateprovince": None, "email1": None, "country": None}
        except Exception as e:
            logger.warning(f"[PO抓取] 收款方 {billto_code} 失败: {e}")
        await asyncio.sleep(0.5)

    try:
        await p.stop()
    except Exception:
        pass

    logger.info(f"[PO抓取] 共获取 {len(result)} 个公司信息")
    return result


# ── 同步公开入口 ─────────────────────────────────────────────────────────────

def rpa_scrape_vendor_from_po(
    vendor_po_map: Dict[str, str],
    billto_po_map: Dict[str, str],
    write_to_cache: bool = True,
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    同步入口：从 Maximo 采购单页面 RPA 抓取供应商/收款方信息。

    Args:
        vendor_po_map:  {vendor_code: po_number} — 每个供应商找一张代表 PO
        billto_po_map:  {billto_code: po_number} — 每个收款方找一张代表 PO
        write_to_cache: 成功后写入 company_cache（默认 True）

    Returns:
        {company_code: {name, address1, address2, city, zip, phone1, contact, email1}}
    """
    if not vendor_po_map and not billto_po_map:
        return {}

    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(_fetch_all(vendor_po_map, billto_po_map))
    except Exception as e:
        logger.warning(f"[PO抓取] 异常，跳过: {e}")
        return {}

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
                logger.info(f"[PO抓取] 已将 {len(result)} 条公司信息写入 company_cache")
            finally:
                cur.close()
                conn.close()
        except Exception as e:
            logger.warning(f"[PO抓取] 写入 company_cache 失败: {e}")

    return result


def build_po_maps(po_list: list) -> tuple:
    """
    从 po_list 构建 {vendor_code: po_number} 和 {billto_code: po_number} 映射。
    每个公司代码只取第一张遇到的 PO 作为代表。

    Returns:
        (vendor_po_map, billto_po_map)
    """
    vendor_po_map: Dict[str, str] = {}
    billto_po_map: Dict[str, str] = {}
    for po in po_list:
        po_num = po.get('ponum', '')
        if not po_num:
            continue
        vendor = po.get('vendor')
        billto = po.get('billto')
        if vendor and vendor not in vendor_po_map:
            vendor_po_map[vendor] = po_num
        if billto and billto not in billto_po_map:
            billto_po_map[billto] = po_num
    return vendor_po_map, billto_po_map
