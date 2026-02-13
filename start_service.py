"""
一键启动 Maximo RPA 服务

自动完成以下步骤：
1. 检查并启动浏览器（调试模式）
2. 检查 Maximo 登录状态
3. 启动 API 服务

使用方法：
    python start_service.py              # 正常启动
    python start_service.py --clean      # 清理旧进程后启动
"""
import subprocess
import os
import sys
import time
import requests
import asyncio
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

# Windows 平台需要设置事件循环策略
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


# API 配置
API_PORT = 8000


def print_header(title):
    """打印标题"""
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)
    print()


def kill_edge_processes():
    """杀掉所有 Edge 进程"""
    print("正在关闭所有 Edge 进程...")
    try:
        # Windows 使用 taskkill
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "msedge.exe", "/T"],
            capture_output=True,
            text=True
        )
        
        if "成功" in result.stdout or "SUCCESS" in result.stdout:
            print("✓ Edge 进程已关闭")
            time.sleep(2)  # 等待进程完全关闭
            return True
        elif "找不到" in result.stdout or "not found" in result.stdout.lower():
            print("✓ 没有运行中的 Edge 进程")
            return True
        else:
            print(f"⚠ {result.stdout}")
            return True
    except Exception as e:
        print(f"⚠ 无法关闭 Edge 进程: {e}")
        return False


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


def navigate_to_manage_shell(page_id: str):
    """导航到 manage-shell 页面"""
    target_url = "https://main.manage.scania-acc.suite.maximo.com/maximo/oslc/graphite/manage-shell"
    
    try:
        # 使用 CDP 协议导航页面
        response = requests.post(
            f"http://localhost:{DEBUG_PORT}/json",
            json={
                "method": "Page.navigate",
                "params": {
                    "url": target_url
                }
            },
            timeout=5
        )
        return True
    except Exception as e:
        print(f"⚠ 导航失败: {e}")
        return False


async def navigate_to_manage_shell_async():
    """使用 Playwright 执行 JavaScript 跳转到 ITEM 应用"""
    from playwright.async_api import async_playwright
    
    try:
        p = await async_playwright().start()
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
        
        # 查找 home 页面
        home_page = None
        for context in browser.contexts:
            for page in context.pages:
                if "main.home.scania-acc.suite.maximo.com" in page.url:
                    home_page = page
                    break
            if home_page:
                break
        
        if home_page:
            print(f"✓ 找到 home 页面，正在执行跳转...")
            
            # 执行 JavaScript 跳转到 ITEM 应用
            await home_page.evaluate("sendEvent('changeapp','startcntr','ITEM',3);")
            print(f"✓ 已执行跳转命令")
            
            # 等待 60 秒
            print("⏳ 等待 60 秒让页面完全加载...")
            for i in range(60, 0, -1):
                print(f"  剩余 {i} 秒...", end="\r", flush=True)
                await asyncio.sleep(1)
            print()
            print("✓ 等待完成")
            
            await browser.close()
            await p.stop()
            return True
        else:
            print("⚠ 未找到 home 页面")
            await browser.close()
            await p.stop()
            return False
            
    except Exception as e:
        print(f"⚠ 导航失败: {e}")
        return False


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
        for i in range(15):  # 增加到 15 秒
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
    # 检查命令行参数
    clean_mode = "--clean" in sys.argv or "-c" in sys.argv
    
    print_header("Maximo RPA 服务启动")
    
    # 如果是清理模式，先杀掉所有 Edge 进程
    if clean_mode:
        print("🧹 清理模式：将关闭所有 Edge 进程")
        kill_edge_processes()
        print()
    
    # 步骤 1: 检查/启动浏览器
    print("步骤 1/3: 检查浏览器")
    if check_browser_running():
        print("✓ 浏览器已运行")
    else:
        print("浏览器未运行，正在启动...")
        if not start_browser():
            print()
            print("❌ 浏览器启动失败")
            print()
            print("💡 提示：")
            print("   1. 可能有其他 Edge 进程占用端口")
            print("   2. 尝试使用清理模式：python start_service.py --clean")
            print("   3. 或手动关闭所有 Edge 窗口后重试")
            return False
        print("✓ 浏览器启动成功")
    
    # 步骤 2: 检查登录状态
    print()
    print("步骤 2/3: 检查登录状态")
    logged_in, url = check_maximo_logged_in()
    
    if logged_in:
        print(f"✓ 已登录 Maximo")
        print(f"  当前页面：{url}")
        
        # 检查是否在 home 页面，如果是则跳转到 manage-shell
        if url and 'main.home.scania-acc.suite.maximo.com' in url:
            print()
            print("检测到 home 页面，正在跳转到 ITEM 应用...")
            
            # 使用异步函数导航
            try:
                success = asyncio.run(navigate_to_manage_shell_async())
                if not success:
                    print("⚠ 自动跳转失败，请手动导航")
                    print("  请在浏览器中手动打开 ITEM 应用")
                    print()
                    input("完成后按回车键继续...")
            except Exception as e:
                print(f"⚠ 跳转过程出现问题: {e}")
                print("  请在浏览器中手动打开 ITEM 应用")
                print()
                input("完成后按回车键继续...")
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
