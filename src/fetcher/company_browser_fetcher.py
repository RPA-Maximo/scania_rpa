"""
通过浏览器 CDP 自动抓取公司/供应商详情（RPA 方式）

流程：
  1. 连接本地已登录的 Edge/Chrome debug 实例（CDP port 9223）
  2. 导航到 Maximo 采购单应用 → 打开指定 PO 详情页
  3. Playwright 拦截页面加载时 Maximo 发出的全部 API 响应
     （Maximo UI 使用完整用户权限加载数据，包含供应商 + 收款方信息）
  4. 点击"收款方"选项卡，触发收款方信息的延迟加载
  5. 从拦截到的 JSON 响应中提取 vendor / billto 公司数据
  6. 同时尝试从 DOM 中直接读取可见字段值（备用方案）

前置条件：
  Edge/Chrome 以 --remote-debugging-port=9223 启动，且已登录 Maximo。
  （见 config/browser.py 中的 CDP_URL 配置）
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import quote, urlencode

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import MAXIMO_BASE_URL
from config.browser import CDP_URL

# PO 应用 URL（Maximo Application Framework）
_PO_APP_URL = f"{MAXIMO_BASE_URL}/ui/?event=loadapp&value=po"

# 拦截用的 MXAPIPO 显式字段：让浏览器请求中包含这些字段
_PO_VENDOR_SELECT = (
    "ponum,vendor,billto,"
    "vendorname,venaddress1,venaddress2,vencity,venzip,venstate,venphone,venemailaddress,vencontact,"
    "billtocomp,billtoaddress1,billtoaddress2,billtocity,billtozip,billtocountry"
)

# 收款方 tab 可能的标签文字（中英文均尝试）
_BILLTO_TAB_LABELS = ["收款方", "收款人", "Bill-To", "Bill To", "Billto", "Ship/Bill To"]

# 等待页面加载的超时（ms）
_NAV_TIMEOUT = 30_000
_TAB_TIMEOUT = 5_000


# ─────────────────────────────────────────────────────────────────────────────
# 内部工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(data: dict) -> dict:
    """去除 Maximo 命名空间前缀（spi:、rdfs: 等）"""
    result = {}
    for key, value in data.items():
        clean = key.split(":", 1)[1] if ":" in key else key
        if not isinstance(value, (dict, list)):
            result[clean] = value
    return result


def _extract_from_response(data: Any, captured: Dict[str, Dict]) -> None:
    """
    从任意 Maximo API 响应中提取供应商/收款方公司数据。
    支持：MXAPIPO 响应（含 billto*/ven* 字段）、MXAPIVENDOR/MXAPICOMPANY 响应。
    """
    if not isinstance(data, dict):
        return

    members = data.get("member") or data.get("rdfs:member")
    if not members:
        # 单条资源（直接是 PO/Company 对象）
        members = [data]

    for raw in members:
        if not isinstance(raw, dict):
            continue
        item = _normalize(raw)

        # ── Case 1: PO 记录（含 vendor + billto 字段）────────────────────────
        if "ponum" in item:
            # 供应商
            vendor_code = item.get("vendor")
            if vendor_code and vendor_code not in captured:
                entry = {
                    "name":          item.get("vendorname")      or None,
                    "address1":      (item.get("venaddress1") or item.get("venaddr1")) or None,
                    "address2":      (item.get("venaddress2") or item.get("venaddr2")) or None,
                    "city":          item.get("vencity")          or None,
                    "stateprovince": item.get("venstate")         or None,
                    "zip":           (item.get("venzip") or item.get("venpostalcode")) or None,
                    "phone1":        item.get("venphone")         or None,
                    "email1":        item.get("venemailaddress")  or None,
                    "contact":       item.get("vencontact")       or None,
                }
                if any(v for v in entry.values() if v):
                    captured[vendor_code] = entry
                    print(f"  [拦截] 供应商 {vendor_code}: {entry.get('name')}")

            # 收款方
            billto_code = item.get("billto")
            if billto_code and billto_code not in captured:
                entry = {
                    "name":    (item.get("billtocomp") or item.get("billtoname")) or None,
                    "address1": (item.get("billtoaddress1") or item.get("billtoaddr1")) or None,
                    "address2": item.get("billtoaddress2") or None,
                    "city":     item.get("billtocity")     or None,
                    "zip":      (item.get("billtozip") or item.get("billtopostalcode")) or None,
                    "country":  item.get("billtocountry")  or None,
                }
                if any(v for v in entry.values() if v):
                    captured[billto_code] = entry
                    print(f"  [拦截] 收款方 {billto_code}: {entry.get('name')}")

        # ── Case 2: VENDOR / COMPANY 记录 ─────────────────────────────────────
        company_code = item.get("company") or item.get("vendor")
        if company_code and "name" in item and company_code not in captured:
            entry = {
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
            if any(v for v in entry.values() if v):
                captured[company_code] = entry
                print(f"  [拦截] 公司 {company_code}: {entry.get('name')}")


async def _click_billto_tab(page) -> bool:
    """尝试点击"收款方"选项卡，返回是否成功"""
    for label in _BILLTO_TAB_LABELS:
        for selector in [
            f'a:text-is("{label}")',
            f'button:text-is("{label}")',
            f'[role="tab"]:text-is("{label}")',
            f'td:text-is("{label}")',
            f'span:text-is("{label}")',
            f'li:text-is("{label}")',
        ]:
            try:
                locator = page.locator(selector).first
                if await locator.is_visible(timeout=1_000):
                    await locator.click(timeout=_TAB_TIMEOUT)
                    print(f"  [RPA] 点击收款方 tab: {selector}")
                    return True
            except Exception:
                continue
    return False


async def _read_dom_field(page, label: str) -> Optional[str]:
    """通过 label 文字查找对应 input/span 的值（Maximo MAF 通用）"""
    # Maximo MAF 的字段布局：label cell 紧邻 value cell
    try:
        # 方式1：Maximo 传统布局 td.labelcell → 下一个 td input
        value = await page.evaluate(
            """(label) => {
                const cells = Array.from(document.querySelectorAll('td'));
                const lc = cells.find(c => c.textContent.trim() === label);
                if (!lc) return null;
                const next = lc.nextElementSibling;
                if (!next) return null;
                const inp = next.querySelector('input[type="text"], input:not([type]), textarea');
                if (inp) return inp.value || inp.getAttribute('value') || null;
                return next.textContent.trim() || null;
            }""",
            label,
        )
        if value:
            return value.strip() or None
    except Exception:
        pass

    # 方式2：aria-label / placeholder 属性匹配
    try:
        locator = page.locator(f'input[aria-label="{label}"]').first
        val = await locator.input_value(timeout=1_000)
        return val.strip() or None
    except Exception:
        pass

    return None


async def _read_company_from_dom(page, code_hint: str) -> Dict[str, Any]:
    """从当前页面 DOM 读取公司/收款方字段值"""
    fields = {
        "name":    ["Company", "公司名称", "供应商名称", "Vendor Name"],
        "address1": ["Address 1", "地址1", "Address Line 1", "Address"],
        "address2": ["Address 2", "地址2", "Address Line 2"],
        "city":    ["City", "城市"],
        "zip":     ["ZIP", "Zip", "邮政编码", "Postal Code"],
        "country": ["Country", "国家"],
        "phone1":  ["Phone", "电话"],
        "email1":  ["Email", "邮箱"],
        "contact": ["Contact", "联系人"],
    }
    result = {}
    for db_field, label_candidates in fields.items():
        for label in label_candidates:
            val = await _read_dom_field(page, label)
            if val:
                result[db_field] = val
                break
    if any(result.values()):
        print(f"  [DOM] {code_hint}: {result.get('name')}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 主抓取函数
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_company_details_via_browser(
    company_codes: List[str],
    po_numbers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    RPA 方式批量抓取供应商/收款方公司详情。

    流程：
      1. 连接 CDP 浏览器（已登录 Maximo）
      2. 对每个 PO 号，导航到 Maximo 采购单详情页
         → 拦截 Maximo 内部 API 响应，提取 vendor + billto 信息
         → 点击"收款方"选项卡，触发收款方字段加载
         → 备用：从 DOM 读取可见字段
      3. 如仍有代码未获取，尝试直接访问 MXAPIVENDOR（原有方式）

    Args:
        company_codes: 需要查询的公司代码列表（vendor_code / billto_code）
        po_numbers:    用于导航的 PO 单号列表；为空时自动尝试直接 OSLC 方式

    Returns:
        {company_code: {name, address1, address2, city, stateprovince,
                        zip, country, phone1, email1, contact}}
    """
    from playwright.async_api import async_playwright

    deduped_codes = list(dict.fromkeys(company_codes))
    captured: Dict[str, Any] = {}

    print(f"[INFO] company_browser_fetcher: 连接 CDP 浏览器 ({CDP_URL})...")

    try:
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(CDP_URL)
            except Exception as e:
                print(f"[WARN] CDP 连接失败 — {e}")
                print(f"[WARN] 请确保 Edge/Chrome 以 --remote-debugging-port=9223 启动并已登录 Maximo")
                return {}

            contexts = browser.contexts
            context = contexts[0] if contexts else await browser.new_context()

            # ── 方式一：RPA 导航 PO 详情页（有 po_numbers 时执行）────────────
            if po_numbers:
                await _rpa_navigate_po_pages(context, po_numbers, captured)

            # ── 方式二：直接访问 MXAPIVENDOR（用浏览器 session，补充未抓到的）──
            missing = [c for c in deduped_codes if c not in captured]
            if missing:
                print(f"[INFO] 尝试 MXAPIVENDOR 直接查询，剩余 {len(missing)} 个代码...")
                await _fetch_via_mxapivendor(context, missing, captured)

            # ── 方式三：MXAPIPO 显式字段查询（仍有缺失时，通过 PO 反查）────────
            missing = [c for c in deduped_codes if c not in captured]
            if missing and po_numbers:
                print(f"[INFO] 尝试 MXAPIPO 显式字段查询，剩余 {len(missing)} 个代码...")
                await _fetch_via_mxapipo_explicit(context, po_numbers[:5], captured)

    except Exception as e:
        print(f"[WARN] company_browser_fetcher 意外异常: {e}")

    found = {k: v for k, v in captured.items() if k in deduped_codes}
    print(
        f"[INFO] company_browser_fetcher: "
        f"查询 {len(deduped_codes)} 个代码，获得 {len(found)} 条"
    )
    return found


