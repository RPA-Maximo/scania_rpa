"""
认证状态管理器（单例）
支持内存中维护认证状态，可通过 API 动态更新，无需手动修改文件
"""
import os
import re
import threading
from datetime import datetime
from pathlib import Path


class AuthManager:
    """Maximo 认证信息管理器（单例模式）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._auth = None
        self._updated_at = None
        self._source = None  # 'curl_file' | 'api_curl' | 'api_fields' | 'env'
        self._curl_file_path = Path(__file__).parent / "响应标头.txt"
        self._initialized = True
        # 启动时从文件或环境变量加载
        self._load_initial()

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _load_initial(self):
        """启动时尝试从 curl 文件 / .env 加载"""
        # 1. 尝试 curl 文件
        auth = self._parse_curl_file(self._curl_file_path)
        if auth:
            self._auth = auth
            self._updated_at = datetime.now()
            self._source = 'curl_file'
            return

        # 2. 尝试 .env
        self._load_env_file()
        cookie = os.getenv('MAXIMO_COOKIE', '')
        csrf_token = os.getenv('MAXIMO_CSRF_TOKEN', '')
        refresh_token = os.getenv('MAXIMO_REFRESH_TOKEN', '')
        if cookie and csrf_token:
            self._auth = {
                'cookie': cookie,
                'csrf_token': csrf_token,
                'refresh_token': refresh_token,
            }
            self._updated_at = datetime.now()
            self._source = 'env'

    @staticmethod
    def _load_env_file(env_path: Path = None):
        """加载 .env 文件到环境变量"""
        if env_path is None:
            env_path = Path(__file__).parent / ".env"
        if not env_path.exists():
            return
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key and not os.getenv(key):
                        os.environ[key] = value

    @staticmethod
    def _parse_curl_text(text: str):
        """
        从 cURL bash 命令文本中提取认证字段

        Returns:
            dict | None: {'cookie', 'csrf_token', 'refresh_token'} 或 None
        """
        # Cookie：-b '...' 或 -b "..."
        cookie_match = re.search(r"-b\s+'([^']+)'", text)
        if not cookie_match:
            cookie_match = re.search(r'-b\s+"([^"]+)"', text)
        cookie = cookie_match.group(1) if cookie_match else ''

        # CSRF Token：csrftoken=<hex>
        csrf_match = re.search(r'csrftoken=([a-zA-Z0-9]+)', text)
        csrf_token = csrf_match.group(1) if csrf_match else ''

        # Refresh Token（从 Cookie 中提取）
        refresh_match = re.search(r'x-refresh-token=([^;]+)', cookie)
        refresh_token = refresh_match.group(1) if refresh_match else ''

        if cookie and csrf_token:
            return {
                'cookie': cookie,
                'csrf_token': csrf_token,
                'refresh_token': refresh_token,
            }
        return None

    @classmethod
    def _parse_curl_file(cls, path: Path):
        """从文件读取 cURL 文本并解析"""
        if not path.exists():
            return None
        try:
            content = path.read_text(encoding='utf-8')
            return cls._parse_curl_text(content)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def update_from_curl(self, curl_text: str) -> dict:
        """
        通过粘贴的 cURL (bash) 命令更新认证信息

        浏览器操作：DevTools → Network → 右键 maximo.jsp 请求 → Copy as cURL (bash)

        Returns:
            dict: {'success': bool, 'message': str, ...}
        """
        auth = self._parse_curl_text(curl_text)
        if not auth:
            missing = []
            if not re.search(r"-b\s+['\"]", curl_text):
                missing.append("Cookie (-b '...')")
            if not re.search(r'csrftoken=', curl_text):
                missing.append("CSRF Token (csrftoken=...)")
            return {
                'success': False,
                'message': f"解析失败，未能提取: {', '.join(missing) or '未知字段'}。"
                           "请确保粘贴的是浏览器 Copy as cURL (bash) 格式",
            }

        with self._lock:
            self._auth = auth
            self._updated_at = datetime.now()
            self._source = 'api_curl'

        # 同步写回文件（供下次启动加载）
        try:
            self._curl_file_path.write_text(curl_text, encoding='utf-8')
        except Exception:
            pass

        return {
            'success': True,
            'message': '认证信息已更新',
            'source': 'api_curl',
            'updated_at': self._updated_at.isoformat(),
            'cookie_length': len(auth['cookie']),
            'csrf_token_preview': auth['csrf_token'][:8] + '...',
            'has_refresh_token': bool(auth['refresh_token']),
        }

    def update_from_fields(self, cookie: str, csrf_token: str, refresh_token: str = '') -> dict:
        """
        直接通过字段更新认证信息（已知各字段值时使用）

        Returns:
            dict: {'success': bool, 'message': str, ...}
        """
        errors = []
        if not cookie:
            errors.append('cookie')
        if not csrf_token:
            errors.append('csrf_token')
        if errors:
            return {'success': False, 'message': f"缺少必填字段: {', '.join(errors)}"}

        auth = {
            'cookie': cookie,
            'csrf_token': csrf_token,
            'refresh_token': refresh_token,
        }
        with self._lock:
            self._auth = auth
            self._updated_at = datetime.now()
            self._source = 'api_fields'

        return {
            'success': True,
            'message': '认证信息已更新',
            'source': 'api_fields',
            'updated_at': self._updated_at.isoformat(),
            'cookie_length': len(cookie),
            'csrf_token_preview': csrf_token[:8] + '...',
            'has_refresh_token': bool(refresh_token),
        }

    def get_auth(self) -> dict:
        """
        获取当前有效的认证信息

        Returns:
            dict: {'cookie': str, 'csrf_token': str, 'refresh_token': str}

        Raises:
            ValueError: 认证信息尚未配置
        """
        if self._auth is None:
            # 再试一次文件加载（文件可能在启动后才放入）
            self._load_initial()
        if self._auth is None:
            raise ValueError(
                "认证信息未配置！请通过以下任一方式更新：\n"
                "  POST /api/auth/curl   - 粘贴浏览器 cURL (bash) 命令\n"
                "  POST /api/auth/fields - 直接提交 cookie/csrf_token 字段"
            )
        return self._auth

    def get_status(self) -> dict:
        """返回当前认证状态（不含敏感信息）"""
        has_auth = self._auth is not None
        return {
            'has_auth': has_auth,
            'source': self._source,
            'updated_at': self._updated_at.isoformat() if self._updated_at else None,
            'cookie_length': len(self._auth['cookie']) if has_auth else 0,
            'has_csrf_token': bool(self._auth.get('csrf_token')) if has_auth else False,
            'has_refresh_token': bool(self._auth.get('refresh_token')) if has_auth else False,
        }

    def clear(self):
        """清除内存中的认证信息"""
        with self._lock:
            self._auth = None
            self._updated_at = None
            self._source = None


# 全局单例
auth_manager = AuthManager()
