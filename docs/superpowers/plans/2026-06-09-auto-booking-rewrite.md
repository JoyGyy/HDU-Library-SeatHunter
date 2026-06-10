# 自动预约系统重写实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写自动预约/签到系统，将 752 行巨石 `auto.py` 拆分为 5 个职责清晰的模块，复用 seathunter 核心组件

**Architecture:** 三层架构 — 路由层（api/auto.py）→ 业务层（core/）→ 基础设施层（seathunter/）。配置硬编码，座位 ID 硬编码，Session 过期自动 re-login。

**Tech Stack:** Python 3.13, FastAPI, Playwright, requests, threading

---

## File Structure

| 文件 | 职责 | 行数估算 |
|------|------|----------|
| `server/core/__init__.py` | 包初始化 | 0 |
| `server/core/config.py` | 硬编码配置常量 | ~40 |
| `server/core/session.py` | Session 验证 + re-login | ~50 |
| `server/core/booker.py` | 预约逻辑 + 重试 | ~100 |
| `server/core/checker.py` | 签到逻辑 | ~70 |
| `server/core/scheduler.py` | 调度器（预约线程 + 签到线程） | ~80 |
| `server/api/auto.py` | 路由层（重写） | ~100 |
| `server/main.py` | 修改自动登录逻辑 | ~50 行改动 |
| `server/static/index.html` | 前端页面 | ~60 |
| `server/static/app.js` | 前端逻辑 | ~120 |
| `server/static/style.css` | 样式（保留现有） | 不变 |

**删除的文件：** 无（旧 auto.py 直接覆盖）

---

### Task 1: 创建配置模块

**Files:**
- Create: `server/core/__init__.py`
- Create: `server/core/config.py`

- [ ] **Step 1: 创建 `server/core/__init__.py`**

```python
"""自动预约核心模块。"""
```

- [ ] **Step 2: 创建 `server/core/config.py`**

```python
"""硬编码配置。

所有固定参数集中管理，修改时只需改这一个文件。
"""

# ─── 用户账号 ────────────────────────────────────────────────────────────────────
USER_STUDENT_ID = "23051110"
USER_PASSWORD = "@Krz201314"
USER_UID = "303687"

COMPANION_STUDENT_ID = "23140322"
COMPANION_PASSWORD = "Pangzidan0713#"
COMPANION_UID = "305033"

# ─── 座位 ────────────────────────────────────────────────────────────────────────
ROOM_NAME = "自习室"
FLOOR_NAME = "比特庭园（二楼西）"
TARGET_SEATS = ["99", "100"]
KNOWN_SEAT_IDS = {"99": "60810", "100": "60811"}

# ─── 时间 ────────────────────────────────────────────────────────────────────────
BEGIN_HOUR = 10
DURATION_HOURS = 12
AUTO_BOOK_HOUR = 20
AUTO_BOOK_MINUTE = 0
AUTO_CHECKIN_HOUR = 9
AUTO_CHECKIN_MINUTE = 30

# ─── 重试 ────────────────────────────────────────────────────────────────────────
MAX_RETRY = 10
RETRY_INTERVAL = 5  # 秒
REQUEST_INTERVAL = 5  # 座位/日期之间的间隔，防封号

# ─── 状态码映射 ──────────────────────────────────────────────────────────────────
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

# ─── 不可重试的错误关键词 ────────────────────────────────────────────────────────
NON_RETRYABLE_ERRORS = ["已有预约", "请勿重复", "无法预约", "不可用", "锁定", "占用", "不开放"]
```

- [ ] **Step 3: Commit**

```bash
git add server/core/__init__.py server/core/config.py
git commit -m "feat: 创建配置模块，集中管理硬编码常量"
```

---

### Task 2: 创建 Session 管理模块

**Files:**
- Create: `server/core/session.py`

- [ ] **Step 1: 创建 `server/core/session.py`**

