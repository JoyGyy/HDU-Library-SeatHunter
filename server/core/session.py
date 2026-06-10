"""Session 验证与自动 re-login。

每次 API 调用前验证 session 是否有效，过期则自动重新登录。
"""

from __future__ import annotations

import logging
from typing import Any

from seathunter.api.client import ApiClient
from seathunter.auth.session_manager import SessionManager

from server.core.config import USER_STUDENT_ID, USER_PASSWORD

logger = logging.getLogger("seathunter.core.session")


class DebugLogger:
    """收集调试日志，供前端显示。"""

    def __init__(self, max_lines: int = 50):
        self._lines: list[str] = []
        self._max = max_lines

    def log(self, msg: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self._lines.append(entry)
        if len(self._lines) > self._max:
            self._lines = self._lines[-self._max:]
        logger.info(msg)

    def get_recent(self, n: int = 20) -> list[str]:
        return self._lines[-n:]


def ensure_valid_session(state: Any, debug: DebugLogger) -> bool:
    """确保 session 有效，过期则重新登录。

    Args:
        state: AppState 实例
        debug: 调试日志收集器

    Returns:
        True if session is valid (or re-login succeeded), False otherwise.
    """
    if state.api_client is None:
        debug.log("api_client 为空，尝试重新登录...")
        return _do_relogin(state, debug)

    try:
        resp = state.api_client.session.get(
            url=state.api_client.base_url + "/Seat/Index/myBookingList",
            timeout=15,
            allow_redirects=False,
        )
        # 重定向到 CAS 登录 → session 过期
        if resp.status_code in (301, 302):
            debug.log("Session 已过期（重定向），重新登录...")
            return _do_relogin(state, debug)
        if "CASLogin" in resp.text[:500]:
            debug.log("Session 已过期（CAS页面），重新登录...")
            return _do_relogin(state, debug)
        if resp.status_code != 200:
            debug.log(f"Session 验证异常: HTTP {resp.status_code}")
            return _do_relogin(state, debug)
        debug.log("Session 有效")
        return True
    except Exception as e:
        debug.log(f"Session 验证失败: {e}")
        return _do_relogin(state, debug)


def _do_relogin(state: Any, debug: DebugLogger) -> bool:
    """执行 re-login。"""
    try:
        debug.log("执行重新登录...")
        success, err = state.session_mgr.relogin()
        if success:
            state.init_after_login()
            debug.log("重新登录成功")
            return True
        else:
            debug.log(f"重新登录失败: {err}")
            return False
    except Exception as e:
        debug.log(f"重新登录异常: {e}")
        return False


def create_temp_session(config: Any, student_id: str, password: str,
                         debug: DebugLogger) -> tuple[SessionManager, ApiClient] | None:
    """创建临时 session（用于签到同伴账号）。

    Returns:
        (SessionManager, ApiClient) 或 None（登录失败时）
    """
    try:
        mgr = SessionManager(config_manager=config)
        mgr.set_credentials(student_id, password)
        ok = mgr.login()
        if not ok:
            debug.log(f"临时登录失败: {student_id}")
            return None
        api = ApiClient(mgr)
        return mgr, api
    except Exception as e:
        debug.log(f"临时登录异常: {e}")
        return None
