"""
Maximo 操作的可复用函数库
"""
import asyncio


async def connect_to_browser(cdp_url="http://localhost:9223"):
    """连接到已启动的浏览器"""
    from playwright.async_api import async_playwright
    
    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp(cdp_url)
    
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
        raise Exception("未找到 Maximo 页面")
    
    # 找到主 iframe
    main_frame = None
    for frame in maximo_page.frames:
        if "maximo/ui/" in frame.url and "uisessionid" in frame.url:
            main_frame = frame
            break
    
    if not main_frame:
        main_frame = maximo_page.main_frame
    
    return p, browser, maximo_page, main_frame


async def click_menu_purchase(main_frame):
    """点击'采购'菜单"""
    await main_frame.evaluate("""
        () => {
            const elem = document.getElementById('mea59820d_ns_menu_PURCHASE_MODULE_a');
            if (elem) elem.click();
        }
    """)
    await asyncio.sleep(1)


async def click_menu_receipts(main_frame):
    """点击'接收'菜单"""
    await main_frame.evaluate("""
        () => {
            const elem = document.getElementById('mea59820d_ns_menu_PURCHASE_MODULE_sub_changeapp_RECEIPTS_a');
            if (elem) elem.click();
        }
    """)
    await asyncio.sleep(3)


async def search_all_po(main_frame):
    """
    在 PO 号文本框按回车，查询所有 PO
    改进：先等待输入框出现，再触发回车
    """
    # 等待输入框出现
    max_wait = 10
    wait_interval = 0.5
    waited = 0
    input_found = False
    
    while waited < max_wait:
        result = await main_frame.evaluate("""
            () => {
                const inputs = document.querySelectorAll('input[role="textbox"]');
                for (let input of inputs) {
                    if (input.id.includes('tfrow') && input.id.includes('txt-tb')) {
                        return { found: true, id: input.id };
                    }
                }
                return { found: false };
            }
        """)
        
        if result.get('found'):
            input_found = True
            break
        
        await asyncio.sleep(wait_interval)
        waited += wait_interval
    
    if not input_found:
        return False, "未找到 PO 号输入框"
    
    # 等待 1 秒
    await asyncio.sleep(1)
    
    # 触发回车
    result = await main_frame.evaluate("""
        () => {
            const inputs = document.querySelectorAll('input[role="textbox"]');
            for (let input of inputs) {
                if (input.id.includes('tfrow') && input.id.includes('txt-tb')) {
                    // 先聚焦
                    input.focus();
                    
                    // 触发多种事件确保生效
                    const keydownEvent = new KeyboardEvent('keydown', {
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13,
                        bubbles: true,
                        cancelable: true
                    });
                    input.dispatchEvent(keydownEvent);
                    
                    const keypressEvent = new KeyboardEvent('keypress', {
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13,
                        bubbles: true,
                        cancelable: true
                    });
                    input.dispatchEvent(keypressEvent);
                    
                    const keyupEvent = new KeyboardEvent('keyup', {
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13,
                        bubbles: true,
                        cancelable: true
                    });
                    input.dispatchEvent(keyupEvent);
                    
                    return { success: true, id: input.id };
                }
            }
            return { success: false };
        }
    """)
    
    if result.get('success'):
        return True, f"已在输入框 {result.get('id')} 触发回车"
    else:
        return False, "触发回车失败"


async def wait_for_po_list(main_frame, max_wait=15):
    """等待 PO 列表加载"""
    wait_interval = 0.5
    waited = 0
    
    while waited < max_wait:
        has_data = await main_frame.evaluate("""
            () => {
                const spans = document.querySelectorAll('span.text.label.anchor');
                return spans.length > 0;
            }
        """)
        
        if has_data:
            return True, waited
        
        await asyncio.sleep(wait_interval)
        waited += wait_interval
    
    return False, waited


