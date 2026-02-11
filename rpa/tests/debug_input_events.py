"""
调试输入框事件的脚本
用于找出 Maximo 真正需要的事件和状态变化
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


async def debug_input_field_auto():
    """自动运行工作流并调试输入框"""
    p, browser, maximo_page, main_frame = await connect_to_browser()
    
    try:
        print("\n=== 自动调试模式 ===")
        print("将自动打开 PO 并获取输入框 ID\n")
        
        # 导航到接收页面
        print("步骤1: 导航到接收页面...")
        await click_menu_purchase(main_frame)
        await asyncio.sleep(0.5)
        await click_menu_receipts(main_frame)
        await asyncio.sleep(0.5)
        
        # 查询 PO
        print("步骤2: 查询采购单...")
        await search_all_po(main_frame)
        await wait_for_po_list(main_frame)
        
        # 打开 PO
        po_number = "CN5123"
        print(f"步骤3: 打开采购单 {po_number}...")
        await click_po_number(main_frame, po_number)
        await asyncio.sleep(1)
        
        # 点击选择已订购项
        print("步骤4: 点击'选择已订购项'...")
        await click_select_ordered_items(main_frame)
        await asyncio.sleep(1)
        
        # 查找并勾选 PO 行
        po_line = "10"
        print(f"步骤5: 查找 PO 行 {po_line}...")
        result = await find_and_check_po_line(main_frame, po_line)
        
        if not result.get('success'):
            print(f"✗ 未找到 PO 行: {result.get('message')}")
            return
        
        row_data = result.get('rowData', {})
        receipt_qty_id = row_data.get('receiptQtyInputId')
        remark_id = row_data.get('remarkInputId')
        
        print(f"\n✓ 找到输入框:")
        print(f"  应到数量 ID: {receipt_qty_id}")
        print(f"  备注 ID: {remark_id}")
        
        # 让用户选择要调试哪个
        print("\n请选择要调试的输入框:")
        print("1. 应到数量")
        print("2. 备注")
        choice = input("输入选择 (1 或 2): ").strip()
        
        if choice == "1":
            input_id = receipt_qty_id
        elif choice == "2":
            input_id = remark_id
        else:
            print("无效选择")
            return
        
        await debug_input_with_id(main_frame, input_id)
        
    finally:
        if p:
            await p.stop()


async def debug_input_field_manual():
    """手动输入 ID 调试"""
    p, browser, maximo_page, main_frame = await connect_to_browser()
    
    try:
        print("\n=== 手动调试模式 ===")
        print("请在浏览器中找到输入框，按 F12 打开开发者工具")
        print("点击左上角的'选择元素'图标，然后点击输入框")
        print("在 Elements 面板找到 <input id=\"...\"> 并复制 ID\n")
        
        input_id = input("输入框 ID: ").strip()
        
        if not input_id:
            print("未输入 ID，退出")
            return
        
        await debug_input_with_id(main_frame, input_id)
        
    finally:
        if p:
            await p.stop()


async def debug_input_with_id(main_frame, input_id):
    """使用指定 ID 调试输入框"""
    # 安装事件监听器
    print(f"\n正在为输入框 {input_id} 安装事件监听器...")
    
    result = await main_frame.evaluate(f"""
        () => {{
            const input = document.getElementById('{input_id}');
            if (!input) {{
                return {{ success: false, message: '未找到输入框' }};
            }}
            
            // 记录所有事件
            window.inputEvents = [];
            
            const events = [
                'focus', 'blur', 'input', 'change', 
                'keydown', 'keyup', 'keypress',
                'click', 'mousedown', 'mouseup',
                'focusin', 'focusout'
            ];
            
            events.forEach(eventName => {{
                input.addEventListener(eventName, (e) => {{
                    window.inputEvents.push({{
                        event: eventName,
                        timestamp: Date.now(),
                        value: input.value,
                        activeElement: document.activeElement === input ? 'self' : document.activeElement?.id || 'other'
                    }});
                    console.log(`[事件] ${{eventName}} - 值: ${{input.value}}`);
                }});
            }});
            
            return {{ 
                success: true, 
                message: '事件监听器已安装',
                currentValue: input.value,
                inputId: input.id,
                inputType: input.type,
                inputClass: input.className
            }};
        }}
    """)
    
    if not result.get('success'):
        print(f"✗ {result.get('message')}")
        return
    
    print(f"✓ {result.get('message')}")
    print(f"  当前值: {result.get('currentValue')}")
    print(f"  类型: {result.get('inputType')}")
    print(f"  Class: {result.get('inputClass')}")
    
    print("\n现在请手动编辑这个输入框，然后按回车...")
    input("按回车键查看捕获的事件...")
    
    # 获取捕获的事件
    events = await main_frame.evaluate("""
        () => {
            return window.inputEvents || [];
        }
    """)
    
    print(f"\n=== 捕获到 {len(events)} 个事件 ===")
    for i, event in enumerate(events, 1):
        print(f"{i}. {event['event']:12s} - 值: {event['value']:20s} - 焦点: {event['activeElement']}")
    
    # 检查输入框状态
    print("\n=== 检查输入框状态 ===")
    state = await main_frame.evaluate(f"""
        () => {{
            const input = document.getElementById('{input_id}');
            if (!input) return null;
            
            return {{
                value: input.value,
                hasFocus: document.activeElement === input,
                activeElementId: document.activeElement?.id,
                classList: Array.from(input.classList),
                attributes: Array.from(input.attributes).map(attr => ({{
                    name: attr.name,
                    value: attr.value
                }})),
                parentClasses: input.parentElement ? Array.from(input.parentElement.classList) : [],
                // 检查是否有 dirty 标记
                isDirty: input.classList.contains('dirty') || 
                         input.classList.contains('modified') ||
                         input.getAttribute('data-dirty') === 'true'
            }};
        }}
    """)
    
    if state:
        print(f"值: {state['value']}")
        print(f"有焦点: {state['hasFocus']}")
        print(f"当前焦点元素: {state['activeElementId']}")
        print(f"Class 列表: {state['classList']}")
        print(f"是否标记为 dirty: {state['isDirty']}")
        print(f"父元素 Class: {state['parentClasses']}")
        
        print("\n所有属性:")
        for attr in state['attributes']:
            print(f"  {attr['name']}: {attr['value']}")
    
    print("\n=== 调试完成 ===")


async def main():
    """主函数"""
    print("\n=== 输入框事件调试工具 ===")
    print("请选择调试模式:")
    print("1. 自动模式（自动打开 PO 并获取输入框 ID）")
    print("2. 手动模式（手动输入输入框 ID）")
    
    choice = input("\n输入选择 (1 或 2): ").strip()
    
    if choice == "1":
        await debug_input_field_auto()
    elif choice == "2":
        await debug_input_field_manual()
    else:
        print("无效选择")


if __name__ == "__main__":
    asyncio.run(main())
