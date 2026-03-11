"""
调试脚本：查找页面元素的正确选择器
"""
import asyncio
from playwright.async_api import async_playwright
from config.browser import DEBUG_PORT

async def debug_element():
    """调试页面元素"""
    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
    
    # 查找 manage-shell 页面
    target_page = None
    for context in browser.contexts:
        for page in context.pages:
            if "manage-shell" in page.url or "maximo" in page.url:
                target_page = page
                break
        if target_page:
            break
    
    if not target_page:
        print("❌ 未找到目标页面")
        await browser.close()
        await p.stop()
        return
    
    print(f"✓ 找到页面：{target_page.url}")
    print()
    
    # 测试不同的选择器
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
                # 检查可见性
                element = target_page.locator(selector).first
                is_visible = await element.is_visible()
                print(f"{'':40}   可见: {is_visible}")
                
                # 获取元素信息
                try:
                    text = await element.text_content(timeout=1000)
                    print(f"{'':40}   文本: {text}")
                except:
                    pass
        except Exception as e:
            print(f"{name:40} → 错误: {e}")
        print()
    
    # 检查 iframe
    print("-" * 60)
    print("检查 iframe：")
    frames = target_page.frames
    print(f"找到 {len(frames)} 个 frame")
    for i, frame in enumerate(frames):
        print(f"  Frame {i}: {frame.url[:80]}")
    
    print()
    print("-" * 60)
    print("在主 frame 中搜索 'Favorite' 相关元素：")
    
    # 搜索包含 "Favorite" 的元素
    try:
        elements = await target_page.locator('text=/.*[Ff]avorite.*/').all()
        print(f"找到 {len(elements)} 个包含 'Favorite' 的元素")
        for i, elem in enumerate(elements[:5]):  # 只显示前5个
            try:
                text = await elem.text_content(timeout=1000)
                print(f"  {i+1}. {text[:50]}")
            except:
                pass
    except Exception as e:
        print(f"搜索失败: {e}")
    
    await browser.close()
    await p.stop()

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(debug_element())
