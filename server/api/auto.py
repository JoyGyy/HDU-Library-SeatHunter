"""全自动预约与签到模块。

固定配置：你和同伴的账号、座位、时间。
- 预约：每天 20:00 自动预约后天的座位（99号+100号）
- 签到：每天 9:30 自动签到
- 支持预约今天/明天/后天的座位（后天需20:00后）
- 已预约的日期不重复预约
- 99号和100号独立预约，互不影响
"""

from __future__ import annotations

import json
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

# 已知座位 ID（兜底用，优先从 API 获取）
KNOWN_SEAT_IDS = {
    "99": "60810",
    "100": "60811",
}

# 固定房间和楼层
ROOM_NAME = "自习室"
FLOOR_NAME = "比特庭园（二楼西）"

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
    "debug_log": [],  # 调试日志
}


def _debug(msg: str) -> None:
    """记录调试信息到状态中，方便前端查看。"""
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    _auto_state["debug_log"].append(entry)
    # 只保留最近 50 条
    if len(_auto_state["debug_log"]) > 50:
        _auto_state["debug_log"] = _auto_state["debug_log"][-50:]
    logger.info(msg)


def _get_state(request: Request):
    return request.app.state.seathunter


# ─── 座位 ID 查找 ────────────────────────────────────────────────────────────────
def _get_seat_ids_from_cache(state) -> Dict[str, str]:
    """从 RoomCache 获取目标座位的真实 ID。返回 {座位号: seat_id}。"""
    seat_map: Dict[str, str] = {}

    if state.room_cache is None or not state.room_cache.is_ready:
        _debug("RoomCache 未就绪")
        return seat_map

    # 打印可用房间和楼层
    room_names = state.room_cache.get_room_names()
    _debug(f"可用房间: {room_names}")

    if ROOM_NAME not in room_names:
        _debug(f"房间 '{ROOM_NAME}' 不在缓存中")
        return seat_map

    floor_names = state.room_cache.get_floor_names(ROOM_NAME)
    _debug(f"'{ROOM_NAME}' 的楼层: {floor_names}")

    # 尝试精确匹配，如果失败则模糊匹配
    actual_floor = FLOOR_NAME
    if FLOOR_NAME not in floor_names:
        # 模糊匹配
        for fn in floor_names:
            if "二楼" in fn and "西" in fn:
                actual_floor = fn
                _debug(f"模糊匹配楼层: '{fn}'")
                break
        else:
            _debug(f"未找到匹配楼层 '{FLOOR_NAME}'，可用: {floor_names}")
            return seat_map

    seats = state.room_cache.get_seats(ROOM_NAME, actual_floor)
    _debug(f"楼层 '{actual_floor}' 座位数: {len(seats)}")

    for s in seats:
        title = s.get("title", "")
        seat_id = str(s.get("id", ""))
        if title in TARGET_SEATS:
            seat_map[title] = seat_id
            _debug(f"座位 {title} -> ID {seat_id}")

    if not seat_map:
        # 打印前 5 个座位的 title 以便调试
        sample = [(s.get("title", "?"), s.get("id", "?")) for s in seats[:5]]
        _debug(f"未找到目标座位，样本: {sample}")

    return seat_map


def _get_seat_ids_fallback() -> Dict[str, str]:
    """使用硬编码的座位 ID 作为兜底。"""
    _debug(f"使用硬编码座位 ID: {KNOWN_SEAT_IDS}")
    return dict(KNOWN_SEAT_IDS)