```python
"""Session 验证与自动 re-login。

每次 API 调用前验证 session 是否有效，过期则自动重新登录。
"""

from __future__ import annotations

import logging
from typing import Any

from seathunter.api.client import ApiClient
from seathunter.auth.session_manager import SessionManager

from server.core.config import USER_STUDENT_ID, USER_PASSWORD

logger = logging.getLogger("seathunter.core.session")


class DebugLogger:
    """收集调试日志，供前端显示。"""

    def __init__(self, max_lines: int = 50):
        self._lines: list[str] = []
        self._max = max_lines

    def log(self, msg: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self._lines.append(entry)
        if len(self._lines) > self._max:
            self._lines = self._lines[-self._max:]
        logger.info(msg)

    def get_recent(self, n: int = 20) -> list[str]:
        return self._lines[-n:]


def ensure_valid_session(state: Any, debug: DebugLogger) -> bool:
    """确保 session 有效，过期则重新登录。

    Args:
        state: AppState 实例
        debug: 调试日志收集器

    Returns:
        True if session is valid (or re-login succeeded), False otherwise.
    """
    if state.api_client is None:
        debug.log("api_client 为空，尝试重新登录...")
        return _do_relogin(state, debug)

    try:
        resp = state.api_client.session.get(
            url=state.api_client.base_url + "/Seat/Index/myBookingList",
            timeout=15,
            allow_redirects=False,
        )
        # 重定向到 CAS 登录 → session 过期
        if resp.status_code in (301, 302):
            debug.log("Session 已过期（重定向），重新登录...")
            return _do_relogin(state, debug)
        if "CASLogin" in resp.text[:500]:
            debug.log("Session 已过期（CAS页面），重新登录...")
            return _do_relogin(state, debug)
        if resp.status_code != 200:
            debug.log(f"Session 验证异常: HTTP {resp.status_code}")
            return _do_relogin(state, debug)
        debug.log("Session 有效")
        return True
    except Exception as e:
        debug.log(f"Session 验证失败: {e}")
        return _do_relogin(state, debug)


def _do_relogin(state: Any, debug: DebugLogger) -> bool:
    """执行 re-login。"""
    try:
        debug.log("执行重新登录...")
        success, err = state.session_mgr.relogin()
        if success:
            state.init_after_login()
            debug.log("重新登录成功")
            return True
        else:
            debug.log(f"重新登录失败: {err}")
            return False
    except Exception as e:
        debug.log(f"重新登录异常: {e}")
        return False


def create_temp_session(config: Any, student_id: str, password: str,
                         debug: DebugLogger) -> tuple[SessionManager, ApiClient] | None:
    """创建临时 session（用于签到同伴账号）。

    Returns:
        (SessionManager, ApiClient) 或 None（登录失败时）
    """
    try:
        mgr = SessionManager(config_manager=config)
        mgr.set_credentials(student_id, password)
        ok = mgr.login()
        if not ok:
            debug.log(f"临时登录失败: {student_id}")
            return None
        api = ApiClient(mgr)
        return mgr, api
    except Exception as e:
        debug.log(f"临时登录异常: {e}")
        return None
```

- [ ] **Step 2: Commit**

```bash
git add server/core/session.py
git commit -m "feat: 创建 session 管理模块，验证+relogin+临时session"
```

---

### Task 3: 创建预约模块

**Files:**
- Create: `server/core/booker.py`

- [ ] **Step 1: 创建 `server/core/booker.py`**

