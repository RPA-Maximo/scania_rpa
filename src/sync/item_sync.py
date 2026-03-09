"""
物料主数据同步服务

功能：
- 增量同步：以 item_number(code) 为唯一键 upsert，WMS 内不重复
- 全量同步：拉取 Maximo changedate >= 昨天00:00 的物料，每天凌晨自动执行
- 内置每日凌晨定时调度器，与 FastAPI lifespan 集成
"""
import logging
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetcher.item_fetcher import fetch_items
from src.utils.db import get_connection, generate_id

# ── 日志 ──────────────────────────────────────────────────────────────────────


def _setup_logger() -> logging.Logger:
    log_dir = PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("item_sync")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger

    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(str(log_dir / "item_sync.log"), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


item_logger = _setup_logger()

# ── 数据库表初始化 ────────────────────────────────────────────────────────────


def _add_col(cursor, table: str, col: str, definition: str):
    """安全添加列（已存在则跳过）"""
    cursor.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (col,))
    if cursor.fetchone() is None:
        cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {definition}")


def ensure_material_columns(conn):
    """
    确保 material 表有物料同步所需字段

    新增字段：
      - maximo_changedate  Maximo 物料最近更新时间（用于增量判断）
      - sync_time          WMS 最近同步时间
    """
    cursor = conn.cursor()
    try:
        _add_col(
            cursor, "material", "maximo_changedate",
            "DATETIME NULL COMMENT 'Maximo 物料最近更新时间'",
        )
        _add_col(
            cursor, "material", "sync_time",
            "DATETIME NULL COMMENT 'WMS 最近同步时间'",
        )
        conn.commit()
    except Exception as e:
        item_logger.warning(f"ensure_material_columns 警告: {e}")
    finally:
        cursor.close()


# ── 核心同步逻辑 ──────────────────────────────────────────────────────────────


def _safe_str(v, maxlen: int = 255) -> Optional[str]:
    if v is None:
        return None
    s = str(v)
    return s[:maxlen] if len(s) > maxlen else s


def _parse_changedate(v) -> Optional[datetime]:
    """解析 Maximo changedate 字符串为 datetime（格式如 2024-06-01T08:00:00+00:00）"""
    if not v:
        return None
    try:
        s = str(v)[:19]          # 取前19位去掉时区
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        try:
            return datetime.strptime(str(v)[:10], "%Y-%m-%d")
        except Exception:
            return None


def sync_items_from_maximo(
    since_date: Optional[datetime] = None,
    item_numbers: Optional[List[str]] = None,
    max_pages: int = 100,
    page_size: int = 100,
) -> Dict[str, int]:
    """
    从 Maximo 同步物料主数据到 material 表

    Args:
        since_date:    增量起始时间（筛选 changedate >= since_date）；
                       None 表示抓取全量（不加时间过滤）
        item_numbers:  指定物料编号列表；None 表示全部
        max_pages:     最多抓取页数
        page_size:     每页条数

    Returns:
        {'inserted': N, 'updated': N, 'skipped': N}
    """
    raw_items = fetch_items(
        since_date=since_date,
        item_numbers=item_numbers,
        max_pages=max_pages,
        page_size=page_size,
    )

    if not raw_items:
        item_logger.warning("未获取到任何物料数据")
        return {"inserted": 0, "updated": 0, "skipped": 0}

    conn = get_connection()
    try:
        ensure_material_columns(conn)
        cursor = conn.cursor(dictionary=True)
        stats = {"inserted": 0, "updated": 0, "skipped": 0}
        now = datetime.now()

        for item in raw_items:
            code = _safe_str(item.get("itemnum"), 50)
            if not code:
                stats["skipped"] += 1
                continue

            name          = _safe_str(item.get("description"), 50)
            ordering_unit = _safe_str(item.get("orderunit"), 255)
            issuing_unit  = _safe_str(item.get("issueunit"), 255)
            status        = _safe_str(item.get("status"), 255)
            lot_type      = _safe_str(item.get("lottype"), 255)
            changedate    = _parse_changedate(item.get("changedate"))

            # 查询是否已存在（以 code 为唯一键）
            cursor.execute(
                "SELECT id FROM material WHERE code=%s AND del_flag=0",
                (code,),
            )
            existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    """UPDATE material SET
                        name=%s, ordering_unit=%s, issuing_unit=%s,
                        status=%s, batch_type=%s,
                        maximo_changedate=%s, sync_time=%s,
                        last_update_time=%s
                       WHERE id=%s""",
                    (
                        name, ordering_unit, issuing_unit,
                        status, lot_type,
                        changedate, now,
                        now,
                        existing["id"],
                    ),
                )
                stats["updated"] += 1
            else:
                cursor.execute(
                    """INSERT INTO material
                        (id, code, name, ordering_unit, issuing_unit,
                         status, batch_type,
                         maximo_changedate, sync_time,
                         create_time, last_update_time, del_flag)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)""",
                    (
                        generate_id(),
                        code, name, ordering_unit, issuing_unit,
                        status, lot_type,
                        changedate, now,
                        now, now,
                    ),
                )
                stats["inserted"] += 1

        conn.commit()
        item_logger.info(f"物料同步完成: {stats}")
        return stats

    except Exception as e:
        conn.rollback()
        item_logger.error(f"物料同步失败: {e}", exc_info=True)
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        conn.close()


# ── 同步服务 ──────────────────────────────────────────────────────────────────


