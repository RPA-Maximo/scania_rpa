"""
使用示例
演示不同的配置和使用场景
"""

# ============================================================
# 示例 1: 从文件加载并同步（默认模式）
# ============================================================
EXAMPLE_1_FILE_MODE = {
    'fetch_mode': 'file',
    'auto_sync_materials': True,
    'update_existing_po': False,
    'data_directory': None,  # 使用默认 data/raw
    'file_pattern': 'po_*_detail.json',
}

# ============================================================
# 示例 2: 从 API 抓取指定订单号
# ============================================================
EXAMPLE_2_API_SPECIFIC = {
    'fetch_mode': 'api',
    'po_numbers': ['CN5123', 'CN5124', 'CN5125'],  # 指定订单号
    'auto_sync_materials': True,
    'update_existing_po': False,
}

# ============================================================
# 示例 3: 从 API 分页查询（按状态筛选）
# ============================================================
EXAMPLE_3_API_PAGINATED = {
    'fetch_mode': 'api',
    'po_numbers': None,  # 不指定订单号，使用分页查询
    'status_filter': 'APPR',  # 只查询已批准的订单
    'max_pages': 2,
    'page_size': 20,
    'auto_sync_materials': True,
    'update_existing_po': False,
}

# ============================================================
# 示例 4: 更新已存在的订单
# ============================================================
EXAMPLE_4_UPDATE_MODE = {
    'fetch_mode': 'file',
    'auto_sync_materials': True,
    'update_existing_po': True,  # 更新已存在的订单
    'data_directory': None,
    'file_pattern': 'po_*_detail.json',
}

# ============================================================
# 示例 5: 手动物料同步（不自动同步）
# ============================================================
EXAMPLE_5_MANUAL_MATERIAL = {
    'fetch_mode': 'file',
    'auto_sync_materials': False,  # 不自动同步物料，遇到缺失物料会报错
    'update_existing_po': False,
    'data_directory': None,
    'file_pattern': 'po_*_detail.json',
}


# ============================================================
# 如何使用这些示例
# ============================================================
"""
1. 复制你想要的示例配置
2. 粘贴到 src/main.py 中的 CONFIG 变量
3. 运行 python main.py

例如，要使用示例 2（从 API 抓取指定订单）：

在 src/main.py 中：
CONFIG = {
    'fetch_mode': 'api',
    'po_numbers': ['CN5123', 'CN5124', 'CN5125'],
    'auto_sync_materials': True,
    'update_existing_po': False,
}
"""
