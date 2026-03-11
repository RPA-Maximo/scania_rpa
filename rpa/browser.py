"""
Maximo 浏览器连接模块

LLM 提示：处理浏览器连接和页面查找

连接方式：
  使用 launch_persistent_context 直接启动浏览器并导航至 Maximo manage-shell，
  无需预先启动调试端口（9223）。
  Cookie 持久化存储在 USER_DATA_DIR，首次登录后后续无需重新登录。
"""
import sys
from typing import Tuple
from playwright.async_api import async_playwright, BrowserContext, Page, Frame

# Windows 平台需要设置事件循环策略
if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from config.browser import (
    BROWSER_PATH,
    USER_DATA_DIR,
    MAXIMO_SHELL_URL,
    MAXIMO_LOGIN_URL,
)


async def connect_to_browser(
    maximo_url: str = MAXIMO_SHELL_URL,
) -> Tuple:
    """
    启动浏览器并连接到 Maximo 页面。

    直接使用 launch_persistent_context 导航至 Maximo manage-shell，
    无需 Chrome DevTools Protocol 调试端口。

    Args:
        maximo_url: Maximo 主页 URL，默认为 manage-shell

    Returns:
        (playwright_instance, context, maximo_page, main_frame)

    Raises:
        Exception: 浏览器启动失败或需要重新登录

    LLM 提示：
    - 首次运行会打开浏览器，需要手动登录 Maximo
    - 登录后 Cookie 保存在 USER_DATA_DIR，下次自动免登录
    - 返回的 main_frame 是主要操作对象

    Example:
        p, context, page, frame = await connect_to_browser()
        # 使用 frame 进行操作
        await frame.evaluate("...")
    """
    p = await async_playwright().start()

    # 启动参数
    launch_kwargs = dict(
        user_data_dir=USER_DATA_DIR,
        headless=False,
        args=['--start-maximized'],
        no_viewport=True,
    )
    # 如果找到 Edge/Chrome 可执行文件，指定使用它
    if BROWSER_PATH:
        launch_kwargs['executable_path'] = BROWSER_PATH

    try:
        context = await p.chromium.launch_persistent_context(**launch_kwargs)
    except Exception as e:
        await p.stop()
        raise Exception(
            f"无法启动浏览器: {e}\n\n"
            "请检查：\n"
            "  1. Edge 或 Chrome 浏览器已安装\n"
            "  2. 没有其他进程占用相同的用户数据目录\n"
            f"  用户数据目录: {USER_DATA_DIR}"
        )

    # 查找已打开的 Maximo 页面，或新开一个
    maximo_page = None
    for page in context.pages:
        if "maximo" in page.url.lower():
            maximo_page = page
            break

    if not maximo_page:
        maximo_page = context.pages[0] if context.pages else await context.new_page()
        try:
            await maximo_page.goto(
                maximo_url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )
        except Exception as e:
            await context.close()
            await p.stop()
            raise Exception(f"导航到 Maximo 失败: {e}")

    # 检查是否被重定向到登录页
    current_url = maximo_page.url
    if "auth.scania" in current_url.lower() or "login" in current_url.lower():
        raise Exception(
            "检测到登录页面，请先在浏览器中完成 Maximo 登录\n"
            f"当前页面：{current_url}\n"
            f"登录地址：{MAXIMO_LOGIN_URL}"
        )

    # 查找主 iframe
    main_frame = _find_main_frame(maximo_page)

    return p, context, maximo_page, main_frame


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
