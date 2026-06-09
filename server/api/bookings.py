"""预约路由：查询当前用户的预约列表。"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from server.models.schemas import BookingListResponse

logger = logging.getLogger("seathunter.server")

router = APIRouter()


def _get_state(request: Request):
    """从 app.state 获取全局 AppState 实例。"""
    return request.app.state.seathunter


def _join_with_timeout(t: threading.Thread, timeout: float, label: str) -> bool:
    """等待线程结束，超时时记录警告。返回 True 表示超时。"""
    t.join(timeout=timeout)
    if t.is_alive():
        logger.warning("线程超时（%.0fs）: %s", timeout, label)
        return True
    return False


@router.get("", response_model=BookingListResponse)
def list_bookings(request: Request):
    """获取当前用户的预约列表（后台线程调用 API）。"""
    state = _get_state(request)

    if state.api_client is None:
        raise HTTPException(status_code=401, detail="尚未登录，请先登录")

    result: List[Dict[str, Any]] = []
    error: Optional[str] = None

    def _fetch():
        nonlocal result, error
        try:
            result = state.api_client.get_my_bookings()
        except Exception as e:
            error = str(e)

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()

    if _join_with_timeout(t, 30, "list_bookings"):
        raise HTTPException(status_code=504, detail="获取预约列表超时")
    if error:
        raise HTTPException(status_code=500, detail=f"获取预约列表失败: {error}")

    return BookingListResponse(success=True, bookings=result)