def _ensure_session(state) -> bool:
    """确保 session 有效，过期则重新登录。返回是否可用。"""
    if state.api_client is None:
        _debug("api_client 为空，尝试重新登录...")
        return _do_relogin(state)

    # 用一个轻量请求验证 session
    try:
        resp = state.api_client.session.get(
            url=state.api_client.base_url + "/Seat/Index/myBookingList",
            timeout=15,
            allow_redirects=False,
        )
        _debug(f"Session 验证: HTTP {resp.status_code}, 长度={len(resp.text)}")
        # 如果返回重定向到 CAS 登录，说明 session 过期
        if resp.status_code in (301, 302):
            location = resp.headers.get("Location", "")
            _debug(f"Session 重定向到: {location[:100]}")
            _debug("Session 已过期，重新登录...")
            return _do_relogin(state)
        if "CASLogin" in resp.text[:500]:
            _debug("Session 返回 CAS 登录页，重新登录...")
            return _do_relogin(state)
        if resp.status_code != 200:
            _debug(f"Session 验证异常: HTTP {resp.status_code}")
            return _do_relogin(state)
        _debug("Session 有效")
        return True
    except Exception as e:
        _debug(f"Session 验证失败: {e}")
        return _do_relogin(state)


def _do_relogin(state) -> bool:
    """重新登录。返回是否成功。"""
    try:
        _debug("执行重新登录...")
        success, err = state.session_mgr.relogin()
        if success:
            state.init_after_login()
            _auto_state["logged_in"] = True
            _debug("重新登录成功")
            return True
        else:
            _auto_state["logged_in"] = False
            _debug(f"重新登录失败: {err}")
            return False
    except Exception as e:
        _debug(f"重新登录异常: {e}")
        return False


def _search_seats_via_api(api_client, target_time: datetime) -> Dict[str, str]:
    """通过 API 搜索座位（备用方案）。返回 {座位号: seat_id}。"""
    seat_map: Dict[str, str] = {}
    try:
        # 获取房间信息
        rooms = api_client.query_rooms()
        if ROOM_NAME not in rooms:
            _debug(f"房间 '{ROOM_NAME}' 未在 API 返回中找到，可用: {list(rooms.keys())}")
            return seat_map

        room_data = rooms[ROOM_NAME]
        category_id = room_data["space_category"]["category_id"]
        content_id = room_data["space_category"]["content_id"]
        _debug(f"房间 category_id={category_id}, content_id={content_id}")

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

        # 保存原始响应用于调试
        resp_keys = list(resp.keys())
        _debug(f"searchSeats 响应 keys: {resp_keys}")

        all_content = resp.get("allContent", resp.get("content", {}))
        children = all_content.get("children", [])
        _debug(f"allContent.children 数量: {len(children)}")

        # 遍历所有 children 找楼层
        for i, child in enumerate(children):
            if not isinstance(child, dict):
                continue

            # 尝试各种可能的结构
            inner = child.get("children", child)
            if isinstance(inner, dict):
                floors = inner.get("children", [])
                if isinstance(floors, list):
                    for floor in floors:
                        if not isinstance(floor, dict):
                            continue
                        room_name = floor.get("roomName", "")
                        _debug(f"  child[{i}] floor roomName='{room_name}'")
                        if room_name == FLOOR_NAME:
                            pois = floor.get("seatMap", {}).get("POIs", [])
                            _debug(f"  找到目标楼层，座位数: {len(pois)}")
                            for poi in pois:
                                title = poi.get("title", "")
                                sid = str(poi.get("id", ""))
                                if title in TARGET_SEATS:
                                    seat_map[title] = sid
                                    _debug(f"  座位 {title} -> ID {sid}")
            elif isinstance(inner, list):
                for j, sub in enumerate(inner):
                    if not isinstance(sub, dict):
                        continue
                    inner2 = sub.get("children", sub)
                    if isinstance(inner2, dict):
                        floors = inner2.get("children", [])
                        if isinstance(floors, list):
                            for floor in floors:
                                if not isinstance(floor, dict):
                                    continue
                                room_name = floor.get("roomName", "")
                                _debug(f"  child[{i}][{j}] floor roomName='{room_name}'")
                                if room_name == FLOOR_NAME:
                                    pois = floor.get("seatMap", {}).get("POIs", [])
                                    _debug(f"  找到目标楼层，座位数: {len(pois)}")
                                    for poi in pois:
                                        title = poi.get("title", "")
                                        sid = str(poi.get("id", ""))
                                        if title in TARGET_SEATS:
                                            seat_map[title] = sid
                                            _debug(f"  座位 {title} -> ID {sid}")

        if not seat_map:
            _debug(f"未找到座位 {TARGET_SEATS}")
            # 保存部分响应用于调试
            try:
                resp_str = json.dumps(resp, ensure_ascii=False)[:2000]
                _debug(f"响应片段: {resp_str}")
            except Exception:
                pass

    except Exception as e:
        _debug(f"API 搜索座位异常: {e}")

    return seat_map


