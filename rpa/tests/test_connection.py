"""
测试连接到已启动的 Edge 浏览器
调试端口: localhost:9223
"""
import asyncio
from playwright.async_api import async_playwright


async def test_browser_connection():
    """连接到已启动的浏览器并获取基本信息"""
    async with async_playwright() as p:
        try:
            # 连接到调试端口
            browser = await p.chromium.connect_over_cdp("http://localhost:9223")
            print("✓ 成功连接到浏览器")
            
            # 获取所有上下文和页面
            contexts = browser.contexts
            print(f"\n浏览器上下文数量: {len(contexts)}")
            
            all_pages = []
            for i, context in enumerate(contexts):
                pages = context.pages
                all_pages.extend(pages)
                print(f"\n上下文 {i + 1} 的页面数量: {len(pages)}")
                
                for j, page in enumerate(pages):
                    print(f"  页面 {j + 1}:")
                    print(f"    URL: {page.url}")
                    print(f"    标题: {await page.title()}")
            
            # 尝试找到 Maximo 页面
            maximo_page = None
            for page in all_pages:
                if "maximo" in page.url.lower() or "scania" in page.url.lower():
                    maximo_page = page
                    print(f"\n✓ 找到 Maximo 页面: {page.url}")
                    break
            
            if maximo_page:
                # 获取页面的基本信息
                print("\n=== Maximo 页面详细信息 ===")
                print(f"完整 URL: {maximo_page.url}")
                print(f"标题: {await maximo_page.title()}")
                
                # 检查是否有 iframe
                frames = maximo_page.frames
                print(f"\nFrame 数量: {len(frames)}")
                for idx, frame in enumerate(frames):
                    print(f"  Frame {idx + 1}: {frame.url}")
                
                # 尝试获取页面的一些基本元素信息
                print("\n=== 尝试获取页面元素 ===")
                try:
                    # 获取页面的 body 内容（前 500 字符）
                    body_text = await maximo_page.evaluate("() => document.body.innerText.substring(0, 500)")
                    print(f"页面文本预览:\n{body_text}")
                except Exception as e:
                    print(f"获取页面文本失败: {e}")
                
                # 尝试查找常见的 Maximo 元素
                print("\n=== 查找 Maximo 常见元素 ===")
                selectors_to_check = [
                    "input[id*='ponum']",  # 采购单号输入框
                    "input[id*='itemnum']",  # 物料号输入框
                    "table[id*='grid']",  # 表格
                    "iframe",  # iframe
                    "[id*='menu']",  # 菜单
                ]
                
                for selector in selectors_to_check:
                    try:
                        elements = await maximo_page.query_selector_all(selector)
                        if elements:
                            print(f"  ✓ 找到 {len(elements)} 个元素: {selector}")
                    except Exception as e:
                        print(f"  ✗ 查找失败 {selector}: {e}")
                
            else:
                print("\n⚠ 未找到 Maximo 页面，请确保浏览器中已打开 Maximo")
                print("\n当前打开的页面:")
                for page in all_pages:
                    print(f"  - {page.url}")
            
            print("\n✓ 测试完成，浏览器保持连接状态")
            
        except Exception as e:
            print(f"✗ 连接失败: {e}")
            print("\n请确保:")
            print("  1. Edge 浏览器已启动")
            print("  2. 启动时使用了 --remote-debugging-port=9223 参数")
            print("  3. 端口 9223 未被占用")


if __name__ == "__main__":
    asyncio.run(test_browser_connection())
