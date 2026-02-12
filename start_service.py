"""
一键启动 Maximo RPA 服务

自动完成以下步骤：
1. 检查并启动浏览器（调试模式）
2. 检查 Maximo 登录状态
3. 启动 API 服务

使用方法：
    python start_service.py
"""
import subprocess
import os
import sys
import time
import requests
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config.browser import (
    BROWSER_PATH,
    BROWSER_NAME,
    USER_DATA_DIR,
    DEBUG_PORT,
    MAXIMO_LOGIN_URL
)


# API 配置
API_PORT = 8000


def print_header(title):
    """打印标题"""
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)
    print()


def check_browser_running():
    """检查浏览器是否已在调试模式运行"""
    try:
        response = requests.get(f"http://localhost:{DEBUG_PORT}/json/version", timeout=2)
        return response.status_code == 200
    except:
        return False


def check_maximo_logged_in():
    """检查是否已登录 Maximo（通过检查是否有 maximo 页面）"""
    try:
        response = requests.get(f"http://localhost:{DEBUG_PORT}/json", timeout=2)
        pages = response.json()
        
        for page in pages:
            url = page.get('url', '').lower()
            if 'maximo' in url and 'login' not in url:
                return True, page.get('url')
        
        # 检查是否在登录页
        for page in pages:
            url = page.get('url', '').lower()
            if 'login' in url or 'auth.scania' in url:
                return False, url
        
        return False, None
    except:
        return False, None


def start_browser():
    """启动浏览器"""
    if not BROWSER_PATH or not os.path.exists(BROWSER_PATH):
        print(f"❌ 错误：未找到浏览器")
        if BROWSER_PATH:
            print(f"   路径：{BROWSER_PATH}")
        return False
    
    print(f"正在启动 {BROWSER_NAME} 浏览器...")
    
    cmd = [
        BROWSER_PATH,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--profile-directory=Default",
        MAXIMO_LOGIN_URL
    ]
    
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # 等待浏览器启动
        print("等待浏览器启动...", end="", flush=True)
        for i in range(10):
            time.sleep(1)
            if check_browser_running():
                print(" ✓")
                return True
            print(".", end="", flush=True)
        
        print(" ❌")
        return False
        
    except Exception as e:
        print(f"\n❌ 启动失败：{e}")
        return False


def wait_for_login():
    """等待用户登录"""
    print()
    print("⏳ 等待登录 Maximo...")
    print("   请在浏览器中完成登录")
    print()
    
    for i in range(60):  # 最多等待 60 秒
        time.sleep(1)
        logged_in, url = check_maximo_logged_in()
        if logged_in:
            print(f"✓ 登录成功！")
            print(f"  当前页面：{url}")
            return True
        
        if i % 5 == 0:
            print(f"  等待中... ({i}s)", end="\r", flush=True)
    
    print()
    print("❌ 登录超时")
    return False


def start_api():
    """启动 API 服务"""
    print()
    print("正在启动 API 服务...")
    print(f"  端口：{API_PORT}")
    print()
    
    try:
        # 使用 uvicorn 启动 API
        subprocess.run([
            sys.executable,
            "-m", "uvicorn",
            "api.main:app",
            "--host", "0.0.0.0",
            "--port", str(API_PORT),
            "--reload"
        ])
    except KeyboardInterrupt:
        print()
        print("API 服务已停止")


def main():
    """主流程"""
    print_header("Maximo RPA 服务启动")
    
    # 步骤 1: 检查/启动浏览器
    print("步骤 1/3: 检查浏览器")
    if check_browser_running():
        print("✓ 浏览器已运行")
    else:
        print("浏览器未运行，正在启动...")
        if not start_browser():
            print()
            print("❌ 浏览器启动失败")
            print("   请手动运行：python start_browser.py")
            return False
        print("✓ 浏览器启动成功")
    
    # 步骤 2: 检查登录状态
    print()
    print("步骤 2/3: 检查登录状态")
    logged_in, url = check_maximo_logged_in()
    
    if logged_in:
        print(f"✓ 已登录 Maximo")
        print(f"  当前页面：{url}")
    else:
        if url:
            print(f"⚠ 检测到登录页面：{url}")
        else:
            print(f"⚠ 未检测到 Maximo 页面")
        
        if not wait_for_login():
            print()
            print("❌ 请先登录 Maximo，然后重新运行此脚本")
            return False
    
    # 步骤 3: 启动 API
    print()
    print("步骤 3/3: 启动 API 服务")
    print()
    print_header("服务已就绪")
    print("API 文档：http://localhost:8000/docs")
    print("健康检查：http://localhost:8000/health")
    print()
    print("按 Ctrl+C 停止服务")
    print()
    
    start_api()
    return True


if __name__ == "__main__":
    try:
        success = main()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print()
        print("服务已停止")
        sys.exit(0)