# ─── 预约逻辑 ─────────────────────────────────────────────────────────────────────
def _check_already_booked(api_client, target_date) -> Dict[str, bool]:
    """检查指定日期是否已有预约，返回 {座位号: 是否已预约}。"""
    result = {s: False for s in TARGET_SEATS}
    try:
        bookings = api_client.get_my_bookings()
        for b in bookings:
            bt = b.get("beginTime")
            if bt is None:
                continue
            if bt.date() == target_date:
                seat_num = str(b.get("seatNum", ""))
                if seat_num in TARGET_SEATS:
                    status = b.get("status", "")
                    # 状态 0=待签到, 1=已签到, 5=预约中 都算已预约
                    if status in ("0", "1", "5", "6", "7"):
                        result[seat_num] = True
                        _debug(f"座位 {seat_num} 在 {target_date} 已有预约 (状态: {STATUS_MAP.get(status, status)})")
    except Exception as e:
        _debug(f"检查已有预约失败: {e}")
    return result


def _do_book_single(api_client, seat_id: str, seat_num: str,
                     booker_uid: str, target_time: datetime, state=None) -> Dict:
    """预约单个座位，失败时自动重试登录。"""
    _debug(f"预约座位 {seat_num} (ID: {seat_id}) -> {target_time.strftime('%m-%d %H:%M')}")
    try:
        resp = api_client.book_seat(
            begin_time=target_time,
            duration_hours=DURATION_HOURS,
            seat_ids=[seat_id],
            booker_uids=[booker_uid],
        )

        # 检查是否是 CAS 重定向（session 过期）
        if isinstance(resp, dict) and resp.get("ui_type") == "com.Redirect":
            _debug(f"座位 {seat_num} 遇到 CAS 重定向，尝试重新登录...")
            if state and _do_relogin(state):
                # 重新登录后重试
                api_client = state.api_client
                resp = api_client.book_seat(
                    begin_time=target_time,
                    duration_hours=DURATION_HOURS,
                    seat_ids=[seat_id],
                    booker_uids=[booker_uid],
                )
            else:
                _debug(f"重新登录失败，无法预约座位 {seat_num}")
                return resp

        code = resp.get("CODE", "")
        if code == "ok":
            _debug(f"座位 {seat_num} 预约成功")
        else:
            msg = resp.get("MESSAGE", resp.get("msg", str(resp)))
            _debug(f"座位 {seat_num} 预约失败: {msg}")
        return resp
    except Exception as e:
        _debug(f"预约座位 {seat_num} 异常: {e}")
        return {"CODE": "error", "MESSAGE": str(e)}


