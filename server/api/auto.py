"""自动预约和签到路由：定时任务 + 手动触发。"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from server.models.schemas import MessageResponse

logger = logging.getLogger("seathunter.server")

router = APIRouter()

# 固定配置
USER_CONFIG = {
    "student_id": "23051110",
    "password": "@Krz201314",
}

COMPANION_CONFIG = {
    "student_id": "23140322",
    "password": "Pangzidan0713#",
}

ROOM_NAME = "自习室二楼西"
SEAT_IDS = ["99", "100"]  # 99号=同伴, 100号=用户
BEGIN_TIME = "10:00:00"
DURATION_HOURS = 12

# 调度配置
BOOK_HOUR = 20  # 每晚8点预约
CHECKIN_HOUR = 9  # 每天9点
CHECKIN_MINUTE = 30  # 9:30签到

# 全局状态
_scheduler_running = False
_scheduler_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_last_book_result = ""
_last_checkin_result = ""


def _get_state(request: Request):
    return request.app.state.seathunter


def _format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S")


def _get_next_trigger(hour: int, minute: int = 0) -> datetime:
    """获取下次触发时间。"""
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _do_book(state) -> Dict[str, Any]:
    """执行预约：为用户和同伴预约后天的座位。"""
    global _last_book_result
    try:
        if state.api_client is None:
            _last_book_result = "未登录，无法预约"
            return {"success": False, "message": _last_book_result}

        # 计算后天日期
        target_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        begin_dt = datetime.strptime(f"{target_date} {BEGIN_TIME}", "%Y-%m-%d %H:%M:%S")

        # 获取座位 ID（从房间缓存查找）
        seat_ids = []
        if state.room_cache and state.room_cache.is_ready:
            seats = state.room_cache.get_seats(ROOM_NAME, "")
            if not seats:
                # 尝试所有楼层
                for floor in state.room_cache.get_floor_names(ROOM_NAME):
                    seats = state.room_cache.get_seats(ROOM_NAME, floor)
                    if seats:
                        break

            for seat_num in SEAT_IDS:
                found = False
                for s in seats:
                    s_num = str(s.get("title", "") or s.get("seatNum", "") or s.get("id", ""))
                    s_id = str(s.get("id", "") or s.get("seatId", "") or s.get("seat_id", ""))
                    if s_num == seat_num or s_id == seat_num:
                        seat_ids.append(s_id)
                        found = True
                        break
                if not found:
                    seat_ids.append(seat_num)  # fallback: 直接用座位号

        if not seat_ids:
            seat_ids = SEAT_IDS

        # 获取 booker_uids
        user_uid = state.session_mgr.uid or ""
        companion_uid = ""

        # 尝试获取同伴 UID（从好友列表）
        try:
            friends = state.friend_store.get_all()
            for f in friends:
                if f.get("student_id") == COMPANION_CONFIG["student_id"]:
                    companion_uid = f.get("uid", "")
                    break
        except:
            pass

        booker_uids = [companion_uid, user_uid]  # 99号=同伴, 100号=用户

        # 执行预约
        result = state.api_client.book_seat(
            begin_time=begin_dt,
            duration_hours=DURATION_HOURS,
            seat_ids=seat_ids,
            booker_uids=booker_uids,
        )

        _last_book_result = f"预约成功: {target_date} {ROOM_NAME} 座位 {', '.join(SEAT_IDS)}"
        logger.info(_last_book_result)
        return {"success": True, "message": _last_book_result}

    except Exception as e:
        _last_book_result = f"预约失败: {str(e)}"
        logger.error(_last_book_result)
        return {"success": False, "message": _last_book_result}


def _do_checkin(state) -> Dict[str, Any]:
    """执行签到：签到今天的预约。"""
    global _last_checkin_result
    try:
        if state.api_client is None:
            _last_checkin_result = "未登录，无法签到"
            return {"success": False, "message": _last_checkin_result}

        # 获取今天的预约列表
        bookings = state.api_client.get_my_bookings()

        if not bookings:
            _last_checkin_result = "没有找到今天的预约"
            return {"success": False, "message": _last_checkin_result}

        # 签到所有预约
        success_count = 0
        for b in bookings:
            booking_id = b.get("booking_id") or b.get("bookingId") or b.get("id")
            if booking_id:
                try:
                    state.api_client.check_in(booking_id)
                    success_count += 1
                    logger.info("签到成功: %s", booking_id)
                except Exception as e:
                    logger.warning("签到失败 %s: %s", booking_id, e)

        _last_checkin_result = f"签到完成: {success_count}/{len(bookings)} 成功"
        logger.info(_last_checkin_result)
        return {"success": True, "message": _last_checkin_result}

    except Exception as e:
        _last_checkin_result = f"签到失败: {str(e)}"
        logger.error(_last_checkin_result)
        return {"success": False, "message": _last_checkin_result}


def _scheduler_loop():
    """调度主循环。"""
    global _scheduler_running
    logger.info("自动调度已启动")

    while not _stop_event.is_set():
        now = datetime.now()

        # 检查是否到了预约时间（每晚20:00）
        if now.hour == BOOK_HOUR and now.minute == 0:
            logger.info("触发自动预约")
            # 需要获取 state，但这里无法直接访问 request
            # 通过全局变量存储 state
            if _auto_state:
                _do_book(_auto_state)
            _stop_event.wait(65)  # 等待 65 分钟避免重复触发

        # 检查是否到了签到时间（每天9:30）
        elif now.hour == CHECKIN_HOUR and now.minute == CHECKIN_MINUTE:
            logger.info("触发自动签到")
            if _auto_state:
                _do_checkin(_auto_state)
            _stop_event.wait(65)

        else:
            _stop_event.wait(30)  # 30秒检查一次

    _scheduler_running = False
    logger.info("自动调度已停止")


# 全局 state 引用（用于调度线程）
_auto_state = None


@router.get("/status")
def get_status(request: Request):
    """获取自动任务状态。"""
    state = _get_state(request)
    logged_in = bool(state.session_mgr and state.session_mgr.uid)

    next_book = _get_next_trigger(BOOK_HOUR)
    next_checkin = _get_next_trigger(CHECKIN_HOUR, CHECKIN_MINUTE)

    return {
        "logged_in": logged_in,
        "user_name": state.session_mgr.name if state.session_mgr else "",
        "auto_book_running": _scheduler_running,
        "auto_checkin_running": _scheduler_running,
        "next_book_time": next_book.strftime("%m-%d %H:%M"),
        "next_checkin_time": next_checkin.strftime("%m-%d %H:%M"),
        "last_book_result": _last_book_result,
        "last_checkin_result": _last_checkin_result,
    }


@router.get("/bookings")
def get_bookings(request: Request):
    """获取当前预约列表。"""
    state = _get_state(request)
    if state.api_client is None:
        return {"bookings": []}

    try:
        bookings = state.api_client.get_my_bookings()
        result = []
        for b in bookings:
            result.append({
                "booking_id": b.get("booking_id") or b.get("bookingId") or b.get("id"),
                "room_name": b.get("room_name") or b.get("roomName") or ROOM_NAME,
                "seat_num": b.get("seat_num") or b.get("seatNum") or "",
                "time_range": f"{b.get('begin_time') or b.get('beginTime') or ''} ~ {b.get('end_time') or b.get('endTime') or ''}",
                "status": b.get("status", ""),
                "user_name": state.session_mgr.name or "",
            })
        return {"bookings": result}
    except Exception as e:
        logger.error("获取预约失败: %s", e)
        return {"bookings": [], "error": str(e)}


@router.post("/book", response_model=MessageResponse)
def manual_book(request: Request):
    """手动触发预约。"""
    global _auto_state
    state = _get_state(request)
    _auto_state = state
    result = _do_book(state)
    return MessageResponse(success=result["success"], message=result["message"])


@router.post("/checkin", response_model=MessageResponse)
def manual_checkin(request: Request):
    """手动触发签到。"""
    global _auto_state
    state = _get_state(request)
    _auto_state = state
    result = _do_checkin(state)
    return MessageResponse(success=result["success"], message=result["message"])


@router.post("/start", response_model=MessageResponse)
def start_scheduler(request: Request):
    """启动自动调度。"""
    global _scheduler_running, _scheduler_thread, _auto_state
    state = _get_state(request)
    _auto_state = state

    if _scheduler_running:
        return MessageResponse(success=True, message="调度已在运行")

    _stop_event.clear()
    _scheduler_running = True
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True, name="AutoScheduler")
    _scheduler_thread.start()

    return MessageResponse(success=True, message="自动调度已启动")


@router.post("/stop", response_model=MessageResponse)
def stop_scheduler():
    """停止自动调度。"""
    global _scheduler_running
    _stop_event.set()
    _scheduler_running = False
    return MessageResponse(success=True, message="自动调度已停止")
