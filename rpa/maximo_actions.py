"""
Maximo 操作的可复用函数库

LLM 提示：这个文件保留用于向后兼容
新代码建议直接使用模块化的接口：
    from rpa import connect_to_browser, find_and_check_po_line
    
或者使用原有方式：
    from rpa.maximo_actions import connect_to_browser, find_and_check_po_line
"""

# 向后兼容：从新模块导入所有函数
from .browser import connect_to_browser
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
from .po_operations import (
    find_and_check_po_line,
    edit_receipt_quantity,
    edit_remark,
    debug_table_columns,
    _find_po_line_in_current_page,
    _check_checkbox
)
from .workflows import process_multiple_po_lines


__all__ = [
    'connect_to_browser',
    'navigate_to_receipts_page',
    'click_menu_purchase',
    'click_menu_receipts',
    'search_all_po',
    'wait_for_po_list',
    'click_po_number',
    'click_select_ordered_items',
    'click_confirm_button',
    'click_save_button',
    'find_and_check_po_line',
    'edit_receipt_quantity',
    'edit_remark',
    'debug_table_columns',
    'process_multiple_po_lines',
]
