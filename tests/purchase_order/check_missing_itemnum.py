"""
检查订单明细中 itemnum 为 null 的情况
"""
import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import RAW_DATA_DIR


def check_missing_itemnum():
    """检查所有订单中 itemnum 为 null 的明细行"""
    
    print(">>> 检查订单明细中缺失 itemnum 的情况")
    print("="*60)
    
    json_files = list(RAW_DATA_DIR.glob("po_*_detail.json"))
    
    total_lines = 0
    missing_itemnum_lines = 0
    
    for json_file in sorted(json_files):
        with open(json_file, 'r', encoding='utf-8') as f:
            po_data = json.load(f)
        
        po_num = po_data.get('ponum', 'N/A')
        poline = po_data.get('poline', [])
        
        if not poline:
            continue
        
        total_lines += len(poline)
        
        # 检查每一行
        missing_in_po = []
        for i, line in enumerate(poline, 1):
            itemnum = line.get('itemnum')
            linetype = line.get('linetype', 'N/A')
            description = line.get('description', 'N/A')
            
            if not itemnum:
                missing_itemnum_lines += 1
                missing_in_po.append({
                    'line_num': i,
                    'linetype': linetype,
                    'description': description[:50] if description else 'N/A'
                })
        
        if missing_in_po:
            print(f"\n订单: {po_num} ({len(poline)} 行，{len(missing_in_po)} 行缺失 itemnum)")
            for item in missing_in_po:
                print(f"  行 {item['line_num']}: {item['linetype']:<10} - {item['description']}")
    
    print(f"\n" + "="*60)
    print(f"总计:")
    print(f"  总明细行数: {total_lines}")
    print(f"  缺失 itemnum: {missing_itemnum_lines} ({missing_itemnum_lines/total_lines*100:.1f}%)")
    print("="*60)


if __name__ == "__main__":
    check_missing_itemnum()
