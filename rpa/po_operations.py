"""
Maximo PO 行操作模块
处理 PO 行的查找、勾选、编辑等操作

LLM 提示：这个模块是核心业务逻辑，处理具体的 PO 行操作
"""
import asyncio
from typing import Dict, Any
from playwright.async_api import Frame

from .config import SELECTORS, COLUMNS, WAIT_TIMES, LIMITS
from .utils import escape_js_string


async def find_and_check_po_line(
    main_frame: Frame,
    po_line: str,
    max_pages: int = None,
    auto_check: bool = True
) -> Dict[str, Any]:
    """
    查找并勾选指定的 PO 行
    
    Args:
        main_frame: Playwright frame 对象
        po_line: PO 行号，如 "20"
        max_pages: 最多翻页次数（默认使用配置值）
        auto_check: 是否自动勾选（默认 True）
    
    Returns:
        dict: {
            success: bool,
            message: str,
            checkboxId: str,
            newState: str,
            rowData: dict  # 包含行数据和 input ID
        }
    
    LLM 提示：
    - 先在当前页查找
    - 如果没找到，自动翻页继续查找
    - 找到后根据 auto_check 决定是否勾选
    - 返回行数据包括所有字段的值和可编辑字段的 input ID
    """
    if max_pages is None:
        max_pages = LIMITS.MAX_PAGES_TO_SEARCH
    
    # 先在当前页查找
    result = await _find_po_line_in_current_page(main_frame, po_line)
    
    if result.get('found'):
        # 找到了
        if auto_check:
            # 勾选并返回数据
            check_result = await _check_checkbox(main_frame, result.get('checkboxId'))
            check_result['rowData'] = result.get('rowData')
            return check_result
        else:
            # 不勾选，直接返回数据
            return {
                'success': True,
                'message': f'找到 PO 行 {po_line}（未勾选）',
                'checkboxId': result.get('checkboxId'),
                'newState': result.get('checkboxChecked'),
                'rowData': result.get('rowData')
            }
    
    # 当前页没找到，尝试翻页
    for page_num in range(max_pages):
        try:
            # 查找所有包含 "next_on.gif" 的图片（表示下一页按钮可用）
            next_button_img = main_frame.locator(f'img[src*="{SELECTORS.NEXT_PAGE_BUTTON_IMAGE}"]')
            
            # 检查按钮是否存在
            count = await next_button_img.count()
            
            if count == 0:
                # 没有可用的下一页按钮，可能已经是最后一页
                return {
                    'success': False,
                    'message': f'未找到 PO 行 {po_line}（已到最后一页，共翻 {page_num + 1} 页）'
                }
            
            # 获取按钮的父元素 <a> 标签
            next_button_link = next_button_img.locator('..').first
            
            # 滚动到按钮
            await next_button_link.scroll_into_view_if_needed()
            await asyncio.sleep(WAIT_TIMES.SCROLL_DELAY)
            
            # 点击按钮
            await next_button_link.click(force=True)
            
            # 等待页面加载
            await asyncio.sleep(WAIT_TIMES.AFTER_PAGE_TURN)
            
        except Exception as e:
            return {
                'success': False,
                'message': f'未找到 PO 行 {po_line}（翻页失败: {str(e)}）'
            }
        
        # 再次查找
        result = await _find_po_line_in_current_page(main_frame, po_line)
        
        if result.get('found'):
            if auto_check:
                check_result = await _check_checkbox(main_frame, result.get('checkboxId'))
                check_result['rowData'] = result.get('rowData')
                return check_result
            else:
                return {
                    'success': True,
                    'message': f'找到 PO 行 {po_line}（未勾选）',
                    'checkboxId': result.get('checkboxId'),
                    'newState': result.get('checkboxChecked'),
                    'rowData': result.get('rowData')
                }
    
    return {
        'success': False,
        'message': f'未找到 PO 行 {po_line}（已翻 {max_pages} 页）'
    }


