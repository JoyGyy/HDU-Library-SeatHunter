"""签到路由：签到、获取预约列表。"""

from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException, Request

from server.models.schemas import (
    BookingItem,
    BookingListResponse,
    CheckInResponse,
    MessageResponse,
)

router = APIRouter()


def _get_state(request: Request):
    """从 app.state 获取全局 AppState 实例。"""
    return request.app.state.seathunter


def _require_api_client(request: Request):
    """检查是否已登录，未登录则返回 401。"""
    state = _get_state(request)
    if state.api_client is None:
        raise HTTPException(status_code=401, detail="未登录，请先登录")
    return state


@router.post("/{booking_id}", response_model=CheckInResponse)
def check_in(booking_id: str, request: Request):
    """签到：在后台线程中调用 API。"""
    state = _require_api_client(request)

    result = {"success": False, "message": "", "bid": ""}

    def _do_checkin():
        result["success"], result["message"], result["bid"] = (
            state.api_client.check_in(booking_id)
        )

    t = threading.Thread(target=_do_checkin, daemon=True)
    t.start()
    t.join(timeout=30)

    if t.is_alive():
        return CheckInResponse(success=False, message="签到超时")

    return CheckInResponse(success=result["success"], message=result["message"])


@router.get("/bookings", response_model=BookingListResponse)
def get_bookings(request: Request):
    """获取当前用户的预约列表。"""
    state = _require_api_client(request)

    result = {"bookings": []}

    def _do_fetch():
        result["bookings"] = state.api_client.get_my_bookings()

    t = threading.Thread(target=_do_fetch, daemon=True)
    t.start()
    t.join(timeout=30)

    if t.is_alive():
        return BookingListResponse(success=False, message="获取预约列表超时")

    items = [BookingItem(**b) for b in result["bookings"]]
    return BookingListResponse(success=True, bookings=items)
