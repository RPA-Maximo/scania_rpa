"""
对比手动编辑和脚本编辑后的输入框状态差异
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
    find_and_check_po_line,
    edit_receipt_quantity
)


async def capture_input_state(main_frame, input_id):
    """捕获输入框的完整状态"""
    state = await main_frame.evaluate(f"""
        () => {{
            const input = document.getElementById('{input_id}');
            if (!input) return null;
            
            // 获取所有属性
            const attrs = {{}};
            for (let attr of input.attributes) {{
                attrs[attr.name] = attr.value;
            }}
            
            // 获取计算样式
            const computedStyle = window.getComputedStyle(input);
            
            return {{
                // 基本信息
                value: input.value,
                defaultValue: input.defaultValue,
                
                // 所有属性
                attributes: attrs,
                
                // 特殊属性
                ov: input.getAttribute('ov'),  // original value?
                work: input.getAttribute('work'),
                async: input.getAttribute('async'),
                ae: input.getAttribute('ae'),
                
                // DOM 属性
                classList: Array.from(input.classList),
                dataset: Object.assign({{}}, input.dataset),
                
                // 父元素信息
                parentClasses: input.parentElement ? Array.from(input.parentElement.classList) : [],
                
                // 检查是否有变更标记
                isDirty: input.classList.contains('dirty') || 
                         input.classList.contains('modified') ||
                         input.getAttribute('data-dirty') === 'true' ||
                         input.getAttribute('work') === '1',
                
                // 焦点状态
                hasFocus: document.activeElement === input,
                activeElementId: document.activeElement?.id
            }};
        }}
    """)
    return state


async def main():
    """主函数"""
    p, browser, maximo_page, main_frame = await connect_to_browser()
    
    try:
        print("\n=== 对比手动编辑 vs 脚本编辑 ===\n")
        
        # 导航到页面
        print("步骤1: 导航到接收页面...")
        await click_menu_purchase(main_frame)
        await asyncio.sleep(0.5)
        await click_menu_receipts(main_frame)
        await asyncio.sleep(0.5)
        
        print("步骤2: 查询采购单...")
        await search_all_po(main_frame)
        await wait_for_po_list(main_frame)
        
        po_number = "CN5123"
        print(f"步骤3: 打开采购单 {po_number}...")
        await click_po_number(main_frame, po_number)
        await asyncio.sleep(1)
        
        print("步骤4: 点击'选择已订购项'...")
        await click_select_ordered_items(main_frame)
        await asyncio.sleep(1)
        
        po_line = "10"
        print(f"步骤5: 查找 PO 行 {po_line}...")
        result = await find_and_check_po_line(main_frame, po_line)
        
        if not result.get('success'):
            print(f"✗ 未找到 PO 行")
            return
        
        row_data = result.get('rowData', {})
        input_id = row_data.get('receiptQtyInputId')
        
        print(f"\n找到输入框 ID: {input_id}")
        print(f"当前值: {row_data.get('receiptQty')}")
        
        # === 第一部分：手动编辑 ===
        print("\n" + "="*60)
        print("第一部分：请手动编辑输入框")
        print("="*60)
        print(f"1. 在浏览器中找到 PO 行 {po_line} 的应到数量输入框")
        print(f"2. 手动修改值（比如改成 7.00）")
        print(f"3. 点击页面其他地方让输入框失去焦点")
        input("\n完成后按回车继续...")
        
        # 捕获手动编辑后的状态
        manual_state = await capture_input_state(main_frame, input_id)
        
        print("\n手动编辑后的状态:")
        print(f"  值: {manual_state['value']}")
        print(f"  原始值 (ov): {manual_state['ov']}")
        print(f"  work 属性: {manual_state['work']}")
        print(f"  isDirty: {manual_state['isDirty']}")
        
        # 刷新页面（上一页再下一页）
        print("\n正在刷新页面（模拟上一页再下一页）...")
        await maximo_page.go_back()
        await asyncio.sleep(1)
        await maximo_page.go_forward()
        await asyncio.sleep(2)
        
        # 检查值是否保留
        manual_state_after_refresh = await capture_input_state(main_frame, input_id)
        print(f"\n刷新后的值: {manual_state_after_refresh['value']}")
        print(f"✓ 手动编辑的值{'保留了' if manual_state_after_refresh['value'] == manual_state['value'] else '丢失了'}")
        
        # === 第二部分：脚本编辑 ===
        print("\n" + "="*60)
        print("第二部分：使用脚本编辑")
        print("="*60)
        
        # 重新导航到页面
        print("重新导航到页面...")
        await click_menu_purchase(main_frame)
        await asyncio.sleep(0.5)
        await click_menu_receipts(main_frame)
        await asyncio.sleep(0.5)
        await search_all_po(main_frame)
        await wait_for_po_list(main_frame)
        await click_po_number(main_frame, po_number)
        await asyncio.sleep(1)
        await click_select_ordered_items(main_frame)
        await asyncio.sleep(1)
        
        # 重新查找 PO 行
        result = await find_and_check_po_line(main_frame, po_line)
        row_data = result.get('rowData', {})
        input_id = row_data.get('receiptQtyInputId')
        
        print(f"使用脚本修改值为 8.00...")
        await edit_receipt_quantity(main_frame, input_id, "8.00")
        await asyncio.sleep(0.5)
        
        # 捕获脚本编辑后的状态
        script_state = await capture_input_state(main_frame, input_id)
        
        print("\n脚本编辑后的状态:")
        print(f"  值: {script_state['value']}")
        print(f"  原始值 (ov): {script_state['ov']}")
        print(f"  work 属性: {script_state['work']}")
        print(f"  isDirty: {script_state['isDirty']}")
        
        # 刷新页面
        print("\n正在刷新页面（模拟上一页再下一页）...")
        await maximo_page.go_back()
        await asyncio.sleep(1)
        await maximo_page.go_forward()
        await asyncio.sleep(2)
        
        # 检查值是否保留
        script_state_after_refresh = await capture_input_state(main_frame, input_id)
        print(f"\n刷新后的值: {script_state_after_refresh['value']}")
        print(f"✗ 脚本编辑的值{'保留了' if script_state_after_refresh['value'] == script_state['value'] else '丢失了'}")
        
        # === 对比差异 ===
        print("\n" + "="*60)
        print("状态对比")
        print("="*60)
        
        print("\n手动编辑后:")
        print(f"  value: {manual_state['value']}")
        print(f"  ov: {manual_state['ov']}")
        print(f"  work: {manual_state['work']}")
        print(f"  async: {manual_state['async']}")
        print(f"  ae: {manual_state['ae']}")
        
        print("\n脚本编辑后:")
        print(f"  value: {script_state['value']}")
        print(f"  ov: {script_state['ov']}")
        print(f"  work: {script_state['work']}")
        print(f"  async: {script_state['async']}")
        print(f"  ae: {script_state['ae']}")
        
        print("\n关键差异:")
        for key in ['value', 'ov', 'work', 'async', 'ae']:
            manual_val = manual_state.get(key)
            script_val = script_state.get(key)
            if manual_val != script_val:
                print(f"  {key}: 手动={manual_val}, 脚本={script_val} ❌")
        
        print("\n所有属性对比:")
        manual_attrs = set(manual_state['attributes'].keys())
        script_attrs = set(script_state['attributes'].keys())
        
        all_attrs = manual_attrs | script_attrs
        for attr in sorted(all_attrs):
            manual_val = manual_state['attributes'].get(attr, '(无)')
            script_val = script_state['attributes'].get(attr, '(无)')
            if manual_val != script_val:
                print(f"  {attr}: 手动={manual_val}, 脚本={script_val}")
        
    finally:
        if p:
            await p.stop()


if __name__ == "__main__":
    asyncio.run(main())