async def click_po_number(main_frame, po_number):
    """点击指定的采购单号"""
    result = await main_frame.evaluate(f"""
        () => {{
            const spans = document.querySelectorAll('span[mxevent="click"]');
            for (let span of spans) {{
                if (span.textContent.trim() === '{po_number}') {{
                    span.click();
                    const mousedownEvent = new MouseEvent('mousedown', {{ bubbles: true, cancelable: true, view: window }});
                    span.dispatchEvent(mousedownEvent);
                    const mouseupEvent = new MouseEvent('mouseup', {{ bubbles: true, cancelable: true, view: window }});
                    span.dispatchEvent(mouseupEvent);
                    const clickEvent = new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }});
                    span.dispatchEvent(clickEvent);
                    return {{ success: true, id: span.id }};
                }}
            }}
            return {{ success: false }};
        }}
    """)
    
    if result.get('success'):
        await asyncio.sleep(5)
    
    return result.get('success')


async def click_select_ordered_items(main_frame):
    """点击'选择已订购项'按钮"""
    result = await main_frame.evaluate("""
        () => {
            const btn = document.getElementById('m52852ffc_bg_button_selorditem-pb');
            if (btn) {
                btn.click();
                return { success: true };
            }
            return { success: false };
        }
    """)
    
    if result.get('success'):
        # 等待弹窗加载完成，确保翻页按钮状态正确
        await asyncio.sleep(4)
    
    return result.get('success')


async def find_and_check_po_line(main_frame, po_line, max_pages=5):
    """
    查找并勾选指定的 PO 行
    使用方案1: 通过 PO 行号查找同一行的 checkbox
    
    Args:
        main_frame: Playwright frame 对象
        po_line: PO 行号，如 "20"
        max_pages: 最多翻页次数
    
    Returns:
        dict: {success: bool, message: str, checkbox_id: str}
    """
    # 先在当前页查找
    result = await _find_po_line_in_current_page(main_frame, po_line)
    
    if result.get('found'):
        # 找到了，勾选并返回数据
        check_result = await _check_checkbox(main_frame, result.get('checkboxId'))
        check_result['rowData'] = result.get('rowData')
        return check_result
    
    # 当前页没找到，尝试翻页
    for page_num in range(max_pages):
        # 使用 Playwright 的 locator 点击下一页按钮
        try:
            # 查找所有包含 "next_on.gif" 的图片（表示下一页按钮可用）
            next_button_img = main_frame.locator('img[src*="tablebtn_next_on.gif"]')
            
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
            await asyncio.sleep(0.5)
            
            # 点击按钮
            await next_button_link.click(force=True)
            
            # 等待页面加载
            await asyncio.sleep(3)
            
        except Exception as e:
            return {
                'success': False,
                'message': f'未找到 PO 行 {po_line}（翻页失败: {str(e)}）'
            }
        
        # 再次查找
        result = await _find_po_line_in_current_page(main_frame, po_line)
        
        if result.get('found'):
            check_result = await _check_checkbox(main_frame, result.get('checkboxId'))
            check_result['rowData'] = result.get('rowData')
            return check_result
    
    return {
        'success': False,
        'message': f'未找到 PO 行 {po_line}（已翻 {max_pages} 页）'
    }


async def _find_po_line_in_current_page(main_frame, po_line):
    """在当前页查找 PO 行并返回完整数据"""
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
                if (text && title && text === title && /^\d+$/.test(text)) {{
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
                                if (i === 2) rowData.poLine = spanText;
                                else if (i === 3) rowData.itemNum = spanText;
                                else if (i === 4) rowData.description = spanTitle || spanText;
                                else if (i === 7) rowData.toStoreroom = spanText;
                                else if (i === 9) rowData.orderQty = spanText;
                                else if (i === 10) rowData.reservedQty = spanText;
                            }}
                            
                            // 查找 input（可编辑字段）
                            const input = cell.querySelector('input');
                            if (input) {{
                                const inputValue = input.value;
                                
                                // 根据列索引判断字段
                                if (i === 8) rowData.receiptQty = inputValue;
                                else if (i === 11) rowData.orderUnit = inputValue;
                                else if (i === 12) rowData.invoice = inputValue;
                                else if (i === 13) rowData.remark = inputValue;
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


async def _check_checkbox(main_frame, checkbox_id):
    """勾选 checkbox"""
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
                    }}, 200);
                }});
            }}
            return {{ success: false }};
        }}
    """)
    
    if result.get('success'):
        await asyncio.sleep(1)
    
    return result
