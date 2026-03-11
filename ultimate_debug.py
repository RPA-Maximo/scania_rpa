"""
终极调试脚本：深度分析页面结构
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from rpa.browser import connect_to_browser


async def ultimate_debug():
    """深度调试页面"""
    p, context, target_page, _ = await connect_to_browser()
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

            results.totalElements = document.querySelectorAll('*').length;

            const allElements = document.querySelectorAll('*');
            allElements.forEach(el => {
                const id = el.id || '';
                const className = el.className || '';
                const text = el.textContent || '';

                if (id.toLowerCase().includes('favorite') ||
                    className.toLowerCase().includes('favorite') ||
                    text.includes('Favorite')) {
                    results.favoriteElements.push({
                        tag: el.tagName, id, class: className,
                        text: text.substring(0, 50)
                    });
                }
                if (id) results.allIds.push(id);
            });

            document.querySelectorAll('a').forEach(link => {
                results.allLinks.push({
                    id: link.id,
                    text: link.textContent.trim().substring(0, 30),
                    href: link.href
                });
            });

            document.querySelectorAll('iframe').forEach(iframe => {
                results.iframes.push({ id: iframe.id, src: iframe.src });
            });

            allElements.forEach(el => {
                if (el.shadowRoot) results.shadowRoots.push({ host: el.tagName, id: el.id });
            });

            return results;
        }
    """)

    print("=" * 80)
    print(f"总元素数: {result['totalElements']}")

    print(f"\n包含 'Favorite' 的元素 ({len(result['favoriteElements'])} 个):")
    for elem in result['favoriteElements'][:10]:
        print(f"  [{elem['tag']}] id={elem['id']} text={elem['text']}")

    print(f"\niframe 列表 ({len(result['iframes'])} 个):")
    for iframe in result['iframes']:
        print(f"  ID: {iframe['id']}  Src: {iframe['src'][:80]}")

    print(f"\nShadow DOM ({len(result['shadowRoots'])} 个):")
    for shadow in result['shadowRoots']:
        print(f"  Host: {shadow['host']}, ID: {shadow['id']}")

    print(f"\n所有链接 (前 20 个):")
    for link in result['allLinks'][:20]:
        if link['text']:
            print(f"  [{link['id']}] {link['text']}")

    search_texts = ['主项目', '库存', '资产', '公司', 'ITEM']
    for search_text in search_texts:
        matching = [l for l in result['allLinks'] if search_text in l['text'] or search_text in l['id']]
        if matching:
            print(f"\n包含 '{search_text}' 的链接:")
            for link in matching[:5]:
                print(f"  ID: {link['id']}, 文本: {link['text']}")

    await context.close()
    await p.stop()


if __name__ == "__main__":
    asyncio.run(ultimate_debug())
