"""
认证管理 API 路由

通过 API 动态更新 Maximo 认证信息，无需手动编辑文件。

使用流程：
  1. 浏览器打开 Maximo，登录后访问 maximo.jsp
  2. DevTools → Network → 找到 maximo.jsp 请求
  3. 右键 → Copy as cURL (bash)
  4. POST /api/auth/curl，粘贴复制的内容到 curl_text 字段
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from config.auth_manager import auth_manager

router = APIRouter(prefix="/api/auth", tags=["认证管理"])


class CurlUpdateRequest(BaseModel):
    curl_text: str = Field(
        ...,
        description="从浏览器 Copy as cURL (bash) 复制的完整 cURL 命令",
        example="curl 'https://main.manage.scania-acc.suite.maximo.com/maximo/maximo.jsp' "
                "-b 'LtpaToken2=xxx; x-refresh-token=yyy' "
                "--data-raw 'csrftoken=abc123'",
    )


class FieldsUpdateRequest(BaseModel):
    cookie: str = Field(..., description="完整的 Cookie 字符串")
    csrf_token: str = Field(..., description="CSRF Token（csrftoken 的值）")
    refresh_token: Optional[str] = Field("", description="Refresh Token（可选）")


@router.post("/curl", summary="通过 cURL 命令更新认证")
async def update_auth_from_curl(request: CurlUpdateRequest):
    """
    粘贴从浏览器复制的 cURL (bash) 命令来更新认证信息。

    **操作步骤：**
    1. 浏览器打开 Maximo 并登录
    2. 打开 DevTools (F12) → Network 标签
    3. 刷新页面，找到 `maximo.jsp` 请求
    4. 右键该请求 → **Copy as cURL (bash)**
    5. 将复制内容粘贴到下方 `curl_text` 字段中提交
    """
    result = auth_manager.update_from_curl(request.curl_text)
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['message'])
    return result


@router.post("/fields", summary="通过字段直接更新认证")
async def update_auth_from_fields(request: FieldsUpdateRequest):
    """
    直接提交 Cookie 和 CSRF Token 字段更新认证信息。

    适合已单独提取出各字段值的场景。
    """
    result = auth_manager.update_from_fields(
        cookie=request.cookie,
        csrf_token=request.csrf_token,
        refresh_token=request.refresh_token or '',
    )
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['message'])
    return result


@router.get("/status", summary="查询当前认证状态")
async def get_auth_status():
    """
    返回当前认证信息的状态（不含敏感内容）。

    - `has_auth`：是否已配置认证
    - `source`：认证来源（curl_file / api_curl / api_fields / env）
    - `updated_at`：最近更新时间
    """
    return auth_manager.get_status()
