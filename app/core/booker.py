"""预约逻辑：检查已预约 → 逐天逐座预约 → 重试。"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

from app.config import (
    BEGIN_HOUR, COMPANION_UID, DURATION_HOURS, KNOWN_SEAT_IDS,
    MAX_RETRY, NON_RETRYABLE_ERRORS, REQUEST_INTERVAL,
    RETRY_INTERVAL, STATUS_MAP, TARGET_SEATS, USER_UID,
    AUTO_BOOK_HOUR, AUTO_BOOK_MINUTE,
)

logger = logging.getLogger("seathunter.core.booker")


class DebugLogger:
    """收集调试日志，供前端显示。"""

    def __init__(self, max_lines: int = 50):
        self._lines: list[str] = []
        self._max = max_lines

    def log(self, msg: str) -> None:
        ts = (datetime.utcnow() + timedelta(hours=8)).strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self._lines.append(entry)
        if len(self._lines) > self._max:
            self._lines = self._lines[-self._max:]
        logger.info(msg)

    def get_recent(self, n: int = 20) -> list[str]:
        return self._lines[-n:]


def ensure_valid_session(state: Any, debug: DebugLogger) -> bool:
    """确保 session 有效，过期则重新登录。"""
    if state.api_client is None:
        debug.log("api_client 为空，尝试重新登录...")
        return _do_relogin(state, debug)

    try:
        resp = state.api_client.session.get(
            url=state.api_client.base_url + "/Seat/Index/myBookingList",
            timeout=15,
            allow_redirects=False,
        )
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


def book_for_all_dates(state: Any, debug: DebugLogger) -> str:
    """预约今天/明天/后天的座位。"""
    if not ensure_valid_session(state, debug):
        return "预约失败: 无法登录"

    api = state.api_client
    now = datetime.utcnow() + timedelta(hours=8)
    results: list[str] = []

    dates = _get_dates_to_book(now, debug)

    for date_idx, (target_date, target_time) in enumerate(dates):
        if date_idx > 0:
            debug.log(f"等待 {REQUEST_INTERVAL} 秒后预约下一天...")
            time.sleep(REQUEST_INTERVAL)

        debug.log(f"检查 {target_date} 的预约...")

        already = _check_already_booked(api, target_date, debug)
        if all(already.values()):
            debug.log(f"{target_date} 所有座位已预约")
            results.append(f"{target_date}: 已预约")
            continue

        for seat_idx, seat_num in enumerate(TARGET_SEATS):
            if seat_idx > 0:
                debug.log(f"等待 {REQUEST_INTERVAL} 秒后预约下一个座位...")
                time.sleep(REQUEST_INTERVAL)

            if already.get(seat_num):
                debug.log(f"座位 {seat_num} 在 {target_date} 已预约，跳过")
                continue

            seat_id = KNOWN_SEAT_IDS.get(seat_num)
            if not seat_id:
                debug.log(f"座位 {seat_num} 无 ID，跳过")
                results.append(f"{target_date} 座位{seat_num}: 无ID")
                continue

            booker_uids = _get_booker_uids(seat_num)
            resp = _book_with_retry(api, seat_id, seat_num, booker_uids,
                                     target_time, state, debug)
            code = resp.get("CODE", "")
            msg = resp.get("MESSAGE", resp.get("msg", ""))
            if code == "ok":
                results.append(f"{target_date} 座位{seat_num}: ✅")
            else:
                results.append(f"{target_date} 座位{seat_num}: ❌ {msg}")

    summary = "; ".join(results) if results else "无需预约"
    debug.log(f"预约完成: {summary}")
    return summary


def _get_dates_to_book(now: datetime, debug: DebugLogger) -> list[tuple]:
    """返回需要预约的 (date, datetime) 列表。"""
    dates = []
    for delta in [0, 1, 2]:
        target_date = (now + timedelta(days=delta)).date()
        target_time = datetime.combine(
            target_date,
            datetime.min.time().replace(hour=BEGIN_HOUR, minute=0)
        )
        if delta == 2:
            book_available_at = datetime.combine(
                now.date(),
                datetime.min.time().replace(hour=AUTO_BOOK_HOUR, minute=AUTO_BOOK_MINUTE)
            )
            if now < book_available_at:
                debug.log(f"后天 ({target_date}) 需在 {book_available_at.strftime('%H:%M')} 后才能预约")
                continue
        dates.append((target_date, target_time))
    return dates


def _check_already_booked(api: Any, target_date, debug: DebugLogger) -> dict[str, bool]:
    """检查指定日期是否已有预约。"""
    result = {s: False for s in TARGET_SEATS}
    try:
        bookings = api.get_my_bookings()
        for b in bookings:
            bt = b.get("beginTime")
            if bt is None:
                continue
            if bt.date() == target_date:
                seat_num = str(b.get("seatNum", ""))
                if seat_num in TARGET_SEATS:
                    status = str(b.get("status", ""))
                    if status in ("0", "1", "5", "6", "7"):
                        result[seat_num] = True
                        debug.log(f"座位 {seat_num} 在 {target_date} 已有预约 ({STATUS_MAP.get(status, status)})")
    except Exception as e:
        debug.log(f"检查已有预约失败: {e}")
    return result


def _get_booker_uids(seat_num: str) -> list[str]:
    """返回预约人 UID 列表。"""
    if seat_num == "99":
        return [COMPANION_UID, USER_UID]
    return [USER_UID]


def _book_with_retry(api: Any, seat_id: str, seat_num: str,
                      booker_uids: list[str], target_time: datetime,
                      state: Any, debug: DebugLogger) -> dict:
    """带重试的预约。"""
    resp = {}
    for attempt in range(1, MAX_RETRY + 1):
        debug.log(f"预约座位 {seat_num} (ID: {seat_id}) -> {target_time.strftime('%m-%d %H:%M')} [尝试 {attempt}/{MAX_RETRY}]")

        resp = api.book_seat(
            begin_time=target_time,
            duration_hours=DURATION_HOURS,
            seat_ids=[seat_id],
            booker_uids=booker_uids,
        )

        if isinstance(resp, dict) and resp.get("ui_type") == "com.Redirect":
            debug.log(f"座位 {seat_num} 遇到 CAS 重定向，尝试重新登录...")
            if _do_relogin_and_wait(state, debug):
                api = state.api_client
                continue
            else:
                return resp

        code = resp.get("CODE", "")
        if code == "ok":
            debug.log(f"座位 {seat_num} 预约成功")
            return resp

        msg = resp.get("MESSAGE", resp.get("msg", str(resp)))
        debug.log(f"座位 {seat_num} 预约失败: {msg}")

        if any(kw in msg for kw in NON_RETRYABLE_ERRORS):
            debug.log(f"不可重试的错误，停止: {msg}")
            return resp

        if attempt < MAX_RETRY:
            debug.log(f"等待 {RETRY_INTERVAL} 秒后重试...")
            time.sleep(RETRY_INTERVAL)

    return resp


def _do_relogin_and_wait(state: Any, debug: DebugLogger) -> bool:
    """重新登录并等待。"""
    ok = _do_relogin(state, debug)
    if ok:
        time.sleep(2)
    return ok
