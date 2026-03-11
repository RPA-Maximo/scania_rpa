"""
启动 Edge 浏览器（直连模式）

直接启动浏览器并导航至 Maximo manage-shell。
Cookie 持久化存储在 RPA 专用用户数据目录，首次登录后后续自动免登录。

使用方法：
    python start_browser.py

注意：
- 首次启动需要手动登录 Maximo
- 登录后 Cookie 会保存，下次启动无需重新登录
- 请保持浏览器窗口打开，关闭后需要重新启动
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from rpa.browser import connect_to_browser
from config.browser import MAXIMO_SHELL_URL, MAXIMO_LOGIN_URL


async def start():
    print()
    print("=" * 60)
    print("Maximo RPA - 浏览器启动工具")
    print("=" * 60)
    print()
    print(f"目标页面: {MAXIMO_SHELL_URL}")
    print()

    try:
        p, context, page, frame = await connect_to_browser()
        print(f"✓ 浏览器已启动")
        print(f"  当前页面: {page.url}")
        print()
        print("=" * 60)
        print("✓ 启动成功！浏览器已就绪，请保持窗口打开。")
        print("=" * 60)
        print()
        print("下一步：")
        print("  运行：python start_api.py")
        print()
        # 保持运行，等待用户关闭
        print("按 Ctrl+C 关闭此脚本（不会关闭浏览器窗口）")
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        await p.stop()

    except Exception as e:
        print(f"❌ 启动失败：{e}")
        print()
        if "登录" in str(e):
            print(f"  请在浏览器中登录后重试：{MAXIMO_LOGIN_URL}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(start())
