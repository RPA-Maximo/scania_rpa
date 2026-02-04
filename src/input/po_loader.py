"""
采购订单数据加载器
负责从文件系统加载 JSON 数据
"""
import json
from pathlib import Path
from typing import Dict, List, Optional


def load_single_po(file_path: str) -> Optional[Dict]:
    """
    加载单个采购订单 JSON 文件
    
    Args:
        file_path: JSON 文件路径
        
    Returns:
        dict: 采购订单数据，失败返回 None
    """
    try:
        path = Path(file_path)
        if not path.exists():
            print(f"[WARN] 文件不存在: {file_path}")
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            po_data = json.load(f)
        
        # 验证基本结构
        if not validate_po_structure(po_data):
            print(f"[WARN] 文件结构无效: {file_path}")
            return None
        
        return po_data
        
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON 解析失败 ({file_path}): {e}")
        return None
    except Exception as e:
        print(f"[ERROR] 加载文件失败 ({file_path}): {e}")
        return None


def load_po_files(directory: str = None, pattern: str = "po_*_detail.json") -> List[Dict]:
    """
    批量加载采购订单 JSON 文件
    
    Args:
        directory: 目录路径，默认为 data/raw
        pattern: 文件名模式
        
    Returns:
        list: 采购订单数据列表
    """
    if directory is None:
        # 默认目录
        project_root = Path(__file__).parent.parent.parent
        directory = project_root / "data" / "raw"
    else:
        directory = Path(directory)
    
    if not directory.exists():
        print(f"[ERROR] 目录不存在: {directory}")
        return []
    
    # 查找匹配的文件
    json_files = list(directory.glob(pattern))
    
    if not json_files:
        print(f"[WARN] 未找到匹配的文件: {directory}/{pattern}")
        return []
    
    print(f"[INFO] 找到 {len(json_files)} 个 JSON 文件")
    
    # 加载所有文件
    po_list = []
    for json_file in json_files:
        po_data = load_single_po(json_file)
        if po_data:
            po_list.append(po_data)
            po_code = po_data.get('ponum', 'Unknown')
            print(f"  ✓ {json_file.name} ({po_code})")
        else:
            print(f"  ✗ {json_file.name}")
    
    print(f"[INFO] 成功加载 {len(po_list)} 个采购订单")
    return po_list


def validate_po_structure(po_data: Dict) -> bool:
    """
    验证采购订单 JSON 结构
    
    Args:
        po_data: 采购订单数据
        
    Returns:
        bool: 是否有效
    """
    # 检查必需字段
    if not po_data.get('ponum'):
        return False
    
    # 检查是否有明细行
    poline = po_data.get('poline')
    if not isinstance(poline, list):
        return False
    
    return True


def get_po_summary(po_list: List[Dict]) -> Dict:
    """
    获取采购订单列表的摘要信息
    
    Args:
        po_list: 采购订单列表
        
    Returns:
        dict: 摘要信息
    """
    total_lines = 0
    po_codes = []
    
    for po in po_list:
        po_codes.append(po.get('ponum', 'Unknown'))
        poline = po.get('poline', [])
        total_lines += len(poline)
    
    return {
        'total_pos': len(po_list),
        'total_lines': total_lines,
        'po_codes': po_codes,
        'avg_lines_per_po': total_lines / len(po_list) if po_list else 0
    }
