"""签到路由：签到。"""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, HTTPException, Request

from server.models.schemas import CheckInResponse

logger = logging.getLogger("seathunter.server")

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


def _join_with_timeout(t: threading.Thread, timeout: float, label: str) -> bool:
    """等待线程结束，超时时记录警告。返回 True 表示超时。"""
    t.join(timeout=timeout)
    if t.is_alive():
        logger.warning("线程超时（%.0fs）: %s", timeout, label)
        return True
    return False


@router.post("/do/{booking_id}", response_model=CheckInResponse)
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

    if _join_with_timeout(t, 30, f"check_in({booking_id})"):
        return CheckInResponse(success=False, message="签到超时")

    return CheckInResponse(success=result["success"], message=result["message"])