class ItemSyncService:
    """
    物料主数据同步服务

    同步策略：
      - 手动触发：可指定 since_date（默认昨天00:00）
      - 定时触发（每日凌晨）：自动取昨天00:00作为起点
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._sync_count: int = 0
        self._last_sync_time: Optional[datetime] = None
        self._last_sync_result: Optional[dict] = None

        self._config = {
            "max_pages": 100,
            "page_size": 100,
        }

    def update_config(self, **kwargs) -> dict:
        allowed = {"max_pages", "page_size"}
        for k, v in kwargs.items():
            if k in allowed and v is not None:
                self._config[k] = v
        return dict(self._config)

    def get_status(self) -> dict:
        return {
            "sync_count":       self._sync_count,
            "last_sync_time":   self._last_sync_time.isoformat() if self._last_sync_time else None,
            "last_sync_result": self._last_sync_result,
            "config":           dict(self._config),
        }

    def sync_once(
        self,
        since_date: Optional[datetime] = None,
        full_no_filter: bool = False,
    ) -> dict:
        """
        执行一次同步（线程安全）

        Args:
            since_date:      增量起点；None 时默认取昨天00:00
            full_no_filter:  True=完全不加时间过滤（全量抓取所有物料，量大慎用）
        """
        if not self._lock.acquire(blocking=False):
            return {"success": False, "skipped": True, "message": "同步任务正在运行中，本次跳过"}
        try:
            return self._do_sync(since_date=since_date, full_no_filter=full_no_filter)
        finally:
            self._lock.release()

    def _do_sync(self, since_date: Optional[datetime], full_no_filter: bool) -> dict:
        start_ts = datetime.now()
        self._sync_count += 1
        n = self._sync_count

        # 默认起点：昨天00:00:00
        if not full_no_filter and since_date is None:
            yesterday = datetime.now() - timedelta(days=1)
            since_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)

        item_logger.info(
            f"ITEM SYNC #{n} | 开始 | "
            f"since={since_date.strftime('%Y-%m-%d %H:%M:%S') if since_date else '全量(无过滤)'}"
        )

        try:
            stats = sync_items_from_maximo(
                since_date=since_date if not full_no_filter else None,
                max_pages=self._config["max_pages"],
                page_size=self._config["page_size"],
            )
            elapsed = (datetime.now() - start_ts).total_seconds()
            result = {
                "success":  True,
                "stats":    stats,
                "since":    since_date.isoformat() if since_date else None,
                "elapsed_seconds": round(elapsed, 2),
                "message":  (
                    f"同步完成：新增 {stats['inserted']} 条，"
                    f"更新 {stats['updated']} 条，"
                    f"跳过 {stats['skipped']} 条"
                ),
            }
            item_logger.info(
                f"ITEM SYNC #{n} | ✅ 完成 | "
                f"新增 {stats['inserted']} 更新 {stats['updated']} | 耗时 {elapsed:.1f}s"
            )
        except Exception as e:
            result = {"success": False, "message": str(e)}
            item_logger.error(f"ITEM SYNC #{n} | ❌ 失败: {e}", exc_info=True)

        self._last_sync_result = result
        self._last_sync_time = datetime.now()
        return result


# ── 每日凌晨调度器 ────────────────────────────────────────────────────────────


def _seconds_until_midnight() -> float:
    """计算距下次凌晨00:00:00的秒数"""
    now = datetime.now()
    next_midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (next_midnight - now).total_seconds()


class ItemSyncScheduler:
    """
    物料主数据每日凌晨定时调度器

    每天00:00:00自动触发全量同步（changedate >= 昨天00:00）
    使用 threading.Timer 实现，与 FastAPI lifespan 集成：
        scheduler.start()   # FastAPI 启动时调用
        scheduler.stop()    # FastAPI 关闭时调用
    """

    def __init__(self, service: ItemSyncService):
        self._service = service
        self._running = False
        self._timer: Optional[threading.Timer] = None
        self._start_time: Optional[datetime] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._start_time = datetime.now()
        wait = _seconds_until_midnight()
        item_logger.info(
            f"ITEM SYNC SCHEDULER | 已启动 | "
            f"首次执行将在 {wait/3600:.1f}h 后（次日凌晨00:00）"
        )
        self._schedule_next()

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        item_logger.info("ITEM SYNC SCHEDULER | 已停止")

    def get_status(self) -> dict:
        wait = _seconds_until_midnight()
        return {
            "running":    self._running,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "next_run_in_seconds": int(wait),
            "next_run_at": (
                datetime.now() + timedelta(seconds=wait)
            ).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def trigger_now(self) -> dict:
        """立即触发一次同步（调试用）"""
        return self._service.sync_once()

    def _schedule_next(self):
        if not self._running:
            return
        wait = _seconds_until_midnight()
        self._timer = threading.Timer(wait, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self):
        if not self._running:
            return
        item_logger.info("ITEM SYNC SCHEDULER | 凌晨定时任务触发")
        try:
            result = self._service.sync_once()
            if result.get("skipped"):
                item_logger.info("ITEM SYNC SCHEDULER | 本次触发被跳过（上次仍在运行）")
        except Exception as e:
            item_logger.error(f"ITEM SYNC SCHEDULER | 调度执行异常: {e}", exc_info=True)
        finally:
            self._schedule_next()  # 重新调度下一次


# ── 全局单例 ──────────────────────────────────────────────────────────────────

item_sync_service   = ItemSyncService()
item_sync_scheduler = ItemSyncScheduler(item_sync_service)
