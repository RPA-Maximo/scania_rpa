"""
采购单 JSON 解析模块
从 MXAPIPO API 返回的 JSON 中提取指定字段
"""
import json
from pathlib import Path
from typing import Dict, List, Any


# 订单头字段映射: 显示名 -> JSON 字段名
PO_HEADER_FIELDS = {
    'PO号': 'ponum',
    '描述': 'description',
    '买家代码': 'purchaseagent',
    '地点': 'siteid',
    '状态': 'status',
    '供应商编码': 'vendor',
    '状态日期': 'statusdate',
    '订单日期': 'orderdate',
    '总成本': 'totalcost',
    '币种': 'currencycode',
}

# 订单明细字段映射: 显示名 -> JSON 字段名
PO_LINE_FIELDS = {
    '行号': 'polinenum',
    '物料编号': 'itemnum',
    '描述': 'description',
    '数量': 'orderqty',
    '收货完成': 'receiptscomplete',
    '订单单位': 'orderunit',
    '单价': 'unitcost',
}


def parse_po_header(po_data: Dict) -> Dict:
    """
    解析订单头信息
    
    Args:
        po_data: 完整的 PO JSON 数据
        
    Returns:
        dict: 提取的订单头字段
    """
    result = {}
    for display_name, json_field in PO_HEADER_FIELDS.items():
        result[display_name] = po_data.get(json_field)
    return result


def parse_po_lines(po_data: Dict) -> List[Dict]:
    """
    解析订单明细行
    
    Args:
        po_data: 完整的 PO JSON 数据
        
    Returns:
        list: 订单明细列表
    """
    poline = po_data.get('poline', [])
    result = []
    
    for line in poline:
        line_data = {}
        for display_name, json_field in PO_LINE_FIELDS.items():
            line_data[display_name] = line.get(json_field)
        result.append(line_data)
    
    return result


def parse_po_json(json_path: str) -> Dict:
    """
    解析 PO JSON 文件
    
    Args:
        json_path: JSON 文件路径
        
    Returns:
        dict: 包含 header 和 lines 的解析结果
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        po_data = json.load(f)
    
    return {
        'header': parse_po_header(po_data),
        'lines': parse_po_lines(po_data),
        'line_count': len(po_data.get('poline', []))
    }


def print_po_summary(parsed: Dict):
    """
    打印 PO 摘要信息
    """
    header = parsed['header']
    lines = parsed['lines']
    
    print("="*60)
    print("采购订单摘要")
    print("="*60)
    
    print("\n[订单头]")
    for name, value in header.items():
        print(f"  {name}: {value}")
    
    print(f"\n[订单明细] 共 {parsed['line_count']} 行")
    print("-"*60)
    
    # 只显示前 5 行
    for i, line in enumerate(lines[:5], 1):
        print(f"  行 {i}:")
        for name, value in line.items():
            print(f"    {name}: {value}")
        print()
    
    if len(lines) > 5:
        print(f"  ... 还有 {len(lines) - 5} 行")


if __name__ == "__main__":
    import sys
    
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    
    # 默认测试文件
    default_file = PROJECT_ROOT / "data" / "raw" / "po_CN5123_detail.json"
    
    json_path = sys.argv[1] if len(sys.argv) > 1 else str(default_file)
    
    if not Path(json_path).exists():
        print(f"[FAIL] 文件不存在: {json_path}")
        sys.exit(1)
    
    print(f"解析文件: {json_path}")
    parsed = parse_po_json(json_path)
    print_po_summary(parsed)
