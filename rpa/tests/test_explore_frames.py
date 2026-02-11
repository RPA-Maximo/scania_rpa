"""
深入探索 Maximo 的 iframe 结构和元素
"""
import asyncio
from playwright.async_api import async_playwright


async def explore_maximo_frames():
    """探索 Maximo 页面的 iframe 和元素"""
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9223")
            print("✓ 成功连接到浏览器\n")
            
            # 找到 Maximo 页面
            maximo_page = None
            for context in browser.contexts:
                for page in context.pages:
                    if "maximo" in page.url.lower():
                        maximo_page = page
                        break
                if maximo_page:
                    break
            
            if not maximo_page:
                print("✗ 未找到 Maximo 页面")
                return
            
            print(f"当前页面: {await maximo_page.title()}")
            print(f"URL: {maximo_page.url}\n")
            
            # 遍历所有 frame
            frames = maximo_page.frames
            print(f"=== 共有 {len(frames)} 个 Frame ===\n")
            
            for idx, frame in enumerate(frames):
                print(f"--- Frame {idx + 1} ---")
                print(f"URL: {frame.url}")
                print(f"Name: {frame.name}")
                
                # 跳过 about:blank
                if frame.url == "about:blank":
                    print("(空白 frame，跳过)\n")
                    continue
                
                try:
                    # 获取 frame 的标题
                    title = await frame.title()
                    print(f"标题: {title}")
                    
                    # 尝试获取一些文本内容
                    try:
                        text_sample = await frame.evaluate("() => document.body.innerText.substring(0, 300)")
                        print(f"文本预览: {text_sample[:200]}...")
                    except:
                        pass
                    
                    # 查找输入框
                    print("\n查找输入框:")
                    inputs = await frame.query_selector_all("input[type='text'], input:not([type])")
                    print(f"  找到 {len(inputs)} 个文本输入框")
                    
                    # 获取前几个输入框的信息
                    for i, inp in enumerate(inputs[:5]):
                        try:
                            inp_id = await inp.get_attribute("id")
                            inp_name = await inp.get_attribute("name")
                            inp_placeholder = await inp.get_attribute("placeholder")
                            inp_value = await inp.get_attribute("value")
                            print(f"    输入框 {i+1}: id={inp_id}, name={inp_name}, placeholder={inp_placeholder}, value={inp_value}")
                        except:
                            pass
                    
                    # 查找按钮
                    print("\n查找按钮:")
                    buttons = await frame.query_selector_all("button, input[type='button'], input[type='submit']")
                    print(f"  找到 {len(buttons)} 个按钮")
                    for i, btn in enumerate(buttons[:5]):
                        try:
                            btn_text = await btn.inner_text()
                            btn_id = await btn.get_attribute("id")
                            print(f"    按钮 {i+1}: id={btn_id}, text={btn_text}")
                        except:
                            pass
                    
                    # 查找表格
                    print("\n查找表格:")
                    tables = await frame.query_selector_all("table")
                    print(f"  找到 {len(tables)} 个表格")
                    
                    # 查找特定的 Maximo 元素
                    print("\n查找 Maximo 特定元素:")
                    maximo_selectors = {
                        "物料号": ["input[id*='itemnum']", "input[name*='itemnum']"],
                        "采购单号": ["input[id*='ponum']", "input[name*='ponum']"],
                        "数量": ["input[id*='quantity']", "input[name*='qty']"],
                        "仓库": ["input[id*='location']", "input[name*='location']"],
                        "保存按钮": ["button[id*='save']", "img[id*='save']"],
                    }
                    
                    for label, selectors in maximo_selectors.items():
                        for selector in selectors:
                            try:
                                elements = await frame.query_selector_all(selector)
                                if elements:
                                    print(f"  ✓ {label}: 找到 {len(elements)} 个 ({selector})")
                                    # 获取第一个元素的详细信息
                                    elem = elements[0]
                                    elem_id = await elem.get_attribute("id")
                                    elem_value = await elem.get_attribute("value")
                                    print(f"      第一个元素: id={elem_id}, value={elem_value}")
                                    break
                            except:
                                pass
                    
                except Exception as e:
                    print(f"探索 frame 时出错: {e}")
                
                print("\n")
            
            print("✓ 探索完成")
            
        except Exception as e:
            print(f"✗ 错误: {e}")


if __name__ == "__main__":
    asyncio.run(explore_maximo_frames())
