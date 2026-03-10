"""
全量集成测试脚本 - Scania RPA / Maximo 同步服务
=================================================

覆盖范围：
  1. 配置项检查（settings.py / settings_manager）
  2. 数据库连通性 + 核心业务表
  3. 认证信息解析（auth / auth_manager）
  4. Maximo OSLC API 连通性（需有效 Cookie）
  5. FastAPI 本地服务端点（需先启动 start_api.py）
     - 基础: GET /, /health, /api/keepalive/status
     - 认证: GET /api/auth/status
     - 设置: GET /api/settings, /api/settings/proxy
     - PO同步: GET /api/sync/po/status
     - 出库单: GET /api/mr
     - 物料: GET /api/items, /api/items/sync/status
     - 供应商: GET /api/vendor
     - 仓库: GET /api/warehouse, /api/warehouse/bins
     - 物料仓位: GET /api/material-location
  6. 设置写操作（非破坏性）

用法：
  python tests/test_full.py                # 全量
  python tests/test_full.py --skip-maximo  # 跳过 Maximo API
  python tests/test_full.py --skip-api     # 跳过本地 FastAPI
  python tests/test_full.py --api-url http://192.168.1.100:8000
"""

import sys
import argparse
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

PASS = "✓"
FAIL = "✗"
SKIP = "○"
WARN = "!"

_results = []   # (section, name, ok, detail)


def _record(section: str, name: str, ok: bool, detail: str = ""):
    _results.append((section, name, ok, detail))
    mark = PASS if ok else FAIL
    msg = f"  [{mark}] {name}"
    if detail:
        msg += f"  →  {detail}"
    print(msg)


