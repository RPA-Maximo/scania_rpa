"""
批量入库接收流程测试
一次性处理多个 PO 行
"""
import asyncio
import sys
sys.path.insert(0, '.')

from rpa.maximo_actions import (
    connect_to_browser,
    search_all_po,
    wait_for_po_list,
    click_po_number,
    click_select_ordered_items,
    process_multiple_po_lines
)
from rpa.navigation import navigate_to_receipts_page, get_current_page_title
from rpa.logger import logger, log_workflow


@log_workflow("批量入库工作流")
async def batch_receipt_workflow(po_number="CN5123", po_lines_data=None, auto_save=False):
    """
    批量入库接收流程
    
    Args:
        po_number: 采购单号，如 "CN5123"
        po_lines_data: PO 行数据列表，格式：
            [
                {'po_line': '7', 'quantity': '5.00', 'remark': '备注1'},
                {'po_line': '20', 'quantity': '3.00', 'remark': '备注2'},
                ...
            ]
        auto_save: 是否自动保存（默认 False）
    
    Returns:
        dict: 处理结果，包含 success, total, processed, failed, saved, results 等字段
    """
    if po_lines_data is None:
        po_lines_data = [
            {'po_line': '7', 'quantity': '5.00', 'remark': '第一行测试备注'},
            {'po_line': '20', 'quantity': '3.00', 'remark': '第二行测试备注'}
        ]
    
    logger.info(f"PO 单号: {po_number}")
    logger.info(f"PO 行数: {len(po_lines_data)}")
    logger.info(f"自动保存: {auto_save}")
    
    p = None
    try:
        # 连接浏览器
        logger.step(0, 6, "连接浏览器")
        p, browser, maximo_page, main_frame = await connect_to_browser()
        current_title = await get_current_page_title(main_frame)
        logger.success(f"成功连接到浏览器，当前页面: {current_title}")
        
        # 导航到接收查询页面（从任意页面均可自动导航）
        logger.subsection("导航到接收查询页面")
        logger.step(1, 6, "导航到接收查询页面")
        on_search_page = await navigate_to_receipts_page(main_frame)
        if not on_search_page:
            logger.error("无法导航到接收查询页面")
            return {
                'success': False,
                'total': len(po_lines_data),
                'processed': 0,
                'failed': len(po_lines_data),
                'error': '无法导航到接收查询页面'
            }
        logger.success("已到达接收查询页面")

        logger.step(3, 6, "查询所有 PO")
        try:
            success, message = await search_all_po(main_frame)
            if success:
                logger.success(message)
            else:
                logger.error(message)
                return {
                    'success': False,
                    'total': len(po_lines_data),
                    'processed': 0,
                    'failed': len(po_lines_data),
                    'error': message
                }
        except Exception as e:
            logger.error(f"异常: {e}")
            raise
        
        logger.info("等待列表加载...")
        try:
            success, waited = await wait_for_po_list(main_frame)
            if success:
                logger.success(f"列表已加载（等待了 {waited:.1f} 秒）")
            else:
                logger.error("列表加载超时")
                return {
                    'success': False,
                    'total': len(po_lines_data),
                    'processed': 0,
                    'failed': len(po_lines_data),
                    'error': '列表加载超时'
                }
        except Exception as e:
            logger.error(f"异常: {e}")
            raise
        
        logger.step(4, 6, f"点击采购单号 '{po_number}'")
        try:
            if await click_po_number(main_frame, po_number):
                logger.success("完成")
            else:
                logger.error("未找到采购单")
                return {
                    'success': False,
                    'total': len(po_lines_data),
                    'processed': 0,
                    'failed': len(po_lines_data),
                    'error': f'未找到采购单 {po_number}'
                }
        except Exception as e:
            logger.error(f"异常: {e}")
            raise
        
        # === 批量处理 PO 行 ===
        logger.subsection(f"批量处理 {len(po_lines_data)} 个 PO 行")
        
        logger.step(5, 6, "点击'选择已订购项'")
        try:
            if await click_select_ordered_items(main_frame):
                logger.success("完成")
            else:
                logger.error("未找到'选择已订购项'按钮")
                return {
                    'success': False,
                    'total': len(po_lines_data),
                    'processed': 0,
                    'failed': len(po_lines_data),
                    'error': '未找到"选择已订购项"按钮'
                }
        except Exception as e:
            logger.error(f"异常: {e}")
            raise
        
        logger.step(6, 6, "批量处理 PO 行")
        try:
            batch_result = await process_multiple_po_lines(main_frame, po_lines_data, auto_save=auto_save)
        except Exception as e:
            logger.error(f"异常: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # 显示处理结果
        logger.subsection("批量处理结果")
        logger.info(f"总数: {batch_result['total']}")
        logger.info(f"成功: {batch_result['processed']}")
        logger.info(f"失败: {batch_result['failed']}")
        
        if auto_save:
            if batch_result.get('saved'):
                logger.success("保存状态: 已保存")
            else:
                logger.warning("保存状态: 未保存")
        
        if batch_result['success']:
            logger.success("所有 PO 行处理完成！")
        else:
            logger.warning("部分 PO 行处理失败")
            for result in batch_result['results']:
                if not result['success']:
                    logger.error(f"PO 行 {result.get('po_line', 'N/A')}: {result['message']}")
        
        return batch_result
        
    except Exception as e:
        logger.error(f"工作流异常: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'total': len(po_lines_data) if po_lines_data else 0,
            'processed': 0,
            'failed': len(po_lines_data) if po_lines_data else 0,
            'error': str(e),
            'traceback': traceback.format_exc()
        }
    finally:
        if p:
            logger.info("关闭浏览器连接...")
            await p.stop()
            logger.success("浏览器连接已关闭")


if __name__ == "__main__":
    # 示例1: 使用默认数据（处理 PO 行 7 和 20），不自动保存
    # asyncio.run(batch_receipt_workflow(po_number="CN5123"))
    
    # 示例2: 自定义 PO 行数据，启用自动保存
    custom_po_lines = [
        {'po_line': '10', 'quantity': '5.00', 'remark': '自动化测试-行10'},
        {'po_line': '22', 'quantity': '2.00', 'remark': '自动化测试-行22'},
    ]
    asyncio.run(batch_receipt_workflow(
        po_number="CN5123",
        po_lines_data=custom_po_lines,
        auto_save=False  # 启用自动保存
    ))
