"""Pydantic 请求/响应模型定义。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ── 通用 ────────────────────────────────────────────────

class MessageResponse(BaseModel):
    """通用消息响应。"""
    success: bool
    message: str = ""


# ── 认证 ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """登录请求。"""
    student_id: str = Field(..., description="学号")
    password: str = Field(..., description="密码")


class LoginResponse(BaseModel):
    """登录响应。"""
    success: bool
    message: str = ""
    uid: str = ""
    name: str = ""


class AuthStatusResponse(BaseModel):
    """认证状态响应。"""
    logged_in: bool
    uid: str = ""
    name: str = ""
    student_id: str = ""


# ── 预约 ────────────────────────────────────────────────

class BookingItem(BaseModel):
    """单条预约信息。"""
    booking_id: str = Field("", alias="bookingId")
    room_name: str = Field("", alias="roomName")
    seat_num: str = Field("", alias="seatNum")
    begin_time: Optional[datetime] = Field(None, alias="beginTime")
    end_time: Optional[datetime] = Field(None, alias="endTime")
    status: str = ""

    model_config = {"populate_by_name": True}


class BookingListResponse(BaseModel):
    """预约列表响应。"""
    success: bool
    message: str = ""
    bookings: List[BookingItem] = []


# ── 签到 ────────────────────────────────────────────────

class CheckInRequest(BaseModel):
    """签到请求。"""
    booking_id: str = Field(..., alias="bookingId")

    model_config = {"populate_by_name": True}


class CheckInResponse(BaseModel):
    """签到响应。"""
    success: bool
    message: str = ""


# ── 好友 ────────────────────────────────────────────────

class FriendItem(BaseModel):
    """好友信息。"""
    student_id: str
    name: str
    uid: str


class FriendListResponse(BaseModel):
    """好友列表响应。"""
    success: bool
    friends: List[FriendItem] = []


class AddFriendRequest(BaseModel):
    """添加好友请求。"""
    student_id: str
    password: str


class AddFriendResponse(BaseModel):
    """添加好友响应。"""
    success: bool
    message: str = ""
    name: str = ""
    uid: str = ""


class TestLoginResponse(BaseModel):
    """好友登录测试响应。"""
    success: bool
    message: str = ""


# ── 方案 (Plan) ─────────────────────────────────────────

class SeatInfoSchema(BaseModel):
    """座位信息。"""
    seat_id: str
    seat_num: str
    booker_uid: str = ""


class PlanSchema(BaseModel):
    """预约方案。"""
    id: str
    room_name: str
    floor_name: str = ""
    begin_time: str = Field(..., description="HH:MM:SS 格式")
    duration_hours: int = Field(..., ge=1)
    seats: List[SeatInfoSchema] = []
    target_date: str = ""
    booking_id: str = ""


class PlanListResponse(BaseModel):
    """方案列表响应。"""
    success: bool
    plans: List[PlanSchema] = []


class AddPlanRequest(BaseModel):
    """添加方案请求。"""
    id: str
    room_name: str
    floor_name: str = ""
    begin_time: str
    duration_hours: int = Field(..., ge=1)
    seats: List[SeatInfoSchema] = []
    target_date: str = ""


# ── 调度 (Schedule) ────────────────────────────────────

class DateMappingSchema(BaseModel):
    """日期-方案映射。"""
    target_date: str
    plan_ids: List[str]


class ScheduleItem(BaseModel):
    """调度项。"""
    mode: str = Field(..., description="'weekdays' 或 'dates'")
    enabled: bool = True
    target_weekdays: List[int] = []
    plan_ids: List[str] = []
    mappings: List[DateMappingSchema] = []


class ScheduleListResponse(BaseModel):
    """调度列表响应。"""
    success: bool
    schedules: List[ScheduleItem] = []


class AddScheduleRequest(BaseModel):
    """添加调度请求。"""
    mode: str
    enabled: bool = True
    target_weekdays: List[int] = []
    plan_ids: List[str] = []
    mappings: List[DateMappingSchema] = []


# ── 调度引擎状态 ────────────────────────────────────────

class SchedulerStatusResponse(BaseModel):
    """调度引擎状态响应。"""
    running: bool
    trigger_time: Optional[datetime] = None
    target_date: Optional[datetime] = None
    remaining_seconds: Optional[int] = None
