"""
记录用户在 Maximo 页面的操作流程
监听点击、输入、选择等事件，并保存为 JSON 格式
"""
import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright


class ActionRecorder:
    def __init__(self):
        self.actions = []
        self.start_time = datetime.now()
    
    def add_action(self, action_type, details):
        """记录一个操作"""
        timestamp = (datetime.now() - self.start_time).total_seconds()
        action = {
            "timestamp": round(timestamp, 2),
            "type": action_type,
            "details": details
        }
        self.actions.append(action)
        
        # 实时打印
        print(f"[{timestamp:.2f}s] {action_type}: {details}")
    
    def save_to_file(self, filename):
        """保存记录到文件"""
        output = {
            "recorded_at": self.start_time.isoformat(),
            "total_actions": len(self.actions),
            "actions": self.actions
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"\n✓ 操作记录已保存到: {filename}")


async def record_maximo_actions():
    """连接到浏览器并记录操作"""
    recorder = ActionRecorder()
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9223")
            print("✓ 成功连接到浏览器")
            print("=" * 60)
            print("开始记录操作...")
            print("提示: 在浏览器中执行你的操作流程")
            print("提示: 按 Ctrl+C 停止记录并保存")
            print("=" * 60)
            print()
            
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
            
            # 找到主要的 iframe (Frame 2)
            main_frame = None
            for frame in maximo_page.frames:
                if "maximo/ui/" in frame.url and "uisessionid" in frame.url:
                    main_frame = frame
                    break
            
            if not main_frame:
                main_frame = maximo_page.main_frame
            
            recorder.add_action("session_start", {
                "page_url": maximo_page.url,
                "page_title": await maximo_page.title(),
                "frame_url": main_frame.url
            })
            
            # 监听点击事件
            async def on_click(event):
                try:
                    element = event
                    tag_name = await element.evaluate("el => el.tagName")
                    element_id = await element.get_attribute("id")
                    element_class = await element.get_attribute("class")
                    element_text = await element.inner_text() if tag_name in ["BUTTON", "A", "SPAN"] else ""
                    
                    recorder.add_action("click", {
                        "tag": tag_name,
                        "id": element_id,
                        "class": element_class,
                        "text": element_text[:50] if element_text else ""
                    })
                except:
                    pass
            
            # 监听输入事件
            async def on_input(selector, value):
                try:
                    recorder.add_action("input", {
                        "selector": selector,
                        "value": value
                    })
                except:
                    pass
            
            # 使用 CDP 监听所有事件
            cdp = await maximo_page.context.new_cdp_session(maximo_page)
            
            # 启用 DOM 和 Runtime
            await cdp.send("DOM.enable")
            await cdp.send("Runtime.enable")
            
            # 注入监听脚本到页面
            await maximo_page.evaluate("""
                () => {
                    // 记录点击
                    document.addEventListener('click', (e) => {
                        const target = e.target;
                        window._lastClick = {
                            tag: target.tagName,
                            id: target.id,
                            class: target.className,
                            text: target.innerText?.substring(0, 50) || '',
                            xpath: getXPath(target)
                        };
                    }, true);
                    
                    // 记录输入
                    document.addEventListener('input', (e) => {
                        const target = e.target;
                        window._lastInput = {
                            tag: target.tagName,
                            id: target.id,
                            name: target.name,
                            value: target.value,
                            xpath: getXPath(target)
                        };
                    }, true);
                    
                    // 记录选择
                    document.addEventListener('change', (e) => {
                        const target = e.target;
                        window._lastChange = {
                            tag: target.tagName,
                            id: target.id,
                            name: target.name,
                            value: target.value,
                            xpath: getXPath(target)
                        };
                    }, true);
                    
                    // 获取元素的 XPath
                    function getXPath(element) {
                        if (element.id) return `//*[@id="${element.id}"]`;
                        if (element === document.body) return '/html/body';
                        
                        let ix = 0;
                        const siblings = element.parentNode?.childNodes || [];
                        for (let i = 0; i < siblings.length; i++) {
                            const sibling = siblings[i];
                            if (sibling === element) {
                                return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                            }
                            if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                                ix++;
                            }
                        }
                    }
                }
            """)
            
            # 轮询检查事件
            last_click = None
            last_input = None
            last_change = None
            
            while True:
                await asyncio.sleep(0.5)
                
                # 检查点击
                try:
                    click_data = await maximo_page.evaluate("() => window._lastClick")
                    if click_data and click_data != last_click:
                        recorder.add_action("click", click_data)
                        last_click = click_data
                        await maximo_page.evaluate("() => window._lastClick = null")
                except:
                    pass
                
                # 检查输入
                try:
                    input_data = await maximo_page.evaluate("() => window._lastInput")
                    if input_data and input_data != last_input:
                        recorder.add_action("input", input_data)
                        last_input = input_data
                        await maximo_page.evaluate("() => window._lastInput = null")
                except:
                    pass
                
                # 检查选择
                try:
                    change_data = await maximo_page.evaluate("() => window._lastChange")
                    if change_data and change_data != last_change:
                        recorder.add_action("change", change_data)
                        last_change = change_data
                        await maximo_page.evaluate("() => window._lastChange = null")
                except:
                    pass
            
        except KeyboardInterrupt:
            print("\n\n停止记录...")
            
            # 保存记录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"rpa/recorded_actions_{timestamp}.json"
            recorder.save_to_file(filename)
            
            # 打印摘要
            print(f"\n=== 记录摘要 ===")
            print(f"总操作数: {len(recorder.actions)}")
            
            action_types = {}
            for action in recorder.actions:
                action_type = action["type"]
                action_types[action_type] = action_types.get(action_type, 0) + 1
            
            for action_type, count in action_types.items():
                print(f"  {action_type}: {count} 次")
            
        except Exception as e:
            print(f"✗ 错误: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("Maximo 操作记录器")
    print("=" * 60)
    asyncio.run(record_maximo_actions())
