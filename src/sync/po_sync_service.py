"""
采购订单增量同步服务

功能：
- 从 Maximo API 抓取 PO 数据（按状态筛选）
- 增量模式：按 PO 号判断 WMS 中是否已存在，已存在则跳过
- 内置 5 分钟定时调度器，与 FastAPI lifespan 集成
- 提供手动触发和状态查询接口
"""
import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetcher.po_fetcher import fetch_po_list
from src.sync.db_init import init_schema
from src.sync.material import validate_and_sync_materials
from src.sync.po_header import batch_insert_headers, check_po_exists
from src.sync.po_detail import batch_insert_details
from src.utils.db import get_connection

# ── 日志 ──────────────────────────────────────────────────────────────────────

def _setup_sync_logger() -> logging.Logger:
    log_dir = PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("po_sync")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger

    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(str(log_dir / "po_sync.log"), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


sync_logger = _setup_sync_logger()

# ── 同步服务 ──────────────────────────────────────────────────────────────────

class POSyncService:
    """
    采购订单增量同步服务

    同步策略：
      1. 从 Maximo 按状态分页抓取 PO
      2. 过滤掉 WMS 中已存在（按 PO 号匹配）的单据
      3. 对新 PO 执行物料验证 → 插入主表 → 插入明细
    """

    def __init__(self):
        self._lock = threading.Lock()

        # 同步配置（可通过 API 动态修改）
        self._config = {
            'status_filter': 'APPR',   # 状态筛选
            'max_pages': 5,            # 每次最多抓取页数
            'page_size': 20,           # 每页条数
            'auto_sync_materials': True,  # 自动同步缺失物料
        }

        # 运行统计
        self._sync_count: int = 0
        self._last_sync_time: Optional[datetime] = None
        self._last_sync_result: Optional[dict] = None
        self._schema_initialized: bool = False

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def update_config(self, **kwargs) -> dict:
        """动态更新同步配置"""
        allowed = {'status_filter', 'max_pages', 'page_size', 'auto_sync_materials'}
        updated = {}
        for k, v in kwargs.items():
            if k in allowed and v is not None:
                self._config[k] = v
                updated[k] = v
        return {'updated': updated, 'current': dict(self._config)}

    def get_config(self) -> dict:
        return dict(self._config)

    def sync_once(self) -> dict:
        """
        执行一次增量同步（线程安全，同一时刻只允许一个同步任务）

        Returns:
            dict: 同步结果摘要
        """
        if not self._lock.acquire(blocking=False):
            return {
                'success': False,
                'skipped': True,
                'message': '同步任务正在运行中，本次跳过',
            }
        try:
            return self._do_sync()
        finally:
            self._lock.release()

    def get_status(self) -> dict:
        """返回同步服务状态"""
        return {
            'sync_count': self._sync_count,
            'last_sync_time': (
                self._last_sync_time.isoformat() if self._last_sync_time else None
            ),
            'last_sync_result': self._last_sync_result,
            'config': self.get_config(),
            'is_running': not self._lock.acquire(blocking=False) or self._lock.release() or False,
        }

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _ensure_schema(self, conn):
        """首次运行时初始化数据库字段（只执行一次）"""
        if self._schema_initialized:
            return
        try:
            init_schema(conn)
            self._schema_initialized = True
            sync_logger.info("SYNC | 数据库字段初始化完成")
        except Exception as e:
            sync_logger.warning(f"SYNC | 数据库字段初始化警告: {e}")

    def _do_sync(self) -> dict:
        """实际执行增量同步"""
        start_ts = datetime.now()
        self._sync_count += 1
        count = self._sync_count

        sync_logger.info(
            f"SYNC #{count} | 开始增量同步 | "
            f"状态={self._config['status_filter']} "
            f"页数={self._config['max_pages']} 每页={self._config['page_size']}"
        )

        # 步骤 1：从 Maximo 抓取 PO
        try:
            po_list = fetch_po_list(
                status_filter=self._config['status_filter'],
                max_pages=self._config['max_pages'],
                page_size=self._config['page_size'],
                save_to_file=False,
            )
        except Exception as e:
            msg = f"从 Maximo 抓取数据失败: {e}"
            sync_logger.error(f"SYNC #{count} | ❌ {msg}")
            result = {'success': False, 'message': msg}
            self._last_sync_result = result
            self._last_sync_time = datetime.now()
            return result

        if not po_list:
            msg = "Maximo 未返回任何数据（可能认证过期或无符合条件的 PO）"
            sync_logger.warning(f"SYNC #{count} | ⚠ {msg}")
            result = {'success': True, 'total_fetched': 0, 'new_pos': 0, 'message': msg}
            self._last_sync_result = result
            self._last_sync_time = datetime.now()
            return result

        sync_logger.info(f"SYNC #{count} | 抓取到 {len(po_list)} 个 PO，开始过滤...")

        # 步骤 2：连接数据库，过滤已存在的 PO
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # 初始化 schema（安全添加新字段）
            self._ensure_schema(conn)

            # 增量过滤：只保留 WMS 中不存在的 PO
            new_pos = [
                po for po in po_list
                if not check_po_exists(cursor, po.get('ponum'))
            ]

            skipped = len(po_list) - len(new_pos)
            sync_logger.info(
                f"SYNC #{count} | 已存在: {skipped} 个（跳过）| 新增: {len(new_pos)} 个"
            )

            if not new_pos:
                elapsed = (datetime.now() - start_ts).total_seconds()
                result = {
                    'success': True,
                    'total_fetched': len(po_list),
                    'new_pos': 0,
                    'skipped_existing': skipped,
                    'message': '所有 PO 均已存在于 WMS，无需同步',
                    'elapsed_seconds': round(elapsed, 2),
                }
                self._last_sync_result = result
                self._last_sync_time = datetime.now()
                return result

            # 步骤 3：物料验证/同步
            material_map = validate_and_sync_materials(
                cursor, new_pos,
                auto_sync=self._config['auto_sync_materials'],
            )
            if material_map is None:
                material_map = {}

            # 步骤 4：插入主表（增量，不更新已有记录）
            header_map = batch_insert_headers(cursor, new_pos, update_existing=False)

            # 步骤 5：插入明细
            detail_stats = batch_insert_details(cursor, new_pos, header_map, material_map)

            conn.commit()

            elapsed = (datetime.now() - start_ts).total_seconds()
            result = {
                'success': True,
                'total_fetched': len(po_list),
                'new_pos': len(new_pos),
                'skipped_existing': skipped,
                'inserted_headers': len(header_map),
                'detail_stats': detail_stats,
                'elapsed_seconds': round(elapsed, 2),
                'message': f'成功同步 {len(new_pos)} 个新 PO',
            }
            self._last_sync_result = result
            self._last_sync_time = datetime.now()

            sync_logger.info(
                f"SYNC #{count} | ✅ 完成 | "
                f"新增 {len(new_pos)} 个 PO | 明细 {detail_stats.get('inserted', 0)} 行 | "
                f"耗时 {elapsed:.1f}s"
            )
            return result

        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            msg = f"数据库操作失败: {e}"
            sync_logger.error(f"SYNC #{count} | ❌ {msg}", exc_info=True)
            result = {'success': False, 'message': msg}
            self._last_sync_result = result
            self._last_sync_time = datetime.now()
            return result

        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


# ── 调度器 ────────────────────────────────────────────────────────────────────

SYNC_INTERVAL_DEFAULT = 300   # 5 分钟（秒）


class POSyncScheduler:
    """
    PO 增量同步定时调度器

    使用 threading.Timer 实现，与 FastAPI lifespan 集成：
        scheduler = POSyncScheduler(sync_service)
        scheduler.start()   # 在 FastAPI 启动时调用
        scheduler.stop()    # 在 FastAPI 关闭时调用
    """

    def __init__(
        self,
        service: POSyncService,
        interval: int = SYNC_INTERVAL_DEFAULT,
    ):
        self._service = service
        self._interval = interval
        self._running = False
        self._timer: Optional[threading.Timer] = None
        self._start_time: Optional[datetime] = None

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def start(self):
        """启动定时调度（FastAPI 启动时调用）"""
        if self._running:
            return
        self._running = True
        self._start_time = datetime.now()
        sync_logger.info(
            f"SYNC SCHEDULER | 已启动 | 同步间隔: {self._interval}s "
            f"({self._interval // 60} 分钟) | 首次同步将在 {self._interval}s 后执行"
        )
        self._schedule_next()

    def stop(self):
        """停止定时调度（FastAPI 关闭时调用）"""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        sync_logger.info("SYNC SCHEDULER | 已停止")

    def set_interval(self, seconds: int):
        """动态修改同步间隔（立即对下次执行生效）"""
        self._interval = seconds
        sync_logger.info(f"SYNC SCHEDULER | 同步间隔已修改为 {seconds}s ({seconds // 60} 分钟)")

    def get_status(self) -> dict:
        """返回调度器状态"""
        return {
            'running': self._running,
            'interval_seconds': self._interval,
            'interval_minutes': round(self._interval / 60, 1),
            'start_time': self._start_time.isoformat() if self._start_time else None,
        }

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _schedule_next(self):
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self):
        """定时器到期回调"""
        if not self._running:
            return
        try:
            result = self._service.sync_once()
            if result.get('skipped'):
                sync_logger.info("SYNC SCHEDULER | 本次触发被跳过（上次仍在运行）")
        except Exception as e:
            sync_logger.error(f"SYNC SCHEDULER | 调度执行异常: {e}", exc_info=True)
        finally:
            self._schedule_next()


# ── 全局单例 ──────────────────────────────────────────────────────────────────

po_sync_service = POSyncService()
po_sync_scheduler = POSyncScheduler(po_sync_service, interval=SYNC_INTERVAL_DEFAULT)
