"""
检查 Maximo RPA 环境配置

验证所有必要的组件是否正确配置
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    import requests
    requests_ok = True
except Exception:
    requests_ok = False

try:
    from config.browser import BROWSER_PATH, BROWSER_NAME, MAXIMO_SHELL_URL
    config_ok = True
except Exception:
    config_ok = False
    BROWSER_PATH = None
    BROWSER_NAME = None
    MAXIMO_SHELL_URL = "https://main.manage.scania-acc.suite.maximo.com/maximo/oslc/graphite/manage-shell"


def print_status(name, status, details=""):
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


def check_maximo_reachable():
    """检查 Maximo 服务器是否可访问"""
    print("\n2. Maximo 服务器连通性")

    if not requests_ok:
        print_status("requests 库", False, "请安装: pip install requests")
        return False

    try:
        response = requests.get(MAXIMO_SHELL_URL, timeout=10, verify=False, allow_redirects=True)
        # 200 表示已登录；302/303 通常重定向到登录页，也说明服务器可达
        reachable = response.status_code in (200, 302, 303, 401, 403)
        if reachable:
            if "login" in response.url.lower() or "auth.scania" in response.url.lower():
                print_status("Maximo 服务器", True, "可访问（需登录）")
            else:
                print_status("Maximo 服务器", True, f"已登录 ({response.status_code})")
        else:
            print_status("Maximo 服务器", False, f"HTTP {response.status_code}")
        return reachable
    except requests.exceptions.SSLError:
        # SSL 错误说明服务器可达但证书问题，视为可访问
        print_status("Maximo 服务器", True, "可访问（SSL 证书警告）")
        return True
    except Exception as e:
        print_status("Maximo 服务器", False, f"无法连接: {e}")
        return False


def check_dependencies():
    """检查 Python 依赖"""
    print("\n3. Python 依赖")

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
    print("\n4. API 服务状态")

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
    except Exception:
        print_status("API 服务", False, "服务未启动")
        return False


def main():
    print("=" * 60)
    print("Maximo RPA 环境检查")
    print("=" * 60)

    results = {
        '浏览器配置':     check_browser(),
        'Maximo 连通性':  check_maximo_reachable(),
        'Python 依赖':    check_dependencies(),
        'API 服务':       check_api_running(),
    }

    print("\n" + "=" * 60)
    print("检查结果汇总")
    print("=" * 60)

    for name, status in results.items():
        icon = "✓" if status else "✗"
        print(f"  {icon} {name}")

    print()

    if not results['浏览器配置']:
        print("⚠ 建议：检查 config/browser.py 中的浏览器路径")
    if not results['Maximo 连通性']:
        print(f"⚠ 建议：确认可访问 {MAXIMO_SHELL_URL}")
    if not results['Python 依赖']:
        print("⚠ 建议：运行 uv sync 或 pip install -r requirements.txt")
    if not results['API 服务']:
        print("⚠ 建议：运行 python start_api.py 启动 API 服务")

    if all(results.values()):
        print("✓ 所有检查通过！环境配置正常")
        print("\n下一步：python start_api.py")
        print("  API 文档: http://localhost:8000/docs")
    else:
        print("\n部分检查未通过，请根据上述建议进行修复")

    print()


if __name__ == "__main__":
    main()