```python
"""预约逻辑。

检查已预约 → 逐天逐座预约 → 重试 → 记录结果。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict

from server.core.config import (
    BEGIN_HOUR, COMPANION_UID, DURATION_HOURS, KNOWN_SEAT_IDS,
    MAX_RETRY, NON_RETRYABLE_ERRORS, REQUEST_INTERVAL,
    RETRY_INTERVAL, STATUS_MAP, TARGET_SEATS, USER_UID,
    AUTO_BOOK_HOUR, AUTO_BOOK_MINUTE,
)
from server.core.session import DebugLogger, ensure_valid_session

logger = logging.getLogger("seathunter.core.booker")


def book_for_all_dates(state: Any, debug: DebugLogger) -> str:
    """预约今天/明天/后天的座位。

    Returns:
        结果摘要字符串。
    """
    # 确保 session 有效
    if not ensure_valid_session(state, debug):
        return "预约失败: 无法登录"

    api = state.api_client
    now = datetime.now()
    results: list[str] = []

    # 确定要预约的日期
    dates = _get_dates_to_book(now, debug)

    for date_idx, (target_date, target_time) in enumerate(dates):
        if date_idx > 0:
            debug.log(f"等待 {REQUEST_INTERVAL} 秒后预约下一天...")
            time.sleep(REQUEST_INTERVAL)

        debug.log(f"检查 {target_date} 的预约...")

        # 检查是否已预约
        already = _check_already_booked(api, target_date, debug)
        if all(already.values()):
            debug.log(f"{target_date} 所有座位已预约")
            results.append(f"{target_date}: 已预约")
            continue

        # 逐个座位预约
        for seat_idx, seat_num in enumerate(TARGET_SEATS):
            if seat_idx > 0:
                debug.log(f"等待 {REQUEST_INTERVAL} 秒后预约下一个座位...")
                time.sleep(REQUEST_INTERVAL)

            if already.get(seat_num):
                debug.log(f"座位 {seat_num} 在 {target_date} 已预约，跳过")
                continue

            seat_id = KNOWN_SEAT_IDS.get(seat_num)
            if not seat_id:
                debug.log(f"座位 {seat_num} 无 ID，跳过")
                results.append(f"{target_date} 座位{seat_num}: 无ID")
                continue

            # 预约人列表：当前用户必须在列
            booker_uids = _get_booker_uids(seat_num)

            resp = _book_with_retry(api, seat_id, seat_num, booker_uids,
                                     target_time, state, debug)
            code = resp.get("CODE", "")
            msg = resp.get("MESSAGE", resp.get("msg", ""))
            if code == "ok":
                results.append(f"{target_date} 座位{seat_num}: ✅")
            else:
                results.append(f"{target_date} 座位{seat_num}: ❌ {msg}")

    summary = "; ".join(results) if results else "无需预约"
    debug.log(f"预约完成: {summary}")
    return summary


def _get_dates_to_book(now: datetime, debug: DebugLogger) -> list[tuple]:
    """返回需要预约的 (date, datetime) 列表。"""
    dates = []
    for delta in [0, 1, 2]:  # 今天、明天、后天
        target_date = (now + timedelta(days=delta)).date()
        target_time = datetime.combine(
            target_date,
            datetime.min.time().replace(hour=BEGIN_HOUR, minute=0)
        )

        if delta == 2:
            # 后天：需在今天 20:00 后才能预约
            book_available_at = datetime.combine(
                now.date(),
                datetime.min.time().replace(hour=AUTO_BOOK_HOUR, minute=AUTO_BOOK_MINUTE)
            )
            if now < book_available_at:
                debug.log(f"后天 ({target_date}) 需在 {book_available_at.strftime('%H:%M')} 后才能预约")
                continue

        dates.append((target_date, target_time))
    return dates


def _check_already_booked(api: Any, target_date, debug: DebugLogger) -> Dict[str, bool]:
    """检查指定日期是否已有预约。"""
    result = {s: False for s in TARGET_SEATS}
    try:
        bookings = api.get_my_bookings()
        for b in bookings:
            bt = b.get("beginTime")
            if bt is None:
                continue
            if bt.date() == target_date:
                seat_num = str(b.get("seatNum", ""))
                if seat_num in TARGET_SEATS:
                    status = str(b.get("status", ""))
                    if status in ("0", "1", "5", "6", "7"):
                        result[seat_num] = True
                        debug.log(f"座位 {seat_num} 在 {target_date} 已有预约 ({STATUS_MAP.get(status, status)})")
    except Exception as e:
        debug.log(f"检查已有预约失败: {e}")
    return result


def _get_booker_uids(seat_num: str) -> list[str]:
    """返回预约人 UID 列表。当前登录用户必须在列。"""
    if seat_num == "99":
        return [COMPANION_UID, USER_UID]
    return [USER_UID]


def _book_with_retry(api: Any, seat_id: str, seat_num: str,
                      booker_uids: list[str], target_time: datetime,
                      state: Any, debug: DebugLogger) -> dict:
    """带重试的预约。最多 MAX_RETRY 次，间隔 RETRY_INTERVAL 秒。"""
    for attempt in range(1, MAX_RETRY + 1):
        debug.log(f"预约座位 {seat_num} (ID: {seat_id}, 预约人: {booker_uids}) -> {target_time.strftime('%m-%d %H:%M')} [尝试 {attempt}/{MAX_RETRY}]")

        resp = api.book_seat(
            begin_time=target_time,
            duration_hours=DURATION_HOURS,
            seat_ids=[seat_id],
            booker_uids=booker_uids,
        )

        # CAS 重定向 → session 过期 → relogin 并重试
        if isinstance(resp, dict) and resp.get("ui_type") == "com.Redirect":
            debug.log(f"座位 {seat_num} 遇到 CAS 重定向，尝试重新登录...")
            if _do_relogin_and_wait(state, debug):
                api = state.api_client
                continue
            else:
                return resp

        code = resp.get("CODE", "")
        if code == "ok":
            debug.log(f"座位 {seat_num} 预约成功")
            return resp

        msg = resp.get("MESSAGE", resp.get("msg", str(resp)))
        debug.log(f"座位 {seat_num} 预约失败: {msg}")

        # 不可重试的错误
        if any(kw in msg for kw in NON_RETRYABLE_ERRORS):
            debug.log(f"不可重试的错误，停止: {msg}")
            return resp

        # 还有重试机会
        if attempt < MAX_RETRY:
            debug.log(f"等待 {RETRY_INTERVAL} 秒后重试...")
            time.sleep(RETRY_INTERVAL)

    return resp


def _do_relogin_and_wait(state: Any, debug: DebugLogger) -> bool:
    """重新登录并等待。"""
    from server.core.session import _do_relogin
    ok = _do_relogin(state, debug)
    if ok:
        time.sleep(2)
    return ok
```

- [ ] **Step 2: Commit**

```bash
git add server/core/booker.py
git commit -m "feat: 创建预约模块，带重试和 CAS 重定向处理"
```

---

### Task 4: 创建签到模块

**Files:**
- Create: `server/core/checker.py`

- [ ] **Step 1: 创建 `server/core/checker.py`**

