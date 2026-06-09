"""全自动预约与签到模块。

固定配置：你和同伴的账号、座位、时间。
- 预约：每天 20:00 自动预约后天的座位（99号+100号）
- 签到：每天 9:30 自动签到
- 支持预约今天/明天/后天的座位（后天需20:00后）
- 已预约的日期不重复预约
- 99号和100号独立预约，互不影响
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("seathunter.server")
router = APIRouter()

# ─── 固定配置 ────────────────────────────────────────────────────────────────────
# 你的账号
USER_STUDENT_ID = "23051110"
USER_PASSWORD = "@Krz201314"
USER_UID = "303687"

# 同伴的账号
COMPANION_STUDENT_ID = "23140322"
COMPANION_PASSWORD = "Pangzidan0713#"
COMPANION_UID = "305033"

# 固定座位（SeatInfo 的 title 字段，即座位号）
TARGET_SEATS = ["99", "100"]

# 固定房间和楼层
ROOM_NAME = "自习室二楼西"
FLOOR_NAME = "二楼西"

# 固定时间：10:00 开始，12 小时
BEGIN_HOUR = 10
DURATION_HOURS = 12

# 自动触发时间
AUTO_BOOK_HOUR = 20  # 每天 20:00 预约
AUTO_BOOK_MINUTE = 0
AUTO_CHECKIN_HOUR = 9  # 每天 9:30 签到
AUTO_CHECKIN_MINUTE = 30

# 状态码中文映射
STATUS_MAP = {
    "0": "待签到",
    "1": "已签到",
    "2": "已结束",
    "3": "已取消",
    "4": "已过期",
    "5": "预约中",
    "6": "待确认",
    "7": "已确认",
}


# ─── 全局状态 ─────────────────────────────────────────────────────────────────────
_auto_state: Dict[str, Any] = {
    "running": False,
    "logged_in": False,
    "student_id": USER_STUDENT_ID,
    "last_book_result": "",
    "last_checkin_result": "",
    "last_error": "",
}


def _get_state(request: Request):
    return request.app.state.seathunter


# ─── 预约逻辑 ─────────────────────────────────────────────────────────────────────
def _search_seats_for_time(api_client, target_time: datetime) -> Dict[str, Any]:
    """搜索指定时间的座位，返回座位号 -> 真实 seat_id 的映射。"""
    try:
        # 获取房间信息
        rooms = api_client.query_rooms()
        if ROOM_NAME not in rooms:
            logger.error("房间 '%s' 未找到", ROOM_NAME)
            return {}

        room_data = rooms[ROOM_NAME]
        category_id = room_data["space_category"]["category_id"]
        content_id = room_data["space_category"]["content_id"]

        # 搜索指定时间的座位
        data = {
            "beginTime": int(target_time.timestamp()),
            "duration": DURATION_HOURS * 3600,
            "num": 1,
            "space_category[category_id]": category_id,
            "space_category[content_id]": content_id,
        }
        resp = api_client.session.post(
            url=api_client.base_url + "/Seat/Index/searchSeats",
            data=data,
            timeout=30,
        ).json()

        # 从搜索结果中找到目标楼层的座位
        seat_map = {}
        for child in resp.get("allContent", {}).get("children", []):
            if isinstance(child, dict) and "children" in child:
                for floor in child.get("children", {}).get("children", []):
                    if isinstance(floor, dict) and floor.get("roomName") == FLOOR_NAME:
                        pois = floor.get("seatMap", {}).get("POIs", [])
                        for poi in pois:
                            title = poi.get("title", "")
                            seat_id = str(poi.get("id", ""))
                            if title in TARGET_SEATS:
                                seat_map[title] = seat_id
                                logger.info("找到座位 %s -> ID %s", title, seat_id)

        return seat_map
    except Exception as e:
        logger.error("搜索座位失败: %s", e)
        return {}


def _check_already_booked(api_client, target_date: datetime.date) -> Dict[str, bool]:
    """检查指定日期是否已有预约，返回 {座位号: 是否已预约}。"""
    result = {s: False for s in TARGET_SEATS}
    try:
        bookings = api_client.get_my_bookings()
        for b in bookings:
            if b.get("beginTime") and b["beginTime"].date() == target_date:
                seat_num = b.get("seatNum", "")
                if seat_num in TARGET_SEATS:
                    status = b.get("status", "")
                    # 状态 0=待签到, 1=已签到, 5=预约中 都算已预约
                    if status in ("0", "1", "5", "6", "7"):
                        result[seat_num] = True
                        logger.info("座位 %s 在 %s 已有预约 (状态: %s)", seat_num, target_date, status)
    except Exception as e:
        logger.warning("检查已有预约失败: %s", e)
    return result


def _do_book_single(api_client, seat_id: str, seat_num: str,
                     booker_uid: str, target_time: datetime) -> Dict:
    """预约单个座位。"""
    logger.info("预约座位 %s (ID: %s) -> %s", seat_num, seat_id, target_time)
    try:
        resp = api_client.book_seat(
            begin_time=target_time,
            duration_hours=DURATION_HOURS,
            seat_ids=[seat_id],
            booker_uids=[booker_uid],
        )
        code = resp.get("CODE", "")
        if code == "ok":
            logger.info("座位 %s 预约成功", seat_num)
        else:
            msg = resp.get("MESSAGE", resp.get("msg", str(resp)))
            logger.warning("座位 %s 预约失败: %s", seat_num, msg)
        return resp
    except Exception as e:
        logger.error("预约座位 %s 异常: %s", seat_num, e)
        return {"CODE": "error", "MESSAGE": str(e)}


def _do_book(state) -> None:
    """预约逻辑：预约今天/明天/后天的座位。"""
    try:
        api = state.api_client
        now = datetime.now()
        results = []

        # 确定要预约哪些天
        dates_to_book = []
        for delta in [0, 1, 2]:  # 今天、明天、后天
            target_date = (now + timedelta(days=delta)).date()
            target_time = datetime.combine(target_date, datetime.min.time().replace(
                hour=BEGIN_HOUR, minute=0
            ))

            if delta == 2:
                # 后天：需要在今天 20:00 后才能预约
                book_available_at = datetime.combine(
                    now.date(), datetime.min.time().replace(
                        hour=AUTO_BOOK_HOUR, minute=AUTO_BOOK_MINUTE
                    )
                )
                if now < book_available_at:
                    logger.info("后天座位需在 %s 后才能预约，跳过", book_available_at)
                    continue

            dates_to_book.append((target_date, target_time))

        for target_date, target_time in dates_to_book:
            logger.info("检查 %s 的预约...", target_date)

            # 检查是否已预约
            already_booked = _check_already_booked(api, target_date)
            if all(already_booked.values()):
                logger.info("%s 所有座位已预约，跳过", target_date)
                results.append(f"{target_date}: 已预约")
                continue

            # 搜索可用座位（获取真实 seat_id）
            seat_map = _search_seats_for_time(api, target_time)
            if not seat_map:
                logger.warning("%s 未找到可用座位", target_date)
                results.append(f"{target_date}: 未找到座位")
                continue

            # 逐个预约座位（独立预约，互不影响）
            for seat_num in TARGET_SEATS:
                if already_booked.get(seat_num):
                    logger.info("座位 %s 在 %s 已预约，跳过", seat_num, target_date)
                    continue

                seat_id = seat_map.get(seat_num)
                if not seat_id:
                    logger.warning("座位 %s 未在搜索结果中找到", seat_num)
                    results.append(f"{target_date} 座位{seat_num}: 未找到")
                    continue

                # 确定预约人 UID
                booker_uid = COMPANION_UID if seat_num == "99" else USER_UID

                resp = _do_book_single(api, seat_id, seat_num, booker_uid, target_time)
                code = resp.get("CODE", "")
                msg = resp.get("MESSAGE", resp.get("msg", ""))
                if code == "ok":
                    results.append(f"{target_date} 座位{seat_num}: ✅ 成功")
                else:
                    results.append(f"{target_date} 座位{seat_num}: ❌ {msg}")

        _auto_state["last_book_result"] = "; ".join(results) if results else "无需预约"
        _auto_state["last_error"] = ""
        logger.info("预约完成: %s", _auto_state["last_book_result"])
    except Exception as e:
        _auto_state["last_error"] = str(e)
        _auto_state["last_book_result"] = f"预约异常: {e}"
        logger.error("预约异常: %s", e)


# ─── 签到逻辑 ─────────────────────────────────────────────────────────────────────
def _do_checkin_for_user(student_id: str, password: str, user_name: str,
                          state) -> List[str]:
    """登录指定用户并签到其预约。"""
    results = []
    try:
        from seathunter.auth.session_manager import SessionManager
        from seathunter.api.client import ApiClient as LibApiClient

        # 创建临时会话
        temp_session_mgr = SessionManager()
        temp_session_mgr.set_credentials(student_id, password)
        login_ok = temp_session_mgr.login()
        if not login_ok:
            results.append(f"{user_name}: ❌ 登录失败")
            return results

        temp_api = LibApiClient(temp_session_mgr)
        bookings = temp_api.get_my_bookings()

        today = datetime.now().date()
        checked_count = 0
        for b in bookings:
            if not b.get("beginTime"):
                continue
            if b["beginTime"].date() != today:
                continue
            if b.get("status") != "0":
                continue

            booking_id = b.get("bookingId", "")
            seat_num = b.get("seatNum", "")
            success, msg, _ = temp_api.check_in(booking_id)
            if success:
                results.append(f"{user_name} 座位{seat_num}: ✅ 签到成功")
                checked_count += 1
            else:
                results.append(f"{user_name} 座位{seat_num}: ❌ {msg}")

        if checked_count == 0:
            results.append(f"{user_name}: 无需签到的预约")

        temp_session_mgr.logout()
    except Exception as e:
        results.append(f"{user_name}: ❌ 异常 {e}")
        logger.error("签到异常 (%s): %s", user_name, e)

    return results


def _do_checkin(state) -> None:
    """签到逻辑：签到你和同伴的预约。"""
    all_results = []

    # 签到你的预约
    your_results = _do_checkin_for_user(
        USER_STUDENT_ID, USER_PASSWORD, "我", state
    )
    all_results.extend(your_results)

    # 签到同伴的预约
    companion_results = _do_checkin_for_user(
        COMPANION_STUDENT_ID, COMPANION_PASSWORD, "同伴", state
    )
    all_results.extend(companion_results)

    _auto_state["last_checkin_result"] = "; ".join(all_results)
    _auto_state["last_error"] = ""
    logger.info("签到完成: %s", _auto_state["last_checkin_result"])


# ─── 调度器 ───────────────────────────────────────────────────────────────────────
def _scheduler_loop(state) -> None:
    """后台调度器：检查是否到触发时间。"""
    logger.info("调度器已启动")
    last_book_date: Optional[str] = None
    last_checkin_date: Optional[str] = None

    while _auto_state["running"]:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            # 检查预约时间：每天 20:00
            if (now.hour == AUTO_BOOK_HOUR
                    and now.minute == AUTO_BOOK_MINUTE
                    and last_book_date != today_str):
                logger.info("触发自动预约")
                last_book_date = today_str
                threading.Thread(
                    target=_do_book, args=(state,), daemon=True
                ).start()

            # 检查签到时间：每天 9:30
            if (now.hour == AUTO_CHECKIN_HOUR
                    and now.minute == AUTO_CHECKIN_MINUTE
                    and last_checkin_date != today_str):
                logger.info("触发自动签到")
                last_checkin_date = today_str
                threading.Thread(
                    target=_do_checkin, args=(state,), daemon=True
                ).start()

        except Exception as e:
            logger.error("调度器异常: %s", e)

        # 每 30 秒检查一次
        for _ in range(30):
            if not _auto_state["running"]:
                break
            import time
            time.sleep(1)

    logger.info("调度器已停止")


# ─── API 路由 ─────────────────────────────────────────────────────────────────────
@router.get("/status")
def get_status(request: Request):
    """获取当前状态。"""
    state = _get_state(request)
    return {
        "logged_in": state.api_client is not None,
        "running": _auto_state["running"],
        "student_id": _auto_state["student_id"],
        "last_book_result": _auto_state["last_book_result"],
        "last_checkin_result": _auto_state["last_checkin_result"],
        "last_error": _auto_state["last_error"],
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
    state = _get_state(request)
    if state.api_client is None:
        raise HTTPException(status_code=401, detail="尚未登录")

    all_bookings: List[Dict[str, Any]] = []

    # 获取你的预约
    try:
        your_bookings = state.api_client.get_my_bookings()
        for b in your_bookings:
            all_bookings.append({
                "user": "我",
                "roomName": b.get("roomName", ""),
                "seatNum": b.get("seatNum", ""),
                "beginTime": b["beginTime"].strftime("%m-%d %H:%M") if b.get("beginTime") else "",
                "endTime": b["endTime"].strftime("%H:%M") if b.get("endTime") else "",
                "status": STATUS_MAP.get(b.get("status", ""), b.get("status", "")),
                "bookingId": b.get("bookingId", ""),
            })
    except Exception as e:
        logger.warning("获取你的预约失败: %s", e)

    # 获取同伴的预约
    try:
        from seathunter.auth.session_manager import SessionManager
        from seathunter.api.client import ApiClient as LibApiClient

        temp_mgr = SessionManager()
        temp_mgr.set_credentials(COMPANION_STUDENT_ID, COMPANION_PASSWORD)
        if temp_mgr.login():
            temp_api = LibApiClient(temp_mgr)
            companion_bookings = temp_api.get_my_bookings()
            for b in companion_bookings:
                all_bookings.append({
                    "user": "同伴",
                    "roomName": b.get("roomName", ""),
                    "seatNum": b.get("seatNum", ""),
                    "beginTime": b["beginTime"].strftime("%m-%d %H:%M") if b.get("beginTime") else "",
                    "endTime": b["endTime"].strftime("%H:%M") if b.get("endTime") else "",
                    "status": STATUS_MAP.get(b.get("status", ""), b.get("status", "")),
                    "bookingId": b.get("bookingId", ""),
                })
            temp_mgr.logout()
    except Exception as e:
        logger.warning("获取同伴预约失败: %s", e)

    return {"bookings": all_bookings}


@router.post("/book")
def manual_book(request: Request):
    """手动触发预约（立即执行）。"""
    state = _get_state(request)
    if state.api_client is None:
        raise HTTPException(status_code=401, detail="尚未登录")

    threading.Thread(target=_do_book, args=(state,), daemon=True).start()
    return {"ok": True, "message": "正在预约，请稍后刷新查看结果"}


@router.post("/checkin")
def manual_checkin(request: Request):
    """手动触发签到（立即执行）。"""
    state = _get_state(request)
    if state.api_client is None:
        raise HTTPException(status_code=401, detail="尚未登录")

    threading.Thread(target=_do_checkin, args=(state,), daemon=True).start()
    return {"ok": True, "message": "正在签到，请稍后刷新查看结果"}


@router.post("/start")
def start_scheduler(request: Request):
    """启动自动调度器。"""
    if _auto_state["running"]:
        return {"ok": True, "message": "调度器已在运行"}

    _auto_state["running"] = True
    state = _get_state(request)
    threading.Thread(
        target=_scheduler_loop, args=(state,), daemon=True, name="AutoScheduler"
    ).start()
    return {"ok": True, "message": "调度器已启动"}


@router.post("/stop")
def stop_scheduler():
    """停止自动调度器。"""
    _auto_state["running"] = False
    return {"ok": True, "message": "调度器已停止"}
