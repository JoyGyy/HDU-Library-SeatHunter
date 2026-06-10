"""定时调度器：预约线程 + 签到线程。

threading.Event 实现可中断等待。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any

from app.config import AUTO_BOOK_HOUR, AUTO_BOOK_MINUTE, AUTO_CHECKIN_HOUR, AUTO_CHECKIN_MINUTE
from app.core.booker import book_for_all_dates, DebugLogger
from app.core.checker import checkin_for_all_users

logger = logging.getLogger("seathunter.core.scheduler")

# 全局状态
_state: dict[str, Any] = {
    "running": False,
    "last_book_result": "",
    "last_checkin_result": "",
    "last_error": "",
}
debug = DebugLogger()


def get_state() -> dict[str, Any]:
    """获取当前状态（供 API 路由使用）。"""
    return {
        **_state,
        "debug_log": debug.get_recent(20),
    }


def get_debug_log() -> DebugLogger:
    """获取调试日志实例。"""
    return debug


class AutoScheduler:
    """自动预约/签到调度器。"""

    def __init__(self, app_state: Any):
        self._app_state = app_state
        self._stop = threading.Event()
        self._book_thread: threading.Thread | None = None
        self._checkin_thread: threading.Thread | None = None

    def start(self) -> None:
        """启动调度器。"""
        if _state["running"]:
            debug.log("调度器已在运行")
            return

        _state["running"] = True
        self._stop.clear()

        self._book_thread = threading.Thread(
            target=self._book_loop, daemon=True, name="BookScheduler"
        )
        self._book_thread.start()

        self._checkin_thread = threading.Thread(
            target=self._checkin_loop, daemon=True, name="CheckinScheduler"
        )
        self._checkin_thread.start()

        debug.log("调度器已启动")

    def stop(self) -> None:
        """停止调度器。"""
        _state["running"] = False
        self._stop.set()
        debug.log("调度器已停止")

    def _book_loop(self) -> None:
        """预约线程：每 30 秒检查，20:00 触发。"""
        last_trigger: str | None = None
        while not self._stop.is_set():
            now = datetime.utcnow() + timedelta(hours=8)
            today = now.strftime("%Y-%m-%d")
            if (now.hour == AUTO_BOOK_HOUR
                    and now.minute == AUTO_BOOK_MINUTE
                    and last_trigger != today):
                last_trigger = today
                debug.log("触发自动预约")
                try:
                    result = book_for_all_dates(self._app_state, debug)
                    _state["last_book_result"] = result
                    _state["last_error"] = ""
                except Exception as e:
                    _state["last_error"] = str(e)
                    _state["last_book_result"] = f"预约异常: {e}"
                    debug.log(f"预约异常: {e}")
            self._stop.wait(timeout=30)

    def _checkin_loop(self) -> None:
        """签到线程：每 30 秒检查，9:30 触发。"""
        last_trigger: str | None = None
        while not self._stop.is_set():
            now = datetime.utcnow() + timedelta(hours=8)
            today = now.strftime("%Y-%m-%d")
            if (now.hour == AUTO_CHECKIN_HOUR
                    and now.minute == AUTO_CHECKIN_MINUTE
                    and last_trigger != today):
                last_trigger = today
                debug.log("触发自动签到")
                try:
                    result = checkin_for_all_users(self._app_state, debug)
                    _state["last_checkin_result"] = result
                    _state["last_error"] = ""
                except Exception as e:
                    _state["last_error"] = str(e)
                    _state["last_checkin_result"] = f"签到异常: {e}"
                    debug.log(f"签到异常: {e}")
            self._stop.wait(timeout=30)


# 模块级调度器实例
_scheduler: AutoScheduler | None = None


def init_scheduler(app_state: Any) -> AutoScheduler:
    """初始化并返回调度器实例。"""
    global _scheduler
    _scheduler = AutoScheduler(app_state)
    return _scheduler


def get_scheduler() -> AutoScheduler | None:
    """获取调度器实例。"""
    return _scheduler
