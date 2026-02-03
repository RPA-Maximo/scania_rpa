"""
认证信息管理模块
从环境变量或 .env 文件中读取 Maximo API 认证信息
支持从 响应标头.txt 中解析 curl 命令获取认证信息
"""
import os
import re
from pathlib import Path
from urllib.parse import unquote


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


def parse_curl_file(curl_file_path: str = None):
    """
    从 curl 命令文件中解析认证信息
    
    Args:
        curl_file_path: curl 文件路径，默认为 config/响应标头.txt
        
    Returns:
        dict: 包含 cookie, csrf_token, refresh_token 的字典，解析失败返回 None
    """
    if curl_file_path is None:
        curl_file_path = Path(__file__).parent / "响应标头.txt"
    
    if not Path(curl_file_path).exists():
        return None
    
    try:
        with open(curl_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取 Cookie（-b 参数后的内容）
        cookie_match = re.search(r"-b\s+'([^']+)'", content)
        if not cookie_match:
            cookie_match = re.search(r'-b\s+"([^"]+)"', content)
        
        cookie = cookie_match.group(1) if cookie_match else ''
        
        # 提取 CSRF Token（从 --data-raw 中的 csrftoken 参数）
        csrf_match = re.search(r'csrftoken=([a-z0-9]+)', content)
        csrf_token = csrf_match.group(1) if csrf_match else ''
        
        # 提取 Refresh Token（从 Cookie 中的 x-refresh-token）
        refresh_match = re.search(r'x-refresh-token=([^;]+)', cookie)
        refresh_token = refresh_match.group(1) if refresh_match else ''
        
        if cookie and csrf_token:
            return {
                'cookie': cookie,
                'csrf_token': csrf_token,
                'refresh_token': refresh_token
            }
        
        return None
        
    except Exception as e:
        print(f"解析 curl 文件失败: {e}")
        return None


def get_maximo_auth():
    """
    获取 Maximo API 认证信息
    优先从 响应标头.txt 解析，失败则从 .env 读取
    
    Returns:
        dict: 包含 cookie, csrf_token, refresh_token 的字典
    """
    # 优先尝试从 响应标头.txt 解析
    auth_info = parse_curl_file()
    
    if auth_info:
        return auth_info
    
    # 回退到 .env 文件
    load_env_file()
    
    cookie = os.getenv('MAXIMO_COOKIE', '')
    csrf_token = os.getenv('MAXIMO_CSRF_TOKEN', '')
    refresh_token = os.getenv('MAXIMO_REFRESH_TOKEN', '')
    
    if not cookie or not csrf_token:
        raise ValueError(
            "缺少认证信息！请在 config/响应标头.txt 或 config/.env 文件中设置认证信息"
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
