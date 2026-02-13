"""
调试菜单点击问题
检查元素是否存在、是否可见、是否可点击
"""
import asyncio
from playwright.async_api import async_playwright

DEBUG_PORT = 9223

async def debug_menu():
    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
    
    # 查找页面
    home_page = None
    for context in browser.contexts:
        for page in context.pages:
            if "main.home.scania-acc.suite.maximo.com" in page.url or "manage-shell" in page.url:
                home_page = page
                break
        if home_page:
            break
    
    if not home_page:
        print("❌ 未找到页面")
        await browser.close()
        await p.stop()
        return
    
    print(f"✓ 找到页面: {home_page.url}")
    
    # 获取 main frame
    main_frame = None
    for frame in home_page.frames:
        if 'main' in frame.url or 'manage-shell' in frame.url:
            main_frame = frame
            break
    
    if not main_frame:
        main_frame = home_page.main_frame
    
    print(f"✓ 使用 frame: {main_frame.url}")
    print()
    
    # 检查采购菜单
    purchase_id = 'm7f8f3e49_ns_menu_PURCHASE_MODULE_a'
    print(f"检查采购菜单 (ID: {purchase_id})...")
    
    result = await main_frame.evaluate(f"""
        () => {{
            const elem = document.getElementById('{purchase_id}');
            if (!elem) {{
                return {{ exists: false }};
            }}
            
            const rect = elem.getBoundingClientRect();
            const style = window.getComputedStyle(elem);
            
            return {{
                exists: true,
                visible: style.display !== 'none' && style.visibility !== 'hidden',
                inViewport: rect.top >= 0 && rect.left >= 0,
                width: rect.width,
                height: rect.height,
                text: elem.textContent.trim(),
                disabled: elem.disabled || elem.getAttribute('aria-disabled') === 'true',
                clickable: !elem.disabled && style.pointerEvents !== 'none'
            }};
        }}
    """)
    
    print(f"  存在: {result.get('exists')}")
    if result.get('exists'):
        print(f"  可见: {result.get('visible')}")
        print(f"  在视口内: {result.get('inViewport')}")
        print(f"  尺寸: {result.get('width')}x{result.get('height')}")
        print(f"  文本: {result.get('text')}")
        print(f"  禁用: {result.get('disabled')}")
        print(f"  可点击: {result.get('clickable')}")
    print()
    
    # 检查接收菜单
    receipts_id = 'm7f8f3e49_ns_menu_PURCHASE_MODULE_sub_changeapp_RECEIPTS_a'
    print(f"检查接收菜单 (ID: {receipts_id})...")
    
    result = await main_frame.evaluate(f"""
        () => {{
            const elem = document.getElementById('{receipts_id}');
            if (!elem) {{
                return {{ exists: false }};
            }}
            
            const rect = elem.getBoundingClientRect();
            const style = window.getComputedStyle(elem);
            
            return {{
                exists: true,
                visible: style.display !== 'none' && style.visibility !== 'hidden',
                inViewport: rect.top >= 0 && rect.left >= 0,
                width: rect.width,
                height: rect.height,
                text: elem.textContent.trim(),
                disabled: elem.disabled || elem.getAttribute('aria-disabled') === 'true',
                clickable: !elem.disabled && style.pointerEvents !== 'none'
            }};
        }}
    """)
    
    print(f"  存在: {result.get('exists')}")
    if result.get('exists'):
        print(f"  可见: {result.get('visible')}")
        print(f"  在视口内: {result.get('inViewport')}")
        print(f"  尺寸: {result.get('width')}x{result.get('height')}")
        print(f"  文本: {result.get('text')}")
        print(f"  禁用: {result.get('disabled')}")
        print(f"  可点击: {result.get('clickable')}")
    print()
    
    # 尝试多种点击方式
    print("尝试点击采购菜单...")
    
    # 方式1: 直接 click()
    print("  方式1: elem.click()")
    result1 = await main_frame.evaluate(f"""
        () => {{
            const elem = document.getElementById('{purchase_id}');
            if (elem) {{
                elem.click();
                return {{ success: true }};
            }}
            return {{ success: false }};
        }}
    """)
    print(f"    结果: {result1.get('success')}")
    await asyncio.sleep(2)
    
    # 方式2: 触发鼠标事件
    print("  方式2: 触发鼠标事件")
    result2 = await main_frame.evaluate(f"""
        () => {{
            const elem = document.getElementById('{purchase_id}');
            if (elem) {{
                elem.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true }}));
                elem.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true }}));
                elem.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true }}));
                return {{ success: true }};
            }}
            return {{ success: false }};
        }}
    """)
    print(f"    结果: {result2.get('success')}")
    await asyncio.sleep(2)
    
    # 方式3: 使用 Playwright 的 click
    print("  方式3: Playwright click")
    try:
        await main_frame.click(f'#{purchase_id}', timeout=5000)
        print(f"    结果: True")
    except Exception as e:
        print(f"    结果: False - {e}")
    
    await asyncio.sleep(2)
    
    print()
    print("检查接收菜单是否可见...")
    result = await main_frame.evaluate(f"""
        () => {{
            const elem = document.getElementById('{receipts_id}');
            if (!elem) return {{ exists: false }};
            const style = window.getComputedStyle(elem);
            return {{
                exists: true,
                visible: style.display !== 'none' && style.visibility !== 'hidden'
            }};
        }}
    """)
    print(f"  存在: {result.get('exists')}, 可见: {result.get('visible')}")
    
    await browser.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(debug_menu())
