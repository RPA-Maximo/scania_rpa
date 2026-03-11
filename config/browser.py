"""
浏览器配置

用于配置浏览器启动参数
"""
import os
from pathlib import Path


# 浏览器路径（自动检测 Edge 和 Chrome）
def get_browser_path():
    """自动检测浏览器路径"""
    # Edge 路径
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    
    # Chrome 路径
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    
    # 优先使用 Edge
    for path in edge_paths:
        if os.path.exists(path):
            return path, "Edge"
    
    # 其次使用 Chrome
    for path in chrome_paths:
        if os.path.exists(path):
            return path, "Chrome"
    
    return None, None


# 浏览器配置
BROWSER_PATH, BROWSER_NAME = get_browser_path()

# 用户数据目录（持久化 Cookie，无需每次重新登录）
# 使用独立的 RPA 专用目录，避免与正常 Edge 实例冲突
USER_DATA_DIR = os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\RPA_Profile")

# ── Maximo 直连 URL（取代原 CDP 调试端口方案）────────────────────────────────
# 连接目标：Maximo manage-shell 主页，登录后直接导航至此
MAXIMO_SHELL_URL = (
    "https://main.manage.scania-acc.suite.maximo.com"
    "/maximo/oslc/graphite/manage-shell"
)

# Maximo 认证登录页（首次登录或 Cookie 过期时跳转至此）
MAXIMO_LOGIN_URL = "https://auth.scania-acc.suite.maximo.com/login/#/form"

# ── 保留向后兼容（旧版 CDP 调试端口）────────────────────────────────────────
# 新代码请直接使用 MAXIMO_SHELL_URL；下列常量仅供旧版脚本引用
DEBUG_PORT = 9223
CDP_URL = f"http://localhost:{DEBUG_PORT}"


# 验证配置
if not BROWSER_PATH:
    print("⚠ 警告：未找到 Edge 或 Chrome 浏览器")
    print("   请手动设置 config/browser.py 中的 BROWSER_PATH")
