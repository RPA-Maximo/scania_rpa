"""
库存使用情况（Inventory Usage / Issue）RPA 操作模块

选择器策略：
  优先使用 data-attribute（Application Designer 中定义的字段名，静态稳定）
  和 event 属性（Maximo Action 名称，不随版本变动）。
  避免使用动态生成的 id="mx..."，因其在每次页面渲染时可能变化。

  XPath 模板：//{tag}[@data-attribute='{FIELD}']
  事件模板：  //a[@event='{ACTION}'] 或 [id*='{ACTION}']
"""
import asyncio
from typing import Dict, List, Optional, Tuple

from playwright.async_api import Frame

from .config import WAIT_TIMES
from .logger import logger

# Maximo 判定"忙"状态的选择器（进度条 / busy indicator）
_BUSY_SELECTORS = [
    ".progress-indicator",
    "[id*='progressbar']",
    ".maximo-busy",
    "[aria-busy='true']",
]
_BUSY_POLL_INTERVAL = 0.3
_BUSY_MAX_WAIT = 30.0


# ── Maximo 忙状态等待 ─────────────────────────────────────────────────────────

async def wait_for_maximo_ready(frame: Frame, max_wait: float = _BUSY_MAX_WAIT) -> bool:
    """
    等待 Maximo 完成网络请求（进度条消失 / aria-busy 消除）。
    在每次点击保存、变更状态后必须调用，否则下一步操作可能打到"加载中"的页面。

    Returns:
        True=页面就绪，False=等待超时
    """
    waited = 0.0
    while waited < max_wait:
        busy = await frame.evaluate("""
            () => {
                const selectors = [
                    '.progress-indicator',
                    '[id*="progressbar"]',
                    '.maximo-busy',
                    '[aria-busy="true"]',
                ];
                for (const s of selectors) {
                    const el = document.querySelector(s);
                    if (el && el.offsetParent !== null) return true;
                }
                return false;
            }
        """)
        if not busy:
            return True
        await asyncio.sleep(_BUSY_POLL_INTERVAL)
        waited += _BUSY_POLL_INTERVAL

    logger.warning(f"wait_for_maximo_ready: 等待超时 ({max_wait}s)")
    return False


# ── 字段读取（data-attribute 选择器）────────────────────────────────────────

async def _get_field_value(frame: Frame, field_name: str) -> Optional[str]:
    """
    通过 data-attribute 读取 Maximo 表单字段值。
    field_name 对应 Application Designer 中的属性名（大小写不敏感）。
    """
    result = await frame.evaluate(f"""
        () => {{
            const upper = '{field_name.upper()}';
            const lower = '{field_name.lower()}';
            const el = document.querySelector(
                `[data-attribute='${{upper}}'], [data-attribute='${{lower}}']`
            );
            if (!el) return null;
            return (el.value || el.textContent || el.innerText || '').trim() || null;
        }}
    """)
    return result


# ── 页面识别 ─────────────────────────────────────────────────────────────────

async def check_if_on_invusage_page(frame: Frame) -> bool:
    """
    判断当前是否在库存使用情况模块。
    通过 USAGENUM 字段（data-attribute）和 URL 双重判断。
    """
    return await frame.evaluate("""
        () => {
            if (window.location.href.includes('invusage')) return true;
            return !!(document.querySelector("[data-attribute='USAGENUM']"));
        }
    """)


async def check_if_on_detail_page(frame: Frame) -> bool:
    """判断是否在详情页（有 USAGENUM 字段且有 STORELOC/INVUSELINETYPE 字段）"""
    return await frame.evaluate("""
        () => !!( document.querySelector("[data-attribute='USAGENUM']") &&
                  document.querySelector("[data-attribute='STORELOC']") )
    """)


# ── 流水号读取 ────────────────────────────────────────────────────────────────

async def get_current_usage_num(frame: Frame) -> Optional[str]:
    """
    读取当前详情页的使用情况号（流水号）。
    使用 data-attribute='USAGENUM'，比 id 选择器稳定。
    """
    return await _get_field_value(frame, "USAGENUM")


# ── 可用量检查（负数预警）────────────────────────────────────────────────────

