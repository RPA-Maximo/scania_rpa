"""
Maximo 浏览器连接模块

LLM 提示：处理浏览器连接和页面查找
"""
from typing import Tuple
from playwright.async_api import async_playwright, Browser, Page, Frame


async def connect_to_browser(cdp_url: str = "http://localhost:9223") -> Tuple:
    """
    连接到已启动的浏览器并找到 Maximo 页面
    
    Args:
        cdp_url: Chrome DevTools Protocol URL
    
    Returns:
        (playwright_instance, browser, maximo_page, main_frame)
    
    Raises:
        Exception: 未找到 Maximo 页面
    
    LLM 提示：
    - 浏览器需要以调试模式启动：chrome.exe --remote-debugging-port=9223
    - 返回的 main_frame 是主要操作对象
    
    Example:
        p, browser, page, frame = await connect_to_browser()
        # 使用 frame 进行操作
        await frame.evaluate("...")
    """
    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp(cdp_url)
    
    # 查找 Maximo 页面
    maximo_page = None
    for context in browser.contexts:
        for page in context.pages:
            if "maximo" in page.url.lower():
                maximo_page = page
                break
        if maximo_page:
            break
    
    if not maximo_page:
        raise Exception("未找到 Maximo 页面，请确保浏览器中已打开 Maximo 系统")
    
    # 查找主 iframe
    main_frame = _find_main_frame(maximo_page)
    
    return p, browser, maximo_page, main_frame


def _find_main_frame(page: Page) -> Frame:
    """
    查找 Maximo 的主 iframe
    
    Args:
        page: Playwright Page 对象
    
    Returns:
        主 iframe 或 main_frame
    
    LLM 提示：Maximo 使用 iframe 架构，主要内容在特定 iframe 中
    特征：URL 包含 "maximo/ui/" 和 "uisessionid"
    """
    for frame in page.frames:
        if "maximo/ui/" in frame.url and "uisessionid" in frame.url:
            return frame
    return page.main_frame
