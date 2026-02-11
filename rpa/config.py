"""
Maximo RPA 配置文件
集中管理所有元素选择器、常量和配置项

LLM 提示：修改元素 ID 时只需要修改这个文件
"""
from dataclasses import dataclass


@dataclass
class ElementSelectors:
    """Maximo 页面元素选择器"""
    
    # 菜单相关
    MENU_PURCHASE: str = 'mea59820d_ns_menu_PURCHASE_MODULE_a'
    MENU_RECEIPTS: str = 'mea59820d_ns_menu_PURCHASE_MODULE_sub_changeapp_RECEIPTS_a'
    
    # 按钮相关
    BUTTON_SELECT_ORDERED_ITEMS: str = 'm52852ffc_bg_button_selorditem-pb'
    BUTTON_CONFIRM: str = 'mab71af75-pb'  # 确定按钮
    BUTTON_SAVE_IMAGE: str = 'toolactions_SAVE-tbb_image'  # 保存按钮（图片）
    
    # 输入框相关（使用部分匹配）
    INPUT_PO_NUMBER_PATTERN: str = 'tfrow'  # PO 号输入框 ID 包含此字符串
    
    # 翻页按钮
    NEXT_PAGE_BUTTON_IMAGE: str = 'tablebtn_next_on.gif'


@dataclass
class ColumnIndexes:
    """表格列索引配置
    
    LLM 提示：这些索引对应 Maximo 接收页面表格的列位置
    """
    
    # 只读字段列索引
    PO_LINE: int = 2
    ITEM_NUM: int = 3
    DESCRIPTION: int = 4
    TO_STOREROOM: int = 7
    ORDER_QTY: int = 9
    RESERVED_QTY: int = 10
    
    # 可编辑字段列索引
    RECEIPT_QTY: int = 8
    ORDER_UNIT: int = 11
    INVOICE: int = 12
    REMARK: int = 13


@dataclass
class WaitTimes:
    """等待时间配置（秒）
    
    LLM 提示：这些时间是根据 Maximo 系统响应速度调整的
    """
    
    # 操作后等待
    AFTER_MENU_CLICK: float = 1
    AFTER_RECEIPTS_CLICK: float = 3
    AFTER_PO_CLICK: float = 5
    AFTER_SELECT_ITEMS_CLICK: float = 4
    AFTER_CHECKBOX_CLICK: float = 1
    AFTER_INPUT_EDIT: float = 0.5
    AFTER_PAGE_TURN: float = 3
    SCROLL_DELAY: float = 0.5
    CHECKBOX_STATE_UPDATE: float = 0.2
    AFTER_CONFIRM_CLICK: float = 2  # 点击确定后等待
    AFTER_SAVE_CLICK: float = 3  # 点击保存后等待
    
    # 轮询等待
    INPUT_SEARCH_MAX_WAIT: float = 10
    INPUT_SEARCH_INTERVAL: float = 0.5
    PO_LIST_MAX_WAIT: float = 15
    PO_LIST_INTERVAL: float = 0.5


@dataclass
class Limits:
    """限制配置"""
    
    MAX_PAGES_TO_SEARCH: int = 5  # 最多翻页次数
    MAX_REMARK_LENGTH: int = 254  # 备注最大长度


# 全局配置实例
# LLM 提示：直接导入这些实例使用，例如：from rpa.config import SELECTORS
SELECTORS = ElementSelectors()
COLUMNS = ColumnIndexes()
WAIT_TIMES = WaitTimes()
LIMITS = Limits()
