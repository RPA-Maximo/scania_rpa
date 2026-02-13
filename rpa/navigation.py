"""
Maximo 页面导航模块
处理菜单点击、PO 查询等导航操作

LLM 提示：这个模块负责在 Maximo 系统中导航
"""
import asyncio
from typing import Tuple
from playwright.async_api import Frame

from .config import SELECTORS, WAIT_TIMES


async def click_menu_purchase(main_frame: Frame) -> None:
    """
    点击'采购'菜单
    
    Args:
        main_frame: Playwright frame 对象
    
    LLM 提示：这是进入采购模块的第一步
    """
    await main_frame.evaluate(f"""
        () => {{
            const elem = document.getElementById('{SELECTORS.MENU_PURCHASE}');
            if (elem) elem.click();
        }}
    """)
    await asyncio.sleep(WAIT_TIMES.AFTER_MENU_CLICK)


async def click_menu_receipts(main_frame: Frame) -> None:
    """
    点击'接收'菜单
    
    Args:
        main_frame: Playwright frame 对象
    
    LLM 提示：从采购模块进入接收页面
    """
    await main_frame.evaluate(f"""
        () => {{
            const elem = document.getElementById('{SELECTORS.MENU_RECEIPTS}');
            if (elem) elem.click();
        }}
    """)
    await asyncio.sleep(WAIT_TIMES.AFTER_RECEIPTS_CLICK)


async def search_all_po(main_frame: Frame) -> Tuple[bool, str]:
    """
    在 PO 号文本框按回车，查询所有 PO
    
    Args:
        main_frame: Playwright frame 对象
    
    Returns:
        (是否成功, 消息)
    
    LLM 提示：
    - 先等待输入框出现
    - 然后触发回车键事件
    - 这会查询所有采购单
    """
    # 等待输入框出现
    waited = 0
    input_found = False
    
    while waited < WAIT_TIMES.INPUT_SEARCH_MAX_WAIT:
        result = await main_frame.evaluate(f"""
            () => {{
                const inputs = document.querySelectorAll('input[role="textbox"]');
                for (let input of inputs) {{
                    if (input.id.includes('{SELECTORS.INPUT_PO_NUMBER_PATTERN}') && input.id.includes('txt-tb')) {{
                        return {{ found: true, id: input.id }};
                    }}
                }}
                return {{ found: false }};
            }}
        """)
        
        if result.get('found'):
            input_found = True
            input_id = result.get('id')
            break
        
        await asyncio.sleep(WAIT_TIMES.INPUT_SEARCH_INTERVAL)
        waited += WAIT_TIMES.INPUT_SEARCH_INTERVAL
    
    if not input_found:
        return False, "未找到 PO 号输入框"
    
    # 等待 1 秒
    await asyncio.sleep(1)
    
    # 触发回车
    result = await main_frame.evaluate(f"""
        () => {{
            const inputs = document.querySelectorAll('input[role="textbox"]');
            for (let input of inputs) {{
                if (input.id.includes('{SELECTORS.INPUT_PO_NUMBER_PATTERN}') && input.id.includes('txt-tb')) {{
                    // 先聚焦
                    input.focus();
                    
                    // 触发多种事件确保生效
                    const keydownEvent = new KeyboardEvent('keydown', {{
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13,
                        bubbles: true,
                        cancelable: true
                    }});
                    input.dispatchEvent(keydownEvent);
                    
                    const keypressEvent = new KeyboardEvent('keypress', {{
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13,
                        bubbles: true,
                        cancelable: true
                    }});
                    input.dispatchEvent(keypressEvent);
                    
                    const keyupEvent = new KeyboardEvent('keyup', {{
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13,
                        bubbles: true,
                        cancelable: true
                    }});
                    input.dispatchEvent(keyupEvent);
                    
                    return {{ success: true, id: input.id }};
                }}
            }}
            return {{ success: false }};
        }}
    """)
    
    if result.get('success'):
        return True, f"已在输入框 {result.get('id')} 触发回车"
    else:
        return False, "触发回车失败"


async def wait_for_po_list(main_frame: Frame) -> Tuple[bool, float]:
    """
    等待 PO 列表加载
    
    Args:
        main_frame: Playwright frame 对象
    
    Returns:
        (是否成功, 等待时间)
    
    LLM 提示：通过检查页面上是否有 anchor 元素来判断列表是否加载完成
    """
    waited = 0
    
    while waited < WAIT_TIMES.PO_LIST_MAX_WAIT:
        has_data = await main_frame.evaluate("""
            () => {
                const spans = document.querySelectorAll('span.text.label.anchor');
                return spans.length > 0;
            }
        """)
        
        if has_data:
            return True, waited
        
        await asyncio.sleep(WAIT_TIMES.PO_LIST_INTERVAL)
        waited += WAIT_TIMES.PO_LIST_INTERVAL
    
    return False, waited


async def click_po_number(main_frame: Frame, po_number: str) -> bool:
    """
    点击指定的采购单号
    
    Args:
        main_frame: Playwright frame 对象
        po_number: 采购单号，如 "CN5123"
    
    Returns:
        是否成功
    
    LLM 提示：在 PO 列表中查找并点击指定的采购单号
    """
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
        await asyncio.sleep(WAIT_TIMES.AFTER_PO_CLICK)
    
    return result.get('success')


