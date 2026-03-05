# Scania RPA 变更记录

## 2026-03-05 — 爬虫自动化 & PO 增量同步

### 一、问题背景

| 问题 | 原因 | 影响 |
|------|------|------|
| 每次爬取前需手动修改 `config/响应标头.txt` | 认证 Cookie/CSRF Token 过期后无 API 更新方式 | 完全依赖人工操作 |
| 批量抓取报错 `Missing dependencies for SOCKS support` | `PROXY_ENABLED=True` 使用 SOCKS5，但 `PySocks` 未安装 | 所有爬虫请求失败 |
| `uv sync` 无法完成 | `playwright==1.58.0` 在国内镜像源下载失败 | FastAPI 未安装，新路由无法加载 |

---

### 二、新增文件

```
config/
├── auth_manager.py        # 认证状态单例管理器
└── settings_manager.py    # 运行时设置单例（代理、请求参数）

api/routers/
├── __init__.py
├── auth.py                # 认证管理 API 路由
├── scraper.py             # 爬虫触发 API 路由
├── settings.py            # 运行时设置 API 路由
└── sync.py                # PO 增量同步管理路由

src/sync/
├── db_init.py             # 数据库列安全迁移（MySQL 5.7+ 兼容）
└── po_sync_service.py     # PO 增量同步服务 + 5分钟调度器
```

---

### 三、修改文件

| 文件 | 变更内容 |
|------|---------|
| `config/auth.py` | `get_maximo_auth()` 委托给 `auth_manager` 单例 |
| `config/settings.py` | `_build_proxies()` 自动检测 PySocks，缺失时降级直连 |
| `src/utils/mapper.py` | 新增 `VENDOR_FIELD_CANDIDATES`、`SHIPTO_FIELD_CANDIDATES`；子表映射增加 `catalogcode`、`newitemdesc`、`location` |
| `src/sync/po_header.py` | `map_header_data()` 新增供应商扩展字段和收货方字段映射 |
| `src/fetcher/po_fetcher.py` | `PROXIES` → `settings_manager.get_proxies()`（支持运行时切换） |
| `api/main.py` | 注册四个新路由；lifespan 中启动/停止 `po_sync_scheduler` |
| `pyproject.toml` | playwright 版本放宽至 `>=1.49.0`；新增 `PySocks>=1.7.1` |

---

### 四、功能详解

#### 4.1 认证自动化

> **再也不需要手动修改 `响应标头.txt`**

**操作步骤：**
1. 浏览器登录 Maximo，打开 DevTools（F12）→ Network
2. 找到 `maximo.jsp` 请求 → 右键 → **Copy as cURL (bash)**
3. 调用 API：

```http
POST /api/auth/curl
Content-Type: application/json

{
  "curl_text": "curl 'https://...' -b 'LtpaToken2=xxx; ...' --data-raw 'csrftoken=abc123'"
}
```

认证信息写入内存并同步覆盖 `config/响应标头.txt`，服务重启后自动恢复。

**认证相关接口：**

| 接口 | 说明 |
|------|------|
| `POST /api/auth/curl` | 粘贴 cURL (bash) 命令更新认证 |
| `POST /api/auth/fields` | 直接提交 cookie / csrf_token 字段 |
| `GET /api/auth/status` | 查询当前认证状态 |

---

#### 4.2 爬虫 API 化

> **无需命令行，直接通过 Swagger UI 触发爬取**

**接口：**

| 接口 | 说明 | 主要参数 |
|------|------|---------|
| `POST /api/scraper/po` | 抓取采购订单 | `po_numbers`、`status_filter`、`max_pages` |
| `POST /api/scraper/inventory` | 抓取库存数据 | `max_pages`、`status_filter`、`item_num_min`、`order_by` |

示例——抓取 APPR 状态前 3 页 PO：
```json
{ "status_filter": "APPR", "max_pages": 3, "page_size": 20 }
```

---

#### 4.3 代理运行时配置

> **无需重启服务即可切换代理**

**接口：**

| 接口 | 说明 |
|------|------|
| `GET /api/settings` | 查看所有运行时设置 |
| `GET /api/settings/proxy` | 查看代理状态（含 PySocks 可用性检测） |
| `POST /api/settings/proxy` | 切换代理开关/地址/端口/协议 |
| `POST /api/settings/request` | 调整请求延迟/SSL/重试次数 |

关闭代理（直连）：
```json
POST /api/settings/proxy
{ "enabled": false }
```

切换为 HTTP 代理：
```json
POST /api/settings/proxy
{ "enabled": true, "host": "127.0.0.1", "port": 7890, "protocol": "http" }
```

---

#### 4.4 PO 增量同步

> **服务启动后自动每 5 分钟同步一次，已存在的 PO 跳过**

**同步字段（主表 `purchase_order`）：**

| 字段组 | 字段 |
|--------|------|
| 基础 | PO号、用户单号、订单日期、状态 |
| 供应商 | 编号、名称、地址、邮编、城市、联系人、电话、邮件 |
| 收货方 | 公司名称、街道地址（address1+address2合并）、邮编、城市、国家（固定 China） |
| 留空字段 | 斯堪尼亚客户代码、联系人、联系电话、电子邮件、接收人（业务要求） |

**同步字段（子表 `purchase_order_bd`）：**

| Maximo 字段 | 数据库列 | 说明 |
|------------|---------|------|
| `itemnum` | `sku` | 物料编号（查 material 表） |
| `description` | `sku_names` | 物料名称 |
| `catalogcode` | `model_num` | 型号 |
| `newitemdesc` | `size_info` | 尺寸/规格 |
| `orderqty` | `qty` | 数量 |
| `orderunit` | `ordering_unit` | 订购单位 |
| `location` | `target_container` | 目标货柜 |
| `storeloc` | `warehouse` | 目标仓库（查 warehouse 表） |

**增量逻辑：**
```
抓取 Maximo PO → 查 purchase_order.code = ponum
  ├── 已存在 → 跳过
  └── 不存在 → 物料验证 → 插入主表 → 插入明细
```

**同步管理接口：**

| 接口 | 说明 |
|------|------|
| `GET /api/sync/po/status` | 查看同步状态、上次同步结果、当前配置 |
| `POST /api/sync/po/trigger` | 手动立即触发一次增量同步 |
| `PUT /api/sync/po/config` | 修改同步参数（状态筛选/页数/每页条数） |
| `PUT /api/sync/po/interval` | 修改同步间隔（默认 5 分钟） |
| `POST /api/sync/po/stop` | 暂停自动同步 |
| `POST /api/sync/po/start` | 恢复自动同步 |

**数据库兼容性：** 首次同步时自动执行 `ALTER TABLE ADD COLUMN`（MySQL 5.7+ 兼容，已有列不重复添加）。

---

### 五、快速启动

```bash
# 安装依赖
uv sync

# 启动服务
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 访问 Swagger UI
# http://localhost:8000/docs
```

**首次使用流程：**
```
1. 登录 Maximo → Copy as cURL (bash) → POST /api/auth/curl
2. 检查认证: GET /api/auth/status
3. 手动触发同步: POST /api/sync/po/trigger
4. 查看同步结果: GET /api/sync/po/status
```

---

### 六、日志文件

| 日志 | 路径 | 内容 |
|------|------|------|
| PO 同步日志 | `data/logs/po_sync.log` | 每次同步的新增/跳过数量、耗时 |
| 保活日志 | `data/logs/keepalive.log` | Maximo 会话保活记录 |
