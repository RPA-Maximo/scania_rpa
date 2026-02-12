"""
检查 Maximo RPA 环境配置

验证所有必要的组件是否正确配置
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

try:
    import requests
    requests_ok = True
except:
    requests_ok = False

try:
    from config.browser import BROWSER_PATH, BROWSER_NAME, DEBUG_PORT
    config_ok = True
except:
    config_ok = False
    BROWSER_PATH = None
    BROWSER_NAME = None
    DEBUG_PORT = None


def print_status(name, status, details=""):
    """打印检查状态"""
    icon = "✓" if status else "✗"
    status_text = "正常" if status else "异常"
    print(f"  {icon} {name}: {status_text}")
    if details:
        print(f"     {details}")


def check_browser():
    """检查浏览器配置"""
    print("\n1. 浏览器配置")
    
    if not config_ok:
        print_status("配置文件", False, "无法加载 config/browser.py")
        return False
    
    if BROWSER_PATH and os.path.exists(BROWSER_PATH):
        print_status("浏览器路径", True, f"{BROWSER_NAME}: {BROWSER_PATH}")
        return True
    else:
        print_status("浏览器路径", False, f"未找到浏览器: {BROWSER_PATH}")
        return False


def check_browser_running():
    """检查浏览器是否运行"""
    print("\n2. 浏览器运行状态")
    
    if not requests_ok:
        print_status("requests 库", False, "请安装: pip install requests")
        return False
    
    try:
        response = requests.get(f"http://localhost:{DEBUG_PORT}/json/version", timeout=2)
        if response.status_code == 200:
            data = response.json()
            browser = data.get('Browser', 'Unknown')
            print_status("浏览器运行", True, f"{browser}")
            return True
        else:
            print_status("浏览器运行", False, "浏览器未启动")
            return False
    except:
        print_status("浏览器运行", False, f"无法连接到端口 {DEBUG_PORT}")
        return False


def check_maximo_page():
    """检查 Maximo 页面"""
    print("\n3. Maximo 页面状态")
    
    if not requests_ok:
        return False
    
    try:
        response = requests.get(f"http://localhost:{DEBUG_PORT}/json", timeout=2)
        pages = response.json()
        
        maximo_pages = []
        login_pages = []
        
        for page in pages:
            url = page.get('url', '').lower()
            if 'maximo' in url and 'login' not in url:
                maximo_pages.append(page.get('url'))
            elif 'login' in url or 'auth.scania' in url:
                login_pages.append(page.get('url'))
        
        if maximo_pages:
            print_status("Maximo 页面", True, f"已登录")
            for url in maximo_pages[:2]:  # 只显示前2个
                print(f"     - {url}")
            return True
        elif login_pages:
            print_status("Maximo 页面", False, "检测到登录页面，请先登录")
            for url in login_pages[:1]:
                print(f"     - {url}")
            return False
        else:
            print_status("Maximo 页面", False, "未找到 Maximo 页面")
            return False
    except:
        print_status("Maximo 页面", False, "无法检查页面状态")
        return False


def check_dependencies():
    """检查 Python 依赖"""
    print("\n4. Python 依赖")
    
    deps = {
        'fastapi': 'FastAPI',
        'uvicorn': 'Uvicorn',
        'playwright': 'Playwright',
        'requests': 'Requests',
    }
    
    all_ok = True
    for module, name in deps.items():
        try:
            __import__(module)
            print_status(name, True)
        except ImportError:
            print_status(name, False, f"请安装: pip install {module}")
            all_ok = False
    
    return all_ok


def check_api_running():
    """检查 API 是否运行"""
    print("\n5. API 服务状态")
    
    if not requests_ok:
        return False
    
    try:
        response = requests.get("http://localhost:8000/health", timeout=2)
        if response.status_code == 200:
            print_status("API 服务", True, "http://localhost:8000")
            return True
        else:
            print_status("API 服务", False, "服务未正常响应")
            return False
    except:
        print_status("API 服务", False, "服务未启动")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("Maximo RPA 环境检查")
    print("=" * 60)
    
    results = {
        '浏览器配置': check_browser(),
        '浏览器运行': check_browser_running(),
        'Maximo 页面': check_maximo_page(),
        'Python 依赖': check_dependencies(),
        'API 服务': check_api_running(),
    }
    
    print("\n" + "=" * 60)
    print("检查结果汇总")
    print("=" * 60)
    
    for name, status in results.items():
        icon = "✓" if status else "✗"
        print(f"  {icon} {name}")
    
    print()
    
    # 给出建议
    if not results['浏览器配置']:
        print("⚠ 建议：检查 config/browser.py 中的浏览器路径")
    
    if not results['浏览器运行']:
        print("⚠ 建议：运行 python start_browser.py 启动浏览器")
    
    if not results['Maximo 页面']:
        print("⚠ 建议：在浏览器中登录 Maximo 系统")
    
    if not results['Python 依赖']:
        print("⚠ 建议：运行 uv sync 或 pip install -r requirements.txt")
    
    if not results['API 服务']:
        print("⚠ 建议：运行 python start_api.py 启动 API 服务")
    
    if all(results.values()):
        print("✓ 所有检查通过！环境配置正常")
        print("\n可以开始使用 Maximo RPA API 了")
        print("  API 文档: http://localhost:8000/docs")
    else:
        print("\n部分检查未通过，请根据上述建议进行修复")
    
    print()


if __name__ == "__main__":
    main()
