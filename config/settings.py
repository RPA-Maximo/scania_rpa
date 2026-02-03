"""
项目配置文件
包含 API 端点、请求参数、数据映射规则等
"""
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# ==================== API 配置 ====================

# Maximo API 基础配置
MAXIMO_BASE_URL = "https://main.manage.scania-acc.suite.maximo.com/maximo"
MAXIMO_API_URL = f"{MAXIMO_BASE_URL}/oslc/os/MXAPIINVENTORY"

# 请求头配置
DEFAULT_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
    'X-MAF-APPNAME': 'manage-shell'
}

# API 请求参数
API_PARAMS = {
    'oslc.pageSize': 20,
    'oslc.select': '*',  # 核心参数：获取所有字段
    '_dropnulls': 1,
    'oslc.where': 'status!="OBSOLETE" and itemnum>="20326793"',
    'oslc.orderBy': '+itemnum'
}

# ==================== 数据配置 ====================

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
LOGS_DIR = DATA_DIR / "logs"

# 确保目录存在
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# 数据字段映射（API 字段 -> 数据库字段）
FIELD_MAPPING = {
    'itemnum': 'material_code',
    'location': 'warehouse_code',
    'curbaltotal': 'quantity',  # 注意：使用 curbaltotal 而不是 curbal
    'binnum': 'bin_code',
    'issueunit': 'unit',
    'status': 'status'
}

# ==================== 爬虫配置 ====================

# 请求间隔（秒）
REQUEST_DELAY = 1

# SSL 验证
VERIFY_SSL = False

# 最大重试次数
MAX_RETRIES = 3

# 代理配置
PROXY_ENABLED = True
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 10808

# 代理字典（用于 requests）
PROXIES = {
    'http': f'socks5://{PROXY_HOST}:{PROXY_PORT}',
    'https': f'socks5://{PROXY_HOST}:{PROXY_PORT}'
} if PROXY_ENABLED else None
