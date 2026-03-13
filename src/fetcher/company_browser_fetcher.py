"""
通过浏览器 CDP 自动抓取公司/供应商详情

原理：
  MXAPIVENDOR 在 OSLC 层需要 COMPANIES READ 权限，requests 直接调用会返回 BMXAA0024E。
  但本地已运行的 Edge/Chrome debug 实例（port 9223）持有人工登录的完整会话，
  该用户账号具有 Maximo UI 级别的 COMPANIES READ 权限。
  通过 Playwright CDP 在该浏览器上下文中发起 OSLC 请求，可绕过 API 账号限制。

前置条件：
  Edge/Chrome 以 --remote-debugging-port=9223 启动，且已登录 Maximo。
  （见 config/browser.py 中的 CDP_URL 配置）
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import MAXIMO_BASE_URL
from config.browser import CDP_URL

# 查询字段（与 vendor_fetcher.py 中的 COMPANY_DETAIL_SELECT 保持一致）
_SELECT = "company,name,address1,address2,city,stateprovince,zip,country,phone1,email1,contact"

# 每批查询数量（URL 长度限制）
_BATCH_SIZE = 10


def _normalize(data: dict) -> dict:
    """去除 Maximo 命名空间前缀"""
    result = {}
    for key, value in data.items():
        clean = key.split(":", 1)[1] if ":" in key else key
        if not isinstance(value, (dict, list)):
            result[clean] = value
    return result


async def fetch_company_details_via_browser(
    company_codes: List[str],
) -> Dict[str, Any]:
    """
    通过 CDP 浏览器批量抓取公司详情。

    Args:
        company_codes: 公司代码列表（vendor code / billto code 均可）

    Returns:
        {company_code: {name, address1, address2, city, stateprovince,
                        zip, country, phone1, email1, contact}}
        失败时返回空 dict（不抛异常）。
    """
    from playwright.async_api import async_playwright

    deduped = list(dict.fromkeys(company_codes))
    result: Dict[str, Any] = {}

    print(f"[INFO] company_browser_fetcher: 连接 CDP 浏览器 ({CDP_URL})...")

    try:
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(CDP_URL)
            except Exception as e:
                print(f"[WARN] company_browser_fetcher: CDP 连接失败 — {e}")
                print(f"[WARN] 请确保 Edge/Chrome 以 --remote-debugging-port=9223 启动并已登录 Maximo")
                return {}

            # 使用已有的浏览器上下文（持有人工登录的 Session）
            contexts = browser.contexts
            context = contexts[0] if contexts else await browser.new_context()
            page = await context.new_page()

            try:
                for i in range(0, len(deduped), _BATCH_SIZE):
                    batch = deduped[i: i + _BATCH_SIZE]
                    batch_num = i // _BATCH_SIZE + 1
                    quoted = ",".join(f'"{c}"' for c in batch)

                    url = (
                        f"{MAXIMO_BASE_URL}/oslc/os/MXAPIVENDOR"
                        f"?oslc.select={quote(_SELECT)}"
                        f"&oslc.where={quote(f'company in [{quoted}]')}"
                        f"&oslc.pageSize={len(batch)}"
                        f"&_dropnulls=0"
                    )

                    try:
                        response = await page.goto(
                            url, wait_until="domcontentloaded", timeout=30_000
                        )
                    except Exception as e:
                        print(f"[WARN] company_browser_fetcher: 批次 {batch_num} 导航失败: {e}")
                        continue

                    if not response:
                        print(f"[WARN] company_browser_fetcher: 批次 {batch_num} 无响应")
                        continue

                    if response.status != 200:
                        body_preview = (await page.evaluate("document.body.innerText"))[:150]
                        print(
                            f"[WARN] company_browser_fetcher: 批次 {batch_num} "
                            f"HTTP {response.status} — {body_preview}"
                        )
                        continue

                    try:
                        body = await page.evaluate("document.body.innerText")
                        data = json.loads(body)
                        members = data.get("member") or data.get("rdfs:member") or []
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
                        print(
                            f"[INFO] company_browser_fetcher: 批次 {batch_num} "
                            f"→ {len(members)} 条 (codes={batch})"
                        )
                    except Exception as e:
                        print(f"[WARN] company_browser_fetcher: 批次 {batch_num} 解析失败: {e}")

            finally:
                await page.close()

    except Exception as e:
        print(f"[WARN] company_browser_fetcher: 意外异常: {e}")

    print(f"[INFO] company_browser_fetcher: 查询 {len(deduped)} 个代码，获得 {len(result)} 条")
    return result
