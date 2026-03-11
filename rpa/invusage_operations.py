"""
库存使用情况（Inventory Usage / Issue）RPA 操作模块

功能：
- 导航到指定出库单（按流水号/usagenum）
- 保存当前记录
- 点击"创建剩余余量使用情况"左侧菜单项
- 读取新生成的使用情况号（流水号）
- 将新流水号回传 WMS
"""
import asyncio
from typing import Optional, Tuple

from playwright.async_api import Frame

from .config import WAIT_TIMES
from .logger import logger


# ── 页面识别 ─────────────────────────────────────────────────────────────────

async def check_if_on_invusage_page(frame: Frame) -> bool:
    """判断当前是否在库存使用情况模块"""
    return await frame.evaluate("""
        () => {
            const title = document.title || '';
            const url = window.location.href || '';
            if (url.includes('invusage') || title.includes('库存使用情况')) return true;
            // 通过页面特有元素判断
            return !!(
                document.querySelector('[id*="invusage"]') ||
                document.querySelector('[id*="INVUSAGE"]')
            );
        }
    """)


async def get_current_usage_num(frame: Frame) -> Optional[str]:
    """
    读取当前详情页的使用情况号（流水号/usagenum）
    主表头部的 usagenum 字段
    """
    result = await frame.evaluate("""
        () => {
            // Maximo 的使用情况号通常在 usagenum 输入框
            const patterns = [
                '[id*="usagenum"]',
                '[id*="USAGENUM"]',
            ];
            for (const p of patterns) {
                const el = document.querySelector(p);
                if (el) {
                    const val = el.value || el.textContent || el.innerText || '';
                    if (val.trim()) return val.trim();
                }
            }
            return null;
        }
    """)
    return result


# ── 导航到指定记录 ────────────────────────────────────────────────────────────

