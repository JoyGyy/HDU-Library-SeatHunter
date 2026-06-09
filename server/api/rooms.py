"""房间与座位查询路由。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("seathunter.server")

router = APIRouter()


def _get_state(request: Request):
    return request.app.state.seathunter


@router.get("")
def list_rooms(request: Request):
    """获取房间列表。"""
    state = _get_state(request)
    if state.room_cache is None:
        raise HTTPException(status_code=401, detail="尚未登录")
    room_names = state.room_cache.get_room_names()
    return {"rooms": room_names}


@router.get("/{room_name}/floors")
def list_floors(room_name: str, request: Request):
    """获取指定房间的楼层列表。"""
    state = _get_state(request)
    if state.room_cache is None:
        raise HTTPException(status_code=401, detail="尚未登录")
    floors = state.room_cache.get_floor_names(room_name)
    if not floors:
        raise HTTPException(status_code=404, detail=f"房间 '{room_name}' 不存在")
    return {"floors": floors}


@router.get("/{room_name}/floors/{floor_name}/seats")
def list_seats(room_name: str, floor_name: str, request: Request):
    """获取指定楼层的座位列表。"""
    state = _get_state(request)
    if state.room_cache is None:
        raise HTTPException(status_code=401, detail="尚未登录")
    seats = state.room_cache.get_seats(room_name, floor_name)
    return {"seats": seats}
