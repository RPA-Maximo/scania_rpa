# Scania RPA — Maximo 入库 & 数据同步服务

基于 **FastAPI + Playwright** 构建的 Maximo ERP 自动化平台，集成浏览器 RPA 入库操作、多维度数据增量同步（PO / MR / 物料 / 仓库 / 供应商）与 WMS 对接能力。

---

## 目录

- [功能模块](#功能模块)
- [项目结构](#项目结构)
- [环境要求](#环境要求)
- [部署步骤](#部署步骤)
- [启动服务](#启动服务)
- [API 接口总览](#api-接口总览)
- [认证配置](#认证配置)
- [代理设置](#代理设置)
- [测试脚本](#测试脚本)
- [常见问题](#常见问题)

---

## 功能模块

### 1. 浏览器 RPA — 自动入库

通过 Playwright 连接调试模式下的 Edge/Chrome 浏览器，自动完成 Maximo 入库单的填写与保存。

- 支持按 **PO 行号** 或 **项目号** 定位入库行
- 支持批量入库（一次请求处理多行）
- 支持浮点数量（如 `2.5` 件）和自定义备注
- `auto_save=false` 模式：仅填写不提交，便于人工复核
- 会话保活（Keep-alive）：每 8 分钟自动执行 PO 查询，防止 Maximo 超时退出

### 2. PO 采购订单同步

从 Maximo `MXAPIPO` 增量拉取采购订单，同步至本地 MySQL 数据库（`purchase_order` / `purchase_order_bd`）。

- **自动调度**：每 5 分钟执行一次（可调整间隔）
- **状态过滤**：可限定 `APPR`（已批准）等状态
- **物料自动补全**：PO 中出现的新物料号自动写入 `material` 表
- **Excel 导出**：`GET /api/sync/po/export` 下载完整 PO 报表

### 3. 出库单（MR）管理

对接 Maximo `MXAPIINVUSE`，同步物料需求单（出库单）至 WMS，并支持执行出库和回传。

- FIFO 先进先出校验：按货柜入库时间自动分配出库仓位
- 出库回传 Maximo：写入流水号、更新状态
- 货柜库存同步（`MXAPIINVBAL` / `MXAPIINVENTORY`）
- 库存 Excel 导出

### 4. 物料主数据同步

从 Maximo `MXAPIITEM` 同步物料档案至 `material` 表。

- **全量**：不限时间，适合首次初始化
- **增量**：仅同步昨日以来变更的物料
- **每日自动同步**：凌晨 0 点触发全量刷新
- 库存成本同步（`MXAPIINVCOST`）及库存报表导出

### 5. 仓库 & 货柜管理

同步 Maximo 仓库（`MXAPILOCATION`）和货柜（Bin）信息，支持 Excel 批量导入货柜映射。

### 6. 供应商账户同步

从 Maximo `MXAPICOMPANY` 同步供应商编号和名称，支持分页查询与 Excel 导出。

### 7. 物料仓位映射

维护物料默认出库仓位（`material_location` 表）：

- Excel 导入（物料编号 + 货柜编号）
- 从 Maximo `defaultbin` 字段自动同步
- 支持单条更新 / 软删除 / 导出

### 8. 运行时配置热更新

所有关键参数（代理、SSL、请求延迟、同步间隔等）均可通过 API 在**不重启服务**的情况下动态修改。

---

## 项目结构

```
scania_rpa/
├── api/                        # FastAPI 应用
│   ├── main.py                 # 应用入口、路由注册、生命周期管理
│   ├── rpa_service.py          # RPA 子进程服务（subprocess 隔离）
│   ├── routers/
│   │   ├── auth.py             # 认证管理
│   │   ├── scraper.py          # 爬虫触发
│   │   ├── settings.py         # 运行时设置（代理 / SSL / 延迟）
│   │   ├── sync.py             # PO 增量同步控制
│   │   ├── mr.py               # 出库单 MR 操作
│   │   ├── items.py            # 物料主数据 & 库存成本
│   │   ├── material_location.py# 物料仓位映射
│   │   ├── vendor.py           # 供应商账户同步
│   │   └── warehouse.py        # 仓库 & 货柜管理
│   └── static/                 # 前端静态页面
│
├── config/                     # 配置层
│   ├── settings.py             # 全局配置（URL、代理、SSL、路径等）
│   ├── settings_manager.py     # 运行时配置单例
│   ├── auth.py                 # cURL 解析 / 环境变量加载
│   ├── auth_manager.py         # 认证状态单例（Cookie / CSRF）
│   └── browser.py              # 浏览器路径 & 调试端口
│
├── rpa/                        # RPA 自动化层
│   ├── browser.py              # Playwright 连接
│   ├── keepalive.py            # 会话保活管理器
│   ├── maximo_actions.py       # Maximo UI 操作（点击 / 填写 / 选择）
│   ├── navigation.py           # 菜单导航
│   ├── workflows.py            # 工作流编排
│   └── tests/                  # RPA 测试脚本
│
├── src/                        # 数据同步层
│   ├── fetcher/                # Maximo OSLC API 数据拉取
│   │   ├── po_fetcher.py
│   │   ├── item_fetcher.py
│   │   ├── mr_fetcher.py
│   │   ├── invcost_fetcher.py
│   │   ├── inventory_fetcher.py
│   │   ├── vendor_fetcher.py
│   │   └── warehouse_fetcher.py
│   ├── sync/                   # 数据库写入 & 调度
│   │   ├── po_sync_service.py  # PO 增量同步 + 5 分钟调度器
│   │   ├── item_sync.py        # 物料同步 + 每日调度器
│   │   ├── mr_sync.py          # 出库单同步 + FIFO 匹配
│   │   ├── inventory_sync.py   # 货柜库存同步
│   │   ├── invcost_sync.py     # 库存成本同步
│   │   ├── vendor_sync.py      # 供应商同步
│   │   ├── warehouse_sync.py   # 仓库 & 货柜同步
│   │   ├── material_location_sync.py
│   │   ├── material.py         # 物料校验 & 补全
│   │   ├── po_header.py        # PO 主表批量写入
│   │   ├── po_detail.py        # PO 子表批量写入
│   │   ├── db_init.py          # 数据库表结构初始化
│   │   └── mr_db_init.py
│   └── utils/
│       ├── db.py               # MySQL 连接 & 工具函数
│       └── mapper.py           # 字段映射规则
│
├── tests/                      # 测试 & 调试脚本
│   ├── test_full.py            # 全量集成测试（本文档末尾有使用说明）
│   └── purchase_order/         # PO 专项测试
│
├── start_api.py                # 仅启动 FastAPI 服务
├── start_browser.py            # 仅启动浏览器（调试模式）
├── start_service.py            # 一键启动（浏览器 + API）
├── check_setup.py              # 环境自检
├── requirements.txt
└── CHANGELOG.md
```

---

## 环境要求

| 组件 | 版本要求 |
|------|---------|
| Python | 3.11+ |
| MySQL | 5.7+ / 8.0 |
| 浏览器 | Microsoft Edge 或 Google Chrome（Windows） |
| 操作系统 | Windows 10/11（RPA 模块依赖 Windows 浏览器路径） |

> **注意**：数据同步（非 RPA）模块可在 Linux/macOS 上运行；RPA 入库功能需要 Windows 环境。

---

## 部署步骤

### 1. 克隆代码

```bash
git clone https://github.com/RPA-Maximo/scania_rpa.git
cd scania_rpa
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

如需使用 SOCKS5 代理，额外安装：

```bash
pip install PySocks
```

安装 Playwright 浏览器驱动（仅 RPA 入库功能需要）：

```bash
playwright install chromium
```

### 3. 配置数据库连接

在项目根目录创建 `.env` 文件（或设置系统环境变量）：

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_NAME=your_database
```

### 4. 初始化数据库表结构

```bash
python -c "from src.sync.db_init import init_db; init_db()"
python -c "from src.sync.mr_db_init import init_mr_db; init_mr_db()"
```

### 5. 配置 Maximo 认证

**方式一（推荐）：启动后通过 API 更新**

服务启动后，在浏览器中：
1. 打开 Maximo 并登录
2. 按 `F12` 打开 DevTools → Network 标签
3. 刷新页面，找到 `maximo.jsp` 请求
4. 右键 → **Copy as cURL (bash)**
5. 调用接口更新：

```bash
curl -X POST http://localhost:8000/api/auth/curl \
  -H "Content-Type: application/json" \
  -d '{"curl_text": "curl '\''https://...'\'' ..."}'
```

**方式二：配置文件**

将从浏览器复制的 cURL 内容保存为 `config/响应标头.txt`，服务启动时自动加载。

**方式三：环境变量**

```env
MAXIMO_COOKIE=LtpaToken2=xxx; x-refresh-token=yyy
MAXIMO_CSRF_TOKEN=your_csrf_token
```

### 6. 代理设置（可选）

默认已关闭代理（直连 Maximo）。如需开启，修改 `config/settings.py`：

```python
PROXY_ENABLED = True
PROXY_HOST    = "127.0.0.1"
PROXY_PORT    = 10820
PROXY_PROTOCOL = "socks5"   # socks5 | http | https
```

也可在服务启动后通过 API 热更新，无需重启：

```bash
curl -X POST http://localhost:8000/api/settings/proxy \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "host": "127.0.0.1", "port": 10820, "protocol": "socks5"}'
```

---

## 启动服务

### 方式一：一键启动（推荐，含 RPA 功能）

```bash
python start_service.py
```

自动完成：启动浏览器（调试模式）→ 等待 Maximo 登录 → 导航到接收页面 → 启动 API 服务。

如遇浏览器端口冲突，使用清理模式：

```bash
python start_service.py --clean
```

### 方式二：仅启动 API（不含 RPA 入库）

适用于只需要数据同步功能，不需要浏览器自动化的场景：

```bash
python start_api.py
```

### 方式三：分步启动

```bash
# 终端 1：启动浏览器
python start_browser.py

# 终端 2：启动 API 服务
python start_api.py
```

服务启动后访问：

| 地址 | 说明 |
|------|------|
| `http://localhost:8000/docs` | Swagger UI 交互文档 |
| `http://localhost:8000/health` | 健康检查 |
| `http://localhost:8000/mr` | 出库单 WMS 前端页面 |

---

## API 接口总览

### 基础

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 服务信息 |
| `GET` | `/health` | 健康检查（含保活状态） |
| `GET` | `/api/keepalive/status` | 查询会话保活状态 |
| `GET` | `/api/keepalive` | 手动触发一次保活 |

### 认证管理 `/api/auth`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/curl` | 通过 cURL 命令更新 Cookie / CSRF Token |
| `POST` | `/api/auth/fields` | 直接填写 Cookie 和 Token 更新 |
| `GET` | `/api/auth/status` | 查看当前认证状态 |

### RPA 入库

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/receipt` | 批量 RPA 自动入库 |

```json
{
  "po_number": "CN5123",
  "items": [
    {"item_num": "20326862", "quantity": 2.0, "remark": "备注"},
    {"po_line": "3",         "quantity": 1.5}
  ],
  "auto_save": false
}
```

### PO 增量同步 `/api/sync/po`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/sync/po/status` | 查询调度器 & 同步状态 |
| `POST` | `/api/sync/po/trigger` | 手动触发一次增量同步 |
| `POST` | `/api/sync/po/start` | 启动自动调度器 |
| `POST` | `/api/sync/po/stop` | 停止自动调度器 |
| `PUT` | `/api/sync/po/config` | 更新同步参数（状态过滤 / 页数） |
| `PUT` | `/api/sync/po/interval` | 修改同步间隔（分钟） |
| `GET` | `/api/sync/po/export` | 导出 PO 为 Excel |

### 出库单 MR `/api/mr`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/mr` | 出库单列表（分页） |
| `GET` | `/api/mr/{id}` | 出库单详情 |
| `POST` | `/api/mr/sync` | 从 Maximo 同步出库单 |
| `POST` | `/api/mr/{id}/issue` | 执行出库（FIFO 校验 + 回传） |
| `POST` | `/api/mr/{id}/writeback` | 手动回传 Maximo |
| `PUT` | `/api/mr/{id}/lines/{line_id}/bin` | 修改子表行仓位 |
| `GET` | `/api/mr/{id}/bins/{item_number}` | 获取可用货柜列表 |
| `POST` | `/api/mr/inventory/sync` | 同步货柜库存 |
| `GET` | `/api/mr/inventory/bins` | 查询货柜库存 |
| `GET` | `/api/mr/inventory/export` | 导出货柜库存 Excel |

### 物料主数据 `/api/items`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/items/sync` | 触发物料同步（增量 / 全量） |
| `GET` | `/api/items` | 物料列表（分页 / 关键词搜索） |
| `GET` | `/api/items/sync/status` | 同步状态 |
| `POST` | `/api/items/invcost/sync` | 同步库存成本 |
| `GET` | `/api/items/inventory/export` | 导出库存成本报表 |

### 供应商 `/api/vendor`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/vendor/sync` | 从 Maximo 同步供应商 |
| `GET` | `/api/vendor` | 供应商列表（分页） |
| `GET` | `/api/vendor/export` | 导出 Excel |

### 仓库 `/api/warehouse`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/warehouse/sync` | 同步仓库信息 |
| `POST` | `/api/warehouse/bins/sync` | 同步货柜信息 |
| `POST` | `/api/warehouse/bins/import` | Excel 批量导入货柜 |
| `GET` | `/api/warehouse` | 仓库列表 |
| `GET` | `/api/warehouse/bins` | 货柜列表 |
| `GET` | `/api/warehouse/{code}/bins` | 指定仓库的货柜 |

### 物料仓位映射 `/api/material-location`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/material-location/import` | Excel 导入（物料 + 默认货柜） |
| `POST` | `/api/material-location/sync` | 从 Maximo defaultbin 同步 |
| `GET` | `/api/material-location` | 列表（分页） |
| `PUT` | `/api/material-location/{id}` | 修改单条 |
| `DELETE` | `/api/material-location/{id}` | 软删除 |
| `GET` | `/api/material-location/template` | 下载导入模板 |
| `GET` | `/api/material-location/export` | 导出当前数据 |

### 运行时设置 `/api/settings`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/settings` | 查看所有运行时设置 |
| `GET` | `/api/settings/proxy` | 查看代理状态 |
| `POST` | `/api/settings/proxy` | 更新代理设置 |
| `POST` | `/api/settings/request` | 更新请求参数（延迟 / SSL / 重试） |

---

## 认证配置

Maximo 使用基于 Cookie + CSRF Token 的会话认证，Token 会定期过期（通常 8-24 小时）。

**Token 过期后的更新流程：**

1. 在浏览器中刷新 Maximo 页面（确保已登录）
2. 打开 DevTools → Network → 找到任意 Maximo 请求
3. 右键 → Copy as cURL (bash)
4. 调用 `POST /api/auth/curl` 提交新的 cURL 文本
5. 服务立即使用新 Token，无需重启

---

## 代理设置

默认关闭代理（直连 Maximo）。如公司网络需要通过代理访问，参考以下配置：

**启动前修改** `config/settings.py`：

```python
PROXY_ENABLED  = True
PROXY_PROTOCOL = "socks5"   # 或 "http"
PROXY_HOST     = "127.0.0.1"
PROXY_PORT     = 10820
```

**运行时热切换**（无需重启）：

```bash
# 开启代理
curl -X POST http://localhost:8000/api/settings/proxy \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "protocol": "socks5", "host": "127.0.0.1", "port": 10820}'

# 关闭代理（直连）
curl -X POST http://localhost:8000/api/settings/proxy \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

> 使用 SOCKS5 代理须安装 `PySocks`：`pip install PySocks`

---

## 测试脚本

`tests/test_full.py` 是覆盖所有模块的集成测试脚本：

```bash
# 全量测试（需 VPN + 服务已启动）
python tests/test_full.py

# 跳过 Maximo API（无 VPN 时）
python tests/test_full.py --skip-maximo

# 跳过本地 FastAPI（服务未启动时）
python tests/test_full.py --skip-api

# 仅测试配置 / 数据库 / 认证
python tests/test_full.py --skip-maximo --skip-api

# 指定非默认 API 地址
python tests/test_full.py --api-url http://192.168.1.100:8000
```

测试覆盖：配置项、数据库连通性（10 张核心表）、认证解析、Maximo 6 个 OSLC 端点、FastAPI 15 个只读端点、设置幂等写操作。

---

## 常见问题

**Q: 入库时提示「RPA 执行超时」**
A: 默认超时 180 秒。Maximo 页面加载慢时可能触发，请检查网络或减少单次批量数量。

**Q: 代理报错 `Missing dependencies for SOCKS support`**
A: 执行 `pip install PySocks`，或将 `PROXY_ENABLED` 改为 `False` 使用直连。

**Q: 数据库连接失败 `No module named 'mysql'`**
A: 执行 `pip install mysql-connector-python`。

**Q: 浏览器启动失败 / 调试端口被占用**
A: 使用 `python start_service.py --clean` 清理旧进程后重试。

**Q: Cookie 过期导致所有 API 请求返回 401**
A: 在 Maximo 浏览器中刷新页面，重新 Copy as cURL，调用 `POST /api/auth/curl` 更新。

**Q: PO 同步无新数据**
A: 检查 `GET /api/sync/po/status` 中的 `last_sync_time` 和错误信息；确认 Maximo 认证有效；可手动触发 `POST /api/sync/po/trigger` 查看详细日志。
