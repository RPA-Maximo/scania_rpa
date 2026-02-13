"""
RPA 日志模块
提供统一的日志记录功能和装饰器
"""
import functools
import inspect
import time
from typing import Any, Callable
from enum import Enum


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Logger:
    """日志记录器"""
    
    def __init__(self, name: str = "RPA"):
        self.name = name
        self.indent_level = 0
    
    def _format_message(self, level: LogLevel, message: str) -> str:
        """格式化日志消息"""
        indent = "  " * self.indent_level
        prefix = {
            LogLevel.DEBUG: "🔍",
            LogLevel.INFO: "ℹ️",
            LogLevel.SUCCESS: "✓",
            LogLevel.WARNING: "⚠",
            LogLevel.ERROR: "✗"
        }.get(level, "")
        
        return f"{indent}{prefix} {message}"
    
    def debug(self, message: str):
        """调试日志"""
        print(self._format_message(LogLevel.DEBUG, message))
    
    def info(self, message: str):
        """信息日志"""
        print(self._format_message(LogLevel.INFO, message))
    
    def success(self, message: str):
        """成功日志"""
        print(self._format_message(LogLevel.SUCCESS, message))
    
    def warning(self, message: str):
        """警告日志"""
        print(self._format_message(LogLevel.WARNING, message))
    
    def error(self, message: str):
        """错误日志"""
        print(self._format_message(LogLevel.ERROR, message))
    
    def section(self, title: str, width: int = 60):
        """打印分节标题"""
        print("\n" + "=" * width)
        print(title)
        print("=" * width)
    
    def subsection(self, title: str, width: int = 60):
        """打印子分节标题"""
        print("\n" + "-" * width)
        print(title)
        print("-" * width)
    
    def step(self, step_num: int, total: int, description: str):
        """打印步骤信息"""
        print(f"\n[步骤 {step_num}/{total}] {description}")
    
    def indent(self):
        """增加缩进级别"""
        self.indent_level += 1
    
    def dedent(self):
        """减少缩进级别"""
        self.indent_level = max(0, self.indent_level - 1)
    
    def reset_indent(self):
        """重置缩进级别"""
        self.indent_level = 0


# 全局日志实例
logger = Logger("RPA")


def log_function(func_name: str = None, log_args: bool = True, log_result: bool = True):
    """
    函数日志装饰器
    
    Args:
        func_name: 自定义函数名（默认使用函数实际名称）
        log_args: 是否记录参数
        log_result: 是否记录返回值
    
    Example:
        @log_function()
        async def my_function(arg1, arg2):
            return result
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            name = func_name or func.__name__
            
            # 记录函数开始
            logger.info(f"开始执行: {name}")
            logger.indent()
            
            # 记录参数
            if log_args and (args or kwargs):
                logger.debug(f"参数: args={args}, kwargs={kwargs}")
            
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                
                # 记录结果
                if log_result:
                    logger.debug(f"返回值: {result}")
                
                logger.success(f"完成: {name} (耗时 {elapsed:.2f}s)")
                logger.dedent()
                
                return result
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"异常: {name} - {str(e)} (耗时 {elapsed:.2f}s)")
                logger.dedent()
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            name = func_name or func.__name__
            
            # 记录函数开始
            logger.info(f"开始执行: {name}")
            logger.indent()
            
            # 记录参数
            if log_args and (args or kwargs):
                logger.debug(f"参数: args={args}, kwargs={kwargs}")
            
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                
                # 记录结果
                if log_result:
                    logger.debug(f"返回值: {result}")
                
                logger.success(f"完成: {name} (耗时 {elapsed:.2f}s)")
                logger.dedent()
                
                return result
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"异常: {name} - {str(e)} (耗时 {elapsed:.2f}s)")
                logger.dedent()
                raise
        
        # 根据函数类型返回对应的包装器
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def log_step(step_description: str):
    """
    步骤日志装饰器
    
    Args:
        step_description: 步骤描述
    
    Example:
        @log_step("点击采购菜单")
        async def click_menu_purchase(frame):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger.info(f"{step_description}...")
            logger.indent()
            
            try:
                result = await func(*args, **kwargs)
                
                # 根据返回值判断成功或失败
                if isinstance(result, dict):
                    if result.get('success'):
                        logger.success("完成")
                    else:
                        logger.error(f"失败: {result.get('message', '未知错误')}")
                elif isinstance(result, tuple) and len(result) == 2:
                    # 处理 (success, message) 格式
                    success, message = result
                    if success:
                        logger.success(f"完成: {message}")
                    else:
                        logger.error(f"失败: {message}")
                elif isinstance(result, bool):
                    if result:
                        logger.success("完成")
                    else:
                        logger.error("失败")
                else:
                    logger.success("完成")
                
                logger.dedent()
                return result
                
            except Exception as e:
                logger.error(f"异常: {str(e)}")
                logger.dedent()
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger.info(f"{step_description}...")
            logger.indent()
            
            try:
                result = func(*args, **kwargs)
                
                # 根据返回值判断成功或失败
                if isinstance(result, dict):
                    if result.get('success'):
                        logger.success("完成")
                    else:
                        logger.error(f"失败: {result.get('message', '未知错误')}")
                elif isinstance(result, tuple) and len(result) == 2:
                    success, message = result
                    if success:
                        logger.success(f"完成: {message}")
                    else:
                        logger.error(f"失败: {message}")
                elif isinstance(result, bool):
                    if result:
                        logger.success("完成")
                    else:
                        logger.error("失败")
                else:
                    logger.success("完成")
                
                logger.dedent()
                return result
                
            except Exception as e:
                logger.error(f"异常: {str(e)}")
                logger.dedent()
                raise
        
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def log_workflow(workflow_name: str):
    """
    工作流日志装饰器
    
    Args:
        workflow_name: 工作流名称
    
    Example:
        @log_workflow("批量入库工作流")
        async def batch_receipt_workflow(po_number, po_lines_data, auto_save):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger.section(f"{workflow_name}开始")
            logger.reset_indent()
            
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                
                logger.section(f"{workflow_name}完成 (总耗时 {elapsed:.2f}s)")
                
                return result
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.section(f"{workflow_name}失败 (总耗时 {elapsed:.2f}s)")
                logger.error(f"错误: {str(e)}")
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger.section(f"{workflow_name}开始")
            logger.reset_indent()
            
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                
                logger.section(f"{workflow_name}完成 (总耗时 {elapsed:.2f}s)")
                
                return result
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.section(f"{workflow_name}失败 (总耗时 {elapsed:.2f}s)")
                logger.error(f"错误: {str(e)}")
                raise
        
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
