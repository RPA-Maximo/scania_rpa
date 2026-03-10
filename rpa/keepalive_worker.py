"""
保活工作脚本
独立进程运行，由 KeepaliveManager 通过 subprocess 调用
从浏览器执行 PO 查询操作，验证 Maximo 会话是否存活

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
from rpa.navigation import (
    navigate_to_receipts_page,
    search_all_po,
    wait_for_po_list
)


async def keepalive_action():
    """
    执行保活动作：
    1. 连接浏览器
    2. 检查/导航到接收查询页面
    3. 执行 PO 搜索
    4. 验证 PO 列表是否加载
    5. 读取 PO 数据条数
    """
    p = None
    try:
        # 连接浏览器
        print("连接浏览器...", file=sys.stderr)
        p, browser, maximo_page, main_frame = await connect_to_browser()
        print("✓ 浏览器已连接", file=sys.stderr)

        # 检查是否在登录页面（外层页面 URL）
        current_url = maximo_page.url.lower()
        if 'login' in current_url or 'auth.scania' in current_url:
            return {
                'success': False,
                'reason': 'session_expired',
                'message': '会话已过期，页面在登录页',
                'url': maximo_page.url,
                'po_count': 0
            }

        # 检查 iframe 本身是否跳转到了登录页
        frame_url = main_frame.url.lower()
        if 'login' in frame_url or 'auth.scania' in frame_url:
            return {
                'success': False,
                'reason': 'session_expired',
                'message': f'会话已过期，iframe 跳转到登录页: {main_frame.url}',
                'url': main_frame.url,
                'po_count': 0
            }

        # 若 main_frame 与外层页面相同，或找不到采购菜单，尝试所有 frame
        # 选出含有 PURCHASE_MODULE_a 的 frame 作为操作目标
        active_frame = main_frame
        found_menu_in_frame = await main_frame.evaluate("""
            () => !!document.querySelector('[id*="PURCHASE_MODULE_a"]')
        """)
        if not found_menu_in_frame:
            print("当前 frame 未找到采购菜单，尝试其他 frames...", file=sys.stderr)
            for frame in maximo_page.frames:
                if frame == main_frame:
                    continue
                try:
                    has_menu = await frame.evaluate("""
                        () => !!document.querySelector('[id*="PURCHASE_MODULE_a"]')
                    """)
                    if has_menu:
                        active_frame = frame
                        print(f"✓ 在 frame [{frame.url[:80]}] 找到采购菜单", file=sys.stderr)
                        break
                except Exception:
                    continue
            else:
                print("⚠ 所有 frames 均未找到采购菜单，继续尝试原 frame", file=sys.stderr)

        # 导航到接收查询页面（从任意页面均可）
        print("检查并导航到接收查询页面...", file=sys.stderr)
        on_search_page = await navigate_to_receipts_page(active_frame)

        if not on_search_page:
            # 尝试诊断：检查页面标题或弹窗
            try:
                page_title = await maximo_page.title()
                frame_count = len(maximo_page.frames)
                frame_urls = [f.url[:60] for f in maximo_page.frames]
            except Exception:
                page_title = "unknown"
                frame_count = 0
                frame_urls = []
            return {
                'success': False,
                'reason': 'navigation_failed',
                'message': (
                    f'无法导航到接收查询页面 | 页面标题: {page_title} | '
                    f'frame数量: {frame_count} | frames: {frame_urls}'
                ),
                'po_count': 0
            }
        print("✓ 已到达接收查询页面", file=sys.stderr)

        # 执行 PO 搜索（触发回车）
        print("执行 PO 搜索...", file=sys.stderr)
        search_success, search_msg = await search_all_po(active_frame)

        if not search_success:
            return {
                'success': False,
                'reason': 'search_failed',
                'message': f'PO 搜索失败: {search_msg}',
                'po_count': 0
            }

        print("✓ PO 搜索已触发", file=sys.stderr)

        # 等待 PO 列表加载
        print("等待 PO 列表加载...", file=sys.stderr)
        list_success, waited = await wait_for_po_list(active_frame)

        if not list_success:
            # 列表没加载出来，可能会话已过期
            # 再次检查是否跳转到了登录页
            current_url = maximo_page.url.lower()
            if 'login' in current_url or 'auth.scania' in current_url:
                return {
                    'success': False,
                    'reason': 'session_expired',
                    'message': '会话已过期，PO 搜索后跳转到登录页',
                    'url': maximo_page.url,
                    'po_count': 0
                }
            return {
                'success': False,
                'reason': 'list_timeout',
                'message': f'PO 列表加载超时 (等待了 {waited:.1f}s)',
                'po_count': 0
            }

        # 读取 PO 列表数据条数
        po_count = await active_frame.evaluate("""
            () => {
                const spans = document.querySelectorAll('span.text.label.anchor');
                return spans.length;
            }
        """)

        print(f"✓ PO 列表已加载，共 {po_count} 条数据 (等待了 {waited:.1f}s)", file=sys.stderr)

        return {
            'success': True,
            'reason': 'ok',
            'message': f'保活成功，PO 列表 {po_count} 条',
            'po_count': po_count,
            'wait_time': round(waited, 1)
        }

    except Exception as e:
        error_msg = str(e)
        # 检查是否是连接失败（浏览器未启动）
        if '无法连接到浏览器' in error_msg or 'connect' in error_msg.lower():
            return {
                'success': False,
                'reason': 'browser_disconnected',
                'message': f'浏览器未启动或无法连接: {error_msg}',
                'po_count': 0
            }
        # 检查是否是会话过期
        if '登录' in error_msg or 'login' in error_msg.lower():
            return {
                'success': False,
                'reason': 'session_expired',
                'message': f'会话已过期: {error_msg}',
                'po_count': 0
            }
        return {
            'success': False,
            'reason': 'unknown_error',
            'message': f'保活异常: {error_msg}',
            'po_count': 0
        }
    finally:
        if p:
            try:
                await p.stop()
                print("✓ 浏览器连接已关闭", file=sys.stderr)
            except Exception:
                pass


async def main():
    """主函数"""
    # 重定向 stdout 到 stderr，保留原始 stdout 用于输出 JSON
    original_stdout = sys.stdout
    sys.stdout = sys.stderr

    try:
        result = await keepalive_action()

        # 恢复 stdout 并输出 JSON 结果
        sys.stdout = original_stdout
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0 if result['success'] else 1)

    except Exception as e:
        sys.stdout = original_stdout
        error_result = {
            'success': False,
            'reason': 'fatal_error',
            'message': f'保活脚本致命错误: {str(e)}',
            'po_count': 0
        }
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
