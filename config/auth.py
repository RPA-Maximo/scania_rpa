"""
认证信息管理模块
从环境变量或 .env 文件中读取 Maximo API 认证信息
"""
import os
from pathlib import Path


def load_env_file(env_path: str = None):
    """
    手动加载 .env 文件（简单实现，避免引入 python-dotenv 依赖）
    """
    if env_path is None:
        # 默认从 config/.env 读取
        env_path = Path(__file__).parent / ".env"
    
    if not Path(env_path).exists():
        return
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过注释和空行
            if not line or line.startswith('#'):
                continue
            
            # 解析 KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                # 只在环境变量不存在时设置
                if key and not os.getenv(key):
                    os.environ[key] = value


def get_maximo_auth():
    """
    获取 Maximo API 认证信息
    
    Returns:
        dict: 包含 cookie, csrf_token, refresh_token 的字典
    """
    # 先尝试加载 .env 文件
    load_env_file()
    
    cookie = os.getenv('MAXIMO_COOKIE', '')
    csrf_token = os.getenv('MAXIMO_CSRF_TOKEN', '')
    refresh_token = os.getenv('MAXIMO_REFRESH_TOKEN', '')
    
    if not cookie or not csrf_token:
        raise ValueError(
            "缺少认证信息！请在 config/.env 文件中设置 MAXIMO_COOKIE 和 MAXIMO_CSRF_TOKEN"
        )
    
    return {
        'cookie': cookie,
        'csrf_token': csrf_token,
        'refresh_token': refresh_token
    }


def get_db_config():
    """
    获取数据库连接配置
    
    Returns:
        dict: 数据库连接参数
    """
    load_env_file()
    
    return {
        'host': os.getenv('DB_HOST', '222.187.11.98'),
        'port': int(os.getenv('DB_PORT', '33060')),
        'database': os.getenv('DB_NAME', 'bmp153'),
        'user': os.getenv('DB_USER', 'bmp153'),
        'password': os.getenv('DB_PASSWORD', '')
    }
