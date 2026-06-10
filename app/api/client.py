"""zhishulib API 客户端。封装所有 HTTP 调用。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import requests

from app.api.token import generate_booking_data
from app.auth.session import SessionManager
from app.config import BASE_URL

logger = logging.getLogger("seathunter.api")


class ApiClient:
    """封装所有 zhishulib.com API 调用。"""

    def __init__(self, session_mgr: SessionManager):
        self.session_mgr = session_mgr

    @property
    def session(self) -> requests.Session:
        return self.session_mgr.session

    @property
    def base_url(self) -> str:
        return BASE_URL

    def get_my_bookings(self) -> list[dict[str, Any]]:
        """获取当前用户的预约列表。"""
        url = self.base_url + "/Seat/Index/myBookingList"
        resp = self.session.get(url=url, params={"LAB_JSON": "1"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        bookings = []
        raw = data.get("data", {}).get("list", []) if isinstance(data.get("data"), dict) else []
        for item in raw:
            booking = {
                "bookingId": item.get("id", ""),
                "roomName": item.get("roomName", ""),
                "seatNum": str(item.get("seatNum", "")),
                "beginTime": datetime.fromtimestamp(item["beginTime"]) if item.get("beginTime") else None,
                "endTime": datetime.fromtimestamp(item["endTime"]) if item.get("endTime") else None,
                "status": str(item.get("status", "")),
            }
            bookings.append(booking)
        return bookings

    def book_seat(
        self,
        begin_time: datetime,
        duration_hours: int,
        seat_ids: list[str],
        booker_uids: list[str],
    ) -> dict[str, Any]:
        """预约座位。"""
        data, api_token = generate_booking_data(
            begin_time, duration_hours, seat_ids, booker_uids
        )
        url = self.base_url + "/Seat/Index/bookSeats"
        self.session.headers["Api-Token"] = api_token
        self.session.headers["Content-Length"] = "114"
        try:
            resp = self.session.post(url=url, data=data, timeout=30)
            return resp.json()
        except Exception as e:
            logger.error("预约请求失败: %s", e)
            return {"CODE": "error", "MESSAGE": str(e)}
        finally:
            self.session.headers.pop("Api-Token", None)
            self.session.headers.pop("Content-Length", None)

    def check_in(self, booking_id: str) -> tuple[bool, str, str]:
        """签到。"""
        url = self.base_url + "/Seat/Index/checkIn"
        try:
            resp = self.session.post(
                url=url,
                data={"id": booking_id, "LAB_JSON": "1"},
                timeout=15,
            )
            data = resp.json()
            code = data.get("CODE", "")
            if code == "ok":
                return True, "", booking_id
            msg = data.get("MESSAGE", data.get("msg", "未知错误"))
            return False, msg, booking_id
        except Exception as e:
            logger.error("签到请求失败: %s", e)
            return False, str(e), booking_id
