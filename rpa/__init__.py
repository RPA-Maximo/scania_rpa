"""
Maximo RPA 自动化包

LLM 提示：这是包的入口文件，导出所有主要接口

使用示例：
    from rpa import connect_to_browser, process_multiple_po_lines
    
    p, browser, page, frame = await connect_to_browser()
    result = await process_multiple_po_lines(frame, po_lines_data)
"""

# 浏览器连接
from .browser import connect_to_browser

# 页面导航
from .navigation import (
    navigate_to_receipts_page,
    click_menu_purchase,
    click_menu_receipts,
    search_all_po,
    wait_for_po_list,
    click_po_number,
    click_select_ordered_items,
    click_confirm_button,
    click_save_button
)

# PO 行操作
from .po_operations import (
    find_and_check_po_line,
    edit_receipt_quantity,
    edit_remark
)

# 高级工作流
from .workflows import process_multiple_po_lines

# 配置（可选导出）
from .config import SELECTORS, COLUMNS, WAIT_TIMES, LIMITS

# 工具函数（可选导出）
from .utils import trigger_input_events, escape_js_string, wait_for_condition

# 供应商/公司信息 RPA 抓取
from .vendor_operations import rpa_fetch_vendor_details, fetch_company_details_via_rpa


__all__ = [
    # 浏览器
    'connect_to_browser',
    
    # 导航
    'navigate_to_receipts_page',
    'click_menu_purchase',
    'click_menu_receipts',
    'search_all_po',
    'wait_for_po_list',
    'click_po_number',
    'click_select_ordered_items',
    'click_confirm_button',
    'click_save_button',
    
    # PO 操作
    'find_and_check_po_line',
    'edit_receipt_quantity',
    'edit_remark',
    
    # 工作流
    'process_multiple_po_lines',
    
    # 配置
    'SELECTORS',
    'COLUMNS',
    'WAIT_TIMES',
    'LIMITS',
    
    # 工具
    'trigger_input_events',
    'escape_js_string',
    'wait_for_condition',

    # 供应商/公司信息 RPA 抓取
    'rpa_fetch_vendor_details',
    'fetch_company_details_via_rpa',
]
