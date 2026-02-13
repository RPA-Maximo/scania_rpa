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
        print("=" * 60)
        print("RPA Service 启动")
        print("=" * 60)
        
        # 从 stdin 读取输入
        print("\n[1/4] 读取输入参数...")
        input_data = sys.stdin.read()
        print(f"  原始输入: {input_data[:200]}..." if len(input_data) > 200 else f"  原始输入: {input_data}")
        
        params = json.loads(input_data)
        print(f"  解析后的参数: {json.dumps(params, ensure_ascii=False, indent=2)}")
        
        # 提取参数
        po_number = params.get('po_number', 'CN5123')
        po_lines_data = params.get('po_lines_data', [])
        auto_save = params.get('auto_save', False)
        
        print(f"\n[2/4] 参数提取完成:")
        print(f"  - PO 单号: {po_number}")
        print(f"  - PO 行数: {len(po_lines_data)}")
        print(f"  - 自动保存: {auto_save}")
        print(f"  - PO 行数据:")
        for idx, line in enumerate(po_lines_data, 1):
            print(f"    {idx}. {json.dumps(line, ensure_ascii=False)}")
        
        # 调用 RPA 工作流（print 会输出到 stderr）
        print(f"\n[3/4] 开始执行 RPA 工作流...")
        print("-" * 60)
        result = await batch_receipt_workflow(
            po_number=po_number,
            po_lines_data=po_lines_data,
            auto_save=auto_save
        )
        print("-" * 60)
        print(f"[3/4] RPA 工作流执行完成")
        
        print(f"\n[4/4] 返回结果:")
        print(f"  {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        # 恢复 stdout 并输出 JSON 结果
        sys.stdout = original_stdout
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
        
    except Exception as e:
        print(f"\n✗ 发生异常: {str(e)}")
        print("\n异常堆栈:")
        import traceback
        traceback.print_exc()
        
        # 恢复 stdout 并输出错误
        sys.stdout = original_stdout
        error_result = {
            'success': False,
            'total': 0,
            'processed': 0,
            'failed': 0,
            'error': str(e),
            'traceback': traceback.format_exc()
        }
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
