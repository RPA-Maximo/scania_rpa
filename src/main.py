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
from src.fetcher.item_fetcher import fetch_item_specs
from src.fetcher.vendor_fetcher import fetch_vendor_details
from src.sync.material import validate_and_sync_materials
from src.sync.po_header import batch_map_headers, batch_insert_headers
from src.sync.po_detail import batch_map_details, batch_insert_details
from src.utils.db import get_connection


# 配置选项
CONFIG = {
    # 数据获取模式
    'fetch_mode': 'api',            # 'file': 从文件加载, 'api': 从API抓取
    'po_numbers': None,             # API模式: 指定订单号列表，如 ['CN5123', 'CN5124']
    'status_filter': 'APPR',       # API模式: 状态筛选，只拉已审批订单
    'max_pages': 10,                # API模式: 最大页数
    'page_size': 20,                # API模式: 每页数量
    
    # 数据同步选项
    'auto_sync_materials': True,    # 自动同步缺失物料
    'update_existing_po': True,     # 更新已存在的订单（默认开启全量更新）
    'check_before_sync': True,      # 同步前检查数据库状态并询问
    
    # 文件模式选项
    'data_directory': None,         # 数据目录，None 表示使用默认 data/raw
    'file_pattern': 'po_*_detail.json',  # 文件名模式
}


def print_banner():
    """打印横幅"""
    print("\n" + "="*60)
    print(" "*15 + "采购订单同步系统")
    print("="*60)


def check_database_status(cursor) -> dict:
    """
    检查数据库当前状态
    
    Args:
        cursor: 数据库游标
        
    Returns:
        dict: 包含订单数、明细数等统计信息
    """
    stats = {}
    
    # 检查订单头数量
    cursor.execute("SELECT COUNT(*) FROM purchase_order WHERE del_flag = 0")
    stats['po_count'] = cursor.fetchone()[0]
    
    # 检查订单明细数量
    cursor.execute("SELECT COUNT(*) FROM purchase_order_bd")
    stats['detail_count'] = cursor.fetchone()[0]
    
    # 检查有仓库信息的明细数量
    cursor.execute("SELECT COUNT(*) FROM purchase_order_bd WHERE warehouse IS NOT NULL")
    stats['detail_with_warehouse'] = cursor.fetchone()[0]
    
    # 检查无仓库信息的明细数量
    stats['detail_without_warehouse'] = stats['detail_count'] - stats['detail_with_warehouse']
    
    return stats


def ask_clear_tables(stats: dict) -> bool:
    """
    询问用户是否清空相关表
    
    Args:
        stats: 数据库状态统计
        
    Returns:
        bool: True=清空, False=保留
    """
    print("\n" + "="*60)
    print("数据库当前状态")
    print("="*60)
    print(f"采购订单数: {stats['po_count']}")
    print(f"订单明细数: {stats['detail_count']}")
    print(f"  - 有仓库信息: {stats['detail_with_warehouse']}")
    print(f"  - 无仓库信息: {stats['detail_without_warehouse']}")
    print("="*60)
    
    if stats['po_count'] == 0 and stats['detail_count'] == 0:
        print("[INFO] 数据库为空，无需清空")
        return False
    
    print("\n[提示] 检测到数据库中已有采购订单数据")
    print("[提示] 当前配置为全量更新模式 (update_existing_po=True)")
    print("[提示] 重新导入会删除旧订单和明细，然后插入最新数据")
    
    while True:
        choice = input("\n是否清空 purchase_order 和 purchase_order_bd 表? (y/n): ").strip().lower()
        if choice in ['y', 'yes']:
            return True
        elif choice in ['n', 'no']:
            print("[INFO] 保留现有数据，将跳过已存在的订单")
            return False
        else:
            print("[ERROR] 请输入 y 或 n")


def clear_po_tables(cursor):
    """
    清空采购订单相关表
    
    Args:
        cursor: 数据库游标
    """
    print("\n[INFO] 正在清空采购订单表...")
    
    # 清空明细表
    cursor.execute("DELETE FROM purchase_order_bd")
    detail_count = cursor.rowcount
    print(f"  ✓ 清空 purchase_order_bd: {detail_count} 行")
    
    # 清空主表
    cursor.execute("DELETE FROM purchase_order")
    po_count = cursor.rowcount
    print(f"  ✓ 清空 purchase_order: {po_count} 行")
    
    print("[OK] 表清空完成")


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
        
        # 检查数据库状态并询问是否清空
        if CONFIG['check_before_sync']:
            stats = check_database_status(cursor)
            should_clear = ask_clear_tables(stats)
            
            if should_clear:
                clear_po_tables(cursor)
                conn.commit()
                # 清空后强制使用插入模式
                CONFIG['update_existing_po'] = False
            else:
                # 保留数据，使用更新模式
                CONFIG['update_existing_po'] = True
        
        # 步骤 1: 物料验证和同步
        material_map = validate_and_sync_materials(
            cursor,
            po_list,
            auto_sync=CONFIG['auto_sync_materials']
        )
        conn.commit()  # 物料同步后立即提交，之后可安全关闭连接

        if material_map is None:
            print("[ERROR] 物料验证失败，终止同步")
            return False

        # ── Maximo API / RPA 查询（耗时较长，期间不持有 DB 连接）─────────────

        # 步骤 2a: 批量查物料规格（cxtypedsg → model_num / size_info）
        item_nums = list({
            line.get('itemnum')
            for po in po_list
            for line in (po.get('poline') or [])
            if line.get('itemnum')
        })
        item_spec_map = fetch_item_specs(item_nums) if item_nums else {}

        # 步骤 2b: 批量查供应商/收款方详情（供应商名称/地址/联系方式等）
        company_codes = list({
            code
            for po in po_list
            for code in (po.get('vendor'), po.get('billto'))
            if code
        })
        vendor_detail_map = fetch_vendor_details(company_codes) if company_codes else {}

        # ── 重新获取 DB 连接（旧连接在 Maximo 查询期间可能已超时断开）────────
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        conn = get_connection()
        cursor = conn.cursor()

        # 步骤 2c: 预清洗订单头（注入 vendor_detail_map）
        cleaned_headers, pre_header_id_map = batch_map_headers(
            cursor, po_list, vendor_detail_map
        )

        # 步骤 2d: 预清洗订单明细（注入 item_spec_map）
        cleaned_details = batch_map_details(
            cursor, po_list, pre_header_id_map, material_map, item_spec_map
        )

        # 步骤 3: 插入订单头
        header_map = batch_insert_headers(
            cursor,
            po_list,
            update_existing=CONFIG['update_existing_po'],
            pre_mapped=cleaned_headers,
        )

        if not header_map:
            print("[ERROR] 订单头插入失败，终止同步")
            return False

        # 步骤 4: 插入订单明细
        detail_stats = batch_insert_details(
            cursor,
            po_list,
            header_map,
            material_map,
            pre_mapped=cleaned_details,
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
