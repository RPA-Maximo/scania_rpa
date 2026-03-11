"""
测试连接到 Maximo 浏览器
目标 URL: https://main.manage.scania-acc.suite.maximo.com/maximo/oslc/graphite/manage-shell
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from rpa.browser import connect_to_browser


async def test_browser_connection():
    """连接到 Maximo 并获取基本信息"""
    try:
        p, context, maximo_page, main_frame = await connect_to_browser()
        print("✓ 成功连接到浏览器")

        # 页面基本信息
        print(f"\n=== Maximo 页面详细信息 ===")
        print(f"完整 URL: {maximo_page.url}")
        print(f"标题: {await maximo_page.title()}")

        # 检查 iframe
        frames = maximo_page.frames
        print(f"\nFrame 数量: {len(frames)}")
        for idx, frame in enumerate(frames):
            print(f"  Frame {idx + 1}: {frame.url}")

        # 获取页面文本预览
        print("\n=== 尝试获取页面元素 ===")
        try:
            body_text = await maximo_page.evaluate(
                "() => document.body.innerText.substring(0, 500)"
            )
            print(f"页面文本预览:\n{body_text}")
        except Exception as e:
            print(f"获取页面文本失败: {e}")

        # 查找常见 Maximo 元素
        print("\n=== 查找 Maximo 常见元素 ===")
        selectors_to_check = [
            "input[id*='ponum']",
            "input[id*='itemnum']",
            "table[id*='grid']",
            "iframe",
            "[id*='menu']",
        ]
        for selector in selectors_to_check:
            try:
                elements = await maximo_page.query_selector_all(selector)
                if elements:
                    print(f"  ✓ 找到 {len(elements)} 个元素: {selector}")
            except Exception as e:
                print(f"  ✗ 查找失败 {selector}: {e}")

        print("\n✓ 测试完成")
        await context.close()
        await p.stop()

    except Exception as e:
        print(f"✗ 连接失败: {e}")
        print("\n请确保：")
        print("  1. 已运行 python start_browser.py 并完成登录")
        print("  2. Edge 或 Chrome 浏览器已安装")


if __name__ == "__main__":
    asyncio.run(test_browser_connection())
