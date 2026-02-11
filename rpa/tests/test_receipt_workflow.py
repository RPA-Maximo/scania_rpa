"""
完整的入库接收流程测试
从打开采购单到勾选指定的 PO 行
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
    edit_receipt_quantity,
    edit_remark
)


async def receipt_workflow(po_number="CN5123", po_line="20", new_quantity=None, new_remark=None):
    """
    入库接收完整流程
    
    Args:
        po_number: 采购单号，如 "CN5123"
        po_line: PO 行号，如 "20"
        new_quantity: 新的应到数量，如 "5.00"（可选）
        new_remark: 新的备注文本（可选）
    """
    p = None
    try:
        # 连接浏览器
        p, browser, maximo_page, main_frame = await connect_to_browser()
        print("✓ 成功连接到浏览器")
        print(f"当前页面: {await maximo_page.title()}\n")
        
        # === 打开采购单详情页 ===
        print(f"=== 打开采购单 {po_number} ===\n")
        
        print("步骤1: 点击'采购'菜单...")
        await click_menu_purchase(main_frame)
        print("  ✓ 完成")
        
        print("\n步骤2: 点击'接收'...")
        await click_menu_receipts(main_frame)
        print("  ✓ 完成")
        
        print("\n步骤3: 查询所有 PO...")
        success, message = await search_all_po(main_frame)
        if success:
            print(f"  ✓ {message}")
        else:
            print(f"  ✗ {message}")
            return
        
        print("  等待列表加载...")
        success, waited = await wait_for_po_list(main_frame)
        if success:
            print(f"  ✓ 列表已加载（等待了 {waited:.1f} 秒）")
        else:
            print("  ✗ 列表加载超时")
            return
        
        print(f"\n步骤4: 点击采购单号 '{po_number}'...")
        if await click_po_number(main_frame, po_number):
            print("  ✓ 完成")
        else:
            print("  ✗ 未找到采购单")
            return
        
        # === 选择并勾选 PO 行 ===
        print(f"\n=== 选择 PO 行 {po_line} ===\n")
        
        print("步骤5: 点击'选择已订购项'...")
        if await click_select_ordered_items(main_frame):
            print("  ✓ 完成")
        else:
            print("  ✗ 未找到'选择已订购项'按钮")
            return
        
        print(f"\n步骤6: 查找并勾选 PO 行 '{po_line}'...")
        result = await find_and_check_po_line(main_frame, po_line)
        
        if result.get('success'):
            print("  ✓ 勾选成功")
            print(f"    Checkbox ID: {result.get('checkboxId')}")
            print(f"    新状态: {result.get('newState')}")
            
            # 显示提取的行数据
            if result.get('rowData'):
                print(f"\n  提取的行数据:")
                row_data = result['rowData']
                print(f"    PO 行: {row_data.get('poLine', 'N/A')}")
                print(f"    项目: {row_data.get('itemNum', 'N/A')}")
                print(f"    描述: {row_data.get('description', 'N/A')}")
                print(f"    目标库房: {row_data.get('toStoreroom', 'N/A')}")
                print(f"    应到数量: {row_data.get('receiptQty', 'N/A')}")
                print(f"    订购量: {row_data.get('orderQty', 'N/A')}")
                print(f"    预定数量: {row_data.get('reservedQty', 'N/A')}")
                print(f"    订购单位: {row_data.get('orderUnit', 'N/A')}")
                print(f"    发票: {row_data.get('invoice', 'N/A')}")
                print(f"    备注: {row_data.get('remark', 'N/A')}")
                
                # === 编辑字段 ===
                if new_quantity or new_remark:
                    print(f"\n=== 编辑字段 ===\n")
                
                # 编辑应到数量
                if new_quantity and row_data.get('receiptQtyInputId'):
                    print(f"步骤7: 修改应到数量为 '{new_quantity}'...")
                    qty_result = await edit_receipt_quantity(
                        main_frame,
                        row_data['receiptQtyInputId'],
                        new_quantity
                    )
                    if qty_result.get('success'):
                        print(f"  ✓ {qty_result.get('message')}")
                        print(f"    原值: {qty_result.get('oldValue')}")
                        print(f"    新值: {qty_result.get('newValue')}")
                    else:
                        print(f"  ✗ {qty_result.get('message')}")
                
                # 编辑备注
                if new_remark and row_data.get('remarkInputId'):
                    print(f"\n步骤8: 修改备注为 '{new_remark}'...")
                    remark_result = await edit_remark(
                        main_frame,
                        row_data['remarkInputId'],
                        new_remark
                    )
                    if remark_result.get('success'):
                        print(f"  ✓ {remark_result.get('message')}")
                        print(f"    原值: {remark_result.get('oldValue')}")
                        print(f"    新值: {remark_result.get('newValue')}")
                    else:
                        print(f"  ✗ {remark_result.get('message')}")
        else:
            print(f"  ✗ {result.get('message')}")
            return
        
        print(f"\n✓ 流程完成！")
        print(f"  采购单: {po_number}")
        print(f"  PO 行: {po_line}")
        print(f"  状态: 已勾选")
        
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if p:
            await p.stop()


if __name__ == "__main__":
    # 可以修改这里的参数
    # 示例1: 只勾选，不编辑
    # asyncio.run(receipt_workflow(po_number="CN5123", po_line="7"))
    
    # 示例2: 勾选并编辑应到数量和备注
    asyncio.run(receipt_workflow(
        po_number="CN5123", 
        po_line="7",
        new_quantity="3.00",
        new_remark="自动化测试备注"
    ))
