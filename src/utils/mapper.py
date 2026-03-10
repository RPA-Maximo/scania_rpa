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
    'vendor_code':       ['vendor'],
    'supplier_address':  ['venaddress1', 'venaddr1', 'vendoraddr1'],
    'supplier_zip':      ['venzip', 'venpostalcode'],
    'supplier_city':     ['vencity'],
    'supplier_country':  ['vencountry', 'vennation'],           # 供应商国家
    'supplier_contact':  ['vencontact'],
    'supplier_phone':    ['venphone'],
    'supplier_email':    ['cxpoemail', 'venemail'],             # cxpoemail = 接收PO的邮箱
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
    'contact_person':       ['billtoattn', 'billtocontact'],    # 联系人
    'contact_phone':        ['billtophone'],                    # 联系电话
    'contact_email':        ['billtoemail', 'contactemail'],    # 联系邮件
    'receiver':             ['shiptoattn', 'shiptocontact', 'shiptocomp'],  # 接收人
    'scania_customer_code': ['buyercode', 'custcode', 'ourreference'],      # 斯堪尼亚客户代码
}

# JSON 字段 -> 数据库字段映射 (订单明细)
PO_LINE_MAPPING = {
    'polinenum': 'number',
    'description': 'sku_names',         # 物料名称描述
    'orderqty': 'qty',
    'receiptscomplete': 'receive_status',
    'orderunit': 'ordering_unit',
    'unitcost': 'unit_cost',
    'linecost': 'line_cost',
    'catalogcode': 'model_num',         # 型号
    'newitemdesc': 'size_info',         # 尺寸/规格
    'location': 'target_container',     # 目标货柜
    # 'itemnum' 需要通过查询 material 表获取 id，映射到 'sku'
    # 'storeloc' 通过查询 warehouse 表获取 id，映射到 'warehouse'
}

# poline -> material 字段映射
MATERIAL_MAPPING = {
    'itemnum': 'code',
    'description': 'name',
    'orderunit': 'ordering_unit',
    'manufacturer': 'manufacturer',
}