def _do_book(state) -> None:
    """预约逻辑：预约今天/明天/后天的座位。"""
    try:
        # 确保 session 有效
        if not _ensure_session(state):
            _auto_state["last_book_result"] = "预约失败: 无法登录"
            return

        api = state.api_client
        now = datetime.now()
        results = []

        # 先从缓存获取座位 ID
        _debug("开始预约流程...")
        seat_map = _get_seat_ids_from_cache(state)

        # 缓存没找到，尝试 API 搜索
        if len(seat_map) < len(TARGET_SEATS):
            _debug("缓存中未找到所有座位，尝试 API 搜索...")
            tomorrow = (now + timedelta(days=1)).replace(
                hour=BEGIN_HOUR, minute=0, second=0, microsecond=0
            )
            api_seat_map = _search_seats_via_api(api, tomorrow)
            # 合并结果（API 搜索的优先）
            seat_map.update(api_seat_map)

        # 最后兜底：使用硬编码 ID
        if len(seat_map) < len(TARGET_SEATS):
            _debug("API 搜索也未找到所有座位，使用硬编码 ID")
            fallback = _get_seat_ids_fallback()
            for s in TARGET_SEATS:
                if s not in seat_map:
                    seat_map[s] = fallback[s]

        if not seat_map:
            _auto_state["last_book_result"] = "未找到任何座位 ID"
            _auto_state["last_error"] = "座位搜索失败"
            return

        _debug(f"可用座位映射: {seat_map}")

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
                    _debug(f"后天 ({target_date}) 需在 {book_available_at.strftime('%H:%M')} 后才能预约")
                    continue

            dates_to_book.append((target_date, target_time))

        for target_date, target_time in dates_to_book:
            _debug(f"检查 {target_date} 的预约...")

            # 检查是否已预约
            already_booked = _check_already_booked(api, target_date)
            if all(already_booked.values()):
                _debug(f"{target_date} 所有座位已预约")
                results.append(f"{target_date}: 已预约")
                continue

            # 逐个预约座位（独立预约，互不影响）
            for seat_num in TARGET_SEATS:
                if already_booked.get(seat_num):
                    _debug(f"座位 {seat_num} 在 {target_date} 已预约，跳过")
                    continue

                seat_id = seat_map.get(seat_num)
                if not seat_id:
                    _debug(f"座位 {seat_num} 无 ID，跳过")
                    results.append(f"{target_date} 座位{seat_num}: 未找到ID")
                    continue

                # 确定预约人 UID
                booker_uid = COMPANION_UID if seat_num == "99" else USER_UID

                resp = _do_book_single(api, seat_id, seat_num, booker_uid, target_time, state=state)
                code = resp.get("CODE", "")
                msg = resp.get("MESSAGE", resp.get("msg", ""))
                if code == "ok":
                    results.append(f"{target_date} 座位{seat_num}: ✅ 成功")
                else:
                    results.append(f"{target_date} 座位{seat_num}: ❌ {msg}")

        _auto_state["last_book_result"] = "; ".join(results) if results else "无需预约"
        _auto_state["last_error"] = ""
        _debug(f"预约完成: {_auto_state['last_book_result']}")
    except Exception as e:
        _auto_state["last_error"] = str(e)
        _auto_state["last_book_result"] = f"预约异常: {e}"
        _debug(f"预约异常: {e}")


# ─── 签到逻辑 ─────────────────────────────────────────────────────────────────────
def _do_checkin_for_user(student_id: str, password: str, user_name: str,
                          state) -> List[str]:
    """登录指定用户并签到其预约。"""
    results = []
    try:
        from seathunter.auth.session_manager import SessionManager
        from seathunter.api.client import ApiClient as LibApiClient

        # 创建临时会话（使用相同的 config_manager）
        temp_session_mgr = SessionManager(config_manager=state.config)
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
            bt = b.get("beginTime")
            if bt is None:
                continue
            if bt.date() != today:
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
            results.append(f"{user_name}: 无需签到")

        temp_session_mgr.logout()
    except Exception as e:
        results.append(f"{user_name}: ❌ 异常 {e}")
        _debug(f"签到异常 ({user_name}): {e}")

    return results


def _do_checkin(state) -> None:
    """签到逻辑：签到你和同伴的预约。"""
    # 确保 session 有效
    if not _ensure_session(state):
        _auto_state["last_checkin_result"] = "签到失败: 无法登录"
        return

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
    _debug(f"签到完成: {_auto_state['last_checkin_result']}")


