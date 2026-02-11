"""
批量入库接收流程测试
一次性处理多个 PO 行
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
    process_multiple_po_lines
)


async def batch_receipt_workflow(po_number="CN5123", po_lines_data=None, auto_save=False):
    """
    批量入库接收流程
    
    Args:
        po_number: 采购单号，如 "CN5123"
        po_lines_data: PO 行数据列表，格式：
            [
                {'po_line': '7', 'quantity': '5.00', 'remark': '备注1'},
                {'po_line': '20', 'quantity': '3.00', 'remark': '备注2'},
                ...
            ]
        auto_save: 是否自动保存（默认 False）
    """
    if po_lines_data is None:
        po_lines_data = [
            {'po_line': '7', 'quantity': '5.00', 'remark': '第一行测试备注'},
            {'po_line': '20', 'quantity': '3.00', 'remark': '第二行测试备注'}
        ]
    
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
        
        # === 批量处理 PO 行 ===
        print(f"\n=== 批量处理 {len(po_lines_data)} 个 PO 行 ===\n")
        
        print("步骤5: 点击'选择已订购项'...")
        if await click_select_ordered_items(main_frame):
            print("  ✓ 完成")
        else:
            print("  ✗ 未找到'选择已订购项'按钮")
            return
        
        print(f"\n步骤6: 批量处理 PO 行...")
        batch_result = await process_multiple_po_lines(main_frame, po_lines_data, auto_save=auto_save)
        
        # 显示处理结果
        print(f"\n=== 批量处理结果 ===")
        print(f"总数: {batch_result['total']}")
        print(f"成功: {batch_result['processed']}")
        print(f"失败: {batch_result['failed']}")
        
        if auto_save:
            if batch_result.get('saved'):
                print(f"保存状态: ✓ 已保存")
            else:
                print(f"保存状态: ✗ 未保存")
        
        if batch_result['success']:
            print(f"\n✓ 所有 PO 行处理完成！")
        else:
            print(f"\n⚠ 部分 PO 行处理失败")
            print("\n失败的 PO 行:")
            for result in batch_result['results']:
                if not result['success']:
                    print(f"  - PO 行 {result['po_line']}: {result['message']}")
        
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if p:
            await p.stop()


if __name__ == "__main__":
    # 示例1: 使用默认数据（处理 PO 行 7 和 20），不自动保存
    # asyncio.run(batch_receipt_workflow(po_number="CN5123"))
    
    # 示例2: 自定义 PO 行数据，启用自动保存
    custom_po_lines = [
        {'po_line': '10', 'quantity': '5.00', 'remark': '自动化测试-行10'},
        {'po_line': '22', 'quantity': '2.00', 'remark': '自动化测试-行22'},
    ]
    asyncio.run(batch_receipt_workflow(
        po_number="CN5123",
        po_lines_data=custom_po_lines,
        auto_save=False  # 启用自动保存
    ))
