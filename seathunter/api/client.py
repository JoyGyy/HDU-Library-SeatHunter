"""HTTP API client for seat booking interactions.

Extracted from killer.py:324-422.
"""

from __future__ import annotations

import logging
from time import sleep
from datetime import datetime, timedelta
from typing import Dict, List, Any
from urllib.parse import unquote

import requests

from seathunter.api.token import generate_booking_data
from seathunter.auth.session_manager import SessionManager

logger = logging.getLogger("seathunter.api")


class ApiClient:
    """Handles all HTTP interactions with the library booking API."""

    def __init__(self, session_manager: SessionManager):
        self.session_mgr = session_manager

    @property
    def session(self) -> requests.Session:
        return self.session_mgr.session

    @property
    def base_url(self) -> str:
        return self.session_mgr.base_url

    def query_rooms(self) -> Dict[str, Any]:
        """Query all available room types and their data.

        Returns dict mapping room name -> room data dict.
        """
        url = self.base_url + "/Space/Category/list"
        self.session.cookies.update({"org_id": "104"})
        resp = self.session.get(url=url, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        raw_rooms = result["content"]["children"][1]["defaultItems"]
        rooms = {}
        for item in raw_rooms:
            room_name = item["name"]
            query_str = unquote(item["link"]["url"]).split("?")[1]
            room_resp = self.session.get(
                url=self.base_url + "/Seat/Index/searchSeats?" + query_str,
                timeout=30,
            ).json()
            rooms[room_name] = room_resp["data"]
            sleep(2)  # Rate limiting
        return rooms

    def query_seats(self, rooms: Dict[str, Any]) -> Dict[str, Any]:
        """Query seat information for each room's floors.

        Mutates rooms dict in-place, adding 'floors' key to each room.
        """
        now = datetime.now()
        if now.hour >= 22:
            now = (now + timedelta(days=1)).replace(hour=11, minute=0, second=0)

        for room_name, room_data in rooms.items():
            data = {
                "beginTime": now.timestamp(),
                "duration": 3600,
                "num": 1,
                "space_category[category_id]": room_data["space_category"]["category_id"],
                "space_category[content_id]": room_data["space_category"]["content_id"],
            }
            resp = self.session.post(
                url=self.base_url + "/Seat/Index/searchSeats",
                data=data,
                timeout=30,
            ).json()
            room_data["floors"] = {
                x["roomName"]: x
                for x in resp["allContent"]["children"][2]["children"]["children"]
            }
            for floor_data in room_data["floors"].values():
                floor_data["seats"] = floor_data["seatMap"]["POIs"]
            sleep(2)  # Rate limiting

        return rooms

    def book_seat(self, begin_time: datetime, duration_hours: int,
                  seat_ids: List[str], booker_uids: List[str]) -> Dict:
        """Execute a single booking attempt.

        Returns the raw API response dict.
        """
        data, api_token = generate_booking_data(
            begin_time, duration_hours, seat_ids, booker_uids
        )
        url = self.base_url + "/Seat/Index/bookSeats"
        self.session.headers["Api-Token"] = api_token
        # Content-Length kept for API compatibility (server-side anti-tampering check)
        self.session.headers["Content-Length"] = "114"
        try:
            resp = self.session.post(url=url, data=data, timeout=30)
            return resp.json()
        except Exception as e:
            logger.error("Booking request failed: %s", e)
            return {"CODE": "error", "MESSAGE": str(e)}
        finally:
            self.session.headers.pop("Api-Token", None)
            self.session.headers.pop("Content-Length", None)

    def get_floor_names(self, rooms: Dict, room_name: str) -> List[str]:
        """Get floor list for a room."""
        return list(rooms[room_name]["floors"].keys())

    def get_seats_by_room_and_floor(self, rooms: Dict, room_name: str,
                                     floor_name: str) -> List[Dict]:
        """Get seats for a specific room and floor."""
        return rooms[room_name]["floors"][floor_name]["seats"]

    def check_in(self, booking_id: str) -> tuple[bool, str, str]:
        """签到

        Args:
            booking_id: 预约 ID

        Returns:
            (成功?, 错误信息, booking_id)
        """
        url = self.base_url + "/Seat/Index/checkIn"
        params = {"bookingId": booking_id, "LAB_JSON": "1"}
        try:
            resp = self.session.post(url=url, params=params, timeout=30)
            if resp.status_code != 200:
                return (False, f"HTTP {resp.status_code}", booking_id)
            data = resp.json()
            if data.get("CODE") == "ok":
                result = data.get("DATA", {}).get("result", "")
                if result == "success":
                    logger.info("签到成功: bookingId=%s", booking_id)
                    return (True, "", booking_id)
                msg = data.get("DATA", {}).get("msg", "签到失败")
                logger.warning("签到失败: %s", msg)
                return (False, msg, booking_id)
            msg = data.get("MESSAGE", "签到失败")
            logger.warning("签到失败: %s", msg)
            return (False, msg, booking_id)
        except Exception as e:
            logger.error("签到请求异常: %s", e)
            return (False, str(e), booking_id)

    def get_my_bookings(self) -> List[Dict[str, Any]]:
        """获取当前用户的预约列表

        Returns:
            预约列表，每项包含 bookingId, devName, beginTime, endTime, status 等
        """
        url = self.base_url + "/Seat/Index/myBookingList"
        params = {"LAB_JSON": "1"}
        try:
            resp = self.session.get(url=url, params=params, timeout=30)
            if resp.status_code != 200:
                logger.warning("获取预约列表 HTTP %d", resp.status_code)
                return []
            data = resp.json()
            if data.get("CODE") == "ok":
                bookings = data.get("DATA", {}).get("bookingList", [])
                logger.info("获取预约列表成功，共 %d 条", len(bookings))
                return bookings
            logger.warning("获取预约列表失败: %s", data.get("MESSAGE", ""))
            return []
        except Exception as e:
            logger.error("获取预约列表异常: %s", e)
            return []
