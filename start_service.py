"""
一键启动 Maximo RPA 服务

自动完成以下步骤：
1. 启动浏览器并导航至 Maximo manage-shell（自动免登录）
2. 确认 Maximo 页面就绪
3. 启动 API 服务

使用方法：
    python start_service.py
"""
import subprocess
import sys
import time
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from config.browser import MAXIMO_SHELL_URL, MAXIMO_LOGIN_URL

# API 配置
API_PORT = 8000


def print_header(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)
    print()


async def launch_and_verify():
    """
    启动浏览器，导航至 Maximo manage-shell，并验证登录状态。

    Returns:
        (context, page, frame): 成功时返回三元组
        None: 需要重新登录
    """
    from rpa.browser import connect_to_browser
    from rpa.navigation import click_menu_purchase, click_menu_receipts

    print("正在启动浏览器...")
    try:
        p, context, page, frame = await connect_to_browser()
        print(f"✓ 浏览器已启动")
        print(f"  当前页面: {page.url}")
        return p, context, page, frame
    except Exception as e:
        error_str = str(e)
        if "登录" in error_str:
            print(f"⚠ {error_str}")
            return None
        raise


async def navigate_receipts(context, page, frame):
    """导航到接收页面"""
    from rpa.navigation import click_menu_purchase, click_menu_receipts

    print()
    print("正在导航到接收页面...")
    try:
        await click_menu_purchase(frame)
        print("✓ 已点击'采购'菜单")
        await asyncio.sleep(1)
        await click_menu_receipts(frame)
        print("✓ 已点击'接收'菜单")
        await asyncio.sleep(3)
        print("✓ 接收页面已就绪")
    except Exception as e:
        print(f"⚠ 自动导航失败 ({e})，请手动导航")


def start_api():
    """启动 API 服务"""
    print()
    print("正在启动 API 服务...")
    print(f"  端口：{API_PORT}")
    print()

    try:
        subprocess.run([
            sys.executable,
            "-m", "uvicorn",
            "api.main:app",
            "--host", "0.0.0.0",
            "--port", str(API_PORT),
            "--reload"
        ])
    except KeyboardInterrupt:
        print()
        print("API 服务已停止")


def main():
    print_header("Maximo RPA 服务启动")
    print(f"目标页面: {MAXIMO_SHELL_URL}")
    print()

    # 步骤 1: 启动浏览器并验证
    print("步骤 1/2: 启动浏览器")
    result = None
    try:
        result = asyncio.run(launch_and_verify())
    except Exception as e:
        print(f"❌ 浏览器启动失败: {e}")
        sys.exit(1)

    if result is None:
        # 需要重新登录
        print()
        print(f"请在打开的浏览器中登录 Maximo：")
        print(f"  {MAXIMO_LOGIN_URL}")
        print()
        input("登录完成后按回车键继续...")

        try:
            result = asyncio.run(launch_and_verify())
        except Exception as e:
            print(f"❌ 仍无法连接: {e}")
            sys.exit(1)

    if result is None:
        print("❌ 登录验证失败，请重新运行")
        sys.exit(1)

    p, context, page, frame = result
    print("✓ Maximo 连接成功")

    # 步骤 2: 启动 API
    print()
    print("步骤 2/2: 启动 API 服务")
    print()
    print_header("服务已就绪")
    print(f"  API 文档:  http://localhost:{API_PORT}/docs")
    print(f"  健康检查:  http://localhost:{API_PORT}/health")
    print()
    print("按 Ctrl+C 停止服务")
    print()

    start_api()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("服务已停止")
        sys.exit(0)
