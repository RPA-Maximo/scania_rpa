"""
解析大型HAR文件 - 专门为入库流程分析
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from F12调试信息.har_parser import HarParser

def main():
    # 直接指定HAR文件路径
    har_file = Path(__file__).parent.parent / "F12调试信息" / "main.manage.scania-acc.suite.maximo.com_入库保存_新建9.har"
    
    if not har_file.exists():
        print(f"文件不存在: {har_file}")
        return
    
    print(f"解析HAR文件: {har_file.name}")
    print(f"文件大小: {har_file.stat().st_size / 1024 / 1024:.1f} MB")
    print()
    
    parser = HarParser(str(har_file))
    
    # 1. 获取摘要
    parser.get_summary()
    
    # 2. 提取Maximo请求
    maximo_requests = parser.filter_maximo_requests()
    print(f"\n找到 {len(maximo_requests)} 个Maximo POST请求")
    
    # 3. 显示流程
    parser.print_maximo_flow()
    
    # 4. 导出数据
    parser.export_maximo_requests()
    parser.export_request_template()

if __name__ == "__main__":
    main()
