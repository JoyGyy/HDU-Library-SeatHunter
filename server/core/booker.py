"""预约逻辑。

检查已预约 → 逐天逐座预约 → 重试 → 记录结果。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict

from server.core.config import (
    BEGIN_HOUR, COMPANION_UID, DURATION_HOURS, KNOWN_SEAT_IDS,
    MAX_RETRY, NON_RETRYABLE_ERRORS, REQUEST_INTERVAL,
    RETRY_INTERVAL, STATUS_MAP, TARGET_SEATS, USER_UID,
    AUTO_BOOK_HOUR, AUTO_BOOK_MINUTE,
)
from server.core.session import DebugLogger, ensure_valid_session

logger = logging.getLogger("seathunter.core.booker")


def book_for_all_dates(state: Any, debug: DebugLogger) -> str:
    """预约今天/明天/后天的座位。

    Returns:
        结果摘要字符串。
    """
    # 确保 session 有效
    if not ensure_valid_session(state, debug):
        return "预约失败: 无法登录"

    api = state.api_client
    now = datetime.now()
    results: list[str] = []

    # 确定要预约的日期
    dates = _get_dates_to_book(now, debug)

    for date_idx, (target_date, target_time) in enumerate(dates):
        if date_idx > 0:
            debug.log(f"等待 {REQUEST_INTERVAL} 秒后预约下一天...")
            time.sleep(REQUEST_INTERVAL)

        debug.log(f"检查 {target_date} 的预约...")

        # 检查是否已预约
        already = _check_already_booked(api, target_date, debug)
        if all(already.values()):
            debug.log(f"{target_date} 所有座位已预约")
            results.append(f"{target_date}: 已预约")
            continue

        # 逐个座位预约
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

            # 预约人列表：当前用户必须在列
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
    for delta in [0, 1, 2]:  # 今天、明天、后天
        target_date = (now + timedelta(days=delta)).date()
        target_time = datetime.combine(
            target_date,
            datetime.min.time().replace(hour=BEGIN_HOUR, minute=0)
        )

        if delta == 2:
            # 后天：需在今天 20:00 后才能预约
            book_available_at = datetime.combine(
                now.date(),
                datetime.min.time().replace(hour=AUTO_BOOK_HOUR, minute=AUTO_BOOK_MINUTE)
            )
            if now < book_available_at:
                debug.log(f"后天 ({target_date}) 需在 {book_available_at.strftime('%H:%M')} 后才能预约")
                continue

        dates.append((target_date, target_time))
    return dates


def _check_already_booked(api: Any, target_date, debug: DebugLogger) -> Dict[str, bool]:
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
    """返回预约人 UID 列表。当前登录用户必须在列。"""
    if seat_num == "99":
        return [COMPANION_UID, USER_UID]
    return [USER_UID]


def _book_with_retry(api: Any, seat_id: str, seat_num: str,
                      booker_uids: list[str], target_time: datetime,
                      state: Any, debug: DebugLogger) -> dict:
    """带重试的预约。最多 MAX_RETRY 次，间隔 RETRY_INTERVAL 秒。"""
    for attempt in range(1, MAX_RETRY + 1):
        debug.log(f"预约座位 {seat_num} (ID: {seat_id}, 预约人: {booker_uids}) -> {target_time.strftime('%m-%d %H:%M')} [尝试 {attempt}/{MAX_RETRY}]")

        resp = api.book_seat(
            begin_time=target_time,
            duration_hours=DURATION_HOURS,
            seat_ids=[seat_id],
            booker_uids=booker_uids,
        )

        # CAS 重定向 → session 过期 → relogin 并重试
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

        # 不可重试的错误
        if any(kw in msg for kw in NON_RETRYABLE_ERRORS):
            debug.log(f"不可重试的错误，停止: {msg}")
            return resp

        # 还有重试机会
        if attempt < MAX_RETRY:
            debug.log(f"等待 {RETRY_INTERVAL} 秒后重试...")
            time.sleep(RETRY_INTERVAL)

    return resp


def _do_relogin_and_wait(state: Any, debug: DebugLogger) -> bool:
    """重新登录并等待。"""
    from server.core.session import _do_relogin
    ok = _do_relogin(state, debug)
    if ok:
        time.sleep(2)
    return ok
