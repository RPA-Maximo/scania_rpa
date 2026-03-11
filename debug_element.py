"""
调试脚本：查找页面元素的正确选择器
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from rpa.browser import connect_to_browser


async def debug_element():
    """调试页面元素"""
    p, context, target_page, _ = await connect_to_browser()
    print(f"✓ 找到页面：{target_page.url}")
    print()

    selectors = [
        ('ID: FavoriteApp_ITEM', '#FavoriteApp_ITEM'),
        ('XPath: //*[@id="FavoriteApp_ITEM"]', 'xpath=//*[@id="FavoriteApp_ITEM"]'),
        ('Text: 主项目', 'text=主项目'),
        ('Text: 库存', 'text=库存'),
        ('Text: 资产', 'text=资产'),
        ('Text: 公司', 'text=公司'),
    ]

    print("测试选择器：")
    print("-" * 60)

    for name, selector in selectors:
        try:
            count = await target_page.locator(selector).count()
            print(f"{name:40} → 找到 {count} 个元素")
            if count > 0:
                element = target_page.locator(selector).first
                is_visible = await element.is_visible()
                print(f"{'':40}   可见: {is_visible}")
                try:
                    text = await element.text_content(timeout=1000)
                    print(f"{'':40}   文本: {text}")
                except Exception:
                    pass
        except Exception as e:
            print(f"{name:40} → 错误: {e}")
        print()

    print("-" * 60)
    frames = target_page.frames
    print(f"找到 {len(frames)} 个 frame")
    for i, frame in enumerate(frames):
        print(f"  Frame {i}: {frame.url[:80]}")

    print()
    print("在主 frame 中搜索 'Favorite' 相关元素：")
    try:
        elements = await target_page.locator('text=/.*[Ff]avorite.*/').all()
        print(f"找到 {len(elements)} 个包含 'Favorite' 的元素")
        for i, elem in enumerate(elements[:5]):
            try:
                text = await elem.text_content(timeout=1000)
                print(f"  {i+1}. {text[:50]}")
            except Exception:
                pass
    except Exception as e:
        print(f"搜索失败: {e}")

    await context.close()
    await p.stop()


if __name__ == "__main__":
    asyncio.run(debug_element())
