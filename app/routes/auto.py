"""API 路由：状态查询、手动预约/签到、调度器控制。"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import (
    AUTO_BOOK_HOUR, AUTO_BOOK_MINUTE,
    AUTO_CHECKIN_HOUR, AUTO_CHECKIN_MINUTE,
    ROOM_NAME, STATUS_MAP, TARGET_SEATS,
)
from app.core.scheduler import get_state, get_debug_log, get_scheduler
from app.core.booker import book_for_all_dates, ensure_valid_session
from app.core.checker import checkin_for_all_users

router = APIRouter()


def _get_app_state(request: Request):
    return request.app.state.app_state


@router.get("/status")
def get_status():
    """获取当前状态。"""
    return {
        **get_state(),
        "target_seats": TARGET_SEATS,
        "room_name": ROOM_NAME,
        "schedule": {
            "book": f"每天 {AUTO_BOOK_HOUR}:{AUTO_BOOK_MINUTE:02d}",
            "checkin": f"每天 {AUTO_CHECKIN_HOUR}:{AUTO_CHECKIN_MINUTE:02d}",
        },
    }


@router.get("/bookings")
def get_bookings(request: Request):
    """获取你和同伴的预约列表。"""
    from app.config import COMPANION_PASSWORD, COMPANION_STUDENT_ID
    from app.auth.session import SessionManager
    from app.api.client import ApiClient

    app_state = _get_app_state(request)
    debug = get_debug_log()

    if app_state.api_client is None:
        if not ensure_valid_session(app_state, debug):
            raise HTTPException(status_code=401, detail="尚未登录")

    all_bookings: list[dict[str, Any]] = []

    # 你的预约
    try:
        for b in app_state.api_client.get_my_bookings():
            all_bookings.append(_format_booking(b, "我"))
    except Exception as e:
        debug.log(f"获取你的预约失败: {e}")

    # 同伴的预约（缓存 session，避免每次重新登录）
    try:
        if app_state.companion_api is None:
            mgr = SessionManager(COMPANION_STUDENT_ID, COMPANION_PASSWORD)
            mgr.init_session()
            success, _ = mgr.login(debug=debug)
            if success:
                app_state.companion_api = ApiClient(mgr)

        if app_state.companion_api:
            try:
                for b in app_state.companion_api.get_my_bookings():
                    all_bookings.append(_format_booking(b, "同伴"))
            except Exception:
                # session 可能过期，重新登录
                debug.log("同伴 session 过期，重新登录...")
                mgr = SessionManager(COMPANION_STUDENT_ID, COMPANION_PASSWORD)
                mgr.init_session()
                success, _ = mgr.login(debug=debug)
                if success:
                    app_state.companion_api = ApiClient(mgr)
                    for b in app_state.companion_api.get_my_bookings():
                        all_bookings.append(_format_booking(b, "同伴"))
    except Exception as e:
        debug.log(f"获取同伴预约失败: {e}")

    return {"bookings": all_bookings}


def _format_booking(b: dict, user: str) -> dict:
    """格式化单条预约。"""
    from datetime import datetime
    bt = b.get("beginTime")
    et = b.get("endTime")
    # 同一天只显示时间，跨天显示完整日期
    if isinstance(bt, datetime) and isinstance(et, datetime):
        if bt.date() == et.date():
            time_str = f"{bt.strftime('%m-%d %H:%M')} - {et.strftime('%H:%M')}"
        else:
            time_str = f"{bt.strftime('%m-%d %H:%M')} - {et.strftime('%m-%d %H:%M')}"
    else:
        time_str = f"{bt or ''} - {et or ''}"
    return {
        "user": user,
        "roomName": b.get("roomName", ""),
        "seatNum": str(b.get("seatNum", "")),
        "time": time_str,
        "status": STATUS_MAP.get(str(b.get("status", "")), str(b.get("status", ""))),
        "bookingId": str(b.get("bookingId", "")),
    }


@router.post("/book")
def manual_book(request: Request):
    """手动触发预约。"""
    app_state = _get_app_state(request)
    if app_state.api_client is None:
        raise HTTPException(status_code=401, detail="尚未登录")

    def _run():
        result = book_for_all_dates(app_state, get_debug_log())
        from app.core.scheduler import _state
        _state["last_book_result"] = result

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": "正在预约，请稍后刷新查看结果"}


@router.post("/checkin")
def manual_checkin(request: Request):
    """手动触发签到。"""
    app_state = _get_app_state(request)
    if app_state.api_client is None:
        raise HTTPException(status_code=401, detail="尚未登录")

    def _run():
        result = checkin_for_all_users(app_state, get_debug_log())
        from app.core.scheduler import _state
        _state["last_checkin_result"] = result

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": "正在签到，请稍后刷新查看结果"}


@router.post("/start")
def start_scheduler(request: Request):
    """启动调度器。"""
    scheduler = get_scheduler()
    if scheduler is None:
        app_state = _get_app_state(request)
        from app.core.scheduler import init_scheduler
        scheduler = init_scheduler(app_state)
    scheduler.start()
    return {"ok": True, "message": "调度器已启动"}


@router.post("/stop")
def stop_scheduler():
    """停止调度器。"""
    scheduler = get_scheduler()
    if scheduler:
        scheduler.stop()
    return {"ok": True, "message": "调度器已停止"}
