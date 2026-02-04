"""
检查采购订单中的仓库字段
"""
import sys
from pathlib import Path
import json
from collections import Counter

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import RAW_DATA_DIR


def check_warehouse_fields():
    """检查所有订单中的仓库字段"""
    
    print(">>> 检查采购订单中的仓库字段")
    print("="*60)
    
    json_files = list(RAW_DATA_DIR.glob("po_*_detail.json"))
    
    # 统计仓库
    header_storeloc_counter = Counter()
    line_storeloc_counter = Counter()
    
    for json_file in sorted(json_files):
        with open(json_file, 'r', encoding='utf-8') as f:
            po_data = json.load(f)
        
        po_num = po_data.get('ponum', 'N/A')
        
        # 订单头的仓库字段
        header_storeloc = po_data.get('storeloc')
        header_storelocsiteid = po_data.get('storelocsiteid')
        
        if header_storeloc:
            header_storeloc_counter[header_storeloc] += 1
        
        # 明细行的仓库字段
        poline = po_data.get('poline', [])
        
        if poline:
            line_storelocs = set()
            for line in poline:
                storeloc = line.get('storeloc')
                if storeloc:
                    line_storelocs.add(storeloc)
                    line_storeloc_counter[storeloc] += 1
            
            if line_storelocs:
                print(f"{po_num}: 明细行仓库 = {', '.join(sorted(line_storelocs))}")
            else:
                print(f"{po_num}: 无仓库信息")
    
    print("\n" + "="*60)
    print("统计结果:")
    print("="*60)
    
    print(f"\n订单头 storeloc 统计:")
    if header_storeloc_counter:
        for loc, count in header_storeloc_counter.most_common():
            print(f"  {loc}: {count} 个订单")
    else:
        print("  (全部为 null)")
    
    print(f"\n明细行 storeloc 统计:")
    if line_storeloc_counter:
        for loc, count in line_storeloc_counter.most_common():
            print(f"  {loc}: {count} 行明细")
    else:
        print("  (全部为 null)")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    check_warehouse_fields()