async def check_availability(frame: Frame) -> Dict:
    """
    扫描所有子表行的「可用量」(AVAILBAL)，检测负数情况。
    可用量 < 0 → 库存不足，不应继续出库。

    Returns:
        {
          'has_negative': bool,
          'negative_lines': [{'item': str, 'availbal': float, 'row_index': int}]
        }
    """
    result = await frame.evaluate("""
        () => {
            // 查找所有 data-attribute='AVAILBAL' 的元素（表格行中）
            const els = Array.from(
                document.querySelectorAll("[data-attribute='AVAILBAL']")
            );
            const negative = [];
            els.forEach((el, idx) => {
                const raw = (el.value || el.textContent || '').trim();
                const val = parseFloat(raw.replace(/,/g, ''));
                if (!isNaN(val) && val < 0) {
                    // 尝试读取同行的 ITEMNUM
                    const row = el.closest('tr') || el.parentElement;
                    const itemEl = row
                        ? row.querySelector("[data-attribute='ITEMNUM']")
                        : null;
                    negative.push({
                        item: itemEl
                            ? (itemEl.value || itemEl.textContent || '').trim()
                            : '未知',
                        availbal: val,
                        row_index: idx,
                    });
                }
            });
            return { has_negative: negative.length > 0, negative_lines: negative };
        }
    """)
    return result


# ── 导航到指定记录 ────────────────────────────────────────────────────────────

async def navigate_to_invusage_list(frame: Frame) -> bool:
    """点击左侧"列表视图"回到列表页"""
    clicked = await frame.evaluate("""
        () => {
            // Maximo 列表视图链接通常含 event="LIST" 或文本"列表视图"
            const el = document.querySelector(
                "a[event='LIST'], a[id*='listview'], [id*='LIST'][id*='link']"
            ) || Array.from(document.querySelectorAll('a')).find(
                a => (a.textContent || '').trim() === '列表视图'
            );
            if (el) { el.click(); return true; }
            return false;
        }
    """)
    if clicked:
        await asyncio.sleep(WAIT_TIMES.AFTER_MENU_CLICK)
        await wait_for_maximo_ready(frame)
    return clicked


