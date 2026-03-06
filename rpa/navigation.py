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


async def click_menu_purchase(main_frame: Frame) -> bool:
    """
    点击'采购'菜单
    使用部分 ID 匹配，兼容 Maximo 动态生成的 hash 前缀

    Args:
        main_frame: Playwright frame 对象

    Returns:
        是否成功点击

    LLM 提示：这是进入采购模块的第一步
    """
    result = await main_frame.evaluate("""
        () => {
            // 优先部分 ID 匹配，兼容动态 hash 前缀
            const elem = document.querySelector('[id*="PURCHASE_MODULE_a"]');
            if (elem) {
                elem.click();
                return { found: true, id: elem.id };
            }
            return { found: false };
        }
    """)

    if result.get('found'):
        logger.debug(f"已点击采购菜单: {result.get('id')}")
        await asyncio.sleep(WAIT_TIMES.AFTER_MENU_CLICK)
        return True
    else:
        logger.warning("未找到采购菜单元素 (尝试了 [id*='PURCHASE_MODULE_a'])")
        return False


async def click_menu_receipts(main_frame: Frame) -> bool:
    """
    点击'接收'子菜单
    等待 Purchase 下拉菜单展开后再点击，使用部分 ID 匹配

    Args:
        main_frame: Playwright frame 对象

    Returns:
        是否成功点击

    LLM 提示：从采购模块进入接收页面，需要等待子菜单可见
    """
    max_wait = 5.0
    interval = 0.5
    waited = 0.0

    while waited < max_wait:
        result = await main_frame.evaluate("""
            () => {
                const elem = document.querySelector('[id*="changeapp_RECEIPTS"]');
                if (!elem) return { found: false };
                const style = window.getComputedStyle(elem);
                const visible = style.display !== 'none' && style.visibility !== 'hidden';
                return { found: true, id: elem.id, visible: visible };
            }
        """)

        if result.get('found') and result.get('visible'):
            await main_frame.evaluate("""
                () => {
                    const elem = document.querySelector('[id*="changeapp_RECEIPTS"]');
                    if (elem) elem.click();
                }
            """)
            logger.debug(f"已点击接收子菜单: {result.get('id')}")
            await asyncio.sleep(WAIT_TIMES.AFTER_RECEIPTS_CLICK)
            return True

        await asyncio.sleep(interval)
        waited += interval

    logger.warning(f"等待 {max_wait}s 后未找到可见的接收子菜单元素")
    return False


async def _try_click_list_or_newsearch(main_frame: Frame) -> None:
    """
    尝试点击 Maximo 工具栏中的"返回列表"或"新建查询"按钮。
    已在接收模块但处于详情页时，菜单点击后可能停留在原页面，
    此函数作为补救措施强制跳转到列表/查询视图。
    """
    await main_frame.evaluate("""
        () => {
            // 优先找"返回列表"按钮（Maximo 标准工具栏 ID 含 BACK 或 LIST）
            const candidates = [
                '[id*="BACK-tbb"]',
                '[id*="LIST-tbb"]',
                '[id*="QUERY-tbb"]',
                '[id*="SEARCH-tbb"]',
            ];
            for (const sel of candidates) {
                const el = document.querySelector(sel);
                if (el) { el.click(); return; }
            }
        }
    """)


async def _poll_for_receipts_page(main_frame: Frame, timeout: float = 10.0) -> bool:
    """
    轮询等待接收查询页面加载完成（含 tfrow 过滤输入框）。
    比固定 sleep 更可靠，适用于网络较慢的场景。
    """
    interval = 0.5
    waited = 0.0
    while waited < timeout:
        if await check_if_on_receipts_search_page(main_frame):
            return True
        await asyncio.sleep(interval)
        waited += interval
    return False


async def navigate_to_receipts_page(main_frame: Frame, max_retries: int = 2) -> bool:
    """
    从任意 Maximo 页面导航到接收查询页面（接收单主页）

    无论当前处于哪个 Maximo 模块，均可通过此函数自动导航到接收查询页面。
    内部使用灵活的 CSS 选择器 + 子菜单可见性等待 + 重试机制。

    Args:
        main_frame: Playwright frame 对象
        max_retries: 导航失败时的最大重试次数（默认 2 次）

    Returns:
        是否成功到达接收查询页面

    LLM 提示：保活 worker 和 RPA 工作流应调用此函数代替手动导航序列
    """
    # 已在接收查询页面，直接返回
    if await check_if_on_receipts_search_page(main_frame):
        logger.debug("已在接收查询页面，无需导航")
        return True

    for attempt in range(max_retries + 1):
        if attempt > 0:
            logger.warning(f"导航失败，开始第 {attempt} 次重试...")
            await asyncio.sleep(2)

        logger.debug(f"导航到接收查询页面（第 {attempt + 1} 次尝试）...")

        purchase_ok = await click_menu_purchase(main_frame)
        if not purchase_ok:
            logger.warning("采购菜单点击失败，跳过本次尝试")
            continue

        receipts_ok = await click_menu_receipts(main_frame)
        if not receipts_ok:
            logger.warning("接收子菜单点击失败，跳过本次尝试")
            continue

        # 轮询等待页面加载（最多 10 秒），比固定 sleep 更可靠
        if await _poll_for_receipts_page(main_frame, timeout=10.0):
            logger.success("成功导航到接收查询页面")
            return True

        # 仍未到达列表页：可能停留在详情页，尝试点击"返回列表/新建查询"
        logger.warning("菜单点击后未到达列表页，尝试点击返回列表按钮...")
        await _try_click_list_or_newsearch(main_frame)

        # 再给 5 秒轮询
        if await _poll_for_receipts_page(main_frame, timeout=5.0):
            logger.success("通过返回列表按钮成功到达接收查询页面")
            return True

        logger.warning("点击菜单后仍未到达接收查询页面")

    logger.error(f"经过 {max_retries + 1} 次尝试后仍无法导航到接收查询页面")
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