def section(title: str):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def summary():
    total = len(_results)
    passed = sum(1 for _, _, ok, _ in _results if ok)
    failed = total - passed
    print(f"\n{'=' * 70}")
    print(f"  测试总结: {passed}/{total} 通过  |  {failed} 失败")
    print(f"{'=' * 70}")
    if failed:
        print("  失败项:")
        for sec, name, ok, detail in _results:
            if not ok:
                print(f"    [{sec}] {name}  →  {detail or '（无详情）'}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: 配置项检查
# ─────────────────────────────────────────────────────────────────────────────

def test_settings():
    section("1. 配置项检查")
    SEC = "配置"

    try:
        from config import settings as S

        # 1-1 Maximo URL
        ok = bool(S.MAXIMO_BASE_URL and "maximo" in S.MAXIMO_BASE_URL)
        _record(SEC, "MAXIMO_BASE_URL", ok, S.MAXIMO_BASE_URL if ok else "未设置或格式异常")

        # 1-2 代理设置
        _record(SEC, f"PROXY_ENABLED={S.PROXY_ENABLED}", True,
                f"{S.PROXY_PROTOCOL}://{S.PROXY_HOST}:{S.PROXY_PORT}" if S.PROXY_ENABLED else "直连模式")

        # 1-3 SSL
        _record(SEC, f"VERIFY_SSL={S.VERIFY_SSL}", True,
                "已关闭 SSL 验证（测试环境常见）" if not S.VERIFY_SSL else "启用 SSL 验证")

        # 1-4 数据目录
        for d in [S.RAW_DATA_DIR, S.PROCESSED_DATA_DIR, S.LOGS_DIR]:
            ok = d.exists()
            _record(SEC, f"目录存在: {d.relative_to(PROJECT_ROOT)}", ok,
                    "" if ok else "目录不存在")

    except Exception as e:
        _record(SEC, "导入 config.settings", False, str(e))

    try:
        from config.settings_manager import settings_manager
        s = settings_manager.get_all_settings()
        _record(SEC, "settings_manager.get_all_settings()", True,
                f"代理={s.get('proxy',{}).get('enabled')}, 延迟={s.get('request',{}).get('delay')}s")
    except Exception as e:
        _record(SEC, "settings_manager", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: 数据库连通性
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_TABLES = [
    "purchase_order",
    "purchase_order_bd",
    "material",
    "mr_header",
    "mr_detail",
    "bin_inventory",
    "warehouse",
    "warehouse_bin",
    "vendor",
    "material_location",
]


def test_database():
    section("2. 数据库连通性")
    SEC = "数据库"

    try:
        from src.utils.db import get_connection
        conn = get_connection()
        _record(SEC, "get_connection()", True)
    except Exception as e:
        _record(SEC, "get_connection()", False, str(e))
        return

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        ver = cursor.fetchone()[0]
        _record(SEC, "MySQL 版本", True, ver)

        cursor.execute("SHOW TABLES")
        existing = {t[0].lower() for t in cursor.fetchall()}
        _record(SEC, f"共发现 {len(existing)} 张表", True)

        for tbl in REQUIRED_TABLES:
            ok = tbl.lower() in existing
            _record(SEC, f"表: {tbl}", ok, "" if ok else "表不存在（可能尚未初始化）")

        cursor.close()
    except Exception as e:
        _record(SEC, "查询表结构", False, str(e))
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: 认证信息解析
# ─────────────────────────────────────────────────────────────────────────────

def test_auth():
    section("3. 认证信息解析")
    SEC = "认证"

    # 3-1 parse_curl_file
    try:
        from config.auth import parse_curl_file
        info = parse_curl_file()
        if info:
            _record(SEC, "parse_curl_file()", True,
                    f"Cookie {len(info['cookie'])} 字符, CSRF={info['csrf_token'][:8]}...")
        else:
            _record(SEC, "parse_curl_file()", False,
                    "未找到 config/响应标头.txt，请提前导出 cURL 或通过 POST /api/auth/curl 更新")
    except Exception as e:
        _record(SEC, "parse_curl_file()", False, str(e))

    # 3-2 get_maximo_auth
    try:
        from config.auth import get_maximo_auth
        auth = get_maximo_auth()
        _record(SEC, "get_maximo_auth()", True,
                f"Cookie {len(auth['cookie'])} 字符")
    except ValueError as e:
        _record(SEC, "get_maximo_auth()", False, str(e))
    except Exception as e:
        _record(SEC, "get_maximo_auth()", False, str(e))

    # 3-3 auth_manager
    try:
        from config.auth_manager import auth_manager
        status = auth_manager.get_status()
        ok = status.get("authenticated", False)
        _record(SEC, "auth_manager.get_status()", ok,
                f"authenticated={ok}, source={status.get('source','?')}")
    except Exception as e:
        _record(SEC, "auth_manager.get_status()", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: Maximo OSLC API 连通性
# ─────────────────────────────────────────────────────────────────────────────

def _maximo_get(url, headers, params, label, sec, proxies, verify):
    """通用 Maximo GET 测试，返回 (ok, members)"""
    try:
        resp = requests.get(url, headers=headers, params=params,
                            proxies=proxies, verify=verify, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            members = data.get("member", data.get("rdfs:member", []))
            total = data.get("responseInfo", {}).get("totalCount", len(members))
            _record(sec, label, True, f"HTTP 200, 共 {total} 条, 本页 {len(members)} 条")
            return True, members
        elif resp.status_code == 401:
            _record(sec, label, False, "401 认证失败，请更新 Cookie")
        elif resp.status_code == 403:
            _record(sec, label, False, "403 权限不足")
        elif resp.status_code == 404:
            _record(sec, label, False, "404 端点不存在")
        else:
            _record(sec, label, False, f"HTTP {resp.status_code}: {resp.text[:100]}")
    except requests.exceptions.ConnectionError as e:
        _record(sec, label, False, f"连接失败: {e}")
    except Exception as e:
        _record(sec, label, False, str(e))
    return False, []


def test_maximo_api():
    section("4. Maximo OSLC API 连通性")
    SEC = "Maximo"

    try:
        from config.auth import get_maximo_auth
        from config import DEFAULT_HEADERS, VERIFY_SSL
        from config.settings import MAXIMO_BASE_URL
        from config.settings_manager import settings_manager
        auth = get_maximo_auth()
    except ValueError as e:
        _record(SEC, "获取认证信息", False, str(e))
        print(f"  {SKIP} 跳过 Maximo API 测试（无认证信息）")
        return
    except Exception as e:
        _record(SEC, "获取认证信息", False, str(e))
        return

    proxies = settings_manager.get_proxies()
    verify = VERIFY_SSL
    headers = {
        **DEFAULT_HEADERS,
        "Cookie": auth["cookie"],
        "x-csrf-token": auth["csrf_token"],
    }
    base = MAXIMO_BASE_URL + "/oslc/os"

    ENDPOINTS = [
        ("MXAPIPO",          {"oslc.select": "ponum,status", "oslc.pageSize": 5},
         "采购订单 MXAPIPO"),
        ("MXAPIINVENTORY",   {"oslc.select": "itemnum,location,curbaltotal", "oslc.pageSize": 5},
         "库存 MXAPIINVENTORY"),
        ("MXAPIITEM",        {"oslc.select": "itemnum,description,status", "oslc.pageSize": 5,
                              "oslc.where": 'status="ACTIVE"'},
         "物料主数据 MXAPIITEM"),
        ("MXAPIINVUSE",      {"oslc.select": "usersiteid,issuetype,status", "oslc.pageSize": 5},
         "出库单 MXAPIINVUSE"),
        ("MXAPICOMPANY",     {"oslc.select": "company,name,type", "oslc.pageSize": 5},
         "供应商 MXAPICOMPANY"),
        ("MXAPILOCATION",    {"oslc.select": "location,description,siteid", "oslc.pageSize": 5,
                              "oslc.where": 'type="COURIER" or type="STOREROOM"'},
         "仓库 MXAPILOCATION"),
    ]

    for endpoint, params, label in ENDPOINTS:
        url = f"{base}/{endpoint}"
        _maximo_get(url, headers, params, label, SEC, proxies, verify)


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: FastAPI 本地服务端点
# ─────────────────────────────────────────────────────────────────────────────

def _api_get(session, base_url, path, label, sec, params=None, expected_keys=None):
    url = base_url.rstrip("/") + path
    try:
        resp = session.get(url, params=params, timeout=10)
        ok = resp.status_code == 200
        if ok and expected_keys:
            data = resp.json()
            missing = [k for k in expected_keys if k not in data]
            if missing:
                _record(sec, label, False, f"HTTP 200 但响应缺少字段: {missing}")
                return False, {}
        _record(sec, label, ok,
                f"HTTP {resp.status_code}" + ("" if ok else f": {resp.text[:120]}"))
        return ok, resp.json() if ok else {}
    except requests.exceptions.ConnectionError:
        _record(sec, label, False, f"无法连接 {base_url}，请先启动 start_api.py")
        return False, {}
    except Exception as e:
        _record(sec, label, False, str(e))
        return False, {}


def _api_post(session, base_url, path, label, sec, json_body=None):
    url = base_url.rstrip("/") + path
    try:
        resp = session.post(url, json=json_body or {}, timeout=10)
        ok = resp.status_code in (200, 201)
        _record(sec, label, ok,
                f"HTTP {resp.status_code}" + ("" if ok else f": {resp.text[:120]}"))
        return ok, resp.json() if resp.text else {}
    except requests.exceptions.ConnectionError:
        _record(sec, label, False, f"无法连接 {base_url}")
        return False, {}
    except Exception as e:
        _record(sec, label, False, str(e))
        return False, {}


def test_fastapi(api_url: str):
    section(f"5. FastAPI 本地服务端点  ({api_url})")
    SEC = "FastAPI"

    session = requests.Session()

    # ── 5.1 基础端点 ─────────────────────────────────────────────────────────
    ok, data = _api_get(session, api_url, "/", "GET /  (根路径)", SEC,
                        expected_keys=["service", "version"])
    if not ok:
        print(f"\n  {SKIP} 服务不可达，跳过其余 FastAPI 测试")
        return

    _api_get(session, api_url, "/health", "GET /health", SEC,
             expected_keys=["status"])

    _api_get(session, api_url, "/api/keepalive/status", "GET /api/keepalive/status", SEC,
             expected_keys=["running"])

    # ── 5.2 认证状态 ─────────────────────────────────────────────────────────
    _api_get(session, api_url, "/api/auth/status", "GET /api/auth/status", SEC)

    # ── 5.3 运行时设置 ───────────────────────────────────────────────────────
    _api_get(session, api_url, "/api/settings", "GET /api/settings", SEC,
             expected_keys=["proxy", "request"])

    _api_get(session, api_url, "/api/settings/proxy", "GET /api/settings/proxy", SEC,
             expected_keys=["enabled"])

    # ── 5.4 PO 增量同步 ──────────────────────────────────────────────────────
    _api_get(session, api_url, "/api/sync/po/status", "GET /api/sync/po/status", SEC,
             expected_keys=["scheduler", "service"])

    # ── 5.5 出库单 MR ────────────────────────────────────────────────────────
    _api_get(session, api_url, "/api/mr", "GET /api/mr", SEC,
             params={"page": 1, "page_size": 10})

    _api_get(session, api_url, "/api/mr/inventory/bins", "GET /api/mr/inventory/bins", SEC,
             params={"page": 1, "page_size": 10})

    # ── 5.6 物料主数据 ───────────────────────────────────────────────────────
    _api_get(session, api_url, "/api/items", "GET /api/items", SEC,
             params={"page": 1, "page_size": 10})

    _api_get(session, api_url, "/api/items/sync/status", "GET /api/items/sync/status", SEC)

    # ── 5.7 供应商 ───────────────────────────────────────────────────────────
    _api_get(session, api_url, "/api/vendor", "GET /api/vendor", SEC,
             params={"page": 1, "page_size": 10})

    # ── 5.8 仓库 ─────────────────────────────────────────────────────────────
    _api_get(session, api_url, "/api/warehouse", "GET /api/warehouse", SEC,
             params={"page": 1, "page_size": 10})

    _api_get(session, api_url, "/api/warehouse/bins", "GET /api/warehouse/bins", SEC,
             params={"page": 1, "page_size": 10})

    # ── 5.9 物料仓位映射 ─────────────────────────────────────────────────────
    _api_get(session, api_url, "/api/material-location",
             "GET /api/material-location", SEC,
             params={"page": 1, "page_size": 10})

    # ── 5.10 Swagger 文档可达 ────────────────────────────────────────────────
    try:
        resp = session.get(api_url.rstrip("/") + "/docs", timeout=5)
        _record(SEC, "GET /docs (Swagger UI)", resp.status_code == 200,
                f"HTTP {resp.status_code}")
    except Exception as e:
        _record(SEC, "GET /docs (Swagger UI)", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 6: 设置写操作（非破坏性）
# ─────────────────────────────────────────────────────────────────────────────

def test_settings_write(api_url: str):
    section("6. 设置写操作（非破坏性回写）")
    SEC = "设置写"

    session = requests.Session()

    # 先获取当前代理状态，再原样写回（幂等）
    try:
        resp = session.get(api_url.rstrip("/") + "/api/settings/proxy", timeout=5)
        if resp.status_code != 200:
            _record(SEC, "获取当前代理设置", False, f"HTTP {resp.status_code}")
            return
        proxy = resp.json()
    except requests.exceptions.ConnectionError:
        _record(SEC, "服务连通性", False, "无法连接，跳过写操作测试")
        return
    except Exception as e:
        _record(SEC, "获取当前代理设置", False, str(e))
        return

    _record(SEC, "获取当前代理设置", True,
            f"enabled={proxy.get('enabled')}, host={proxy.get('host')}")

    # 原样写回（验证 PUT 接口正常工作）
    payload = {
        "enabled": proxy.get("enabled", False),
        "host": proxy.get("host", "127.0.0.1"),
        "port": proxy.get("port", 10820),
        "protocol": proxy.get("protocol", "socks5"),
    }
    try:
        resp = session.post(api_url.rstrip("/") + "/api/settings/proxy",
                            json=payload, timeout=5)
        ok = resp.status_code == 200
        _record(SEC, "POST /api/settings/proxy（幂等回写）", ok,
                f"HTTP {resp.status_code}" + ("" if ok else f": {resp.text[:80]}"))
    except Exception as e:
        _record(SEC, "POST /api/settings/proxy（幂等回写）", False, str(e))

    # 修改同步间隔为当前值（幂等）
    try:
        resp = session.get(api_url.rstrip("/") + "/api/sync/po/status", timeout=5)
        if resp.status_code == 200:
            interval_s = resp.json().get("scheduler", {}).get("interval_seconds", 300)
            interval_m = interval_s / 60
            resp2 = session.put(api_url.rstrip("/") + "/api/sync/po/interval",
                                json={"interval_minutes": interval_m}, timeout=5)
            ok2 = resp2.status_code == 200
            _record(SEC, f"PUT /api/sync/po/interval（幂等回写 {interval_m}min）", ok2,
                    f"HTTP {resp2.status_code}")
    except Exception as e:
        _record(SEC, "PUT /api/sync/po/interval", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Scania RPA 全量集成测试")
    parser.add_argument("--skip-maximo", action="store_true",
                        help="跳过 Maximo OSLC API 测试（无 VPN / 无认证时使用）")
    parser.add_argument("--skip-api", action="store_true",
                        help="跳过本地 FastAPI 测试（服务未启动时使用）")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000",
                        help="FastAPI 服务地址（默认 http://127.0.0.1:8000）")
    return parser.parse_args()


def main():
    args = parse_args()

    print("\n" + "=" * 70)
    print("  Scania RPA / Maximo 同步服务  全量集成测试")
    print("=" * 70)
    print(f"  项目根目录: {PROJECT_ROOT}")
    print(f"  FastAPI 地址: {args.api_url}")
    if args.skip_maximo:
        print(f"  [--skip-maximo] 跳过 Maximo API 测试")
    if args.skip_api:
        print(f"  [--skip-api] 跳过本地 FastAPI 测试")

    test_settings()
    test_database()
    test_auth()

    if not args.skip_maximo:
        test_maximo_api()
    else:
        section("4. Maximo OSLC API 连通性")
        print(f"  {SKIP} 已跳过（--skip-maximo）")

    if not args.skip_api:
        test_fastapi(args.api_url)
        test_settings_write(args.api_url)
    else:
        section("5. FastAPI 本地服务端点")
        print(f"  {SKIP} 已跳过（--skip-api）")
        section("6. 设置写操作")
        print(f"  {SKIP} 已跳过（--skip-api）")

    summary()


if __name__ == "__main__":
    main()