async def navigate_to_invusage_record(
    frame: Frame,
    usage_num: str,
    max_wait: float = 15.0,
) -> bool:
    """
    在库存使用情况列表页搜索并打开指定出库单。

    搜索策略：
      1. 定位 data-attribute='USAGENUM' 的过滤输入框（列表表头过滤行）
      2. 输入 usage_num 并回车
      3. 点击列表中精确匹配的链接
      4. 等待详情页加载，通过 data-attribute 验证流水号

    Args:
        frame:     Playwright frame 对象
        usage_num: 使用情况号（流水号，如 '4988'）
        max_wait:  最长等待秒数
    """
    logger.info(f"导航到出库单: {usage_num}")

    # 若已在此记录详情页，直接返回
    current = await get_current_usage_num(frame)
    if current and current.strip() == usage_num.strip():
        logger.debug(f"已在目标记录: {usage_num}")
        return True

    # 若在其他详情页，先返回列表
    if await check_if_on_detail_page(frame):
        logger.debug("当前在详情页，返回列表...")
        await navigate_to_invusage_list(frame)

    # 在列表过滤行搜索 USAGENUM
    searched = await frame.evaluate(f"""
        () => {{
            // 优先：列表过滤行 data-attribute='USAGENUM' 的 input
            const filterInput = document.querySelector(
                "input[data-attribute='USAGENUM'], input[data-attribute='usagenum']"
            );
            if (filterInput) {{
                filterInput.value = '{usage_num}';
                filterInput.dispatchEvent(new Event('input',  {{bubbles: true}}));
                filterInput.dispatchEvent(new Event('change', {{bubbles: true}}));
                filterInput.dispatchEvent(new KeyboardEvent('keydown',
                    {{key: 'Enter', keyCode: 13, bubbles: true}}));
                filterInput.dispatchEvent(new KeyboardEvent('keyup',
                    {{key: 'Enter', keyCode: 13, bubbles: true}}));
                return 'filter';
            }}
            // 备选：全文搜索框（Maximo 右上角快速搜索）
            const qs = document.querySelector(
                "input[id*='quicksearch'], input[id*='QUICKSEARCH']"
            );
            if (qs) {{
                qs.value = '{usage_num}';
                qs.dispatchEvent(new Event('change', {{bubbles: true}}));
                qs.dispatchEvent(new KeyboardEvent('keydown',
                    {{key: 'Enter', keyCode: 13, bubbles: true}}));
                return 'quicksearch';
            }}
            return null;
        }}
    """)

    if not searched:
        logger.warning(f"未找到搜索框，无法搜索 {usage_num}")
        return False

    logger.debug(f"搜索方式: {searched}，等待结果...")
    await asyncio.sleep(2.0)
    await wait_for_maximo_ready(frame)

    # 点击列表中精确匹配的记录链接
    clicked_record = await frame.evaluate(f"""
        () => {{
            // span.text.label.anchor 是 Maximo 列表行链接的典型 class
            const anchors = Array.from(
                document.querySelectorAll('a, span.text.label.anchor')
            );
            const target = anchors.find(
                el => (el.textContent || '').trim() === '{usage_num}'
            );
            if (target) {{ target.click(); return true; }}
            return false;
        }}
    """)

    if not clicked_record:
        logger.warning(f"列表中未找到记录: {usage_num}")
        return False

    # 等待详情页加载，通过 data-attribute 验证
    waited = 0.0
    interval = 0.5
    while waited < max_wait:
        await wait_for_maximo_ready(frame)
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
    点击右上角保存按钮并等待 Maximo 完成保存。

    Maximo 保存按钮的 event 属性为 "SAVE"（在 Application Designer 工具栏定义）。
    必须在「将状态变更为完成」或「创建剩余使用情况」之前调用。
    """
    saved = await frame.evaluate("""
        () => {
            // 首选：event="SAVE"（Application Designer 工具栏 Action）
            const byEvent = document.querySelector(
                "a[event='SAVE'], button[event='SAVE'], [id*='SAVE'][id*='tbb']"
            );
            if (byEvent && byEvent.offsetParent !== null) {
                byEvent.click();
                return 'event';
            }
            // 备选：工具栏保存图标 img（src 包含 save）
            const byImg = document.querySelector(
                "img[src*='save'], img[alt*='保存'], img[alt*='Save']"
            );
            const saveBtn = byImg ? byImg.closest('a, button') : null;
            if (saveBtn) { saveBtn.click(); return 'img'; }
            return null;
        }
    """)

    if saved:
        logger.info(f"已点击保存 (via {saved})，等待 Maximo 处理...")
        await wait_for_maximo_ready(frame)
        await asyncio.sleep(WAIT_TIMES.AFTER_SAVE_CLICK)
        logger.success("保存完成")
    else:
        logger.warning("未找到保存按钮")
    return bool(saved)


# ── 创建剩余使用情况 ──────────────────────────────────────────────────────────

async def click_create_remaining(frame: Frame) -> bool:
    """
    点击左侧菜单「创建剩余余量使用情况」。

    Maximo Application Designer 中此动作的 Option/event 值为 CREATEREMAINING
    （实际值需在 选择操作 → 添加/修改签名选项 中确认）。
    代码按优先级依次尝试：event 属性 → id 含关键词 → 文本匹配。

    注意：
      - 调用此函数前必须先 save_invusage()，否则 Maximo 会弹出"请先保存"提示。
      - 若按钮 is_displayed()==False，说明当前数量已完全满足，无需创建剩余。
    """
    clicked = await frame.evaluate("""
        () => {
            // 优先：event 属性（最稳定，来自 Application Designer Action 定义）
            const byEvent = document.querySelector(
                "a[event='CREATEREMAINING'], a[event='createremaining']"
            );
            if (byEvent && byEvent.offsetParent !== null) {
                byEvent.click();
                return 'event';
            }
            // 次选：id 含 CREATEREMAINING（Maximo 生成的菜单项 id）
            const byId = document.querySelector("[id*='CREATEREMAINING']");
            if (byId && byId.offsetParent !== null) {
                byId.click();
                return 'id';
            }
            // 备选：文本匹配（最后手段，受语言包影响）
            const allLinks = Array.from(document.querySelectorAll('a, li[role="menuitem"]'));
            const byText = allLinks.find(el =>
                (el.textContent || '').includes('创建剩余') &&
                el.offsetParent !== null
            );
            if (byText) { byText.click(); return 'text'; }
            return null;
        }
    """)

    if clicked:
        logger.info(f"已点击「创建剩余余量使用情况」(via {clicked})")
        await wait_for_maximo_ready(frame)
        await asyncio.sleep(3.0)  # 等待 Maximo 创建并跳转到新记录
    else:
        # 检查按钮是否存在但隐藏（说明数量已全部满足，无需创建）
        btn_exists = await frame.evaluate("""
            () => !!document.querySelector(
                "a[event='CREATEREMAINING'], [id*='CREATEREMAINING']"
            )
        """)
        if btn_exists:
            logger.info("「创建剩余」按钮存在但不可见（数量已全部满足，无需创建）")
        else:
            logger.warning("未找到「创建剩余余量使用情况」菜单项，请在 Application Designer 确认 Action event 名称")
    return bool(clicked)


# ── 变更状态为完成 ────────────────────────────────────────────────────────────

async def change_status_to_complete(frame: Frame) -> bool:
    """
    将出库单状态变更为「完成」(COMPLETE)。

    流程：
      1. 点击左侧菜单「将状态变更为完成」(event='STATUS' 或 id 含 STATUS)
      2. 若弹出状态选择对话框（SELECT），在下拉框中选择 COMPLETE 并确认

    注意：必须在 save_invusage() 之后调用，否则 Maximo 报错。
    """
    # 1. 点击「将状态变更为完成」菜单项
    clicked = await frame.evaluate("""
        () => {
            // 直接完成按钮（部分 Maximo 版本有独立的 COMPLETE 动作）
            const direct = document.querySelector(
                "a[event='COMPLETE'], a[event='complete'], [id*='COMPLETE'][id*='menu']"
            );
            if (direct && direct.offsetParent !== null) {
                direct.click();
                return 'direct';
            }
            // 通用状态变更按钮（弹出对话框选择状态）
            const statusBtn = document.querySelector(
                "a[event='STATUS'], a[event='status'], [id*='STATUS'][id*='menu']"
            ) || Array.from(document.querySelectorAll('a')).find(
                a => (a.textContent || '').includes('将状态变更为') &&
                     (a.textContent || '').includes('完成') &&
                     a.offsetParent !== null
            );
            if (statusBtn) { statusBtn.click(); return 'status_menu'; }
            return null;
        }
    """)

    if not clicked:
        logger.warning("未找到「将状态变更为完成」菜单项")
        return False

    logger.info(f"已点击状态变更 (via {clicked})，等待对话框...")
    await wait_for_maximo_ready(frame)
    await asyncio.sleep(1.5)

    # 2. 若弹出状态选择对话框，选择 COMPLETE 并确认
    dialog_handled = await frame.evaluate("""
        () => {
            // 查找状态下拉框（data-attribute='STATUS' 或 name 含 status）
            const select = document.querySelector(
                "select[data-attribute='STATUS'], select[data-attribute='status'], " +
                "select[name*='status'], select[name*='STATUS']"
            );
            if (select) {
                // 设置为 COMPLETE
                select.value = 'COMPLETE';
                select.dispatchEvent(new Event('change', {bubbles: true}));
                // 点击确认按钮
                const okBtn = document.querySelector(
                    "[id*='ok-pb'], [id*='OK-pb'], button[id*='ok'], " +
                    "a[event='OK'], a[event='SAVE']"
                );
                if (okBtn) { okBtn.click(); return 'dialog_confirmed'; }
                return 'select_set_no_confirm';
            }
            // 没有对话框（直接动作，如 COMPLETE event），认为已完成
            return 'no_dialog';
        }
    """)

    logger.info(f"状态对话框处理结果: {dialog_handled}")

    if dialog_handled in ('dialog_confirmed', 'no_dialog'):
        await wait_for_maximo_ready(frame)
        await asyncio.sleep(WAIT_TIMES.AFTER_CONFIRM_CLICK)
        logger.success("状态已变更为完成")
        return True

    logger.warning(f"状态对话框处理异常: {dialog_handled}")
    return False


# ── 读取新流水号 ──────────────────────────────────────────────────────────────

async def get_newly_created_usage_num(
    frame: Frame,
    original_num: str,
    max_wait: float = 15.0,
) -> Optional[str]:
    """
    创建剩余使用情况后，等待并读取 Maximo 跳转到的新记录流水号。
    通过 data-attribute='USAGENUM' 读取，并排除原流水号。
    """
    waited = 0.0
    interval = 0.5
    while waited < max_wait:
        await wait_for_maximo_ready(frame)
        current = await get_current_usage_num(frame)
        if current and current.strip() != original_num.strip():
            logger.success(f"检测到新流水号: {current}")
            return current.strip()
        await asyncio.sleep(interval)
        waited += interval

    logger.warning("等待超时，未检测到新流水号")
    return None


# ── 读取子表行数据 ────────────────────────────────────────────────────────────

async def read_invusage_lines(frame: Frame) -> List[Dict]:
    """
    读取当前出库单所有子表行的关键字段。
    使用 data-attribute 定位每行的 ITEMNUM / QTY / AVAILBAL / BINNUM。

    Returns:
        [{'item': str, 'qty': float, 'availbal': float, 'binnum': str}, ...]
    """
    rows = await frame.evaluate("""
        () => {
            // 找所有含 ITEMNUM 的行容器
            const itemEls = Array.from(
                document.querySelectorAll("[data-attribute='ITEMNUM']")
            );
            return itemEls.map(itemEl => {
                const row = itemEl.closest('tr') || itemEl.parentElement;
                const get = attr => {
                    if (!row) return null;
                    const el = row.querySelector(`[data-attribute='${attr}']`);
                    return el ? (el.value || el.textContent || '').trim() : null;
                };
                const toFloat = s => {
                    const v = parseFloat((s || '').replace(/,/g, ''));
                    return isNaN(v) ? null : v;
                };
                return {
                    item:     (itemEl.value || itemEl.textContent || '').trim(),
                    qty:      toFloat(get('QUANTITY')),
                    availbal: toFloat(get('AVAILBAL')),
                    binnum:   get('BINNUM') || '',
                };
            });
        }
    """)
    return rows or []


# ── 完整工作流 ────────────────────────────────────────────────────────────────

async def process_invusage_issue(
    frame: Frame,
    usage_num: str,
    wms_qty: float,
    maximo_qty: float,
) -> Tuple[bool, Optional[str], str]:
    """
    出库单完整 RPA 处理流程（SOP 标准路径）：

      1. 可用量检查：发现负数立即停止，返回 'negative_availability'
      2. 打开指定出库单
      3. 保存（先保存，再变更状态）
      4. 数量判断：
         - wms_qty >= maximo_qty → 将状态变更为「完成」
         - wms_qty <  maximo_qty → 点击「创建剩余余量使用情况」，读取新流水号
      5. 等待 Maximo 就绪

    Args:
        frame:       Playwright frame 对象
        usage_num:   出库单流水号
        wms_qty:     WMS 实际出库数量
        maximo_qty:  Maximo 申请数量

    Returns:
        (success: bool, new_usage_num: str | None, reason: str)
        reason 取值：'complete' | 'remaining_created' | 'negative_availability'
                   | 'nav_failed' | 'save_failed' | 'action_failed'
    """
    # ── 步骤1：可用量负数检查 ───────────────────────────────────────────────
    avail_check = await check_availability(frame)
    if avail_check.get("has_negative"):
        neg = avail_check["negative_lines"]
        items = ", ".join(f"{r['item']}({r['availbal']})" for r in neg)
        logger.warning(f"可用量为负，停止自动出库，需人工干预: {items}")
        return False, None, "negative_availability"

    # ── 步骤2：导航到目标记录 ───────────────────────────────────────────────
    if not await navigate_to_invusage_record(frame, usage_num):
        return False, None, "nav_failed"

    # ── 步骤3：先保存 ───────────────────────────────────────────────────────
    if not await save_invusage(frame):
        logger.warning("保存失败，仍继续后续操作（Maximo 可能无未保存变更）")

    # ── 步骤4：数量判断 ─────────────────────────────────────────────────────
    if wms_qty >= maximo_qty:
        # 全部满足 → 直接变更状态为完成
        logger.info(f"数量全部满足 ({wms_qty} >= {maximo_qty})，变更状态为完成")
        ok = await change_status_to_complete(frame)
        if not ok:
            return False, None, "action_failed"
        return True, None, "complete"

    else:
        # 数量不满足 → 创建剩余使用情况
        logger.info(
            f"数量未满足 ({wms_qty} < {maximo_qty})，"
            f"差额 {maximo_qty - wms_qty}，点击「创建剩余余量使用情况」"
        )
        if not await click_create_remaining(frame):
            return False, None, "action_failed"

        new_num = await get_newly_created_usage_num(frame, usage_num)
        if not new_num:
            return False, None, "action_failed"

        return True, new_num, "remaining_created"
