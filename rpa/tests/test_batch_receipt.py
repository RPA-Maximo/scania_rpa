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
    
    Returns:
        dict: 处理结果，包含 success, total, processed, failed, saved, results 等字段
    """
    if po_lines_data is None:
        po_lines_data = [
            {'po_line': '7', 'quantity': '5.00', 'remark': '第一行测试备注'},
            {'po_line': '20', 'quantity': '3.00', 'remark': '第二行测试备注'}
        ]
    
    print("\n" + "=" * 60)
    print(f"批量入库工作流开始")
    print("=" * 60)
    print(f"PO 单号: {po_number}")
    print(f"PO 行数: {len(po_lines_data)}")
    print(f"自动保存: {auto_save}")
    
    p = None
    try:
        # 连接浏览器
        print("\n[步骤 0] 连接浏览器...")
        p, browser, maximo_page, main_frame = await connect_to_browser()
        print("✓ 成功连接到浏览器")
        current_title = await maximo_page.title()
        print(f"当前页面: {current_title}")
        
        # === 打开采购单详情页 ===
        print(f"\n" + "=" * 60)
        print(f"打开采购单 {po_number}")
        print("=" * 60)
        
        print("\n[步骤 1] 点击'采购'菜单...")
        try:
            await click_menu_purchase(main_frame)
            print("  ✓ 完成")
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            raise
        
        print("\n[步骤 2] 点击'接收'...")
        try:
            await click_menu_receipts(main_frame)
            print("  ✓ 完成")
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            raise
        
        print("\n[步骤 3] 查询所有 PO...")
        try:
            success, message = await search_all_po(main_frame)
            if success:
                print(f"  ✓ {message}")
            else:
                print(f"  ✗ {message}")
                return {
                    'success': False,
                    'total': len(po_lines_data),
                    'processed': 0,
                    'failed': len(po_lines_data),
                    'error': message
                }
        except Exception as e:
            print(f"  ✗ 异常: {e}")
            raise
        
        print("\n  等待列表加载...")
        try:
            success, waited = await wait_for_po_list(main_frame)
            if success:
                print(f"  ✓ 列表已加载（等待了 {waited:.1f} 秒）")
            else:
                print("  ✗ 列表加载超时")
                return {
                    'success': False,
                    'total': len(po_lines_data),
                    'processed': 0,
                    'failed': len(po_lines_data),
                    'error': '列表加载超时'
                }
        except Exception as e:
            print(f"  ✗ 异常: {e}")
            raise
        
        print(f"\n[步骤 4] 点击采购单号 '{po_number}'...")
        try:
            if await click_po_number(main_frame, po_number):
                print("  ✓ 完成")
            else:
                print("  ✗ 未找到采购单")
                return {
                    'success': False,
                    'total': len(po_lines_data),
                    'processed': 0,
                    'failed': len(po_lines_data),
                    'error': f'未找到采购单 {po_number}'
                }
        except Exception as e:
            print(f"  ✗ 异常: {e}")
            raise
        
        # === 批量处理 PO 行 ===
        print(f"\n" + "=" * 60)
        print(f"批量处理 {len(po_lines_data)} 个 PO 行")
        print("=" * 60)
        
        print("\n[步骤 5] 点击'选择已订购项'...")
        try:
            if await click_select_ordered_items(main_frame):
                print("  ✓ 完成")
            else:
                print("  ✗ 未找到'选择已订购项'按钮")
                return {
                    'success': False,
                    'total': len(po_lines_data),
                    'processed': 0,
                    'failed': len(po_lines_data),
                    'error': '未找到"选择已订购项"按钮'
                }
        except Exception as e:
            print(f"  ✗ 异常: {e}")
            raise
        
        print(f"\n[步骤 6] 批量处理 PO 行...")
        try:
            batch_result = await process_multiple_po_lines(main_frame, po_lines_data, auto_save=auto_save)
        except Exception as e:
            print(f"  ✗ 异常: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # 显示处理结果
        print(f"\n" + "=" * 60)
        print(f"批量处理结果")
        print("=" * 60)
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
                    print(f"  - PO 行 {result.get('po_line', 'N/A')}: {result['message']}")
        
        return batch_result
        
    except Exception as e:
        print(f"\n✗ 工作流异常: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'total': len(po_lines_data) if po_lines_data else 0,
            'processed': 0,
            'failed': len(po_lines_data) if po_lines_data else 0,
            'error': str(e),
            'traceback': traceback.format_exc()
        }
    finally:
        if p:
            print("\n关闭浏览器连接...")
            await p.stop()
            print("✓ 浏览器连接已关闭")


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
