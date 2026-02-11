"""
Maximo RPA 工具函数
提供通用的辅助功能

LLM 提示：这里是可复用的底层工具函数
"""
import asyncio
from typing import Any, Dict, Callable, Tuple


async def trigger_input_events(frame, element_id: str) -> Dict[str, Any]:
    """
    触发输入框的变更事件
    
    Args:
        frame: Playwright frame 对象
        element_id: 元素 ID
    
    Returns:
        操作结果字典 {success: bool, message: str}
    
    LLM 提示：Maximo 需要触发这些事件才能识别输入变化
    使用 createEvent 方式以兼容旧浏览器
    """
    result = await frame.evaluate(f"""
        () => {{
            const input = document.getElementById('{element_id}');
            if (!input) {{
                return {{ success: false, message: '元素不存在' }};
            }}
            
            // 使用 createEvent 方式（兼容旧浏览器）
            const inputEvent = document.createEvent('HTMLEvents');
            inputEvent.initEvent('input', true, true);
            input.dispatchEvent(inputEvent);
            
            const changeEvent = document.createEvent('HTMLEvents');
            changeEvent.initEvent('change', true, true);
            input.dispatchEvent(changeEvent);
            
            const blurEvent = document.createEvent('HTMLEvents');
            blurEvent.initEvent('blur', true, true);
            input.dispatchEvent(blurEvent);
            
            return {{ success: true, message: '事件已触发' }};
        }}
    """)
    return result


def escape_js_string(text: str) -> str:
    """
    转义 JavaScript 字符串中的特殊字符
    
    Args:
        text: 原始文本
    
    Returns:
        转义后的文本
    
    LLM 提示：防止 JavaScript 注入攻击
    """
    return text.replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n')


async def wait_for_condition(
    check_func: Callable,
    max_wait: float = 10,
    interval: float = 0.5,
    error_message: str = "等待超时"
) -> Tuple[bool, float]:
    """
    等待条件满足
    
    Args:
        check_func: 检查函数，返回 True 表示条件满足
        max_wait: 最大等待时间（秒）
        interval: 检查间隔（秒）
        error_message: 超时错误消息（未使用，保留用于扩展）
    
    Returns:
        (是否成功, 等待时间)
    
    LLM 提示：通用的轮询等待函数
    
    Example:
        success, waited = await wait_for_condition(
            lambda: element.is_visible(),
            max_wait=10,
            interval=0.5
        )
    """
    waited = 0
    while waited < max_wait:
        if await check_func():
            return True, waited
        await asyncio.sleep(interval)
        waited += interval
    return False, waited