async def click_select_ordered_items(main_frame: Frame) -> bool:
    """
    点击'选择已订购项'按钮
    
    Args:
        main_frame: Playwright frame 对象
    
    Returns:
        是否成功
    
    LLM 提示：打开选择 PO 行的弹窗
    """
    result = await main_frame.evaluate(f"""
        () => {{
            const btn = document.getElementById('{SELECTORS.BUTTON_SELECT_ORDERED_ITEMS}');
            if (btn) {{
                btn.click();
                return {{ success: true }};
            }}
            return {{ success: false }};
        }}
    """)
    
    if result.get('success'):
        # 等待弹窗加载完成，确保翻页按钮状态正确
        await asyncio.sleep(WAIT_TIMES.AFTER_SELECT_ITEMS_CLICK)
    
    return result.get('success')



async def click_confirm_button(main_frame: Frame) -> bool:
    """
    点击'确定'按钮
    
    Args:
        main_frame: Playwright frame 对象
    
    Returns:
        是否成功
    
    LLM 提示：在编辑完 PO 行后，需要点击确定按钮确认更改
    """
    result = await main_frame.evaluate(f"""
        () => {{
            const btn = document.getElementById('{SELECTORS.BUTTON_CONFIRM}');
            if (btn) {{
                btn.click();
                return {{ success: true }};
            }}
            return {{ success: false }};
        }}
    """)
    
    if result.get('success'):
        await asyncio.sleep(WAIT_TIMES.AFTER_CONFIRM_CLICK)
    
    return result.get('success')


async def click_save_button(main_frame: Frame) -> bool:
    """
    点击'保存'按钮
    
    Args:
        main_frame: Playwright frame 对象
    
    Returns:
        是否成功
    
    LLM 提示：
    - 保存按钮是一个图片元素
    - 点击后会保存所有更改到 Maximo 系统
    """
    result = await main_frame.evaluate(f"""
        () => {{
            const img = document.getElementById('{SELECTORS.BUTTON_SAVE_IMAGE}');
            if (img) {{
                // 点击图片元素
                img.click();
                
                // 也触发父元素的点击事件
                if (img.parentElement) {{
                    img.parentElement.click();
                }}
                
                return {{ success: true }};
            }}
            return {{ success: false }};
        }}
    """)
    
    if result.get('success'):
        await asyncio.sleep(WAIT_TIMES.AFTER_SAVE_CLICK)
    
    return result.get('success')



async def check_page_state(main_frame: Frame) -> Tuple[bool, str]:
    """
    检查当前页面状态，判断是否在 Manage 页面
    
    Args:
        main_frame: Playwright frame 对象
    
    Returns:
        (是否在正确页面, 状态描述)
    
    LLM 提示：
    - 通过检查侧边栏菜单元素来判断是否在 Manage 页面
    - 如果找到"采购"菜单，说明在正确的页面
    """
    result = await main_frame.evaluate(f"""
        () => {{
            const purchaseMenu = document.getElementById('{SELECTORS.MENU_PURCHASE}');
            if (purchaseMenu) {{
                return {{ found: true, message: '已在 Manage 页面' }};
            }}
            return {{ found: false, message: '未找到侧边栏菜单' }};
        }}
    """)
    
    return result.get('found', False), result.get('message', '未知状态')


async def ensure_in_manage_page(page, main_frame: Frame) -> Tuple[bool, str, Frame]:
    """
    确保浏览器在 Manage 页面，如果不在则自动导航
    
    Args:
        page: Playwright Page 对象
        main_frame: Playwright frame 对象
    
    Returns:
        (是否成功, 消息, 更新后的 main_frame)
    
    LLM 提示：
    - 先检查当前页面状态
    - 如果不在 Manage 页面，自动导航过去
    - 导航后重新查找 main_frame
    """
    from .browser import _find_main_frame
    
    # 检查当前页面状态
    is_ready, state_msg = await check_page_state(main_frame)
    
    if is_ready:
        return True, state_msg, main_frame
    
    # 检查当前URL
    current_url = page.url
    
    # 如果在登录页，无法自动处理
    if "login" in current_url.lower() or "auth" in current_url.lower():
        return False, "浏览器在登录页面，请先登录 Maximo", main_frame
    
    # 如果不在 manage 页面，尝试自动导航
    if "manage" not in current_url.lower():
        manage_url = "https://main.manage.scania-acc.suite.maximo.com/maximo/oslc/graphite/manage-shell"
        
        try:
            # 导航到 manage 页面
            await page.goto(manage_url, wait_until="domcontentloaded", timeout=30000)
            
            # 等待页面加载
            await asyncio.sleep(3)
            
            # 重新查找 main_frame
            main_frame = _find_main_frame(page)
            
            # 再次检查页面状态
            is_ready, state_msg = await check_page_state(main_frame)
            
            if is_ready:
                return True, f"已自动导航到 Manage 页面", main_frame
            else:
                return False, f"导航到 Manage 页面后仍未找到侧边栏菜单，请刷新页面", main_frame
                
        except Exception as e:
            return False, f"自动导航失败：{str(e)}\n请手动导航到 Manage 页面", main_frame
    
    # 在 manage 页面但找不到菜单，尝试刷新
    try:
        await page.reload(wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        # 重新查找 main_frame
        main_frame = _find_main_frame(page)
        
        # 再次检查
        is_ready, state_msg = await check_page_state(main_frame)
        
        if is_ready:
            return True, "页面已刷新，侧边栏菜单已就绪", main_frame
        else:
            return False, "刷新页面后仍未找到侧边栏菜单，请重新登录", main_frame
            
    except Exception as e:
        return False, f"刷新页面失败：{str(e)}", main_frame
