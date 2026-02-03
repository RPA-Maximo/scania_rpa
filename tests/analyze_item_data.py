"""
分析爬取的物料数据，对比数据库表结构
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from config import RAW_DATA_DIR

# 数据库表字段（从截图中提取）
DB_FIELDS = {
    '物料编码': 'itemnum',
    '物料名称': 'description',
    'SAP Material': None,  # 需要映射
    '物料准备状态': None,
    '型号': None,
    '条件包用': None,
    '制造商': None,
    '授收时档案': None,
    '商品组名称': None,
    '商品代码': None,
    '批次类型': None,
    '产品系列': None,
    '物料类别': None,
    
    '物料名称': 'description',
    '英文描述': 'description_longdescription',  # 可能
    '项目库': None,
    '盾线': None,
    '附加数据': None,
    '资本化': None,
    '商品组编号': None,
    '商品代码': None,
    '订购单位': 'orderunit',
    'MSDS': None,
    
    'PackIT Item': None,
    '尺寸/质量': None,
    '工具包': 'iskit',
    '订货号': None,
    '免税': None,
    '商品代码': None,
    '发放单位': 'issueunit',
    '产品代码': None,
}


def find_latest_file():
    """找到最新的物料数据文件"""
    files = list(RAW_DATA_DIR.glob("item_master_*.xlsx"))
    if not files:
        print("未找到物料数据文件")
        return None
    
    latest_file = max(files, key=lambda x: x.stat().st_mtime)
    return latest_file


def analyze_data():
    """分析数据"""
    # 找到最新文件
    filepath = find_latest_file()
    if not filepath:
        return
    
    print(f"分析文件: {filepath.name}")
    print("="*80)
    
    # 读取数据
    df = pd.read_excel(filepath)
    
    print(f"\n数据概况:")
    print(f"  行数: {len(df)}")
    print(f"  列数: {len(df.columns)}")
    
    # 显示第一条数据
    print(f"\n第一条数据示例:")
    first_row = df.iloc[0]
    print(f"  物料编号: {first_row.get('itemnum', 'N/A')}")
    print(f"  描述: {first_row.get('description', 'N/A')}")
    print(f"  状态: {first_row.get('status', 'N/A')}")
    
    # 列出所有字段
    print(f"\n所有字段 ({len(df.columns)} 个):")
    for i, col in enumerate(df.columns, 1):
        value = first_row[col]
        # 只显示有值的字段
        if pd.notna(value) and value != '':
            print(f"  {i:2d}. {col:30s} = {str(value)[:50]}")
    
    # 查找可能的字段映射
    print(f"\n{'='*80}")
    print("字段映射分析:")
    print(f"{'='*80}")
    
    # 关键字段映射
    field_mapping = {
        '物料编码': 'itemnum',
        '物料名称': 'description',
        '状态': 'status',
        '物料类型': 'itemtype',
        '物料集': 'itemsetid',
        '发放单位': 'issueunit',
        '订购单位': 'orderunit',
        '工具包': 'iskit',
        '批次类型': 'lottype',
        '条件代码': 'conditioncode',
        '商品代码': 'commoditygroup',
        '商品组': 'commodity',
    }
    
    print("\n已确认的字段映射:")
    for db_field, api_field in field_mapping.items():
        if api_field in df.columns:
            value = first_row.get(api_field, '')
            status = "✓" if pd.notna(value) and value != '' else "○"
            print(f"  {status} {db_field:15s} -> {api_field:25s} = {str(value)[:40]}")
        else:
            print(f"  ✗ {db_field:15s} -> {api_field:25s} (字段不存在)")
    
    # 查找可能包含特定关键词的字段
    print(f"\n可能相关的字段:")
    keywords = ['sap', 'manufacturer', 'vendor', 'msds', 'pack', 'dimension', 
                'weight', 'size', 'tax', 'capital', 'project']
    
    for keyword in keywords:
        matching_fields = [col for col in df.columns if keyword.lower() in col.lower()]
        if matching_fields:
            print(f"\n  包含 '{keyword}' 的字段:")
            for field in matching_fields:
                value = first_row.get(field, '')
                if pd.notna(value) and value != '':
                    print(f"    - {field:30s} = {str(value)[:50]}")
    
    # 输出完整字段列表到文件
    output_file = RAW_DATA_DIR / "item_master_fields.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("物料主数据 API 字段列表\n")
        f.write("="*80 + "\n\n")
        for i, col in enumerate(df.columns, 1):
            value = first_row[col]
            f.write(f"{i:2d}. {col}\n")
            if pd.notna(value) and value != '':
                f.write(f"    示例值: {str(value)[:100]}\n")
            f.write("\n")
    
    print(f"\n完整字段列表已保存到: {output_file}")


if __name__ == "__main__":
    analyze_data()
