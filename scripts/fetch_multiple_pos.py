"""
批量抓取多个采购订单
支持从列表文件或命令行参数批量抓取采购订单数据
"""
import sys
from pathlib import Path
import argparse
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetcher.po_fetcher import fetch_po_list


# 预定义的采购单列表（从截图中提取）
PREDEFINED_PO_LISTS = {
    'recent': [
        'CN5123', 'CN5121', 'CN5122', 'CN5119', 'CN5120',
        'CN5118', 'CN5117', 'CN5116', 'CN5115', 'CN5113',
        'CN5112', 'CN5111', 'CN5110', 'CN5044', 'CN5109', 'CN5108'
    ],
    'approved': ['CN5123'],  # APPR 状态
    'draft': ['CN5121'],     # DRAFT 状态
    'test': ['CN5123', 'CN5121', 'CN5122'],  # 测试用的几个订单
}


def load_po_numbers_from_file(file_path: str) -> list:
    """
    从文件加载采购单号列表
    
    文件格式（每行一个订单号）:
    CN5123
    CN5121
    CN5122
    
    或者带注释:
    CN5123  # PPE order
    CN5121  # Draft order
    """
    po_numbers = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            # 跳过空行和注释行
            if not line or line.startswith('#'):
                continue
            
            # 移除行内注释
            if '#' in line:
                line = line.split('#')[0].strip()
            
            if line:
                po_numbers.append(line)
    
    return po_numbers


def fetch_by_status(status: str, max_pages: int = 1, page_size: int = 20):
    """
    按状态批量抓取采购订单
    
    Args:
        status: 订单状态，如 'APPR', 'DRAFT', 'WAPPR', 'CALLOFF'
        max_pages: 最大页数
        page_size: 每页数量
    """
    print(f"\n>>> 按状态抓取采购订单: {status}")
    print(f"    最大页数: {max_pages}, 每页: {page_size}")
    
    po_list = fetch_po_list(
        status_filter=status,
        max_pages=max_pages,
        page_size=page_size,
        save_to_file=True
    )
    
    return po_list


def fetch_by_numbers(po_numbers: list):
    """
    按订单号列表批量抓取
    
    Args:
        po_numbers: 订单号列表
    """
    print(f"\n>>> 按订单号批量抓取")
    print(f"    订单数量: {len(po_numbers)}")
    print(f"    订单列表: {', '.join(po_numbers[:5])}" + 
          (f" ... (共{len(po_numbers)}个)" if len(po_numbers) > 5 else ""))
    
    po_list = fetch_po_list(
        po_numbers=po_numbers,
        save_to_file=True
    )
    
    return po_list


def main():
    parser = argparse.ArgumentParser(
        description='批量抓取采购订单数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 1. 抓取预定义列表中的订单
  python scripts/fetch_multiple_pos.py --preset recent
  
  # 2. 抓取指定的订单号
  python scripts/fetch_multiple_pos.py --numbers CN5123 CN5121 CN5122
  
  # 3. 从文件加载订单号列表
  python scripts/fetch_multiple_pos.py --file po_list.txt
  
  # 4. 按状态抓取（分页）
  python scripts/fetch_multiple_pos.py --status APPR --pages 2 --size 20
  
  # 5. 抓取所有最近的订单（不限状态）
  python scripts/fetch_multiple_pos.py --status all --pages 3 --size 50

预定义列表:
  recent  - 最近的16个订单
  approved - 已批准的订单
  draft   - 草稿订单
  test    - 测试用的3个订单
        """
    )
    
    # 互斥的数据源选项
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        '--preset',
        choices=PREDEFINED_PO_LISTS.keys(),
        help='使用预定义的订单列表'
    )
    source_group.add_argument(
        '--numbers',
        nargs='+',
        metavar='PO_NUM',
        help='指定订单号列表，如: CN5123 CN5121'
    )
    source_group.add_argument(
        '--file',
        metavar='FILE',
        help='从文件加载订单号列表（每行一个）'
    )
    source_group.add_argument(
        '--status',
        metavar='STATUS',
        help='按状态抓取，如: APPR, DRAFT, WAPPR, CALLOFF, all'
    )
    
    # 分页选项（仅用于 --status）
    parser.add_argument(
        '--pages',
        type=int,
        default=1,
        metavar='N',
        help='最大页数（默认: 1）'
    )
    parser.add_argument(
        '--size',
        type=int,
        default=20,
        metavar='N',
        help='每页数量（默认: 20）'
    )
    
    args = parser.parse_args()
    
    print("="*60)
    print(" "*15 + "批量抓取采购订单")
    print("="*60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    start_time = datetime.now()
    po_list = []
    
    try:
        # 根据不同的数据源抓取
        if args.preset:
            po_numbers = PREDEFINED_PO_LISTS[args.preset]
            po_list = fetch_by_numbers(po_numbers)
            
        elif args.numbers:
            po_list = fetch_by_numbers(args.numbers)
            
        elif args.file:
            print(f"\n>>> 从文件加载订单号: {args.file}")
            po_numbers = load_po_numbers_from_file(args.file)
            print(f"    加载了 {len(po_numbers)} 个订单号")
            po_list = fetch_by_numbers(po_numbers)
            
        elif args.status:
            if args.status.lower() == 'all':
                # 不限状态，抓取所有
                po_list = fetch_po_list(
                    status_filter=None,
                    max_pages=args.pages,
                    page_size=args.size,
                    save_to_file=True
                )
            else:
                po_list = fetch_by_status(
                    args.status.upper(),
                    max_pages=args.pages,
                    page_size=args.size
                )
        
        # 统计结果
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print("\n" + "="*60)
        print("抓取完成")
        print("="*60)
        print(f"成功抓取: {len(po_list)} 个采购订单")
        print(f"耗时: {elapsed:.2f} 秒")
        print(f"平均: {elapsed/len(po_list):.2f} 秒/订单" if po_list else "")
        
        # 显示订单列表
        if po_list:
            print(f"\n已抓取的订单:")
            for i, po in enumerate(po_list, 1):
                # 处理可能的命名空间前缀 (spi:ponum 或 ponum)
                po_num = (po.get('spi:ponum') or po.get('ponum') or 
                         po.get('PONUM') or 'N/A')
                status = (po.get('spi:status') or po.get('status') or 
                         po.get('STATUS') or 'N/A')
                desc = (po.get('spi:description') or po.get('description') or 
                       po.get('DESCRIPTION') or 'N/A')
                if desc and desc != 'N/A' and len(desc) > 40:
                    desc = desc[:37] + "..."
                print(f"  {i:2d}. {po_num:<10} [{status:<8}] {desc}")
        
        print("\n数据已保存到: data/raw/po_*_detail.json")
        print("="*60)
        
        return True
        
    except KeyboardInterrupt:
        print("\n\n[INFO] 用户中断")
        return False
    except Exception as e:
        print(f"\n[ERROR] 抓取失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
