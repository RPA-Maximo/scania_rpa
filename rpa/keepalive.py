"""
Maximo 会话保活管理器

功能：
- 后台定时执行保活操作（8 分钟 ± 15s 随机抖动）
- 通过 subprocess 调用 keepalive_worker.py 执行 PO 搜索验证会话
- 锁机制：RPA 任务执行时自动暂停保活
- 双日志：控制台 + 文件 (data/logs/keepalive.log)
- 会话持续时间和保活次数追踪
"""
import json
import logging
import os
import random
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 默认保活配置
KEEPALIVE_INTERVAL = 480   # 8 分钟（秒）
KEEPALIVE_JITTER = 15      # ±15 秒随机抖动


def _setup_keepalive_logger() -> logging.Logger:
    """配置保活专用日志（控制台 + 文件双输出）"""
    log_dir = PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "keepalive.log"

    ka_logger = logging.getLogger("keepalive")
    ka_logger.setLevel(logging.DEBUG)

    # 避免重复添加 handler
    if ka_logger.handlers:
        return ka_logger

    # 日志格式
    fmt = logging.Formatter(
        "[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)
    ka_logger.addHandler(console_handler)

    # 文件输出
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    ka_logger.addHandler(file_handler)

    return ka_logger


# 全局日志实例
ka_logger = _setup_keepalive_logger()


class KeepaliveManager:
    """
    Maximo 会话保活管理器
    
    使用方式:
        manager = KeepaliveManager()
        manager.start()    # 启动后台保活定时器
        
        # RPA 任务执行时
        manager.acquire()  # 暂停保活
        try:
            ... # 执行 RPA 任务
        finally:
            manager.release()  # 恢复保活 + 重置计时器
        
        manager.stop()     # 停止保活
    """

    def __init__(
        self,
        interval: int = KEEPALIVE_INTERVAL,
        jitter: int = KEEPALIVE_JITTER
    ):
        self.interval = interval
        self.jitter = jitter

        # 状态追踪
        self.session_start_time: float | None = None
        self.keepalive_count: int = 0
        self.last_keepalive_time: float | None = None
        self.last_keepalive_result: dict | None = None

        # 锁和线程控制
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._running = False
        self._task_active = False  # 标记 RPA 任务是否在执行

    def _get_next_interval(self) -> float:
        """计算下一次保活间隔（带随机抖动）"""
        return self.interval + random.uniform(-self.jitter, self.jitter)

    def _format_duration(self, seconds: float) -> str:
        """格式化时间为 Xh Ym Zs"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def start(self):
        """启动后台保活定时器"""
        if self._running:
            ka_logger.warning("KEEPALIVE | 保活定时器已在运行中")
            return

        self._running = True
        self.session_start_time = time.time()
        self.keepalive_count = 0

        next_interval = self._get_next_interval()
        ka_logger.info(
            f"KEEPALIVE | 保活定时器已启动 | "
            f"间隔: {self.interval}s ± {self.jitter}s | "
            f"首次保活将在 {next_interval:.0f}s 后执行"
        )

        self._schedule_next(next_interval)

    def stop(self):
        """停止后台保活定时器"""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

        session_duration = ""
        if self.session_start_time:
            elapsed = time.time() - self.session_start_time
            session_duration = f" | 会话总时长: {self._format_duration(elapsed)}"

        ka_logger.info(
            f"KEEPALIVE | 保活定时器已停止 | "
            f"累计保活: {self.keepalive_count} 次{session_duration}"
        )

    def acquire(self):
        """
        获取锁：RPA 任务执行前调用
        暂停保活定时器
        """
        self._task_active = True
        self._lock.acquire()

        # 取消当前等待中的定时器
        if self._timer:
            self._timer.cancel()
            self._timer = None

        ka_logger.info("KEEPALIVE | 🔒 保活已暂停（RPA 任务开始执行）")

    def release(self):
        """
        释放锁：RPA 任务执行后调用
        恢复保活定时器，重新开始倒计时
        """
        self._task_active = False
        self._lock.release()

        # 重新调度下次保活
        if self._running:
            next_interval = self._get_next_interval()
            self._schedule_next(next_interval)
            ka_logger.info(
                f"KEEPALIVE | 🔓 保活已恢复（RPA 任务执行完成）| "
                f"下次保活: {next_interval:.0f}s 后"
            )

    def _schedule_next(self, interval: float):
        """安排下次保活"""
        if not self._running:
            return
        self._timer = threading.Timer(interval, self._keepalive_tick)
        self._timer.daemon = True  # 守护线程，主程序退出时自动结束
        self._timer.start()

    def _keepalive_tick(self):
        """定时器到期时调用"""
        if not self._running:
            return

        # 尝试获取锁（非阻塞），如果 RPA 任务在执行则跳过
        if not self._lock.acquire(blocking=False):
            ka_logger.info(
                f"KEEPALIVE | ⏭ 跳过本次保活（RPA 任务执行中）"
            )
            # 继续调度下一次
            if self._running:
                next_interval = self._get_next_interval()
                self._schedule_next(next_interval)
            return

        try:
            self._do_keepalive()
        finally:
            self._lock.release()
            # 调度下一次
            if self._running:
                next_interval = self._get_next_interval()
                self._schedule_next(next_interval)

    def _do_keepalive(self):
        """执行保活操作（通过 subprocess 调用 keepalive_worker.py）"""
        self.keepalive_count += 1
        count = self.keepalive_count
        session_elapsed = time.time() - self.session_start_time if self.session_start_time else 0
        duration_str = self._format_duration(session_elapsed)

        ka_logger.info(
            f"KEEPALIVE #{count} | ⏳ 开始保活... | 会话已持续: {duration_str}"
        )

        start_time = time.time()
        worker_script = Path(__file__).parent / "keepalive_worker.py"

        try:
            result = subprocess.run(
                [sys.executable, str(worker_script)],
                capture_output=True,
                text=True,
                timeout=30,   # 30s 超时（JS fetch 保活，CDP 连接 + 单次请求约 5s）
                cwd=str(PROJECT_ROOT)
            )

            elapsed = time.time() - start_time

            # 输出 worker 的 stderr 日志（调试信息）
            if result.stderr:
                for line in result.stderr.strip().split('\n'):
                    if line.strip():
                        ka_logger.debug(f"KEEPALIVE #{count} | [worker] {line.strip()}")

            # 解析结果
            if result.stdout.strip():
                try:
                    keepalive_result = json.loads(result.stdout.strip())
                except json.JSONDecodeError:
                    keepalive_result = {
                        'success': False,
                        'reason': 'parse_error',
                        'message': f'无法解析 worker 输出: {result.stdout[:200]}',
                        'po_count': 0
                    }
            else:
                keepalive_result = {
                    'success': False,
                    'reason': 'no_output',
                    'message': f'Worker 无输出 (返回码: {result.returncode})',
                    'po_count': 0
                }

            self.last_keepalive_result = keepalive_result
            self.last_keepalive_time = time.time()

            if keepalive_result.get('success'):
                po_count = keepalive_result.get('po_count', 0)
                ka_logger.info(
                    f"KEEPALIVE #{count} | ✅ SUCCESS | "
                    f"会话已持续: {duration_str} | "
                    f"PO数量: {po_count} | "
                    f"耗时: {elapsed:.1f}s"
                )
            else:
                reason = keepalive_result.get('reason', 'unknown')
                message = keepalive_result.get('message', '未知错误')
                ka_logger.warning(
                    f"KEEPALIVE #{count} | ❌ FAILED | "
                    f"会话已持续: {duration_str} | "
                    f"原因: {reason} | "
                    f"详情: {message} | "
                    f"耗时: {elapsed:.1f}s"
                )

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            self.last_keepalive_result = {
                'success': False,
                'reason': 'timeout',
                'message': '保活脚本执行超时 (>30s)',
                'po_count': 0
            }
            self.last_keepalive_time = time.time()
            ka_logger.warning(
                f"KEEPALIVE #{count} | ❌ TIMEOUT | "
                f"会话已持续: {duration_str} | "
                f"保活脚本超时 (>120s)"
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self.last_keepalive_result = {
                'success': False,
                'reason': 'exception',
                'message': str(e),
                'po_count': 0
            }
            self.last_keepalive_time = time.time()
            ka_logger.error(
                f"KEEPALIVE #{count} | ❌ ERROR | "
                f"会话已持续: {duration_str} | "
                f"异常: {e} | "
                f"耗时: {elapsed:.1f}s"
            )

    def trigger_keepalive(self) -> dict:
        """
        手动触发一次保活（供 API 接口调用）
        
        Returns:
            dict: 保活结果 + 会话状态
        """
        # 尝试获取锁
        if not self._lock.acquire(blocking=False):
            return {
                'triggered': False,
                'reason': 'RPA 任务正在执行，无法触发保活',
                'status': self.get_status()
            }

        try:
            self._do_keepalive()
            return {
                'triggered': True,
                'result': self.last_keepalive_result,
                'status': self.get_status()
            }
        finally:
            self._lock.release()

            # 重置定时器（手动保活算一次，重新倒计时）
            if self._running and self._timer:
                self._timer.cancel()
                next_interval = self._get_next_interval()
                self._schedule_next(next_interval)

    def get_status(self) -> dict:
        """获取保活状态信息"""
        now = time.time()
        session_duration = None
        if self.session_start_time:
            session_duration = self._format_duration(now - self.session_start_time)

        next_keepalive_in = None
        if self._timer and self._timer.is_alive():
            # Timer 没有直接暴露剩余时间，给一个估计值
            next_keepalive_in = "定时器运行中"

        return {
            'running': self._running,
            'task_active': self._task_active,
            'keepalive_count': self.keepalive_count,
            'session_duration': session_duration,
            'session_start_time': (
                datetime.fromtimestamp(self.session_start_time).isoformat()
                if self.session_start_time else None
            ),
            'last_keepalive_time': (
                datetime.fromtimestamp(self.last_keepalive_time).isoformat()
                if self.last_keepalive_time else None
            ),
            'last_keepalive_success': (
                self.last_keepalive_result.get('success')
                if self.last_keepalive_result else None
            ),
            'last_keepalive_message': (
                self.last_keepalive_result.get('message')
                if self.last_keepalive_result else None
            ),
            'interval': f"{self.interval}s ± {self.jitter}s"
        }
