"""
Maximo 页面导航模块
处理菜单点击、PO 查询等导航操作

LLM 提示：这个模块负责在 Maximo 系统中导航
"""
import asyncio
from typing import Tuple
from playwright.async_api import Frame

from .config import SELECTORS, WAIT_TIMES
from .logger import logger, log_step


async def get_current_page_title(main_frame: Frame) -> str:
    """
    获取当前页面标题
    
    Args:
        main_frame: Playwright frame 对象
    
    Returns:
        页面标题
    """
    return await main_frame.page.title()


async def check_if_on_receipts_search_page(main_frame: Frame) -> bool:
    """
    检查是否在接收查询页面（有 PO 号输入框的页面）
    
    Args:
        main_frame: Playwright frame 对象
    
    Returns:
        是否在接收查询页面
    """
    result = await main_frame.evaluate(f"""
        () => {{
            const inputs = document.querySelectorAll('input[role="textbox"]');
            for (let input of inputs) {{
                if (input.id.includes('{SELECTORS.INPUT_PO_NUMBER_PATTERN}') && input.id.includes('txt-tb')) {{
                    return true;
                }}
            }}
            return false;
        }}
    """)
    return result


async def force_navigate_to_receipts(main_frame: Frame) -> bool:
    """
    强制导航到接收查询页面
    使用 Playwright 的键盘快捷键或直接操作 DOM
    
    Args:
        main_frame: Playwright frame 对象
    
    Returns:
        是否成功导航
    """
    logger.info("尝试强制导航到接收查询页面...")
    
    # 方法1: 尝试使用 Ctrl+Home 返回主页
    logger.debug("方法1: 尝试 Ctrl+Home 返回主页")
    try:
        page = main_frame.page
        await page.keyboard.press('Control+Home')
        await asyncio.sleep(2)
        
        # 检查是否有菜单元素
        has_menu = await main_frame.evaluate(f"""
            () => {{
                const elem = document.getElementById('{SELECTORS.MENU_PURCHASE}');
                return elem !== null;
            }}
        """)
        
        if has_menu:
            logger.success("成功返回主页，菜单元素已出现")
            return True
    except Exception as e:
        logger.warning(f"Ctrl+Home 失败: {e}")
    
    # 方法2: 查找并点击"返回"或"关闭"按钮
    logger.debug("方法2: 查找返回/关闭按钮")
    try:
        result = await main_frame.evaluate("""
            () => {
                // 查找所有可能的返回按钮
                const buttons = document.querySelectorAll('img[src*="back"], img[src*="close"], img[src*="return"]');
                for (let btn of buttons) {
                    if (btn.parentElement && btn.parentElement.tagName === 'A') {
                        btn.parentElement.click();
                        return { success: true, method: 'button_click' };
                    }
                }
                return { success: false };
            }
        """)
        
        if result.get('success'):
            logger.success("找到并点击了返回按钮")
            await asyncio.sleep(2)
            return True
    except Exception as e:
        logger.warning(f"查找返回按钮失败: {e}")
    
    # 方法3: 尝试查找所有菜单项并点击采购
    logger.debug("方法3: 查找所有菜单项")
    try:
        result = await main_frame.evaluate("""
            () => {
                // 查找所有包含"采购"文本的元素
                const allElements = document.querySelectorAll('*');
                for (let elem of allElements) {
                    if (elem.textContent && elem.textContent.trim() === '采购' && elem.id) {
                        elem.click();
                        return { success: true, id: elem.id };
                    }
                }
                return { success: false };
            }
        """)
        
        if result.get('success'):
            logger.success(f"找到并点击了采购菜单: {result.get('id')}")
            await asyncio.sleep(1)
            return True
    except Exception as e:
        logger.warning(f"查找采购菜单失败: {e}")
    
    logger.error("所有强制导航方法均失败")
    return False


