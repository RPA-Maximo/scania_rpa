"""
运行时设置 API 路由

通过 API 动态调整代理、请求延迟等爬虫参数，无需重启服务。
"""
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.settings_manager import settings_manager

router = APIRouter(prefix="/api/settings", tags=["运行时设置"])


class ProxyUpdateRequest(BaseModel):
    enabled: bool = Field(..., description="是否启用代理")
    host: Optional[str] = Field(None, description="代理主机，如 '127.0.0.1'")
    port: Optional[int] = Field(None, description="代理端口，如 10820", ge=1, le=65535)
    protocol: Optional[str] = Field(
        None,
        description="代理协议：socks5 | http | https",
        pattern="^(socks5|http|https)$",
    )


class RequestParamsUpdateRequest(BaseModel):
    request_delay: Optional[float] = Field(
        None, description="请求间隔（秒），默认 1.0", ge=0, le=30
    )
    verify_ssl: Optional[bool] = Field(None, description="是否验证 SSL 证书")
    max_retries: Optional[int] = Field(
        None, description="最大重试次数", ge=0, le=10
    )


@router.get("", summary="查看所有运行时设置")
async def get_all_settings():
    """返回当前所有运行时设置（代理、请求参数等）"""
    return settings_manager.get_all_settings()


@router.get("/proxy", summary="查看当前代理设置")
async def get_proxy_settings():
    """
    返回当前代理配置及状态。

    - `socks_available`：是否安装了 PySocks（SOCKS5 代理必需）
    - `effective_proxies`：实际生效的代理（若 PySocks 缺失则为 null）
    - `note`：问题提示（如 PySocks 未安装时的安装指引）
    """
    return settings_manager.get_proxy_status()


@router.post("/proxy", summary="更新代理设置")
async def update_proxy_settings(request: ProxyUpdateRequest):
    """
    动态更新代理配置，立即对后续所有爬虫请求生效，无需重启服务。

    **SOCKS5 代理需要安装 PySocks：**
    ```
    pip install PySocks
    ```

    **关闭代理（直连）：**
    ```json
    {"enabled": false}
    ```

    **切换为 HTTP 代理：**
    ```json
    {"enabled": true, "host": "127.0.0.1", "port": 7890, "protocol": "http"}
    ```
    """
    result = settings_manager.update_proxy(
        enabled=request.enabled,
        host=request.host,
        port=request.port,
        protocol=request.protocol,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/request", summary="更新请求参数")
async def update_request_params(request: RequestParamsUpdateRequest):
    """
    动态更新爬虫请求参数。

    - `request_delay`：每次请求之间的间隔秒数（默认 1 秒，防止被限流）
    - `verify_ssl`：是否验证 SSL 证书（Maximo 通常需要设为 false）
    - `max_retries`：失败自动重试次数
    """
    if all(v is None for v in [request.request_delay, request.verify_ssl, request.max_retries]):
        raise HTTPException(status_code=400, detail="至少需要提供一个参数")
    return settings_manager.update_request_params(
        request_delay=request.request_delay,
        verify_ssl=request.verify_ssl,
        max_retries=request.max_retries,
    )