```python
"""签到逻辑。

分别登录你和同伴的账号，签到今天的预约。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from server.core.config import (
    COMPANION_PASSWORD, COMPANION_STUDENT_ID,
    MAX_RETRY, REQUEST_INTERVAL, RETRY_INTERVAL,
    USER_PASSWORD, USER_STUDENT_ID,
)
from server.core.session import DebugLogger, create_temp_session

logger = logging.getLogger("seathunter.core.checker")


def checkin_for_all_users(state: Any, debug: DebugLogger) -> str:
    """签到你和同伴的预约。

    Returns:
        结果摘要字符串。
    """
    results: list[str] = []

    # 签到你的预约
    your_results = _checkin_user(
        USER_STUDENT_ID, USER_PASSWORD, "我", state, debug
    )
    results.extend(your_results)

    # 等待间隔
    debug.log(f"等待 {REQUEST_INTERVAL} 秒后签到同伴...")
    time.sleep(REQUEST_INTERVAL)

    # 签到同伴的预约
    companion_results = _checkin_user(
        COMPANION_STUDENT_ID, COMPANION_PASSWORD, "同伴", state, debug
    )
    results.extend(companion_results)

    summary = "; ".join(results)
    debug.log(f"签到完成: {summary}")
    return summary


def _checkin_user(student_id: str, password: str, user_name: str,
                   state: Any, debug: DebugLogger) -> list[str]:
    """登录指定用户并签到其今天的预约。"""
    results: list[str] = []

    # 创建临时 session
    session_data = create_temp_session(state.config, student_id, password, debug)
    if session_data is None:
        results.append(f"{user_name}: ❌ 登录失败")
        return results

    temp_mgr, temp_api = session_data

    try:
        bookings = temp_api.get_my_bookings()
        today = datetime.now().date()
        checked = 0

        for b in bookings:
            bt = b.get("beginTime")
            if bt is None or bt.date() != today:
                continue
            if b.get("status") != "0":  # 只签到"待签到"的
                continue

            booking_id = b.get("bookingId", "")
            seat_num = b.get("seatNum", "")
            success, msg, _ = _checkin_with_retry(temp_api, booking_id, seat_num, debug)
            if success:
                results.append(f"{user_name} 座位{seat_num}: ✅ 签到成功")
                checked += 1
            else:
                results.append(f"{user_name} 座位{seat_num}: ❌ {msg}")

        if checked == 0:
            results.append(f"{user_name}: 无需签到")
    except Exception as e:
        results.append(f"{user_name}: ❌ 异常 {e}")
        debug.log(f"签到异常 ({user_name}): {e}")
    finally:
        try:
            temp_mgr.session.close()
        except Exception:
            pass

    return results


def _checkin_with_retry(api: Any, booking_id: str, seat_num: str,
                         debug: DebugLogger) -> tuple[bool, str, str]:
    """带重试的签到。"""
    for attempt in range(1, MAX_RETRY + 1):
        debug.log(f"签到座位 {seat_num} (bookingId: {booking_id}) [尝试 {attempt}/{MAX_RETRY}]")
        success, msg, _ = api.check_in(booking_id)
        if success:
            return (True, "", booking_id)
        debug.log(f"签到失败: {msg}")
        if attempt < MAX_RETRY:
            debug.log(f"等待 {RETRY_INTERVAL} 秒后重试...")
            time.sleep(RETRY_INTERVAL)
    return (False, msg, booking_id)
```

- [ ] **Step 2: Commit**

```bash
git add server/core/checker.py
git commit -m "feat: 创建签到模块，独立 session + 重试"
```

---

### Task 5: 创建调度器模块

**Files:**
- Create: `server/core/scheduler.py`

- [ ] **Step 1: 创建 `server/core/scheduler.py`**

