"""
保活工作脚本
独立进程运行，由 KeepaliveManager 通过 subprocess 调用
通过浏览器内 JS fetch 发一次轻量 OSLC 请求，验证 Maximo 会话是否存活

输出 JSON 结果到 stdout
"""
import asyncio
import sys
import json
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Windows 平台设置事件循环策略
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from rpa.browser import connect_to_browser


# 轻量保活请求：whoami 只返回当前用户信息，不走数据库，响应极快（<1s）
# 备用：/maximo/oslc/os（对象结构元数据，同样无 DB 查询）
_PING_URL = '/maximo/oslc/whoami'
_FETCH_TIMEOUT_MS = 10000   # JS fetch 超时 10s（whoami 应在 1s 内响应）


async def keepalive_action():
    """
    执行保活动作：
    1. 通过 CDP 连接已启动的浏览器
    2. 检查是否在登录页
    3. 在 Maximo 页内用 fetch() 发一次 OSLC 轻量请求（same-origin，cookies 自动携带）
    4. 根据 HTTP 状态码判断 session 是否存活
    """
    p = None
    try:
        print("连接浏览器...", file=sys.stderr)
        p, browser, maximo_page, _ = await connect_to_browser()
        print("✓ 浏览器已连接", file=sys.stderr)

        # 检查是否跳转到登录页
        current_url = maximo_page.url.lower()
        if 'login' in current_url or 'auth.scania' in current_url:
            return {
                'success': False,
                'reason': 'session_expired',
                'message': f'会话已过期，页面在登录页: {maximo_page.url}',
                'http_status': 0,
            }

        # 在浏览器页内发 fetch，same-origin 自动带 cookie，无需额外认证
        # AbortController 限时 10s，whoami 端点无 DB 查询应极速响应
        print(f"发送保活 ping: {_PING_URL}", file=sys.stderr)
        fetch_result = await maximo_page.evaluate(f"""
            () => {{
                const ctrl = new AbortController();
                const tid = setTimeout(() => ctrl.abort(), {_FETCH_TIMEOUT_MS});
                return fetch('{_PING_URL}', {{credentials: 'include', signal: ctrl.signal}})
                    .then(r => {{ clearTimeout(tid); return {{status: r.status, ok: r.ok}}; }})
                    .catch(e => {{ clearTimeout(tid); return {{status: 0, ok: false, error: e.message}}; }});
            }}
        """)

        status = fetch_result.get('status', 0)
        ok = fetch_result.get('ok', False)
        fetch_error = fetch_result.get('error')

        print(f"fetch 结果: status={status}, ok={ok}", file=sys.stderr)

        if ok:
            return {
                'success': True,
                'reason': 'ok',
                'message': f'保活成功 (HTTP {status})',
                'http_status': status,
            }
        elif status in (401, 403):
            return {
                'success': False,
                'reason': 'session_expired',
                'message': f'会话已过期 (HTTP {status})',
                'http_status': status,
            }
        elif status == 0 and fetch_error:
            # AbortController 触发时 error message 含 "aborted"
            reason = 'fetch_timeout' if 'abort' in str(fetch_error).lower() else 'fetch_error'
            return {
                'success': False,
                'reason': reason,
                'message': f'fetch {"超时(>10s)" if reason == "fetch_timeout" else "异常"}: {fetch_error}',
                'http_status': 0,
            }
        else:
            return {
                'success': False,
                'reason': 'unexpected_status',
                'message': f'意外的 HTTP 状态码: {status}',
                'http_status': status,
            }

    except Exception as e:
        error_msg = str(e)
        if '无法连接到浏览器' in error_msg or 'connect' in error_msg.lower():
            return {
                'success': False,
                'reason': 'browser_disconnected',
                'message': f'浏览器未启动或无法连接: {error_msg}',
                'http_status': 0,
            }
        return {
            'success': False,
            'reason': 'unknown_error',
            'message': f'保活异常: {error_msg}',
            'http_status': 0,
        }
    finally:
        if p:
            try:
                await p.stop()
            except Exception:
                pass


async def main():
    """主函数"""
    original_stdout = sys.stdout
    sys.stdout = sys.stderr

    try:
        result = await keepalive_action()

        sys.stdout = original_stdout
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0 if result['success'] else 1)

    except Exception as e:
        sys.stdout = original_stdout
        error_result = {
            'success': False,
            'reason': 'fatal_error',
            'message': f'保活脚本致命错误: {str(e)}',
            'http_status': 0,
        }
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