async def _rpa_navigate_po_pages(
    context,
    po_numbers: List[str],
    captured: Dict[str, Any],
) -> None:
    """
    RPA 核心流程：逐一导航到 PO 详情页，拦截 API 响应 + 点击收款方 tab。
    """
    page = await context.new_page()

    # 注册全局响应拦截
    async def on_response(response):
        url = response.url
        if MAXIMO_BASE_URL not in url:
            return
        if response.status != 200:
            return
        ct = response.headers.get("content-type", "")
        if "json" not in ct:
            return
        try:
            data = await response.json()
            _extract_from_response(data, captured)
        except Exception:
            pass

    page.on("response", on_response)

    try:
        for po_num in po_numbers:
            print(f"[RPA] 导航到 PO 详情: {po_num}")

            # ① 直接打开 PO 应用并通过 QBE 过滤到指定单号
            nav_url = (
                f"{_PO_APP_URL}"
                f"&additionalevent=useqbe"
                f"&additionaleventvalue=ponum%3D{po_num}"
            )
            try:
                await page.goto(nav_url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT)
            except Exception as e:
                print(f"  [WARN] 导航失败: {e}")
                continue

            # ② 等待网络静默（Maximo 加载数据完成）
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass

            # ③ 若停在列表视图，尝试点击 PO 名称链接进入详情
            try:
                link = page.locator(f'a:text("{po_num}")').first
                if await link.is_visible(timeout=3_000):
                    await link.click()
                    await page.wait_for_load_state("networkidle", timeout=15_000)
                    print(f"  [RPA] 点击 PO 链接 → 进入详情页")
            except Exception:
                pass  # 已在详情页则跳过

            # ④ 点击"收款方"选项卡，触发收款方数据加载
            tab_clicked = await _click_billto_tab(page)
            if tab_clicked:
                try:
                    await page.wait_for_load_state("networkidle", timeout=8_000)
                except Exception:
                    pass
            else:
                print(f"  [WARN] 未找到收款方 tab，仅从网络拦截获取数据")

            # ⑤ 备用：从 DOM 读取供应商字段（PO tab 上可见）
            try:
                # 先切回 PO tab（若当前在收款方 tab）
                for label in ["PO", "采购单", "Order"]:
                    try:
                        tab = page.locator(f'a:text-is("{label}"), [role="tab"]:text-is("{label}")').first
                        if await tab.is_visible(timeout=1_000):
                            await tab.click(timeout=2_000)
                            await page.wait_for_load_state("networkidle", timeout=5_000)
                            break
                    except Exception:
                        continue

                # 尝试从 DOM 读取供应商信息
                dom_result = await _read_company_from_dom(page, "vendor_from_po_page")
                # 无法直接关联到 vendor_code，仅作补充
            except Exception:
                pass

    finally:
        await page.close()


