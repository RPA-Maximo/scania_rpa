"""
Maximo 浏览器连接模块

LLM 提示：处理浏览器连接和页面查找

连接方式：
  使用 launch_persistent_context 直接启动浏览器并导航至 Maximo manage-shell，
  无需预先启动调试端口（9223）。
  Cookie 持久化存储在 USER_DATA_DIR，首次登录后后续无需重新登录。
"""
import asyncio
import os
import subprocess
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


def _kill_edge_using_profile(user_data_dir: str) -> int:
    """
    杀掉正在使用指定 Profile 目录的 Edge 进程。
    通过 wmic 查找命令行中包含该目录的 msedge.exe 进程并强制结束。
    返回被杀掉的进程数量。
    """
    if sys.platform != 'win32':
        return 0

    killed = 0
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where', 'name="msedge.exe"',
             'get', 'ProcessId,CommandLine'],
            capture_output=True, timeout=10,
            encoding='utf-8', errors='replace',
        )
        profile_lower = user_data_dir.lower()
        for line in result.stdout.splitlines():
            if profile_lower in line.lower():
                # PID 是该行最后一个数字 token
                parts = line.strip().split()
                if parts and parts[-1].isdigit():
                    subprocess.run(
                        ['taskkill', '/F', '/PID', parts[-1]],
                        capture_output=True, timeout=5,
                    )
                    killed += 1
    except Exception:
        pass
    return killed


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

    # 判断是否为 Microsoft Edge
    _is_edge = BROWSER_PATH and 'msedge' in BROWSER_PATH.lower()

    # 基础启动参数
    launch_kwargs = dict(
        user_data_dir=USER_DATA_DIR,
        headless=False,
        no_viewport=True,
        args=['--start-maximized'],
    )

    if _is_edge:
        # 使用 channel='msedge' 让 Playwright 以 Edge 原生方式启动，
        # 避免 executable_path 模式下附加的 Chromium 独有标志
        # （如 --disable-extensions、--enable-automation）在企业 Edge 中引发崩溃
        launch_kwargs['channel'] = 'msedge'
        # 企业环境中 Edge 的 Group Policy 可能强制加载扩展，
        # 移除 --disable-extensions 防止策略冲突导致立即退出
        launch_kwargs['ignore_default_args'] = ['--disable-extensions']
    elif BROWSER_PATH:
        # Chrome 或其他 Chromium 浏览器：直接指定路径
        launch_kwargs['executable_path'] = BROWSER_PATH

    def _is_profile_in_use(err: str) -> bool:
        return (
            'user data directory is already in use' in err.lower()
            or ('target page' in err.lower() and 'closed' in err.lower())
        )

    try:
        context = await p.chromium.launch_persistent_context(**launch_kwargs)
    except Exception as first_err:
        first_msg = str(first_err)
        if _is_profile_in_use(first_msg):
            # Profile 被旧进程占用 → 自动清理后重试一次
            killed = _kill_edge_using_profile(USER_DATA_DIR)
            if killed:
                print(f"  已关闭 {killed} 个占用 Profile 的 Edge 进程，正在重试...")
                await asyncio.sleep(2)
                try:
                    context = await p.chromium.launch_persistent_context(**launch_kwargs)
                except Exception as retry_err:
                    await p.stop()
                    raise Exception(
                        f"无法启动浏览器（重试仍失败）: {retry_err}\n\n"
                        "请手动关闭所有 Edge 窗口后重新运行。"
                    )
            else:
                await p.stop()
                raise Exception(
                    "用户数据目录已被另一个 Edge 进程占用，且自动清理失败，请：\n"
                    "  1. 关闭所有打开的 Edge 浏览器窗口\n"
                    "  2. 或在任务管理器中结束所有 msedge.exe 进程\n"
                    f"  3. 重新运行此脚本\n\n"
                    f"  数据目录: {USER_DATA_DIR}"
                )
        else:
            await p.stop()
            raise Exception(
                f"无法启动浏览器: {first_err}\n\n"
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