```python
"""调度器：预约线程 + 签到线程。

用 threading.Event 替代 time.sleep，可随时中断。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from server.core.booker import book_for_all_dates
from server.core.checker import checkin_for_all_users
from server.core.config import (
    AUTO_BOOK_HOUR, AUTO_BOOK_MINUTE,
    AUTO_CHECKIN_HOUR, AUTO_CHECKIN_MINUTE,
)
from server.core.session import DebugLogger

logger = logging.getLogger("seathunter.core.scheduler")

# 全局状态
_state: dict[str, Any] = {
    "running": False,
    "last_book_result": "",
    "last_checkin_result": "",
    "last_error": "",
}
debug = DebugLogger()


def get_state() -> dict[str, Any]:
    """获取当前状态（供 API 路由使用）。"""
    return {
        **_state,
        "debug_log": debug.get_recent(20),
    }


def get_debug_log() -> DebugLogger:
    """获取调试日志实例。"""
    return debug


class AutoScheduler:
    """自动预约/签到调度器。"""

    def __init__(self, app_state: Any):
        self._app_state = app_state
        self._stop = threading.Event()
        self._book_thread: threading.Thread | None = None
        self._checkin_thread: threading.Thread | None = None

    def start(self) -> None:
        """启动调度器。"""
        if _state["running"]:
            debug.log("调度器已在运行")
            return

        _state["running"] = True
        self._stop.clear()

        self._book_thread = threading.Thread(
            target=self._book_loop, daemon=True, name="BookScheduler"
        )
        self._book_thread.start()

        self._checkin_thread = threading.Thread(
            target=self._checkin_loop, daemon=True, name="CheckinScheduler"
        )
        self._checkin_thread.start()

        debug.log("调度器已启动")

    def stop(self) -> None:
        """停止调度器。"""
        _state["running"] = False
        self._stop.set()
        debug.log("调度器已停止")

    def _book_loop(self) -> None:
        """预约线程：每 30 秒检查，20:00 触发。"""
        last_trigger: str | None = None
        while not self._stop.is_set():
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            if (now.hour == AUTO_BOOK_HOUR
                    and now.minute == AUTO_BOOK_MINUTE
                    and last_trigger != today):
                last_trigger = today
                debug.log("触发自动预约")
                try:
                    result = book_for_all_dates(self._app_state, debug)
                    _state["last_book_result"] = result
                    _state["last_error"] = ""
                except Exception as e:
                    _state["last_error"] = str(e)
                    _state["last_book_result"] = f"预约异常: {e}"
                    debug.log(f"预约异常: {e}")
            self._stop.wait(timeout=30)

    def _checkin_loop(self) -> None:
        """签到线程：每 30 秒检查，9:30 触发。"""
        last_trigger: str | None = None
        while not self._stop.is_set():
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            if (now.hour == AUTO_CHECKIN_HOUR
                    and now.minute == AUTO_CHECKIN_MINUTE
                    and last_trigger != today):
                last_trigger = today
                debug.log("触发自动签到")
                try:
                    result = checkin_for_all_users(self._app_state, debug)
                    _state["last_checkin_result"] = result
                    _state["last_error"] = ""
                except Exception as e:
                    _state["last_error"] = str(e)
                    _state["last_checkin_result"] = f"签到异常: {e}"
                    debug.log(f"签到异常: {e}")
            self._stop.wait(timeout=30)


# 模块级调度器实例（由 main.py 设置）
_scheduler: AutoScheduler | None = None


def init_scheduler(app_state: Any) -> AutoScheduler:
    """初始化并返回调度器实例。"""
    global _scheduler
    _scheduler = AutoScheduler(app_state)
    return _scheduler


def get_scheduler() -> AutoScheduler | None:
    """获取调度器实例。"""
    return _scheduler
```

- [ ] **Step 2: Commit**

```bash
git add server/core/scheduler.py
git commit -m "feat: 创建调度器模块，独立预约/签到线程"
```

---

### Task 6: 重写路由层

**Files:**
- Modify: `server/api/auto.py`（完全重写）

- [ ] **Step 1: 重写 `server/api/auto.py`**

```python
"""自动预约 API 路由。

只做路由，不含业务逻辑。所有逻辑在 server/core/ 中。
"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from server.core.config import STATUS_MAP, TARGET_SEATS, ROOM_NAME, \
    AUTO_BOOK_HOUR, AUTO_BOOK_MINUTE, AUTO_CHECKIN_HOUR, AUTO_CHECKIN_MINUTE
from server.core.scheduler import get_state, get_debug_log, get_scheduler
from server.core.booker import book_for_all_dates
from server.core.checker import checkin_for_all_users
from server.core.session import ensure_valid_session

router = APIRouter()


def _get_app_state(request: Request):
    return request.app.state.seathunter


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
    from server.core.config import (
        COMPANION_PASSWORD, COMPANION_STUDENT_ID,
    )
    from server.core.session import create_temp_session
    from datetime import datetime

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

    # 同伴的预约
    try:
        session_data = create_temp_session(
            app_state.config, COMPANION_STUDENT_ID, COMPANION_PASSWORD, debug
        )
        if session_data:
            mgr, api = session_data
            for b in api.get_my_bookings():
                all_bookings.append(_format_booking(b, "同伴"))
            mgr.session.close()
    except Exception as e:
        debug.log(f"获取同伴预约失败: {e}")

    return {"bookings": all_bookings}


def _format_booking(b: dict, user: str) -> dict:
    """格式化单条预约。"""
    from datetime import datetime
    bt = b.get("beginTime")
    et = b.get("endTime")
    return {
        "user": user,
        "roomName": b.get("roomName", ""),
        "seatNum": str(b.get("seatNum", "")),
        "beginTime": bt.strftime("%Y-%m-%d %H:%M") if isinstance(bt, datetime) else str(bt or ""),
        "endTime": et.strftime("%H:%M") if isinstance(et, datetime) else str(et or ""),
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
        from server.core.scheduler import _state
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
        from server.core.scheduler import _state
        _state["last_checkin_result"] = result

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": "正在签到，请稍后刷新查看结果"}


@router.post("/start")
def start_scheduler(request: Request):
    """启动调度器。"""
    scheduler = get_scheduler()
    if scheduler is None:
        app_state = _get_app_state(request)
        from server.core.scheduler import init_scheduler
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
```

