"""
字段映射配置
定义 JSON 字段到数据库字段的映射关系
"""

# JSON 字段 -> 数据库字段映射 (订单头)
PO_HEADER_MAPPING = {
    'ponum': 'code',
    'description': 'description',
    'purchaseagent': 'user_code',
    'siteid': 'location',
    'status': 'status',
    'vendor': 'supplier_name',
    'statusdate': 'status_date',
    'orderdate': 'order_date',
    'totalcost': 'total_cost',
    'currencycode': 'currency',
    'revisionnum': 'revision',
    'potype': 'type',
    'requireddate': 'request_date',
}

# JSON 字段 -> 数据库字段映射 (订单明细)
PO_LINE_MAPPING = {
    'polinenum': 'number',
    'description': 'sku_names',  # 物料名称描述
    'orderqty': 'qty',
    'receiptscomplete': 'receive_status',
    'orderunit': 'ordering_unit',
    'unitcost': 'unit_cost',
    'linecost': 'line_cost',
    # 'itemnum' 需要通过查询 material 表获取 id，映射到 'sku'
}

# poline -> material 字段映射
MATERIAL_MAPPING = {
    'itemnum': 'code',
    'description': 'name',
    'orderunit': 'ordering_unit',
    'manufacturer': 'manufacturer',
}
