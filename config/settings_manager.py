"""
运行时设置管理器（单例）
支持通过 API 动态修改代理、请求延迟等爬虫参数，无需重启服务
"""
import threading
from config.settings import (
    PROXY_ENABLED,
    PROXY_HOST,
    PROXY_PORT,
    PROXY_PROTOCOL,
    REQUEST_DELAY,
    VERIFY_SSL,
    MAX_RETRIES,
)


class SettingsManager:
    """运行时可调整的爬虫配置（单例模式）"""

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
        # 从 settings.py 初始化默认值
        self._proxy_enabled = PROXY_ENABLED
        self._proxy_host = PROXY_HOST
        self._proxy_port = PROXY_PORT
        self._proxy_protocol = PROXY_PROTOCOL
        self._request_delay = REQUEST_DELAY
        self._verify_ssl = VERIFY_SSL
        self._max_retries = MAX_RETRIES
        self._initialized = True

    # ------------------------------------------------------------------
    # 代理设置
    # ------------------------------------------------------------------

    def get_proxies(self) -> dict | None:
        """
        返回当前代理配置字典（适用于 requests 库）

        若 SOCKS5 缺少 PySocks 依赖，自动降级为无代理返回 None。
        """
        if not self._proxy_enabled:
            return None
        if self._proxy_protocol.startswith("socks"):
            try:
                import socks  # noqa: F401
            except ImportError:
                return None
        return {
            "http": f"{self._proxy_protocol}://{self._proxy_host}:{self._proxy_port}",
            "https": f"{self._proxy_protocol}://{self._proxy_host}:{self._proxy_port}",
        }

    def update_proxy(
        self,
        enabled: bool,
        host: str = None,
        port: int = None,
        protocol: str = None,
    ) -> dict:
        """
        更新代理设置

        Args:
            enabled: 是否启用代理
            host: 代理主机（如 '127.0.0.1'）
            port: 代理端口（如 10820）
            protocol: 代理协议（socks5 | http）

        Returns:
            dict: 更新结果
        """
        errors = []
        if enabled:
            if host is not None and not host.strip():
                errors.append("host 不能为空字符串")
            if port is not None and not (1 <= port <= 65535):
                errors.append("port 必须在 1-65535 之间")
            if protocol is not None and protocol not in ("socks5", "http", "https"):
                errors.append("protocol 仅支持 socks5 / http / https")

        if errors:
            return {"success": False, "message": "; ".join(errors)}

        with self._lock:
            self._proxy_enabled = enabled
            if host is not None:
                self._proxy_host = host
            if port is not None:
                self._proxy_port = port
            if protocol is not None:
                self._proxy_protocol = protocol

        proxies = self.get_proxies()
        if enabled and proxies is None:
            return {
                "success": True,
                "message": "代理已启用，但 SOCKS5 缺少 PySocks 依赖（pip install PySocks），实际将直连",
                "effective_proxies": None,
            }
        return {
            "success": True,
            "message": "代理设置已更新",
            "effective_proxies": proxies,
        }

    def get_proxy_status(self) -> dict:
        """返回当前代理状态"""
        proxies = self.get_proxies()
        socks_available = True
        try:
            import socks  # noqa: F401
        except ImportError:
            socks_available = False

        return {
            "proxy_enabled": self._proxy_enabled,
            "proxy_host": self._proxy_host,
            "proxy_port": self._proxy_port,
            "proxy_protocol": self._proxy_protocol,
            "socks_available": socks_available,
            "effective_proxies": proxies,
            "note": None if proxies or not self._proxy_enabled else
                    "PySocks 未安装，实际直连。运行: pip install PySocks",
        }

    # ------------------------------------------------------------------
    # 请求参数设置
    # ------------------------------------------------------------------

    def get_request_delay(self) -> float:
        return self._request_delay

    def get_verify_ssl(self) -> bool:
        return self._verify_ssl

    def get_max_retries(self) -> int:
        return self._max_retries

    def update_request_params(
        self,
        request_delay: float = None,
        verify_ssl: bool = None,
        max_retries: int = None,
    ) -> dict:
        """更新请求参数"""
        with self._lock:
            if request_delay is not None:
                self._request_delay = request_delay
            if verify_ssl is not None:
                self._verify_ssl = verify_ssl
            if max_retries is not None:
                self._max_retries = max_retries
        return {
            "success": True,
            "message": "请求参数已更新",
            "request_delay": self._request_delay,
            "verify_ssl": self._verify_ssl,
            "max_retries": self._max_retries,
        }

    def get_all_settings(self) -> dict:
        """返回所有运行时设置"""
        return {
            "proxy": self.get_proxy_status(),
            "request_delay": self._request_delay,
            "verify_ssl": self._verify_ssl,
            "max_retries": self._max_retries,
        }


# 全局单例
settings_manager = SettingsManager()