- [ ] **Step 2: Commit**

```bash
git add server/api/auto.py
git commit -m "feat: 重写路由层，调用 core 模块"
```

---

### Task 7: 更新 main.py

**Files:**
- Modify: `server/main.py`

- [ ] **Step 1: 更新 main.py 的自动登录和调度启动逻辑**

```python
"""FastAPI 后端入口。"""

from __future__ import annotations

import logging
import sys
import os

# 将项目根目录加入 sys.path，确保 seathunter 包可导入
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# 初始化日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

from server.models.state import AppState  # noqa: E402

app = FastAPI(title="HDU Library SeatHunter API", version="1.0.0")

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局状态实例（构造时自动加载配置）
state = AppState()

# 将 state 注入到 app 供路由使用
app.state.seathunter = state


@app.on_event("startup")
def on_startup() -> None:
    """启动时自动登录并启动调度。"""
    import threading

    def _auto_init():
        import time
        time.sleep(2)  # 等待服务器完全启动
        try:
            from server.core.config import USER_STUDENT_ID, USER_PASSWORD
            from server.core.scheduler import init_scheduler, get_debug_log
            from server.core.session import ensure_valid_session

            debug = get_debug_log()

            # 自动登录
            state.config.update_user_info(
                login_name=USER_STUDENT_ID,
                password=USER_PASSWORD,
            )
            state.session_mgr.init_session()
            success, err_type = state.session_mgr.login()
            if success:
                state.init_after_login()
                logger.info("自动登录成功: %s", state.session_mgr.name)

                # 启动调度器
                scheduler = init_scheduler(state)
                scheduler.start()
            else:
                logger.error("自动登录失败: %s", err_type)
                debug.log(f"自动登录失败: {err_type}")
        except Exception as e:
            logger.error("自动初始化失败: %s", e)

    threading.Thread(target=_auto_init, daemon=True, name="AutoInit").start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    from server.core.scheduler import get_scheduler
    scheduler = get_scheduler()
    if scheduler:
        scheduler.stop()
    state.shutdown()


# 挂载静态文件
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def root():
    """返回前端页面。"""
    return FileResponse(os.path.join(static_dir, "index.html"))


# 注册路由（只保留 auto，其他路由可按需保留或删除）
from server.api import auto  # noqa: E402

app.include_router(auto.router, prefix="/api/auto", tags=["自动"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 2: Commit**

```bash
git add server/main.py
git commit -m "feat: 更新 main.py，使用 core 模块自动登录和调度"
```

---

### Task 8: 更新前端

**Files:**
- Modify: `server/static/index.html`
- Modify: `server/static/app.js`
- Modify: `server/static/style.css`

- [ ] **Step 1: 重写 `index.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>座位预约</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div class="app">
    <!-- 状态 -->
    <div class="card">
      <h2>状态</h2>
      <div class="status-grid">
        <div class="status-item">
          <span class="status-label">调度器</span>
          <span id="schedulerStatus" class="badge badge-off">检查中…</span>
        </div>
        <div class="status-item">
          <span class="status-label">目标座位</span>
          <span id="targetSeats" class="result-value">-</span>
        </div>
        <div class="status-item">
          <span class="status-label">房间</span>
          <span id="roomName" class="result-value">-</span>
        </div>
      </div>
    </div>

    <!-- 执行结果 -->
    <div class="card">
      <h2>执行结果</h2>
      <div class="result-row">
        <span class="result-label">预约</span>
        <span id="bookResult" class="result-value">-</span>
      </div>
      <div class="result-row">
        <span class="result-label">签到</span>
        <span id="checkinResult" class="result-value">-</span>
      </div>
    </div>

    <!-- 预约列表 -->
    <div class="card">
      <h2>预约列表</h2>
      <div id="bookingList"><div class="empty">加载中…</div></div>
    </div>

    <!-- 操作 -->
    <div class="card action-card">
      <button class="btn btn-primary" onclick="manualBook()">立即预约</button>
      <button class="btn btn-success" onclick="manualCheckin()">立即签到</button>
      <button class="btn btn-warn" onclick="toggleScheduler()" id="toggleBtn">启动/停止</button>
      <button class="btn btn-info" onclick="manualRefresh()">刷新</button>
    </div>

    <!-- 运行日志 -->
    <div class="card">
      <h2>运行日志 <span id="logCount" class="badge badge-info">0</span></h2>
      <div id="log" class="log-container"></div>
    </div>
  </div>

  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 重写 `app.js`**

