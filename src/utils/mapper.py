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
#
# 实测验证（CN5074，102 个返回字段）：
#   ✓ vendor       → 供应商代码（"8970301"），唯一有值的供应商字段
#   ✗ vendorname   → 不返回（Maximo 此字段需 COMPANIES READ 权限）
#   ✗ venaddress1/vencity/venzip 等 → 均不返回（同上）
#   ✓ cxpoemail    → 如有值则为接收 PO 的邮箱（本实例未见有值）
#
# 供应商名称/地址如需填充，通过 POST /api/vendor-cache 手动录入，
# fetch_vendor_details 会优先查本地 company_cache 表。
VENDOR_FIELD_CANDIDATES = {
    'vendor_code':        ['vendor'],
    # 以下字段在当前实例不返回，保留以备权限开放后自动生效
    'supplier_address':   ['venaddress1', 'venaddr1'],
    'supplier_address2':  ['venaddress2', 'venaddr2'],
    'supplier_zip':       ['venzip', 'venpostalcode'],
    'supplier_city':      ['vencity'],
    'supplier_state':     ['venstate', 'venprovince'],
    'supplier_contact':   ['vencontact'],
    'supplier_phone':     ['venphone'],
    'supplier_email':     ['cxpoemail', 'venemail'],
}

# Maximo MXAPIPO 收款方（Bill To）+ 内部买方字段候选名
#
# 实测验证（CN5074）：
#   ✓ billto       → 收款方代码（"BILLTOCHINA"）
#   ✓ shipto       → 收货方代码（"0001"）
#   ✗ billtocomp/billtoaddress1/billtocity 等 → 均不返回
#   ✓ cxcontact    → 买方联系人（"+8618015248228 , sandy.zhang@scania.com.cn"）
#                    格式："+86手机号 , 姓名.姓名@scania.com.cn"
#
# 收款方名称/地址如需填充，同样通过 POST /api/vendor-cache（以 billto 代码为键）录入。
BILLTO_FIELD_CANDIDATES = {
    'company_name':         ['billtocomp', 'billtoname'],       # 不返回，留候选
    'street_address_1':     ['billtoaddress1', 'billtoaddr1'],  # 不返回，留候选
    'street_address_2':     ['billtoaddress2', 'billtoaddr2'],  # 不返回，留候选
    'postal_code':          ['billtozip', 'billtopostalcode'],  # 不返回，留候选
    'city':                 ['billtocity'],                     # 不返回，留候选
    'country':              ['billtocountry'],                  # 不返回，留候选
    'contact_person':       ['billtocontact', 'cxcontact'],     # cxcontact 有值：买方联系人
    'contact_phone':        ['billtophone'],                    # 不返回，留候选
    'contact_email':        ['billtoemail'],                    # 不返回，留候选
    'receiver':             ['shiptoattn'],                     # 不返回，留候选
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