async def _fetch_via_mxapivendor(
    context,
    company_codes: List[str],
    captured: Dict[str, Any],
) -> None:
    """
    方式二：直接在浏览器中访问 MXAPIVENDOR OSLC 接口。
    （若 UI 账号含 COMPANIES READ OSLC 权限，此方式最快）
    """
    _SELECT = "company,name,address1,address2,city,stateprovince,zip,country,phone1,email1,contact"
    _BATCH = 10
    page = await context.new_page()
    try:
        for i in range(0, len(company_codes), _BATCH):
            batch = company_codes[i: i + _BATCH]
            quoted = ",".join(f'"{c}"' for c in batch)
            url = (
                f"{MAXIMO_BASE_URL}/oslc/os/MXAPIVENDOR"
                f"?oslc.select={quote(_SELECT)}"
                f"&oslc.where={quote(f'company in [{quoted}]')}"
                f"&oslc.pageSize={len(batch)}"
                f"&_dropnulls=0"
            )
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                if resp and resp.status == 200:
                    body = await page.evaluate("document.body.innerText")
                    data = json.loads(body)
                    _extract_from_response(data, captured)
                else:
                    status = resp.status if resp else "无响应"
                    print(f"  [WARN] MXAPIVENDOR 批次 {i//10+1}: HTTP {status}")
            except Exception as e:
                print(f"  [WARN] MXAPIVENDOR 批次 {i//10+1}: {e}")
    finally:
        await page.close()


async def _fetch_via_mxapipo_explicit(
    context,
    po_numbers: List[str],
    captured: Dict[str, Any],
) -> None:
    """
    方式三：通过 MXAPIPO 显式请求 billto*/ven* 字段。
    即使 MXAPIVENDOR 无权限，MXAPIPO 自身字段可能对 PO READ 用户可见。
    """
    page = await context.new_page()
    try:
        for po_num in po_numbers:
            where_clause = 'ponum="' + po_num + '"'
            url = (
                f"{MAXIMO_BASE_URL}/oslc/os/MXAPIPO"
                f"?oslc.select={quote(_PO_VENDOR_SELECT)}"
                f"&oslc.where={quote(where_clause)}"
                f"&_dropnulls=0"
            )
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                if resp and resp.status == 200:
                    body = await page.evaluate("document.body.innerText")
                    data = json.loads(body)
                    _extract_from_response(data, captured)
            except Exception as e:
                print(f"  [WARN] MXAPIPO 显式查询 {po_num}: {e}")
    finally:
        await page.close()