```javascript
/* ── 工具函数 ── */
function escHtml(str) {
  if (!str && str !== 0) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function qs(id) { return document.getElementById(id); }

function log(msg) {
  const c = qs('log');
  if (!c) return;
  const t = document.createElement('div');
  t.className = 'log-line';
  t.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  c.appendChild(t);
  c.scrollTop = c.scrollHeight;
  if (c.children.length > 200) c.removeChild(c.firstChild);
  const cnt = qs('logCount');
  if (cnt) cnt.textContent = c.children.length;
}

/* ── API 调用 ── */
function refreshStatus() {
  fetch('/api/auto/status')
    .then(r => r.json())
    .then(d => {
      const schedEl = qs('schedulerStatus');
      if (schedEl) {
        schedEl.textContent = d.running ? '🟢 运行中' : '🔴 已停止';
        schedEl.className = 'badge ' + (d.running ? 'badge-on' : 'badge-off');
      }
      const seatsEl = qs('targetSeats');
      if (seatsEl) seatsEl.textContent = (d.target_seats || []).join(', ') || '-';
      const roomEl = qs('roomName');
      if (roomEl) roomEl.textContent = d.room_name || '-';
      const bookResEl = qs('bookResult');
      if (bookResEl) bookResEl.textContent = d.last_book_result || '-';
      const checkResEl = qs('checkinResult');
      if (checkResEl) checkResEl.textContent = d.last_checkin_result || '-';
      // 后端日志
      if (d.debug_log && d.debug_log.length) {
        const logEl = qs('log');
        if (logEl) {
          const existing = new Set();
          logEl.querySelectorAll('.backend-log').forEach(el => existing.add(el.textContent));
          d.debug_log.forEach(line => {
            if (!existing.has(line)) {
              const t = document.createElement('div');
              t.className = 'log-line backend-log';
              t.textContent = line;
              logEl.appendChild(t);
            }
          });
          logEl.scrollTop = logEl.scrollHeight;
          const cnt = qs('logCount');
          if (cnt) cnt.textContent = logEl.children.length;
        }
      }
    })
    .catch(e => log('状态刷新失败: ' + e));
}

function loadBookings() {
  const el = qs('bookingList');
  if (!el) return;
  el.innerHTML = '<div class="empty">加载中…</div>';
  fetch('/api/auto/bookings')
    .then(r => r.json())
    .then(d => {
      const list = d.bookings || [];
      if (!list.length) { el.innerHTML = '<div class="empty">暂无预约</div>'; return; }
      el.innerHTML = list.map(b => {
        const timeStr = b.beginTime ? (b.endTime ? `${b.beginTime} ~ ${b.endTime}` : b.beginTime) : '时间未知';
        const cls = b.status === '已签到' ? 'status-active' : b.status === '待签到' ? 'status-pending' : 'status-ended';
        return `<div class="booking-item">
          <div class="booking-header">
            <span class="booking-user">${escHtml(b.user)}</span>
            <span class="badge ${cls}">${escHtml(b.status)}</span>
          </div>
          <div class="booking-detail">${escHtml(b.roomName)} 座位 ${escHtml(b.seatNum)}</div>
          <div class="booking-time">${escHtml(timeStr)}</div>
        </div>`;
      }).join('');
    })
    .catch(e => { el.innerHTML = '<div class="empty">加载失败</div>'; log('预约列表加载失败: ' + e); });
}

function manualBook() {
  if (!confirm('确认立即预约？')) return;
  log('手动预约…');
  fetch('/api/auto/book', { method: 'POST' })
    .then(r => r.json())
    .then(d => { log('预约请求: ' + (d.message || JSON.stringify(d))); setTimeout(refreshStatus, 3000); setTimeout(loadBookings, 5000); })
    .catch(e => log('预约失败: ' + e));
}

function manualCheckin() {
  if (!confirm('确认立即签到？')) return;
  log('手动签到…');
  fetch('/api/auto/checkin', { method: 'POST' })
    .then(r => r.json())
    .then(d => { log('签到请求: ' + (d.message || JSON.stringify(d))); setTimeout(refreshStatus, 3000); setTimeout(loadBookings, 5000); })
    .catch(e => log('签到失败: ' + e));
}

function toggleScheduler() {
  const btn = qs('toggleBtn');
  const running = btn && btn.textContent.includes('停止');
  const url = running ? '/api/auto/stop' : '/api/auto/start';
  log(running ? '停止调度器…' : '启动调度器…');
  fetch(url, { method: 'POST' })
    .then(r => r.json())
    .then(d => { log(d.message || JSON.stringify(d)); refreshStatus(); })
    .catch(e => log('操作失败: ' + e));
}

function manualRefresh() {
  log('手动刷新…');
  refreshStatus();
  loadBookings();
}

/* ── 初始化 ── */
document.addEventListener('DOMContentLoaded', () => {
  refreshStatus();
  loadBookings();
  setInterval(() => { refreshStatus(); loadBookings(); }, 30000);
});
```

