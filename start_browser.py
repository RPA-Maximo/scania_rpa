"""
启动 Edge 浏览器（调试模式）

自动启动 Edge 浏览器并打开 Maximo 登录页面
浏览器会以调试模式运行，允许 RPA 脚本连接

使用方法：
    python start_browser.py              # 正常启动
    python start_browser.py --clean      # 清理旧进程后启动

注意：
- 首次启动需要手动登录 Maximo
- 登录后浏览器会保持会话，下次启动无需重新登录
- 请保持浏览器窗口打开，关闭后需要重新启动
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


def check_browser_running():
    """检查浏览器是否已在调试模式运行"""
    try:
        response = requests.get(f"http://localhost:{DEBUG_PORT}/json/version", timeout=2)
        return response.status_code == 200
    except:
        return False


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


def start_browser():
    """启动 Edge 浏览器（调试模式）"""
    
    # 检查浏览器是否存在
    if not BROWSER_PATH or not os.path.exists(BROWSER_PATH):
        print(f"❌ 错误：未找到浏览器")
        if BROWSER_PATH:
            print(f"   路径：{BROWSER_PATH}")
        print(f"\n请检查浏览器安装，或修改 config/browser.py 中的 BROWSER_PATH")
        return False
    
    # 检查是否已经运行
    if check_browser_running():
        print(f"✓ 浏览器已在调试模式运行（端口 {DEBUG_PORT}）")
        print(f"  如需重启，请先关闭浏览器")
        return True
    
    # 启动浏览器
    print(f"正在启动 {BROWSER_NAME} 浏览器...")
    print(f"  调试端口：{DEBUG_PORT}")
    print(f"  用户数据：{USER_DATA_DIR}")
    print()
    
    cmd = [
        BROWSER_PATH,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--profile-directory=Default",
        MAXIMO_LOGIN_URL
    ]
    
    try:
        # 启动浏览器（不等待）
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
                print()
                print("=" * 60)
                print("✓ 浏览器启动成功！")
                print("=" * 60)
                print()
                print("下一步：")
                print("  1. 如果浏览器未自动登录，请手动登录 Maximo")
                print("  2. 登录成功后，运行：python start_api.py")
                print()
                print("提示：")
                print("  - 保持浏览器窗口打开")
                print("  - 关闭浏览器后需要重新运行此脚本")
                print()
                return True
            print(".", end="", flush=True)
        
        print(" ❌")
        print()
        print("❌ 浏览器启动超时")
        print("   请检查是否有其他 Edge 进程占用端口")
        return False
        
    except Exception as e:
        print(f"\n❌ 启动失败：{e}")
        return False


if __name__ == "__main__":
    # 检查命令行参数
    clean_mode = "--clean" in sys.argv or "-c" in sys.argv
    
    print()
    print("=" * 60)
    print("Maximo RPA - 浏览器启动工具")
    print("=" * 60)
    print()
    
    # 如果是清理模式，先杀掉所有 Edge 进程
    if clean_mode:
        print("🧹 清理模式：将关闭所有 Edge 进程")
        kill_edge_processes()
        print()
    
    success = start_browser()
    
    if not success:
        print()
        print("💡 提示：")
        print("   1. 可能有其他 Edge 进程占用端口")
        print("   2. 尝试使用清理模式：python start_browser.py --clean")
        print("   3. 或手动关闭所有 Edge 窗口后重试")
        sys.exit(1)
