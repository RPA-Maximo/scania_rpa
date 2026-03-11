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
    po_line: str = None,
    item_num: str = None,
    max_pages: int = None,
    auto_check: bool = True
) -> Dict[str, Any]:
    """
    查找并勾选指定的 PO 行（支持按行号或项目号查找）
    
    Args:
        main_frame: Playwright frame 对象
        po_line: PO 行号，如 "20"（可选，与 item_num 二选一）
        item_num: 项目号，如 "20326920"（可选，与 po_line 二选一）
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
    - 支持按 PO 行号或项目号查找
    - 先在当前页查找
    - 如果没找到，自动翻页继续查找
    - 找到后根据 auto_check 决定是否勾选
    - 返回行数据包括所有字段的值和可编辑字段的 input ID
    """
    if not po_line and not item_num:
        return {
            'success': False,
            'message': '必须提供 po_line 或 item_num 参数'
        }
    
    if max_pages is None:
        max_pages = LIMITS.MAX_PAGES_TO_SEARCH
    
    search_key = po_line if po_line else item_num
    search_type = 'PO 行' if po_line else '项目号'
    
    # 先在当前页查找
    result = await _find_po_line_in_current_page(main_frame, po_line=po_line, item_num=item_num)
    
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
                'message': f'找到{search_type} {search_key}（未勾选）',
                'checkboxId': result.get('checkboxId'),
                'newState': result.get('checkboxChecked'),
                'rowData': result.get('rowData')
            }
    
    # 当前页没找到，尝试翻页
    for page_num in range(max_pages):
        try:
            # 查找所有包含 "next_on.gif" 的图片（表示下一页按钮可用）
            next_button_img = main_frame.locator(f'img[src*="{SELECTORS.NEXT_PAGE_BUTTON_IMAGE}"]')
            
            # 等待按钮出现并稳定
            try:
                await next_button_img.last.wait_for(state='visible', timeout=3000)
            except:
                # 没有可用的下一页按钮，可能已经是最后一页
                return {
                    'success': False,
                    'message': f'未找到{search_type} {search_key}（已到最后一页，共翻 {page_num + 1} 页）'
                }
            
            # 检查按钮是否存在
            count = await next_button_img.count()
            
            if count == 0:
                # 没有可用的下一页按钮，可能已经是最后一页
                return {
                    'success': False,
                    'message': f'未找到{search_type} {search_key}（已到最后一页，共翻 {page_num + 1} 页）'
                }
            
            # 获取按钮的父元素 <a> 标签
            # 使用 last 而不是 first，因为弹出窗口通常是最后加载的（在最上层）
            next_button_link = next_button_img.locator('..').last
            
            # 等待元素稳定后再滚动
            await asyncio.sleep(WAIT_TIMES.SCROLL_DELAY)
            
            # 使用更安全的方式滚动和点击
            try:
                await next_button_link.scroll_into_view_if_needed(timeout=3000)
                await asyncio.sleep(WAIT_TIMES.SCROLL_DELAY)
            except:
                # 如果滚动失败，尝试直接点击
                pass
            
            # 点击按钮前再次确认元素可见
            await next_button_link.wait_for(state='visible', timeout=3000)
            await next_button_link.click(force=True)
            
            # 等待页面加载完成
            await asyncio.sleep(WAIT_TIMES.AFTER_PAGE_TURN)
            
            # 额外等待确保 DOM 稳定
            await asyncio.sleep(0.5)
            
        except Exception as e:
            return {
                'success': False,
                'message': f'未找到{search_type} {search_key}（翻页失败: {str(e)}）'
            }
        
        # 再次查找
        result = await _find_po_line_in_current_page(main_frame, po_line=po_line, item_num=item_num)
        
        if result.get('found'):
            if auto_check:
                check_result = await _check_checkbox(main_frame, result.get('checkboxId'))
                check_result['rowData'] = result.get('rowData')
                return check_result
            else:
                return {
                    'success': True,
                    'message': f'找到{search_type} {search_key}（未勾选）',
                    'checkboxId': result.get('checkboxId'),
                    'newState': result.get('checkboxChecked'),
                    'rowData': result.get('rowData')
                }
    
    return {
        'success': False,
        'message': f'未找到{search_type} {search_key}（已翻 {max_pages} 页）'
    }