async def _find_po_line_in_current_page(main_frame: Frame, po_line: str) -> Dict[str, Any]:
    """
    在当前页查找 PO 行并返回完整数据
    
    Args:
        main_frame: Playwright frame 对象
        po_line: PO 行号
    
    Returns:
        dict: {
            success: bool,
            found: bool,
            checkboxId: str,
            rowData: dict  # 包含所有字段值和 input ID
        }
    
    LLM 提示：
    - 通过 PO 行号查找对应的 <span> 元素
    - 使用 closest('tr') 找到整行
    - 遍历所有单元格提取数据
    - 保存可编辑字段的 input ID 用于后续编辑
    """
    result = await main_frame.evaluate(f"""
        () => {{
            // 查找所有包含行号的 span
            const allSpans = document.querySelectorAll('span[title]');
            
            // 收集所有可能的行号用于调试
            const foundLines = [];
            
            for (let span of allSpans) {{
                const text = span.textContent.trim();
                const title = span.getAttribute('title');
                
                // 记录所有看起来像行号的 span
                if (text && title && text === title && /^\\d+$/.test(text)) {{
                    foundLines.push(text);
                }}
                
                // 检查是否是目标行号
                if (text === '{po_line}' && title === '{po_line}') {{
                    // 找到包含这个 span 的 tr 行
                    let row = span.closest('tr');
                    if (row) {{
                        // 在同一行中查找 checkbox
                        const checkbox = row.querySelector('a[role="checkbox"] img');
                        if (!checkbox) {{
                            continue;
                        }}
                        
                        // 提取行数据
                        const cells = row.querySelectorAll('td');
                        const rowData = {{}};
                        
                        // 遍历所有单元格
                        for (let i = 0; i < cells.length; i++) {{
                            const cell = cells[i];
                            
                            // 查找 span（只读字段）
                            const span = cell.querySelector('span[title]');
                            if (span) {{
                                const spanText = span.textContent.trim();
                                const spanTitle = span.getAttribute('title');
                                
                                // 根据列索引判断字段
                                if (i === {COLUMNS.PO_LINE}) rowData.poLine = spanText;
                                else if (i === {COLUMNS.ITEM_NUM}) rowData.itemNum = spanText;
                                else if (i === {COLUMNS.DESCRIPTION}) rowData.description = spanTitle || spanText;
                                else if (i === {COLUMNS.TO_STOREROOM}) rowData.toStoreroom = spanText;
                                else if (i === {COLUMNS.ORDER_QTY}) rowData.orderQty = spanText;
                                else if (i === {COLUMNS.RESERVED_QTY}) rowData.reservedQty = spanText;
                            }}
                            
                            // 查找 input（可编辑字段）
                            const input = cell.querySelector('input');
                            if (input) {{
                                const inputValue = input.value;
                                const inputId = input.id;
                                
                                // 根据列索引判断字段，同时保存 input ID
                                if (i === {COLUMNS.RECEIPT_QTY}) {{
                                    rowData.receiptQty = inputValue;
                                    rowData.receiptQtyInputId = inputId;
                                }}
                                else if (i === {COLUMNS.ORDER_UNIT}) {{
                                    rowData.orderUnit = inputValue;
                                    rowData.orderUnitInputId = inputId;
                                }}
                                else if (i === {COLUMNS.INVOICE}) {{
                                    rowData.invoice = inputValue;
                                    rowData.invoiceInputId = inputId;
                                }}
                                else if (i === {COLUMNS.REMARK}) {{
                                    rowData.remark = inputValue;
                                    rowData.remarkInputId = inputId;
                                }}
                            }}
                        }}
                        
                        return {{
                            success: true,
                            found: true,
                            checkboxId: checkbox.id,
                            checkboxChecked: checkbox.getAttribute('checked'),
                            rowId: row.id,
                            rowData: rowData
                        }};
                    }}
                }}
            }}
            
            return {{ 
                success: false, 
                found: false,
                availableLines: foundLines
            }};
        }}
    """)
    
    return result


async def _check_checkbox(main_frame: Frame, checkbox_id: str) -> Dict[str, Any]:
    """
    勾选 checkbox
    
    Args:
        main_frame: Playwright frame 对象
        checkbox_id: checkbox 的 ID
    
    Returns:
        dict: {success: bool, checkboxId: str, newState: str}
    
    LLM 提示：点击 checkbox 并等待状态更新
    """
    result = await main_frame.evaluate(f"""
        () => {{
            const checkbox = document.getElementById('{checkbox_id}');
            if (checkbox) {{
                checkbox.click();
                
                // 等待状态更新
                return new Promise((resolve) => {{
                    setTimeout(() => {{
                        resolve({{
                            success: true,
                            checkboxId: '{checkbox_id}',
                            newState: checkbox.getAttribute('checked')
                        }});
                    }}, {int(WAIT_TIMES.CHECKBOX_STATE_UPDATE * 1000)});
                }});
            }}
            return {{ success: false }};
        }}
    """)
    
    if result.get('success'):
        await asyncio.sleep(WAIT_TIMES.AFTER_CHECKBOX_CLICK)
    
    return result