- [ ] **Step 3: 更新 `style.css`**（添加缺失的样式）

在现有 style.css 末尾追加：

```css
/* ── 补充样式 ── */
.app {
  max-width: 480px;
  margin: 0 auto;
  padding: 20px;
  padding-bottom: 40px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card h2 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
}

.status-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-label {
  color: var(--subtext);
  font-size: 14px;
}

.result-value {
  font-size: 14px;
  word-break: break-all;
}

.result-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 6px 0;
  border-bottom: 1px solid rgba(69, 71, 90, 0.3);
}

.result-row:last-child {
  border-bottom: none;
}

.result-label {
  color: var(--subtext);
  font-size: 14px;
  flex-shrink: 0;
  margin-right: 12px;
}

.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.badge-on {
  background: rgba(166, 227, 161, 0.15);
  color: var(--green);
}

.badge-off {
  background: rgba(243, 139, 168, 0.15);
  color: var(--red);
}

.badge-info {
  background: rgba(137, 180, 250, 0.15);
  color: var(--blue);
}

.booking-item {
  padding: 10px 0;
  border-bottom: 1px solid rgba(69, 71, 90, 0.3);
}

.booking-item:last-child {
  border-bottom: none;
}

.booking-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.booking-user {
  font-weight: 600;
  font-size: 14px;
}

.booking-detail {
  font-size: 13px;
  color: var(--subtext);
}

.booking-time {
  font-size: 13px;
  color: var(--subtext);
  margin-top: 2px;
}

.status-active {
  background: rgba(166, 227, 161, 0.15);
  color: var(--green);
}

.status-pending {
  background: rgba(249, 226, 175, 0.15);
  color: var(--yellow);
}

.status-ended {
  background: rgba(69, 71, 90, 0.3);
  color: var(--subtext);
}

.action-card {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.action-card .btn {
  flex: 1;
  min-width: 80px;
  height: 40px;
  font-size: 13px;
}

.btn-primary {
  background: var(--blue);
  color: var(--bg);
  border: none;
}

.btn-success {
  background: var(--green);
  color: var(--bg);
  border: none;
}

.btn-warn {
  background: var(--yellow);
  color: var(--bg);
  border: none;
}

.btn-info {
  background: var(--overlay);
  color: var(--text);
  border: none;
}

.empty {
  text-align: center;
  color: var(--subtext);
  padding: 16px 0;
  font-size: 14px;
}

.log-line {
  padding: 3px 0;
  font-size: 12px;
  border-bottom: 1px solid rgba(69, 71, 90, 0.2);
}
```

- [ ] **Step 4: Commit**

```bash
git add server/static/index.html server/static/app.js server/static/style.css
git commit -m "feat: 重写前端，极简状态页+操作按钮"
```

---

### Task 9: 清理并测试

**Files:**
- Verify: `server/main.py`
- Verify: `server/api/auto.py`
- Verify: `server/core/*.py`

- [ ] **Step 1: 删除不再需要的旧路由文件**

```bash
# 检查哪些旧路由文件还被 main.py 引用
grep -n "include_router" server/main.py
```

如果 main.py 只注册了 `auto.router`，可以删除其他未使用的路由文件（可选，不删除也不影响功能）。

- [ ] **Step 2: 本地启动测试**

```bash
cd /Users/joygy/Documents/hdu-library/HDU-Library-SeatHunter
.venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

验证：
- 访问 `http://localhost:8000/` 显示前端页面
- 访问 `http://localhost:8000/api/auto/status` 返回状态 JSON
- 日志显示"自动登录成功"
- 日志显示"调度器已启动"

- [ ] **Step 3: 测试手动预约**

```bash
curl -X POST http://localhost:8000/api/auto/book
```

等待几秒后查看：
```bash
curl http://localhost:8000/api/auto/status | python3 -m json.tool
```

验证 `last_book_result` 字段有内容。

- [ ] **Step 4: Commit 最终版本**

```bash
git add -A
git commit -m "feat: 自动预约系统重写完成"
```

---

### Task 10: 部署到 Railway

**Files:**
- Verify: `Dockerfile`
- Verify: `Procfile`

- [ ] **Step 1: 确认 Dockerfile 正确**

```bash
cat Dockerfile
```

应包含：
- Python 3.13-slim
- `playwright install chromium`
- `playwright install-deps chromium`
- `uvicorn server.main:app --host 0.0.0.0 --port $PORT`

- [ ] **Step 2: 推送到 GitHub**

```bash
git push origin main
```

- [ ] **Step 3: 在 Railway 控制台确认部署**

- 访问 Railway 项目页面
- 等待构建完成
- 访问部署 URL 验证前端页面

- [ ] **Step 4: 验证自动功能**

- 查看 Railway 日志，确认"自动登录成功"和"调度器已启动"
- 点击"立即预约"测试手动预约
- 等待 20:00 自动触发（或手动测试）
