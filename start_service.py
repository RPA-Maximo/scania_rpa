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


def navigate_to_manage():
    """导航到 Manage 页面并验证侧边栏"""
    import asyncio
    from playwright.async_api import async_playwright
    
    async def _navigate():
        """异步导航函数"""
        p = None
        try:
            # 连接到浏览器
            p = await async_playwright().start()
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
            
            # 查找 Maximo 页面
            maximo_page = None
            for context in browser.contexts:
                for page in context.pages:
                    url = page.url.lower()
                    if "maximo" in url or "scania" in url:
                        maximo_page = page
                        break
                if maximo_page:
                    break
            
            if not maximo_page:
                print("✗ 未找到 Maximo 页面")
                return False
            
            current_url = maximo_page.url
            print(f"  当前页面：{current_url}")
            
            # 检查是否在 home 页面
            if "main.home" in current_url:
                print("  检测到 Home 页面，查找 Launch 链接...")
                
                # 查找并点击 Launch 链接
                try:
                    launch_link = await maximo_page.wait_for_selector(
                        'a.bx--link[href*="manage-shell"]',
                        timeout=5000
                    )
                    
                    if launch_link:
                        print("  找到 Launch 链接，正在跳转...")
                        await launch_link.click()
                        
                        # 等待页面跳转
                        await asyncio.sleep(5)
                        print(f"  已跳转到：{maximo_page.url}")
                    else:
                        print("  ✗ 未找到 Launch 链接")
                        return False
                        
                except Exception as e:
                    print(f"  ✗ 查找 Launch 链接失败：{e}")
                    return False
            
            # 等待页面完全加载
            print("  等待 Manage 页面加载...")
            await asyncio.sleep(3)
            
            # 查找主 iframe 并检查侧边栏
            print("  检查侧边栏菜单...")
            main_frame = None
            for frame in maximo_page.frames:
                if "maximo/ui/" in frame.url and "uisessionid" in frame.url:
                    main_frame = frame
                    break
            
            if not main_frame:
                main_frame = maximo_page.main_frame
            
            # 检查侧边栏是否存在（查找"采购"菜单）
            try:
                # 使用 rpa/config.py 中的选择器
                from rpa.config import SELECTORS
                
                purchase_menu = await main_frame.evaluate(f"""
                    () => {{
                        const elem = document.getElementById('{SELECTORS.MENU_PURCHASE}');
                        return elem !== null;
                    }}
                """)
                
                if purchase_menu:
                    print("  ✓ 侧边栏菜单已就绪")
                    return True
                else:
                    print("  ✗ 未找到侧边栏菜单")
                    print("  提示：请手动刷新页面或重新登录")
                    return False
                    
            except Exception as e:
                print(f"  ✗ 检查侧边栏失败：{e}")
                return False
            
        except Exception as e:
            print(f"✗ 导航失败：{e}")
            return False
        finally:
            if p:
                await p.stop()
    
    # 运行异步函数
    try:
        return asyncio.run(_navigate())
    except Exception as e:
        print(f"✗ 执行失败：{e}")
        return False


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
    print("步骤 1/4: 检查浏览器")
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
    print("步骤 2/4: 检查登录状态")
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
    
    # 步骤 3: 导航到 Manage 页面并验证
    print()
    print("步骤 3/4: 准备 Manage 页面")
    if not navigate_to_manage():
        print()
        print("❌ 无法准备 Manage 页面")
        print("   请手动导航到 Manage 页面后重试")
        return False
    
    # 步骤 4: 启动 API
    print()
    print("步骤 4/4: 启动 API 服务")
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