async def edit_receipt_quantity(
    main_frame: Frame,
    input_id: str,
    new_quantity: str
) -> Dict[str, Any]:
    """
    编辑应到数量 - 使用 Playwright 的 type() 方法模拟键盘输入
    
    Args:
        main_frame: Playwright frame 对象
        input_id: 应到数量输入框的 ID
        new_quantity: 新的应到数量，如 "5.00"
    
    Returns:
        dict: {success: bool, message: str, oldValue: str, newValue: str, inputId: str}
    
    LLM 提示：
    - 使用 evaluate 直接操作 DOM
    - 使用 Playwright 的 type() 方法模拟真实键盘输入
    """
    try:
        # 获取旧值并聚焦输入框
        result = await main_frame.evaluate(f"""
            () => {{
                const input = document.getElementById('{input_id}');
                if (!input) return {{ success: false }};
                
                const oldValue = input.value;
                
                // 聚焦并选中所有文本
                input.focus();
                input.select();
                
                return {{ success: true, oldValue: oldValue }};
            }}
        """)
        
        if not result.get('success'):
            return {
                'success': False,
                'message': '未找到应到数量输入框',
                'inputId': input_id
            }
        
        old_value = result.get('oldValue')
        
        # 使用 page.keyboard 来模拟真实输入（Frame 没有 keyboard 属性）
        page = main_frame.page
        
        # 先删除现有内容
        await page.keyboard.press('Control+A')
        await page.keyboard.press('Backspace')
        
        # 输入新值
        await page.keyboard.type(new_quantity)
        
        # 让输入框失去焦点 - 点击页面其他位置而不是按 Tab
        # 这样可以避免焦点移动到 checkbox 导致意外触发
        await main_frame.evaluate("""
            () => {
                // 让输入框失去焦点
                document.activeElement.blur();
            }
        """)
        
        # 等待一下让 Maximo 处理
        await asyncio.sleep(WAIT_TIMES.AFTER_INPUT_EDIT)
        
        # 验证新值
        new_value = await main_frame.evaluate(f"""
            () => {{
                const input = document.getElementById('{input_id}');
                return input ? input.value : null;
            }}
        """)
        
        return {
            'success': True,
            'message': '应到数量已修改',
            'oldValue': old_value,
            'newValue': new_value,
            'inputId': input_id
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'修改失败: {str(e)}',
            'inputId': input_id
        }


async def edit_remark(
    main_frame: Frame,
    input_id: str,
    remark_text: str
) -> Dict[str, Any]:
    """
    编辑备注 - 使用 Playwright 的 type() 方法模拟键盘输入
    
    Args:
        main_frame: Playwright frame 对象
        input_id: 备注输入框的 ID
        remark_text: 备注文本，最大 254 字符
    
    Returns:
        dict: {success: bool, message: str, oldValue: str, newValue: str, inputId: str}
    
    LLM 提示：
    - 使用 evaluate 直接操作 DOM
    - 使用 Playwright 的 type() 方法模拟真实键盘输入
    """
    # 限制备注长度
    if len(remark_text) > LIMITS.MAX_REMARK_LENGTH:
        remark_text = remark_text[:LIMITS.MAX_REMARK_LENGTH]
    
    try:
        # 获取旧值并聚焦输入框
        result = await main_frame.evaluate(f"""
            () => {{
                const input = document.getElementById('{input_id}');
                if (!input) return {{ success: false }};
                
                const oldValue = input.value;
                
                // 聚焦并选中所有文本
                input.focus();
                input.select();
                
                return {{ success: true, oldValue: oldValue }};
            }}
        """)
        
        if not result.get('success'):
            return {
                'success': False,
                'message': '未找到备注输入框',
                'inputId': input_id
            }
        
        old_value = result.get('oldValue')
        
        # 使用 page.keyboard 来模拟真实输入（Frame 没有 keyboard 属性）
        page = main_frame.page
        
        # 先删除现有内容
        await page.keyboard.press('Control+A')
        await page.keyboard.press('Backspace')
        
        # 输入新值
        await page.keyboard.type(remark_text)
        
        # 让输入框失去焦点 - 点击页面其他位置而不是按 Tab
        # 这样可以避免焦点移动到 checkbox 导致意外触发
        await main_frame.evaluate("""
            () => {
                // 让输入框失去焦点
                document.activeElement.blur();
            }
        """)
        
        # 等待一下让 Maximo 处理
        await asyncio.sleep(WAIT_TIMES.AFTER_INPUT_EDIT)
        
        # 验证新值
        new_value = await main_frame.evaluate(f"""
            () => {{
                const input = document.getElementById('{input_id}');
                return input ? input.value : null;
            }}
        """)
        
        return {
            'success': True,
            'message': '备注已修改',
            'oldValue': old_value,
            'newValue': new_value,
            'inputId': input_id
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'修改失败: {str(e)}',
            'inputId': input_id
        }