async def navigate_to_invusage_record(
    frame: Frame,
    usage_num: str,
    max_wait: float = 15.0,
) -> bool:
    """
    在库存使用情况列表页搜索并打开指定出库单

    Args:
        frame:     Playwright frame 对象
        usage_num: 使用情况号（流水号，如 '4988'）
        max_wait:  最长等待秒数

    Returns:
        是否成功打开目标记录
    """
    logger.info(f"导航到出库单: {usage_num}")

    # 1. 检查是否已有搜索框（在列表页）
    on_list = await frame.evaluate("""
        () => {
            // 列表页有全文搜索框或过滤行
            return !!(
                document.querySelector('[id*="quicksearch"]') ||
                document.querySelector('[id*="QUICKSEARCH"]') ||
                document.querySelector('input[id*="usagenum"]')
            );
        }
    """)

    if not on_list:
        # 尝试点击"列表视图"按钮返回列表
        logger.debug("不在列表页，尝试返回列表...")
        clicked = await frame.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a, button'));
                const target = links.find(el =>
                    (el.textContent || '').includes('列表视图') ||
                    (el.id || '').includes('listview')
                );
                if (target) { target.click(); return true; }
                return false;
            }
        """)
        if clicked:
            await asyncio.sleep(WAIT_TIMES.AFTER_MENU_CLICK)

    # 2. 在搜索框输入 usage_num 并回车
    searched = await frame.evaluate(f"""
        () => {{
            // 尝试直接在列表过滤行的 usagenum 列输入
            const inputs = Array.from(document.querySelectorAll('input'));
            const target = inputs.find(el => {{
                const id = (el.id || '').toLowerCase();
                const placeholder = (el.placeholder || '').toLowerCase();
                return id.includes('usagenum') || id.includes('usage_num') ||
                       placeholder.includes('使用情况');
            }});
            if (target) {{
                target.value = '{usage_num}';
                target.dispatchEvent(new Event('change', {{bubbles: true}}));
                target.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}}));
                target.dispatchEvent(new KeyboardEvent('keyup', {{key: 'Enter', bubbles: true}}));
                return true;
            }}
            // 备选：全文搜索框
            const qs = document.querySelector('[id*="quicksearch"], [id*="QUICKSEARCH"]');
            if (qs) {{
                qs.value = '{usage_num}';
                qs.dispatchEvent(new Event('change', {{bubbles: true}}));
                qs.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}}));
                return true;
            }}
            return false;
        }}
    """)

    if not searched:
        logger.warning(f"未找到搜索框，无法搜索 {usage_num}")
        return False

    await asyncio.sleep(2.0)  # 等待搜索结果

    # 3. 点击第一条匹配的记录（精确匹配 usage_num 文本）
    clicked_record = await frame.evaluate(f"""
        () => {{
            const links = Array.from(document.querySelectorAll('a, span.text.label.anchor'));
            const target = links.find(el => (el.textContent || '').trim() === '{usage_num}');
            if (target) {{ target.click(); return true; }}
            return false;
        }}
    """)

    if not clicked_record:
        logger.warning(f"列表中未找到记录: {usage_num}")
        return False

    # 4. 等待详情页加载
    waited = 0.0
    interval = 0.5
    while waited < max_wait:
        current = await get_current_usage_num(frame)
        if current and current.strip() == usage_num.strip():
            logger.success(f"已打开出库单: {usage_num}")
            return True
        await asyncio.sleep(interval)
        waited += interval

    logger.warning(f"等待超时，未确认打开出库单: {usage_num}")
    return False


# ── 保存当前记录 ──────────────────────────────────────────────────────────────

async def save_invusage(frame: Frame) -> bool:
    """
    点击右上角保存按钮（必须在点击"将状态变更为完成"之前执行）
    """
    saved = await frame.evaluate("""
        () => {
            // Maximo 保存按钮通常有 SAVE 相关的 ID
            const patterns = [
                '[id*="SAVE"][id*="tbb"]',
                '[id*="save"][id*="image"]',
                'button[title*="保存"]',
                'a[id*="SAVE"]',
            ];
            for (const p of patterns) {
                const el = document.querySelector(p);
                if (el) { el.click(); return true; }
            }
            return false;
        }
    """)
    if saved:
        logger.info("已点击保存按钮")
        await asyncio.sleep(WAIT_TIMES.AFTER_SAVE_CLICK)
    else:
        logger.warning("未找到保存按钮")
    return saved


# ── 创建剩余使用情况 ──────────────────────────────────────────────────────────

async def click_create_remaining(frame: Frame) -> bool:
    """
    点击左侧菜单"创建剩余余量使用情况"

    Maximo 库存使用情况模块左侧菜单项（更多操作 → 创建剩余余量使用情况）
    """
    clicked = await frame.evaluate("""
        () => {
            // 按文本精确查找菜单链接
            const allLinks = Array.from(document.querySelectorAll('a, li, button, span'));
            const keywords = ['创建剩余余量使用情况', '创建剩余使用情况', 'createremaining'];
            for (const kw of keywords) {
                const target = allLinks.find(el => {
                    const text = (el.textContent || el.title || el.id || '').toLowerCase();
                    return text.includes(kw.toLowerCase());
                });
                if (target) {
                    target.click();
                    return true;
                }
            }
            return false;
        }
    """)

    if clicked:
        logger.info("已点击"创建剩余余量使用情况"")
        await asyncio.sleep(3.0)  # 等待 Maximo 创建新记录
    else:
        logger.warning("未找到"创建剩余余量使用情况"菜单项")
    return clicked


async def get_newly_created_usage_num(
    frame: Frame,
    original_num: str,
    max_wait: float = 15.0,
) -> Optional[str]:
    """
    在 Maximo 创建剩余使用情况后，读取新生成的使用情况号

    Args:
        frame:        Playwright frame 对象
        original_num: 原出库单号（用于排除）
        max_wait:     最长等待秒数

    Returns:
        新的使用情况号，失败返回 None
    """
    waited = 0.0
    interval = 0.5
    while waited < max_wait:
        current = await get_current_usage_num(frame)
        if current and current.strip() != original_num.strip():
            logger.success(f"检测到新流水号: {current}")
            return current.strip()
        await asyncio.sleep(interval)
        waited += interval

    logger.warning("等待超时，未检测到新流水号")
    return None


# ── 完整工作流 ────────────────────────────────────────────────────────────────

async def create_remaining_invusage(
    frame: Frame,
    usage_num: str,
) -> Tuple[bool, Optional[str]]:
    """
    完整的"创建剩余使用情况"RPA 工作流：
      1. 打开指定出库单（usage_num）
      2. 保存当前记录
      3. 点击"创建剩余余量使用情况"
      4. 读取并返回新流水号

    Args:
        frame:     Playwright frame 对象
        usage_num: 原出库单号（流水号）

    Returns:
        (success: bool, new_usage_num: str | None)
    """
    # 步骤1：导航到记录
    if not await navigate_to_invusage_record(frame, usage_num):
        return False, None

    # 步骤2：先保存（Maximo 要求先保存再变更状态/创建剩余）
    if not await save_invusage(frame):
        logger.warning("保存失败，继续尝试创建剩余使用情况")

    await asyncio.sleep(1.0)

    # 步骤3：点击"创建剩余余量使用情况"
    if not await click_create_remaining(frame):
        return False, None

    # 步骤4：读取新流水号
    new_num = await get_newly_created_usage_num(frame, usage_num)
    if not new_num:
        return False, None

    return True, new_num
