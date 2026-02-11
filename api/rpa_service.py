"""
RPA 服务脚本
独立进程运行，避免事件循环冲突
从 stdin 读取 JSON 输入，输出 JSON 结果到 stdout
"""
import asyncio
import sys
import json
import io
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Windows 平台设置事件循环策略
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from rpa.tests.test_batch_receipt import batch_receipt_workflow


async def main():
    """主函数"""
    # 重定向 stdout 到 stderr，保留原始 stdout 用于输出 JSON
    original_stdout = sys.stdout
    sys.stdout = sys.stderr
    
    try:
        # 从 stdin 读取输入
        input_data = sys.stdin.read()
        params = json.loads(input_data)
        
        # 提取参数
        po_number = params.get('po_number', 'CN5123')
        po_lines_data = params.get('po_lines_data', [])
        auto_save = params.get('auto_save', False)
        
        # 调用 RPA 工作流（print 会输出到 stderr）
        result = await batch_receipt_workflow(
            po_number=po_number,
            po_lines_data=po_lines_data,
            auto_save=auto_save
        )
        
        # 恢复 stdout 并输出 JSON 结果
        sys.stdout = original_stdout
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
        
    except Exception as e:
        # 恢复 stdout 并输出错误
        sys.stdout = original_stdout
        error_result = {
            'success': False,
            'total': 0,
            'processed': 0,
            'failed': 0,
            'error': str(e)
        }
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
