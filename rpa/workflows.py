"""
Maximo 高级工作流模块
提供批量处理等复杂业务流程

LLM 提示：这个模块组合基础操作实现复杂的业务流程
"""
import asyncio
from typing import List, Dict, Any
from playwright.async_api import Frame

from .po_operations import find_and_check_po_line, edit_receipt_quantity, edit_remark, _check_checkbox
from .navigation import click_confirm_button, click_save_button
from .config import WAIT_TIMES


async def check_po_line(main_frame: Frame, checkbox_id: str) -> Dict[str, Any]:
    """
    勾选指定的 PO 行
    
    Args:
        main_frame: Playwright frame 对象
        checkbox_id: checkbox 的 ID
    
    Returns:
        dict: {success: bool, checkboxId: str, newState: str}
    """
    return await _check_checkbox(main_frame, checkbox_id)


async def process_multiple_po_lines(
    main_frame: Frame,
    po_lines_data: List[Dict[str, str]],
    auto_save: bool = False
) -> Dict[str, Any]:
    """
    批量处理多个 PO 行：先勾选，后编辑
    
    Args:
        main_frame: Playwright frame 对象
        po_lines_data: PO 行数据列表，每个元素格式：
            {
                'po_line': '7',           # PO 行号（必填）
                'quantity': '5.00',       # 新的应到数量（可选）
                'remark': '备注文本'       # 新的备注（可选）
            }
        auto_save: 是否自动保存（默认 False）
    
    Returns:
        dict: {
            success: bool,           # 是否全部成功
            total: int,              # 总数
            processed: int,          # 成功处理的数量
            failed: int,             # 失败的数量
            results: List[dict],     # 每个 PO 行的处理结果
            saved: bool              # 是否已保存（仅当 auto_save=True 时有效）
        }
    
    LLM 提示：
    - 策略：先勾选，后编辑
    - 先勾选 checkbox 可以避免编辑操作导致勾选状态被取消
    - 顺序处理每个 PO 行
    - 某个失败不影响其他行
    - 如果 auto_save=True，处理完后自动点击确定和保存
    - 返回详细的处理结果
    
    Example:
        po_lines = [
            {'po_line': '7', 'quantity': '5.00', 'remark': '第一行备注'},
            {'po_line': '20', 'quantity': '3.00', 'remark': '第二行备注'},
            {'po_line': '25', 'quantity': '10.00'}
        ]
        result = await process_multiple_po_lines(main_frame, po_lines, auto_save=True)
    """
    results = []
    processed = 0
    failed = 0
    
    for idx, po_data in enumerate(po_lines_data):
        po_line = po_data.get('po_line')
        new_quantity = po_data.get('quantity')
        new_remark = po_data.get('remark')
        
        print(f"\n[{idx + 1}/{len(po_lines_data)}] 处理 PO 行 {po_line}...")
        
        result_item = {
            'po_line': po_line,
            'success': False,
            'message': '',
            'find_result': None,
            'quantity_result': None,
            'remark_result': None,
            'check_result': None
        }
        
        try:
            # 步骤1: 查找 PO 行（不勾选）
            print(f"  查找 PO 行 {po_line}...")
            find_result = await find_and_check_po_line(main_frame, po_line, auto_check=False)
            result_item['find_result'] = find_result
            
            if not find_result.get('success'):
                result_item['message'] = f"查找失败: {find_result.get('message')}"
                print(f"  ✗ {result_item['message']}")
                failed += 1
                results.append(result_item)
                continue
            
            print(f"  ✓ 找到 PO 行")
            row_data = find_result.get('rowData', {})
            checkbox_id = find_result.get('checkboxId')
            
            # 步骤2: 先勾选 PO 行
            print(f"  勾选 PO 行...")
            check_result = await check_po_line(main_frame, checkbox_id)
            result_item['check_result'] = check_result
            
            if check_result.get('success'):
                print(f"  ✓ 勾选成功")
            else:
                print(f"  ✗ 勾选失败")
            
            # 等待勾选状态稳定
            await asyncio.sleep(WAIT_TIMES.CHECKBOX_STABILIZE)
            
            # 步骤3: 编辑应到数量（如果提供）
            if new_quantity and row_data.get('receiptQtyInputId'):
                print(f"  修改应到数量: {row_data.get('receiptQty')} -> {new_quantity}")
                qty_result = await edit_receipt_quantity(
                    main_frame,
                    row_data['receiptQtyInputId'],
                    new_quantity
                )
                result_item['quantity_result'] = qty_result
                
                if qty_result.get('success'):
                    print(f"  ✓ 应到数量已修改")
                else:
                    print(f"  ✗ 应到数量修改失败: {qty_result.get('message')}")
            
            # 步骤4: 编辑备注（如果提供）
            if new_remark is not None and row_data.get('remarkInputId'):
                old_remark = row_data.get('remark', '')
                print(f"  修改备注: '{old_remark}' -> '{new_remark}'")
                remark_result = await edit_remark(
                    main_frame,
                    row_data['remarkInputId'],
                    new_remark
                )
                result_item['remark_result'] = remark_result
                
                if remark_result.get('success'):
                    print(f"  ✓ 备注已修改")
                else:
                    print(f"  ✗ 备注修改失败: {remark_result.get('message')}")
            
            result_item['success'] = True
            result_item['message'] = '处理成功'
            processed += 1
            print(f"  ✓ PO 行 {po_line} 处理完成")
            
        except Exception as e:
            result_item['message'] = f"处理异常: {str(e)}"
            print(f"  ✗ {result_item['message']}")
            failed += 1
        
        results.append(result_item)
    
    # 构建返回结果
    result = {
        'success': failed == 0,
        'total': len(po_lines_data),
        'processed': processed,
        'failed': failed,
        'results': results,
        'saved': False
    }
    
    # 如果启用自动保存且有成功处理的行
    if auto_save and processed > 0:
        print(f"\n=== 保存更改 ===")
        
        # 点击确定按钮
        print("点击'确定'按钮...")
        if await click_confirm_button(main_frame):
            print("  ✓ 确定成功")
            
            # 点击保存按钮
            print("点击'保存'按钮...")
            if await click_save_button(main_frame):
                print("  ✓ 保存成功")
                result['saved'] = True
            else:
                print("  ✗ 保存失败：未找到保存按钮")
        else:
            print("  ✗ 确定失败：未找到确定按钮")
    
    return result
