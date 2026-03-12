"""
字段映射配置
定义 JSON 字段到数据库字段的映射关系
"""

# JSON 字段 -> 数据库字段映射 (订单头 - 直接映射字段)
PO_HEADER_MAPPING = {
    'ponum': 'code',
    'description': 'description',      # 用户单号/描述
    'purchaseagent': 'user_code',
    'siteid': 'location',
    'status': 'status',
    # 'vendor' 字段用于查询 sys_department 获取 owner_dept_id；supplier_name 直接取 vendorname
    'statusdate': 'status_date',
    'orderdate': 'order_date',          # 订单日期/发货日期
    'totalcost': 'total_cost',
    'currencycode': 'currency',
    'revisionnum': 'revision',
    'potype': 'type',
    'requireddate': 'request_date',
}

# Maximo MXAPIPO 供应商字段候选名（取第一个非空值）
# 不同 Maximo 版本字段名可能不同
VENDOR_FIELD_CANDIDATES = {
    'vendor_code':        ['vendor'],
    'supplier_address':   ['venaddress1', 'venaddr1', 'vendoraddr1'],
    'supplier_address2':  ['venaddress2', 'venaddr2'],          # 供应商地址2
    'supplier_zip':       ['venzip', 'venpostalcode'],
    'supplier_city':      ['vencity'],
    'supplier_state':     ['venstate', 'venprovince', 'venregion'],  # 供应商省/区
    # supplier_country 不抓（供应商国家不拉）
    'supplier_contact':   ['vencontact'],
    'supplier_phone':     ['venphone'],
    'supplier_email':     ['cxpoemail', 'venemail'],            # cxpoemail = 接收PO的邮箱
}

# Maximo MXAPIPO 收款方（Bill To）+ 内部买方字段候选名
# 对应 Maximo UI "收货方/收款人" 标签页右侧"收款方"区域
BILLTO_FIELD_CANDIDATES = {
    'company_name':         ['billtocomp', 'billtoname'],
    'street_address_1':     ['billtoaddress1', 'billtoaddr1'],
    'street_address_2':     ['billtoaddress2', 'billtoaddr2'],
    'postal_code':          ['billtozip', 'billtopostalcode'],
    'city':                 ['billtocity'],
    'country':              ['billtocountry'],                  # 国家（动态拉取，不写死）
    'contact_person':       ['billtocontact'],                  # 联系人
    'contact_phone':        ['billtophone'],                    # 联系电话
    'contact_email':        ['billtoemail'],                    # 电子邮件
    'receiver':             ['shiptoattn'],                     # 接收人（Ship To Attention）
    # scania_customer_code 不填（无对应 Maximo 字段）
}

# JSON 字段 -> 数据库字段映射 (订单明细)
PO_LINE_MAPPING = {
    'polinenum': 'number',
    'description': 'sku_names',         # 物料名称描述
    'orderqty': 'qty',
    'receiptscomplete': 'receive_status',
    'orderunit': 'ordering_unit',
    'unitcost': 'unit_cost',
    'polinediscpct': 'discount_pct',    # 折扣%
    'linecost': 'line_cost',
    'catalogcode': 'model_num',         # 型号
    'newitemdesc': 'size_info',         # 尺寸/规格
    'itemnum': 'item_code',             # 物料编号（原始字符串，始终保留）
    'location': 'target_container',     # 目标货柜
    # 'currency' 优先取行级字段，fallback 到 PO 头 currencycode（在 map_line_data 中处理）
    # 'sku' 由 itemnum 查询 material 表获取 material_id，可能为 NULL
    # 'warehouse' 由 storeloc 查询 warehouse 表获取 warehouse_id，可能为 NULL
}

# poline -> material 字段映射
MATERIAL_MAPPING = {
    'itemnum': 'code',
    'description': 'name',
    'orderunit': 'ordering_unit',
    'manufacturer': 'manufacturer',
}
