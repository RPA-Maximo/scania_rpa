"""
终极调试脚本：深度分析页面结构
"""
import asyncio
from playwright.async_api import async_playwright
from config.browser import DEBUG_PORT

async def ultimate_debug():
    """深度调试页面"""
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
    
    # 执行深度分析
    result = await target_page.evaluate("""
        () => {
            const results = {
                totalElements: 0,
                favoriteElements: [],
                allIds: [],
                allLinks: [],
                iframes: [],
                shadowRoots: []
            };
            
            // 统计所有元素
            results.totalElements = document.querySelectorAll('*').length;
            
            // 查找所有包含 "favorite" 的元素（不区分大小写）
            const allElements = document.querySelectorAll('*');
            allElements.forEach(el => {
                const id = el.id || '';
                const className = el.className || '';
                const text = el.textContent || '';
                
                if (id.toLowerCase().includes('favorite') || 
                    className.toLowerCase().includes('favorite') ||
                    text.includes('Favorite')) {
                    results.favoriteElements.push({
                        tag: el.tagName,
                        id: id,
                        class: className,
                        text: text.substring(0, 50)
                    });
                }
                
                // 收集所有 ID
                if (id) {
                    results.allIds.push(id);
                }
            });
            
            // 查找所有链接
            const links = document.querySelectorAll('a');
            links.forEach(link => {
                results.allLinks.push({
                    id: link.id,
                    text: link.textContent.trim().substring(0, 30),
                    href: link.href
                });
            });
            
            // 查找所有 iframe
            const iframes = document.querySelectorAll('iframe');
            iframes.forEach(iframe => {
                results.iframes.push({
                    id: iframe.id,
                    src: iframe.src
                });
            });
            
            // 查找 Shadow DOM
            allElements.forEach(el => {
                if (el.shadowRoot) {
                    results.shadowRoots.push({
                        host: el.tagName,
                        id: el.id
                    });
                }
            });
            
            return results;
        }
    """)
    
    print("=" * 80)
    print("页面分析结果")
    print("=" * 80)
    print(f"\n总元素数: {result['totalElements']}")
    
    print(f"\n包含 'Favorite' 的元素 ({len(result['favoriteElements'])} 个):")
    print("-" * 80)
    for elem in result['favoriteElements'][:10]:  # 只显示前10个
        print(f"  标签: {elem['tag']}")
        print(f"  ID: {elem['id']}")
        print(f"  Class: {elem['class']}")
        print(f"  文本: {elem['text']}")
        print()
    
    print(f"\niframe 列表 ({len(result['iframes'])} 个):")
    print("-" * 80)
    for iframe in result['iframes']:
        print(f"  ID: {iframe['id']}")
        print(f"  Src: {iframe['src'][:80]}")
        print()
    
    print(f"\nShadow DOM ({len(result['shadowRoots'])} 个):")
    print("-" * 80)
    for shadow in result['shadowRoots']:
        print(f"  Host: {shadow['host']}, ID: {shadow['id']}")
    
    print(f"\n所有链接 (前 20 个):")
    print("-" * 80)
    for link in result['allLinks'][:20]:
        if link['text']:  # 只显示有文本的链接
            print(f"  [{link['id']}] {link['text']}")
    
    print("\n" + "=" * 80)
    print("搜索特定文本的链接")
    print("=" * 80)
    
    # 搜索包含"主项目"、"库存"等的链接
    search_texts = ['主项目', '库存', '资产', '公司', 'ITEM']
    for search_text in search_texts:
        matching = [l for l in result['allLinks'] if search_text in l['text'] or search_text in l['id']]
        if matching:
            print(f"\n包含 '{search_text}' 的链接:")
            for link in matching[:5]:
                print(f"  ID: {link['id']}, 文本: {link['text']}")
    
    await browser.close()
    await p.stop()

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(ultimate_debug())