async def _find_po_line_in_current_page(main_frame: Frame, po_line: str = None, item_num: str = None) -> Dict[str, Any]:
    """
    在当前页查找 PO 行并返回完整数据（支持按行号或项目号查找）
    
    Args:
        main_frame: Playwright frame 对象
        po_line: PO 行号（可选）
        item_num: 项目号（可选）
    
    Returns:
        dict: {
            success: bool,
            found: bool,
            checkboxId: str,
            rowData: dict  # 包含所有字段值和 input ID
        }
    
    LLM 提示：
    - 支持按 PO 行号或项目号查找
    - 通过查找对应的 <span> 元素
    - 使用 closest('tr') 找到整行
    - 遍历所有单元格提取数据
    - 保存可编辑字段的 input ID 用于后续编辑
    """
    # 构建查找条件
    if po_line:
        search_condition = f"text === '{po_line}' && title === '{po_line}'"
        search_column = COLUMNS.PO_LINE
        search_type = "PO 行号"
    elif item_num:
        search_condition = f"text === '{item_num}' && title === '{item_num}'"
        search_column = COLUMNS.ITEM_NUM
        search_type = "项目号"
    else:
        return {'success': False, 'found': False}
    
    result = await main_frame.evaluate(f"""
        () => {{
            // 查找所有包含行号或项目号的 span
            const allSpans = document.querySelectorAll('span[title]');
            
            // 收集所有可能的值用于调试
            const foundValues = [];
            const debugInfo = [];
            
            for (let span of allSpans) {{
                const text = span.textContent.trim();
                const title = span.getAttribute('title');
                
                // 找到包含这个 span 的 tr 行
                let row = span.closest('tr');
                if (row) {{
                    // 在同一行中查找 checkbox
                    const checkbox = row.querySelector('a[role="checkbox"] img');
                    if (checkbox) {{
                        // 这是一个有效的数据行，提取列索引
                        const cells = row.querySelectorAll('td');
                        
                        // 找到当前 span 在哪一列
                        let columnIndex = -1;
                        for (let i = 0; i < cells.length; i++) {{
                            if (cells[i].contains(span)) {{
                                columnIndex = i;
                                break;
                            }}
                        }}
                        
                        // 记录调试信息
                        if (columnIndex === {search_column}) {{
                            debugInfo.push({{
                                value: text,
                                title: title,
                                columnIndex: columnIndex,
                                matched: {search_condition}
                            }});
                            
                            foundValues.push(text);
                        }}
                        
                        // 检查是否是目标值
                        if (columnIndex === {search_column} && {search_condition}) {{
                            // 提取行数据
                            const rowData = {{}};
                            
                            // 遍历所有单元格
                            for (let i = 0; i < cells.length; i++) {{
                                const cell = cells[i];
                                
                                // 查找 span（只读字段）
                                // 优先找带 title 的 span，兜底找任意 span
                                const span = cell.querySelector('span[title]') || cell.querySelector('span');
                                if (span) {{
                                    const spanText = span.textContent.trim();
                                    const spanTitle = span.getAttribute('title') || '';
                                    // title 属性通常包含完整值（不被 CSS 截断）
                                    const val = spanTitle || spanText;

                                    // 根据列索引判断字段
                                    if (i === {COLUMNS.PO_LINE}) rowData.poLine = val;
                                    else if (i === {COLUMNS.ITEM_NUM}) rowData.itemNum = val;
                                    else if (i === {COLUMNS.DESCRIPTION}) rowData.description = val;
                                    else if (i === {COLUMNS.TO_STOREROOM}) rowData.toStoreroom = val;
                                    else if (i === {COLUMNS.ORDER_QTY}) rowData.orderQty = val;
                                    else if (i === {COLUMNS.RESERVED_QTY}) rowData.reservedQty = val;
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
            }}
            
            return {{ 
                success: false, 
                found: false,
                availableValues: foundValues,
                debugInfo: debugInfo
            }};
        }}
    """)
    
    # 如果没找到，打印调试信息
    if not result.get('found'):
        print(f"  [调试] 在列 {search_column} 中查找{search_type}: {po_line or item_num}")
        print(f"  [调试] 找到的值: {result.get('availableValues', [])}")
        if result.get('debugInfo'):
            print(f"  [调试] 详细信息: {result.get('debugInfo')}")
    
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


async def debug_table_columns(main_frame: Frame) -> Dict[str, Any]:
    """
    诊断工具：扫描当前弹窗中第一条有效数据行的所有列内容，
    帮助校验 config.py 中 ColumnIndexes 的列索引是否正确。

    返回:
        {
          'columns': [
            {'index': 0, 'text': '...', 'title': '...', 'tag': 'span/input/td'},
            ...
          ]
        }
    """
    result = await main_frame.evaluate("""
        () => {
            const allSpans = document.querySelectorAll('span[title]');
            for (let span of allSpans) {
                let row = span.closest('tr');
                if (!row) continue;
                const checkbox = row.querySelector('a[role="checkbox"] img');
                if (!checkbox) continue;

                const cells = row.querySelectorAll('td');
                const columns = [];
                for (let i = 0; i < cells.length; i++) {
                    const cell = cells[i];
                    const inputEl = cell.querySelector('input');
                    const spanEl = cell.querySelector('span[title]') || cell.querySelector('span');
                    if (inputEl) {
                        columns.push({
                            index: i, text: inputEl.value, title: '',
                            tag: 'input', inputType: inputEl.type || 'text'
                        });
                    } else if (spanEl) {
                        columns.push({
                            index: i,
                            text: spanEl.textContent.trim(),
                            title: spanEl.getAttribute('title') || '',
                            tag: 'span'
                        });
                    } else {
                        const txt = cell.textContent.trim();
                        if (txt) columns.push({index: i, text: txt, title: '', tag: 'td'});
                    }
                }
                return {success: true, columns: columns};
            }
            return {success: false, columns: [], message: '未找到有效数据行'};
        }
    """)
    return result
