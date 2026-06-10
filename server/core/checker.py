"""签到逻辑。

分别登录你和同伴的账号，签到今天的预约。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from server.core.config import (
    COMPANION_PASSWORD, COMPANION_STUDENT_ID,
    MAX_RETRY, REQUEST_INTERVAL, RETRY_INTERVAL,
    USER_PASSWORD, USER_STUDENT_ID,
)
from server.core.session import DebugLogger, create_temp_session

logger = logging.getLogger("seathunter.core.checker")


def checkin_for_all_users(state: Any, debug: DebugLogger) -> str:
    """签到你和同伴的预约。

    Returns:
        结果摘要字符串。
    """
    results: list[str] = []

    # 签到你的预约
    your_results = _checkin_user(
        USER_STUDENT_ID, USER_PASSWORD, "我", state, debug
    )
    results.extend(your_results)

    # 等待间隔
    debug.log(f"等待 {REQUEST_INTERVAL} 秒后签到同伴...")
    time.sleep(REQUEST_INTERVAL)

    # 签到同伴的预约
    companion_results = _checkin_user(
        COMPANION_STUDENT_ID, COMPANION_PASSWORD, "同伴", state, debug
    )
    results.extend(companion_results)

    summary = "; ".join(results)
    debug.log(f"签到完成: {summary}")
    return summary


def _checkin_user(student_id: str, password: str, user_name: str,
                   state: Any, debug: DebugLogger) -> list[str]:
    """登录指定用户并签到其今天的预约。"""
    results: list[str] = []

    # 创建临时 session
    session_data = create_temp_session(state.config, student_id, password, debug)
    if session_data is None:
        results.append(f"{user_name}: ❌ 登录失败")
        return results

    temp_mgr, temp_api = session_data

    try:
        bookings = temp_api.get_my_bookings()
        today = datetime.now().date()
        checked = 0

        for b in bookings:
            bt = b.get("beginTime")
            if bt is None or bt.date() != today:
                continue
            if b.get("status") != "0":  # 只签到"待签到"的
                continue

            booking_id = b.get("bookingId", "")
            seat_num = b.get("seatNum", "")
            success, msg, _ = _checkin_with_retry(temp_api, booking_id, seat_num, debug)
            if success:
                results.append(f"{user_name} 座位{seat_num}: ✅ 签到成功")
                checked += 1
            else:
                results.append(f"{user_name} 座位{seat_num}: ❌ {msg}")

        if checked == 0:
            results.append(f"{user_name}: 无需签到")
    except Exception as e:
        results.append(f"{user_name}: ❌ 异常 {e}")
        debug.log(f"签到异常 ({user_name}): {e}")
    finally:
        try:
            temp_mgr.session.close()
        except Exception:
            pass

    return results


def _checkin_with_retry(api: Any, booking_id: str, seat_num: str,
                         debug: DebugLogger) -> tuple[bool, str, str]:
    """带重试的签到。"""
    for attempt in range(1, MAX_RETRY + 1):
        debug.log(f"签到座位 {seat_num} (bookingId: {booking_id}) [尝试 {attempt}/{MAX_RETRY}]")
        success, msg, _ = api.check_in(booking_id)
        if success:
            return (True, "", booking_id)
        debug.log(f"签到失败: {msg}")
        if attempt < MAX_RETRY:
            debug.log(f"等待 {RETRY_INTERVAL} 秒后重试...")
            time.sleep(RETRY_INTERVAL)
    return (False, msg, booking_id)