async def click_menu_purchase(main_frame: Frame) -> bool:
    """
    点击'采购'菜单
    
    Args:
        main_frame: Playwright frame 对象
    
    Returns:
        是否成功点击
    
    LLM 提示：这是进入采购模块的第一步
    """
    logger.debug(f"尝试点击采购菜单，ID: {SELECTORS.MENU_PURCHASE}")
    
    # 检查元素是否存在
    result = await main_frame.evaluate(f"""
        () => {{
            const elem = document.getElementById('{SELECTORS.MENU_PURCHASE}');
            if (elem) {{
                elem.click();
                return {{ success: true, exists: true }};
            }}
            return {{ success: false, exists: false }};
        }}
    """)
    
    if not result.get('exists'):
        logger.warning(f"采购菜单元素不存在 (ID: {SELECTORS.MENU_PURCHASE})")
        return False
    
    if result.get('success'):
        logger.debug("采购菜单元素存在，已执行点击")
        await asyncio.sleep(WAIT_TIMES.AFTER_MENU_CLICK)
        logger.debug(f"等待 {WAIT_TIMES.AFTER_MENU_CLICK}s 后完成")
        return True
    
    return False


async def click_menu_receipts(main_frame: Frame) -> bool:
    """
    点击'接收'菜单
    
    Args:
        main_frame: Playwright frame 对象
    
    Returns:
        是否成功点击
    
    LLM 提示：从采购模块进入接收页面
    """
    logger.debug(f"尝试点击接收菜单，ID: {SELECTORS.MENU_RECEIPTS}")
    
    # 检查元素是否存在
    result = await main_frame.evaluate(f"""
        () => {{
            const elem = document.getElementById('{SELECTORS.MENU_RECEIPTS}');
            if (elem) {{
                elem.click();
                return {{ success: true, exists: true }};
            }}
            return {{ success: false, exists: false }};
        }}
    """)
    
    if not result.get('exists'):
        logger.warning(f"接收菜单元素不存在 (ID: {SELECTORS.MENU_RECEIPTS})")
        return False
    
    if result.get('success'):
        logger.debug("接收菜单元素存在，已执行点击")
        await asyncio.sleep(WAIT_TIMES.AFTER_RECEIPTS_CLICK)
        logger.debug(f"等待 {WAIT_TIMES.AFTER_RECEIPTS_CLICK}s 后完成")
        return True
    
    return False


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
    logger.debug(f"开始查找 PO 号输入框，模式: {SELECTORS.INPUT_PO_NUMBER_PATTERN}")
    
    # 等待输入框出现
    waited = 0
    input_found = False
    input_id = None
    
    while waited < WAIT_TIMES.INPUT_SEARCH_MAX_WAIT:
        # 先检查所有 input 元素
        all_inputs = await main_frame.evaluate("""
            () => {
                const inputs = document.querySelectorAll('input[role="textbox"]');
                const result = [];
                for (let input of inputs) {
                    result.push({
                        id: input.id,
                        name: input.name,
                        value: input.value,
                        placeholder: input.placeholder
                    });
                }
                return result;
            }
        """)
        
        logger.debug(f"找到 {len(all_inputs)} 个 input[role='textbox'] 元素")
        for inp in all_inputs:
            logger.debug(f"  - ID: {inp.get('id')}, Name: {inp.get('name')}")
        
        # 查找匹配的输入框
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
            logger.success(f"找到 PO 号输入框: {input_id}")
            break
        
        logger.debug(f"未找到匹配的输入框，等待 {WAIT_TIMES.INPUT_SEARCH_INTERVAL}s...")
        await asyncio.sleep(WAIT_TIMES.INPUT_SEARCH_INTERVAL)
        waited += WAIT_TIMES.INPUT_SEARCH_INTERVAL
    
    if not input_found:
        logger.error(f"超时未找到 PO 号输入框 (等待了 {waited}s)")
        return False, "未找到 PO 号输入框"
    
    # 等待 1 秒
    logger.debug("等待 1 秒后触发回车...")
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
        logger.success(f"已在输入框 {result.get('id')} 触发回车")
        return True, f"已在输入框 {result.get('id')} 触发回车"
    else:
        logger.error("触发回车失败")
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
