"""
采购订单同步主流程
协调数据输入、物料验证、订单头和明细的同步
"""
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.input.po_loader import load_po_files, get_po_summary
from src.fetcher.po_fetcher import fetch_po_list
from src.sync.material import validate_and_sync_materials
from src.sync.po_header import batch_insert_headers
from src.sync.po_detail import batch_insert_details
from src.utils.db import get_connection


# 配置选项
CONFIG = {
    # 数据获取模式
    'fetch_mode': 'file',           # 'file': 从文件加载, 'api': 从API抓取
    'po_numbers': None,             # API模式: 指定订单号列表，如 ['CN5123', 'CN5124']
    'status_filter': None,          # API模式: 状态筛选，如 'APPR'
    'max_pages': 1,                 # API模式: 最大页数
    'page_size': 20,                # API模式: 每页数量
    
    # 数据同步选项
    'auto_sync_materials': True,    # 自动同步缺失物料
    'update_existing_po': False,    # 更新已存在的订单
    
    # 文件模式选项
    'data_directory': None,         # 数据目录，None 表示使用默认 data/raw
    'file_pattern': 'po_*_detail.json',  # 文件名模式
}


def print_banner():
    """打印横幅"""
    print("\n" + "="*60)
    print(" "*15 + "采购订单同步系统")
    print("="*60)


def print_summary(po_list, material_map, header_map, detail_stats, elapsed_time):
    """打印最终摘要"""
    summary = get_po_summary(po_list)
    
    print("\n" + "="*60)
    print("同步完成摘要")
    print("="*60)
    print(f"处理订单数: {summary['total_pos']}")
    print(f"订单明细行: {summary['total_lines']}")
    print(f"物料数量: {len(material_map)}")
    print(f"订单头插入: {len(header_map)}")
    print(f"明细行插入: {detail_stats['inserted']}/{detail_stats['total_lines']}")
    print(f"耗时: {elapsed_time:.2f} 秒")
    print("="*60)


def main():
    """主流程"""
    start_time = datetime.now()
    
    print_banner()
    
    # 步骤 0: 获取数据
    if CONFIG['fetch_mode'] == 'api':
        # API 抓取模式
        po_list = fetch_po_list(
            po_numbers=CONFIG['po_numbers'],
            status_filter=CONFIG['status_filter'],
            max_pages=CONFIG['max_pages'],
            page_size=CONFIG['page_size'],
            save_to_file=True  # 同时保存到文件
        )
    else:
        # 文件加载模式
        print("\n" + "="*60)
        print("步骤 0: 加载数据文件")
        print("="*60)
        
        po_list = load_po_files(
            directory=CONFIG['data_directory'],
            pattern=CONFIG['file_pattern']
        )
    
    if not po_list:
        print("[ERROR] 没有可处理的数据")
        return False
    
    # 显示摘要
    summary = get_po_summary(po_list)
    print(f"\n[INFO] 数据摘要:")
    print(f"  订单数: {summary['total_pos']}")
    print(f"  明细行: {summary['total_lines']}")
    print(f"  平均每单: {summary['avg_lines_per_po']:.1f} 行")
    
    # 连接数据库
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 步骤 1: 物料验证和同步
        material_map = validate_and_sync_materials(
            cursor, 
            po_list, 
            auto_sync=CONFIG['auto_sync_materials']
        )
        
        if material_map is None:
            print("[ERROR] 物料验证失败，终止同步")
            return False
        
        # 步骤 2: 插入订单头
        header_map = batch_insert_headers(
            cursor,
            po_list,
            update_existing=CONFIG['update_existing_po']
        )
        
        if not header_map:
            print("[ERROR] 订单头插入失败，终止同步")
            return False
        
        # 步骤 3: 插入订单明细
        detail_stats = batch_insert_details(
            cursor,
            po_list,
            header_map,
            material_map
        )
        
        # 提交事务
        conn.commit()
        print("\n[OK] 事务提交成功")
        
        # 打印摘要
        elapsed_time = (datetime.now() - start_time).total_seconds()
        print_summary(po_list, material_map, header_map, detail_stats, elapsed_time)
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] 同步失败: {e}")
        if conn:
            conn.rollback()
            print("[INFO] 事务已回滚")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        if conn and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
