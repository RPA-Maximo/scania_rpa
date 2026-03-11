"""
Maximo 浏览器连接模块

LLM 提示：处理浏览器连接和页面查找
"""
import sys
from typing import Tuple
from playwright.async_api import async_playwright, Browser, Page, Frame

# Windows 平台需要设置事件循环策略
if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from config.browser import CDP_URL


async def connect_to_browser(cdp_url: str = CDP_URL) -> Tuple:
    """
    连接到已启动的浏览器并找到 Maximo 页面
    
    Args:
        cdp_url: Chrome DevTools Protocol URL
    
    Returns:
        (playwright_instance, browser, maximo_page, main_frame)
    
    Raises:
        Exception: 未找到 Maximo 页面或浏览器未启动
    
    LLM 提示：
    - 浏览器需要以调试模式启动：python start_browser.py
    - 返回的 main_frame 是主要操作对象
    
    Example:
        p, browser, page, frame = await connect_to_browser()
        # 使用 frame 进行操作
        await frame.evaluate("...")
    """
    try:
        p = await async_playwright().start()
        browser = await p.chromium.connect_over_cdp(cdp_url)
    except Exception as e:
        error_msg = (
            "无法连接到浏览器，请先启动浏览器：\n\n"
            "  python start_browser.py\n\n"
            f"详细错误：{str(e)}"
        )
        raise Exception(error_msg)
    
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
        # 检查是否在登录页
        login_page = None
        for context in browser.contexts:
            for page in context.pages:
                if "auth.scania" in page.url.lower() or "login" in page.url.lower():
                    login_page = page
                    break
            if login_page:
                break
        
        if login_page:
            error_msg = (
                "检测到登录页面，请先登录 Maximo 系统\n"
                f"当前页面：{login_page.url}"
            )
        else:
            error_msg = (
                "未找到 Maximo 页面，请在浏览器中打开 Maximo 系统\n"
                "或运行：python start_browser.py"
            )
        raise Exception(error_msg)
    
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