# ─── 调度器 ───────────────────────────────────────────────────────────────────────
def _scheduler_loop(state) -> None:
    """后台调度器：检查是否到触发时间。"""
    _debug("调度器已启动")
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
                _debug("触发自动预约")
                last_book_date = today_str
                threading.Thread(
                    target=_do_book, args=(state,), daemon=True
                ).start()

            # 检查签到时间：每天 9:30
            if (now.hour == AUTO_CHECKIN_HOUR
                    and now.minute == AUTO_CHECKIN_MINUTE
                    and last_checkin_date != today_str):
                _debug("触发自动签到")
                last_checkin_date = today_str
                threading.Thread(
                    target=_do_checkin, args=(state,), daemon=True
                ).start()

        except Exception as e:
            _debug(f"调度器异常: {e}")

        # 每 30 秒检查一次
        for _ in range(30):
            if not _auto_state["running"]:
                break
            import time
            time.sleep(1)

    _debug("调度器已停止")


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
        "debug_log": _auto_state["debug_log"][-20:],  # 最近 20 条
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
        # 尝试重新登录
        if not _do_relogin(state):
            raise HTTPException(status_code=401, detail="尚未登录")

    all_bookings: List[Dict[str, Any]] = []

    # 获取你的预约
    try:
        your_bookings = state.api_client.get_my_bookings()
        for b in your_bookings:
            bt = b.get("beginTime")
            et = b.get("endTime")
            all_bookings.append({
                "user": "我",
                "roomName": b.get("roomName", ""),
                "seatNum": str(b.get("seatNum", "")),
                "beginTime": bt.strftime("%Y-%m-%d %H:%M") if isinstance(bt, datetime) else str(bt or ""),
                "endTime": et.strftime("%H:%M") if isinstance(et, datetime) else str(et or ""),
                "status": STATUS_MAP.get(str(b.get("status", "")), str(b.get("status", ""))),
                "bookingId": str(b.get("bookingId", "")),
            })
    except Exception as e:
        logger.warning("获取你的预约失败: %s", e)

    # 获取同伴的预约
    try:
        from seathunter.auth.session_manager import SessionManager
        from seathunter.api.client import ApiClient as LibApiClient

        temp_mgr = SessionManager(config_manager=state.config)
        temp_mgr.set_credentials(COMPANION_STUDENT_ID, COMPANION_PASSWORD)
        if temp_mgr.login():
            temp_api = LibApiClient(temp_mgr)
            companion_bookings = temp_api.get_my_bookings()
            for b in companion_bookings:
                bt = b.get("beginTime")
                et = b.get("endTime")
                all_bookings.append({
                    "user": "同伴",
                    "roomName": b.get("roomName", ""),
                    "seatNum": str(b.get("seatNum", "")),
                    "beginTime": bt.strftime("%Y-%m-%d %H:%M") if isinstance(bt, datetime) else str(bt or ""),
                    "endTime": et.strftime("%H:%M") if isinstance(et, datetime) else str(et or ""),
                    "status": STATUS_MAP.get(str(b.get("status", "")), str(b.get("status", ""))),
                    "bookingId": str(b.get("bookingId", "")),
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


@router.get("/debug")
def debug_info(request: Request):
    """调试信息。"""
    state = _get_state(request)
    info: Dict[str, Any] = {
        "api_client_ready": state.api_client is not None,
        "room_cache_ready": state.room_cache is not None and state.room_cache.is_ready if state.room_cache else False,
        "debug_log": _auto_state["debug_log"][-30:],
    }
    if state.room_cache and state.room_cache.is_ready:
        info["rooms"] = state.room_cache.get_room_names()
        if ROOM_NAME in (info["rooms"] or []):
            info["floors"] = state.room_cache.get_floor_names(ROOM_NAME)
            for fn in info["floors"]:
                seats = state.room_cache.get_seats(ROOM_NAME, fn)
                info[f"seats_{fn}"] = [(s.get("title"), s.get("id")) for s in seats[:10]]
    return info


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
