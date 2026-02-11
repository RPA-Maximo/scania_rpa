"""
检查输入框上绑定的事件处理器
找出 Maximo 在 blur 时调用的函数
"""
import asyncio
import sys
sys.path.insert(0, '.')

from rpa.maximo_actions import (
    connect_to_browser,
    click_menu_purchase,
    click_menu_receipts,
    search_all_po,
    wait_for_po_list,
    click_po_number,
    click_select_ordered_items,
    find_and_check_po_line
)


async def main():
    """主函数"""
    p, browser, maximo_page, main_frame = await connect_to_browser()
    
    try:
        print("\n=== 检查事件处理器 ===\n")
        
        # 导航到页面
        print("导航到接收页面...")
        await click_menu_purchase(main_frame)
        await asyncio.sleep(0.5)
        await click_menu_receipts(main_frame)
        await asyncio.sleep(0.5)
        
        await search_all_po(main_frame)
        await wait_for_po_list(main_frame)
        
        po_number = "CN5123"
        await click_po_number(main_frame, po_number)
        await asyncio.sleep(1)
        
        await click_select_ordered_items(main_frame)
        await asyncio.sleep(1)
        
        po_line = "10"
        result = await find_and_check_po_line(main_frame, po_line)
        
        if not result.get('success'):
            print(f"✗ 未找到 PO 行")
            return
        
        row_data = result.get('rowData', {})
        input_id = row_data.get('receiptQtyInputId')
        
        print(f"找到输入框 ID: {input_id}\n")
        
        # 检查输入框上的事件处理器和属性
        info = await main_frame.evaluate(f"""
            () => {{
                const input = document.getElementById('{input_id}');
                if (!input) return null;
                
                // 获取所有事件监听器（如果可能）
                const listeners = {{}};
                
                // 检查常见的事件属性
                const eventProps = ['onblur', 'onchange', 'oninput', 'onfocus', 'onkeyup', 'onkeydown'];
                eventProps.forEach(prop => {{
                    if (input[prop]) {{
                        listeners[prop] = input[prop].toString();
                    }}
                }});
                
                // 获取所有以 'on' 开头的属性
                for (let attr of input.attributes) {{
                    if (attr.name.startsWith('on')) {{
                        listeners[attr.name] = attr.value;
                    }}
                }}
                
                // 检查特殊属性
                const specialAttrs = {{
                    ae: input.getAttribute('ae'),
                    async: input.getAttribute('async'),
                    work: input.getAttribute('work'),
                    ov: input.getAttribute('ov'),
                    ontr: input.getAttribute('ontr'),
                    db: input.getAttribute('db')
                }};
                
                // 尝试找到关联的验证或处理函数
                const windowFunctions = [];
                if (typeof window.setvalue === 'function') windowFunctions.push('setvalue');
                if (typeof window.validateInput === 'function') windowFunctions.push('validateInput');
                if (typeof window.updateField === 'function') windowFunctions.push('updateField');
                
                return {{
                    listeners: listeners,
                    specialAttrs: specialAttrs,
                    windowFunctions: windowFunctions,
                    inputId: input.id,
                    currentValue: input.value
                }};
            }}
        """)
        
        if not info:
            print("✗ 无法获取输入框信息")
            return
        
        print("=== 事件监听器 ===")
        for event, handler in info['listeners'].items():
            print(f"\n{event}:")
            # 只显示前200个字符
            handler_str = str(handler)[:200]
            print(f"  {handler_str}...")
        
        print("\n=== 特殊属性 ===")
        for attr, value in info['specialAttrs'].items():
            print(f"  {attr}: {value}")
        
        print("\n=== Window 函数 ===")
        for func in info['windowFunctions']:
            print(f"  {func}")
        
        # 尝试调用 ae 属性指定的函数
        ae_func = info['specialAttrs'].get('ae')
        if ae_func:
            print(f"\n=== 尝试调用 ae 函数: {ae_func} ===")
            
            # 先手动修改值
            await main_frame.evaluate(f"""
                () => {{
                    const input = document.getElementById('{input_id}');
                    input.value = '9.00';
                }}
            """)
            
            print("已设置 value = 9.00")
            
            # 调用 ae 函数
            result = await main_frame.evaluate(f"""
                () => {{
                    const input = document.getElementById('{input_id}');
                    if (typeof window['{ae_func}'] === 'function') {{
                        try {{
                            window['{ae_func}'](input);
                            return {{
                                success: true,
                                newValue: input.value,
                                newOv: input.getAttribute('ov')
                            }};
                        }} catch (e) {{
                            return {{
                                success: false,
                                error: e.toString()
                            }};
                        }}
                    }}
                    return {{ success: false, error: '函数不存在' }};
                }}
            """)
            
            print(f"调用结果: {result}")
            
            if result.get('success'):
                print(f"  新值: {result.get('newValue')}")
                print(f"  新 ov: {result.get('newOv')}")
        
        print("\n=== 建议 ===")
        print("根据上面的信息，我们需要:")
        print("1. 调用 ae 属性指定的函数（如果有）")
        print("2. 确保触发正确的事件处理器")
        print("3. 更新所有相关属性")
        
    finally:
        if p:
            await p.stop()


if __name__ == "__main__":
    asyncio.run(main())
