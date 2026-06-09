# FastAPI 后端 + React Native 移动端 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 FastAPI 后端 API 和 React Native 移动端，第一版支持签到和好友代预约。

**Architecture:** 在 `server/` 目录创建 FastAPI 后端，复用 `seathunter/` 现有核心逻辑。在 `mobile/` 目录创建 Expo React Native 应用。后端通过 REST API 暴露功能，移动端通过 HTTP 调用。

**Tech Stack:** Python 3.14, FastAPI, uvicorn, Pydantic, React Native (Expo), TypeScript, Axios

---

## 文件变更总览

| 操作 | 文件 | 职责 |
|------|------|------|
| **创建** | `server/__init__.py` | 包初始化 |
| **创建** | `server/main.py` | FastAPI 入口 + CORS + 路由注册 |
| **创建** | `server/models/schemas.py` | Pydantic 请求/响应模型 |
| **创建** | `server/models/state.py` | 全局状态管理（SessionManager、引擎等） |
| **创建** | `server/models/__init__.py` | 包初始化 |
| **创建** | `server/api/__init__.py` | 包初始化 |
| **创建** | `server/api/auth.py` | 认证路由 |
| **创建** | `server/api/checkin.py` | 签到路由 |
| **创建** | `server/api/friends.py` | 好友路由 |
| **创建** | `server/api/bookings.py` | 预约路由（获取当前预约） |
| **创建** | `server/api/plans.py` | 方案路由 |
| **创建** | `server/api/schedules.py` | 调度路由 |
| **创建** | `tests/test_server_api.py` | 后端 API 测试 |
| **创建** | `mobile/` | Expo React Native 项目 |
| **创建** | `mobile/src/api/client.ts` | API 客户端 |
| **创建** | `mobile/src/screens/HomeScreen.tsx` | 首页 |
| **创建** | `mobile/src/screens/CheckInScreen.tsx` | 签到页 |
| **创建** | `mobile/src/screens/FriendsScreen.tsx` | 好友页 |

---

### Task 1: 后端基础 — schemas + state + main

**Files:**
- Create: `server/__init__.py`
- Create: `server/models/__init__.py`
- Create: `server/models/schemas.py`
- Create: `server/models/state.py`
- Create: `server/main.py`

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p server/models server/api server/services
touch server/__init__.py server/models/__init__.py server/api/__init__.py
```

- [ ] **Step 2: 安装依赖**

```bash
.venv/bin/pip install fastapi uvicorn
```

- [ ] **Step 3: 创建 Pydantic schemas**

创建 `server/models/schemas.py`：

```python
"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# ── 认证 ──

class LoginRequest(BaseModel):
    student_id: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    message: str = ""
    uid: str = ""
    name: str = ""


class AuthStatusResponse(BaseModel):
    logged_in: bool
    uid: str = ""
    name: str = ""
    student_id: str = ""


# ── 预约 ──

class BookingItem(BaseModel):
    booking_id: str
    room_name: str
    seat_num: str
    begin_time: Optional[str] = None
    end_time: Optional[str] = None
    status: str = ""


class BookingListResponse(BaseModel):
    bookings: List[BookingItem]


# ── 签到 ──

class CheckInRequest(BaseModel):
    booking_id: str


class CheckInResponse(BaseModel):
    success: bool
    message: str = ""


# ── 好友 ──

class FriendItem(BaseModel):
    student_id: str
    name: str
    uid: str


class FriendListResponse(BaseModel):
    friends: List[FriendItem]


class AddFriendRequest(BaseModel):
    student_id: str
    password: str


class AddFriendResponse(BaseModel):
    success: bool
    message: str = ""
    name: str = ""
    uid: str = ""


class TestLoginResponse(BaseModel):
    success: bool
    message: str = ""


# ── 方案 ──

class SeatInfoSchema(BaseModel):
    seat_id: str
    seat_num: str
    booker_uid: str = ""


class PlanSchema(BaseModel):
    id: str
    room_name: str
    floor_name: str
    begin_time: str
    duration_hours: int
    seats: List[SeatInfoSchema]
    target_date: str = ""
    booking_id: str = ""


class PlanListResponse(BaseModel):
    plans: List[PlanSchema]


class AddPlanRequest(BaseModel):
    room_name: str
    floor_name: str
    begin_time: str
    duration_hours: int
    seats: List[SeatInfoSchema]
    target_date: str = ""
    plan_id: str = ""


# ── 调度 ──

class ScheduleItem(BaseModel):
    id: str
    type: str
    target: str
    enabled: bool
    plan_ids: List[str]


class ScheduleListResponse(BaseModel):
    schedules: List[ScheduleItem]


class AddScheduleRequest(BaseModel):
    schedule_type: str  # "weekly" or "date"
    target: str  # "1,3,5" or "2026-06-08"
    plan_ids: List[str]
    trigger_time: str = "20:00"


class SchedulerStatusResponse(BaseModel):
    running: bool
    trigger_time: Optional[str] = None
    target_date: Optional[str] = None
    remaining_seconds: Optional[int] = None


# ── 通用 ──

class MessageResponse(BaseModel):
    success: bool
    message: str = ""
```

- [ ] **Step 4: 创建全局状态管理**

创建 `server/models/state.py`：

```python
"""全局状态管理。持有 SessionManager、引擎等单例。"""

from __future__ import annotations

from seathunter.auth.session_manager import SessionManager
from seathunter.auth.friend_store import FriendStore
from seathunter.services.friend_service import FriendService
from seathunter.config.manager import ConfigManager
from seathunter.api.client import ApiClient
from seathunter.scheduler.booking_runner import BookingRunner
from seathunter.scheduler.engine import SchedulerEngine
from seathunter.logging_.history import HistoryLogger
from seathunter.api.room_cache import RoomCache

from seathunter.platform_.paths import get_config_dir


class AppState:
    """应用全局状态。"""

    def __init__(self):
        config_dir = get_config_dir()
        self.config = ConfigManager(config_dir)
        self.session_mgr = SessionManager(self.config)
        self.api_client: ApiClient = None  # 登录后初始化
        self.room_cache = RoomCache(self.config)

        friend_store_path = f"{config_dir}/friends.json"
        self.friend_store = FriendStore(friend_store_path)
        self.friend_service = FriendService(
            self.friend_store,
            base_url="https://hdu.huitu.zhishulib.com",
        )

        self.history = HistoryLogger(f"{config_dir}/history.jsonl")
        self.runner: BookingRunner = None  # 登录后初始化
        self.engine: SchedulerEngine = None  # 登录后初始化

    def init_after_login(self):
        """登录成功后初始化需要 session 的组件。"""
        self.api_client = ApiClient(self.session_mgr)
        self.runner = BookingRunner(
            api_client=self.api_client,
            session_manager=self.session_mgr,
            interval=self.config.get("settings.retry_interval", 5),
            max_try_times=self.config.get("settings.max_retry", 10),
        )
        self.engine = SchedulerEngine(
            config_manager=self.config,
            session_manager=self.session_mgr,
            booking_runner=self.runner,
        )


# 全局单例
state = AppState()
```

- [ ] **Step 5: 创建 FastAPI 入口**

创建 `server/main.py`：

```python
"""FastAPI 应用入口。"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api import auth, checkin, friends, bookings, plans, schedules

app = FastAPI(
    title="HDU Library SeatHunter API",
    description="杭电图书馆自动抢座 API",
    version="1.0.0",
)

# CORS — 允许移动端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(bookings.router, prefix="/api/bookings", tags=["预约"])
app.include_router(checkin.router, prefix="/api/checkin", tags=["签到"])
app.include_router(friends.router, prefix="/api/friends", tags=["好友"])
app.include_router(plans.router, prefix="/api/plans", tags=["方案"])
app.include_router(schedules.router, prefix="/api/schedules", tags=["调度"])


@app.get("/")
async def root():
    return {"name": "HDU Library SeatHunter API", "version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 6: 语法检查**

```bash
.venv/bin/python3 -c "import ast; ast.parse(open('server/main.py').read()); ast.parse(open('server/models/schemas.py').read()); ast.parse(open('server/models/state.py').read()); print('OK')"
```

- [ ] **Step 7: 提交**

```bash
git add server/ requirements.txt
git commit -m "后端基础：FastAPI 入口 + Pydantic schemas + 全局状态管理"
```

---

### Task 2: 认证模块 (auth)

**Files:**
- Create: `server/api/auth.py`

- [ ] **Step 1: 创建认证路由**

创建 `server/api/auth.py`：

```python
"""认证 API 路由。"""

from __future__ import annotations

import threading

from fastapi import APIRouter

from server.models.schemas import LoginRequest, LoginResponse, AuthStatusResponse
from server.models.state import state

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """登录图书馆系统。"""
    state.config.update_user_info(login_name=req.student_id, password=req.password)

    # Playwright 登录在同步线程中执行
    result = {}

    def _do():
        success, err_type = state.session_mgr.login()
        result["success"] = success
        result["err_type"] = err_type

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout=120)  # Playwright 登录可能需要较长时间

    if not result:
        return LoginResponse(success=False, message="登录超时")

    if result["success"]:
        state.init_after_login()
        return LoginResponse(
            success=True,
            uid=state.session_mgr.uid,
            name=state.session_mgr.name,
        )

    msg = "网络错误" if result.get("err_type") == "network" else "登录失败，请检查学号密码"
    return LoginResponse(success=False, message=msg)


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status():
    """获取登录状态。"""
    return AuthStatusResponse(
        logged_in=bool(state.session_mgr.uid),
        uid=state.session_mgr.uid or "",
        name=state.session_mgr.name or "",
        student_id=state.config.get("account.student_id", ""),
    )


@router.post("/logout")
async def logout():
    """退出登录。"""
    state.session_mgr.uid = ""
    state.session_mgr.name = ""
    state.session_mgr.session = None
    return {"success": True, "message": "已退出登录"}
```

- [ ] **Step 2: 语法检查**

```bash
.venv/bin/python3 -c "import ast; ast.parse(open('server/api/auth.py').read()); print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add server/api/auth.py
git commit -m "认证模块：登录/状态/退出 API"
```

---

### Task 3: 签到模块 (checkin)

**Files:**
- Create: `server/api/checkin.py`

- [ ] **Step 1: 创建签到路由**

创建 `server/api/checkin.py`：

```python
"""签到 API 路由。"""

from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException

from server.models.schemas import CheckInResponse, BookingListResponse, BookingItem
from server.models.state import state

router = APIRouter()


@router.post("/{booking_id}", response_model=CheckInResponse)
async def checkin(booking_id: str):
    """手动签到。"""
    if not state.api_client:
        raise HTTPException(status_code=401, detail="请先登录")

    result = {}

    def _do():
        success, msg, _ = state.api_client.check_in(booking_id)
        result["success"] = success
        result["message"] = msg

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout=30)

    if not result:
        return CheckInResponse(success=False, message="签到超时")

    return CheckInResponse(success=result["success"], message=result.get("message", ""))


@router.get("/bookings", response_model=BookingListResponse)
async def get_current_bookings():
    """获取当前预约列表（用于选择签到）。"""
    if not state.api_client:
        raise HTTPException(status_code=401, detail="请先登录")

    result = {}

    def _do():
        bookings = state.api_client.get_my_bookings()
        result["bookings"] = bookings

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout=30)

    bookings = result.get("bookings", [])
    items = []
    for b in bookings:
        begin = b.get("beginTime")
        end = b.get("endTime")
        items.append(BookingItem(
            booking_id=str(b.get("bookingId", "")),
            room_name=b.get("roomName", ""),
            seat_num=b.get("seatNum", ""),
            begin_time=begin.strftime("%m-%d %H:%M") if begin else None,
            end_time=end.strftime("%H:%M") if end else None,
            status=b.get("status", ""),
        ))

    return BookingListResponse(bookings=items)
```

- [ ] **Step 2: 语法检查**

```bash
.venv/bin/python3 -c "import ast; ast.parse(open('server/api/checkin.py').read()); print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add server/api/checkin.py
git commit -m "签到模块：手动签到 + 获取当前预约 API"
```

---

### Task 4: 好友模块 (friends)

**Files:**
- Create: `server/api/friends.py`

- [ ] **Step 1: 创建好友路由**

创建 `server/api/friends.py`：

```python
"""好友 API 路由。"""

from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException

from server.models.schemas import (
    FriendListResponse, FriendItem,
    AddFriendRequest, AddFriendResponse,
    TestLoginResponse, MessageResponse,
)
from server.models.state import state

router = APIRouter()


@router.get("", response_model=FriendListResponse)
async def list_friends():
    """获取好友列表。"""
    friends = []
    for sid, info in state.friend_store.get_all().items():
        friends.append(FriendItem(
            student_id=info.get("student_id", sid),
            name=info.get("name", ""),
            uid=info.get("uid", ""),
        ))
    return FriendListResponse(friends=friends)


@router.post("", response_model=AddFriendResponse)
async def add_friend(req: AddFriendRequest):
    """添加好友（查询 UID 并保存）。"""
    result = {}

    def _do():
        from seathunter.auth.session_manager import lookup_uid
        ok, uid, name = lookup_uid(req.student_id, req.password)
        if ok:
            state.friend_store.add(req.student_id, uid, name, req.password)
        result["success"] = ok
        result["uid"] = uid
        result["name"] = name

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout=120)

    if not result:
        return AddFriendResponse(success=False, message="查询超时")

    if result["success"]:
        return AddFriendResponse(
            success=True,
            message="添加成功",
            name=result["name"],
            uid=result["uid"],
        )
    return AddFriendResponse(success=False, message="查询失败，请检查学号密码")


@router.delete("/{student_id}", response_model=MessageResponse)
async def delete_friend(student_id: str):
    """删除好友。"""
    if state.friend_store.remove(student_id):
        return MessageResponse(success=True, message="已删除")
    raise HTTPException(status_code=404, detail="好友不存在")


@router.post("/{student_id}/test", response_model=TestLoginResponse)
async def test_friend_login(student_id: str):
    """测试好友登录。"""
    result = {}

    def _do():
        ok, msg = state.friend_service.test_login(student_id)
        result["success"] = ok
        result["message"] = msg

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout=120)

    if not result:
        return TestLoginResponse(success=False, message="测试超时")

    return TestLoginResponse(success=result["success"], message=result.get("message", ""))
```

- [ ] **Step 2: 语法检查**

```bash
.venv/bin/python3 -c "import ast; ast.parse(open('server/api/friends.py').read()); print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add server/api/friends.py
git commit -m "好友模块：列表/添加/删除/测试登录 API"
```

---

### Task 5: 预约 + 方案 + 调度路由

**Files:**
- Create: `server/api/bookings.py`
- Create: `server/api/plans.py`
- Create: `server/api/schedules.py`

- [ ] **Step 1: 创建预约路由**

创建 `server/api/bookings.py`：

```python
"""预约 API 路由。"""

from __future__ import annotations

import threading
from datetime import datetime

from fastapi import APIRouter, HTTPException

from server.models.schemas import BookingListResponse, BookingItem
from server.models.state import state

router = APIRouter()


@router.get("", response_model=BookingListResponse)
async def list_bookings():
    """获取当前预约列表。"""
    if not state.api_client:
        raise HTTPException(status_code=401, detail="请先登录")

    result = {}

    def _do():
        result["bookings"] = state.api_client.get_my_bookings()

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout=30)

    items = []
    for b in result.get("bookings", []):
        begin = b.get("beginTime")
        end = b.get("endTime")
        items.append(BookingItem(
            booking_id=str(b.get("bookingId", "")),
            room_name=b.get("roomName", ""),
            seat_num=b.get("seatNum", ""),
            begin_time=begin.strftime("%m-%d %H:%M") if begin else None,
            end_time=end.strftime("%H:%M") if end else None,
            status=b.get("status", ""),
        ))
    return BookingListResponse(bookings=items)
```

- [ ] **Step 2: 创建方案路由**

创建 `server/api/plans.py`：

```python
"""方案 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.models.schemas import (
    PlanListResponse, PlanSchema, SeatInfoSchema,
    AddPlanRequest, MessageResponse,
)
from server.models.state import state
from seathunter.models.plan import Plan, SeatInfo

router = APIRouter()


def _plan_to_schema(plan: Plan) -> PlanSchema:
    return PlanSchema(
        id=plan.id,
        room_name=plan.room_name,
        floor_name=plan.floor_name,
        begin_time=plan.begin_time,
        duration_hours=plan.duration_hours,
        seats=[SeatInfoSchema(seat_id=s.seat_id, seat_num=s.seat_num,
                              booker_uid=s.booker_uid) for s in plan.seats],
        target_date=plan.target_date,
        booking_id=plan.booking_id,
    )


@router.get("", response_model=PlanListResponse)
async def list_plans():
    """获取方案列表。"""
    plans = state.config.get_plans()
    return PlanListResponse(plans=[_plan_to_schema(p) for p in plans])


@router.post("", response_model=MessageResponse)
async def add_plan(req: AddPlanRequest):
    """添加方案。"""
    plan = Plan(
        id=req.plan_id or f"plan_{datetime.now().strftime('%H%M%S')}",
        room_name=req.room_name,
        floor_name=req.floor_name,
        begin_time=req.begin_time,
        duration_hours=req.duration_hours,
        seats=[SeatInfo(seat_id=s.seat_id, seat_num=s.seat_num,
                        booker_uid=s.booker_uid) for s in req.seats],
        target_date=req.target_date,
    )
    state.config.add_plan(plan)
    return MessageResponse(success=True, message=f"方案 {plan.id} 已添加")


@router.delete("/{plan_id}", response_model=MessageResponse)
async def delete_plan(plan_id: str):
    """删除方案。"""
    if state.config.remove_plan(plan_id):
        return MessageResponse(success=True, message="已删除")
    raise HTTPException(status_code=404, detail="方案不存在")
```

- [ ] **Step 3: 创建调度路由**

创建 `server/api/schedules.py`：

```python
"""调度 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.models.schemas import (
    ScheduleListResponse, ScheduleItem,
    AddScheduleRequest, SchedulerStatusResponse,
    MessageResponse,
)
from server.models.state import state

router = APIRouter()


@router.get("", response_model=ScheduleListResponse)
async def list_schedules():
    """获取调度列表。"""
    schedules = state.config.get_schedules()
    items = []
    for s in schedules:
        info = s.to_dict()
        items.append(ScheduleItem(
            id=info.get("id", ""),
            type=info.get("type", ""),
            target=info.get("target", ""),
            enabled=info.get("enabled", True),
            plan_ids=info.get("plan_ids", []),
        ))
    return ScheduleListResponse(schedules=items)


@router.post("", response_model=MessageResponse)
async def add_schedule(req: AddScheduleRequest):
    """添加调度。"""
    from seathunter.models.schedule import Schedule
    schedule = Schedule(
        type=req.schedule_type,
        target=req.target,
        plan_ids=req.plan_ids,
        trigger_time=req.trigger_time,
    )
    state.config.add_schedule(schedule)
    return MessageResponse(success=True, message="调度已添加")


@router.delete("/{schedule_id}", response_model=MessageResponse)
async def delete_schedule(schedule_id: str):
    """删除调度。"""
    if state.config.remove_schedule(schedule_id):
        return MessageResponse(success=True, message="已删除")
    raise HTTPException(status_code=404, detail="调度不存在")


@router.post("/start", response_model=MessageResponse)
async def start_scheduler():
    """启动调度引擎。"""
    if not state.engine:
        raise HTTPException(status_code=401, detail="请先登录")
    state.engine.start()
    return MessageResponse(success=True, message="调度引擎已启动")


@router.post("/stop", response_model=MessageResponse)
async def stop_scheduler():
    """停止调度引擎。"""
    if state.engine:
        state.engine.stop()
    return MessageResponse(success=True, message="调度引擎已停止")


@router.get("/status", response_model=SchedulerStatusResponse)
async def scheduler_status():
    """获取调度引擎状态。"""
    if not state.engine:
        return SchedulerStatusResponse(running=False)
    status = state.engine.get_status()
    trigger = status.get("trigger_time")
    target = status.get("target_date")
    return SchedulerStatusResponse(
        running=status.get("running", False),
        trigger_time=trigger.strftime("%H:%M") if trigger else None,
        target_date=target.strftime("%Y-%m-%d") if target else None,
        remaining_seconds=status.get("remaining_seconds"),
    )
```

- [ ] **Step 4: 语法检查**

```bash
.venv/bin/python3 -c "
import ast
for f in ['server/api/bookings.py', 'server/api/plans.py', 'server/api/schedules.py']:
    ast.parse(open(f).read())
print('OK')
"
```

- [ ] **Step 5: 提交**

```bash
git add server/api/bookings.py server/api/plans.py server/api/schedules.py
git commit -m "预约/方案/调度路由"
```

---

### Task 6: 后端集成测试

**Files:**
- Create: `tests/test_server_api.py`

- [ ] **Step 1: 编写 API 测试**

创建 `tests/test_server_api.py`：

```python
"""FastAPI 后端 API 测试。"""

from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "HDU Library SeatHunter API"


def test_auth_status_not_logged_in():
    resp = client.get("/api/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["logged_in"] is False


def test_friends_empty():
    resp = client.get("/api/friends")
    assert resp.status_code == 200
    assert "friends" in resp.json()


def test_plans_empty():
    resp = client.get("/api/plans")
    assert resp.status_code == 200
    assert "plans" in resp.json()


def test_schedules_empty():
    resp = client.get("/api/schedules")
    assert resp.status_code == 200
    assert "schedules" in resp.json()


def test_scheduler_status():
    resp = client.get("/api/schedules/status")
    assert resp.status_code == 200
    assert "running" in resp.json()


def test_checkin_not_logged_in():
    resp = client.post("/api/checkin/12345")
    assert resp.status_code == 401


def test_bookings_not_logged_in():
    resp = client.get("/api/bookings")
    assert resp.status_code == 401
```

- [ ] **Step 2: 运行测试**

```bash
.venv/bin/python3 -m pytest tests/test_server_api.py -v
```

预期: 全部 PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_server_api.py
git commit -m "后端 API 测试"
```

---

### Task 7: React Native 移动端 — 项目初始化

**Files:**
- Create: `mobile/` (Expo 项目)

- [ ] **Step 1: 创建 Expo 项目**

```bash
npx create-expo-app@latest mobile --template blank-typescript
cd mobile
npx expo install @react-navigation/native @react-navigation/bottom-tabs react-native-screens react-native-safe-area-context axios
```

- [ ] **Step 2: 创建 API 客户端**

创建 `mobile/src/api/client.ts`：

```typescript
import axios from 'axios';

// 默认连接本机，用户可在设置中修改
const BASE_URL = 'http://192.168.1.100:8000';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

export const setBaseURL = (url: string) => {
  api.defaults.baseURL = url;
};

// ── 认证 ──
export const login = (studentId: string, password: string) =>
  api.post('/api/auth/login', { student_id: studentId, password });

export const getAuthStatus = () => api.get('/api/auth/status');

// ── 签到 ──
export const checkIn = (bookingId: string) =>
  api.post(`/api/checkin/${bookingId}`);

export const getCurrentBookings = () => api.get('/api/checkin/bookings');

// ── 好友 ──
export const getFriends = () => api.get('/api/friends');

export const addFriend = (studentId: string, password: string) =>
  api.post('/api/friends', { student_id: studentId, password });

export const deleteFriend = (studentId: string) =>
  api.delete(`/api/friends/${studentId}`);

export const testFriendLogin = (studentId: string) =>
  api.post(`/api/friends/${studentId}/test`);

// ── 预约 ──
export const getBookings = () => api.get('/api/bookings');

export default api;
```

- [ ] **Step 3: 提交**

```bash
cd ..
git add mobile/
git commit -m "React Native 移动端：Expo 项目初始化 + API 客户端"
```

---

### Task 8: 移动端 — 首页 + 导航

**Files:**
- Create: `mobile/src/screens/HomeScreen.tsx`
- Modify: `mobile/App.tsx`

- [ ] **Step 1: 创建首页**

创建 `mobile/src/screens/HomeScreen.tsx`：

```tsx
import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput, Alert } from 'react-native';
import { getAuthStatus, login, setBaseURL } from '../api/client';

export default function HomeScreen() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [userName, setUserName] = useState('');
  const [serverIP, setServerIP] = useState('192.168.1.100');
  const [studentId, setStudentId] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    checkStatus();
  }, []);

  const checkStatus = async () => {
    try {
      const resp = await getAuthStatus();
      setLoggedIn(resp.data.logged_in);
      setUserName(resp.data.name);
    } catch (e) {
      // 后端未连接
    }
  };

  const handleLogin = async () => {
    setBaseURL(`http://${serverIP}:8000`);
    setLoading(true);
    try {
      const resp = await login(studentId, password);
      if (resp.data.success) {
        setLoggedIn(true);
        setUserName(resp.data.name);
        Alert.alert('成功', `欢迎, ${resp.data.name}`);
      } else {
        Alert.alert('失败', resp.data.message);
      }
    } catch (e) {
      Alert.alert('错误', '无法连接后端，请检查 IP 地址');
    }
    setLoading(false);
  };

  if (!loggedIn) {
    return (
      <View style={styles.container}>
        <Text style={styles.title}>HDU 图书馆抢座</Text>
        <TextInput style={styles.input} placeholder="后端 IP" value={serverIP}
          onChangeText={setServerIP} placeholderTextColor="#666" />
        <TextInput style={styles.input} placeholder="学号" value={studentId}
          onChangeText={setStudentId} placeholderTextColor="#666" />
        <TextInput style={styles.input} placeholder="密码" value={password}
          onChangeText={setPassword} secureTextEntry placeholderTextColor="#666" />
        <TouchableOpacity style={styles.button} onPress={handleLogin} disabled={loading}>
          <Text style={styles.buttonText}>{loading ? '登录中...' : '登录'}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>HDU 图书馆抢座</Text>
      <Text style={styles.subtitle}>已登录: {userName}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#1e1e2e', padding: 20 },
  title: { fontSize: 24, fontWeight: 'bold', color: '#cdd6f4', marginBottom: 20 },
  subtitle: { fontSize: 16, color: '#a6adc8' },
  input: { width: '100%', height: 48, backgroundColor: '#313244', borderRadius: 8, paddingHorizontal: 16,
           color: '#cdd6f4', fontSize: 16, marginBottom: 12, borderWidth: 1, borderColor: '#45475a' },
  button: { width: '100%', height: 48, backgroundColor: '#89b4fa', borderRadius: 8,
            justifyContent: 'center', alignItems: 'center', marginTop: 8 },
  buttonText: { color: '#1e1e2e', fontSize: 16, fontWeight: 'bold' },
});
```

- [ ] **Step 2: 配置导航**

修改 `mobile/App.tsx`：

```tsx
import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import HomeScreen from './src/screens/HomeScreen';

const Tab = createBottomTabNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <Tab.Navigator screenOptions={{
        headerShown: false,
        tabBarStyle: { backgroundColor: '#1e1e2e', borderTopColor: '#45475a' },
        tabBarActiveTintColor: '#89b4fa',
        tabBarInactiveTintColor: '#a6adc8',
      }}>
        <Tab.Screen name="首页" component={HomeScreen} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
```

- [ ] **Step 3: 提交**

```bash
git add mobile/
git commit -m "移动端首页：登录界面 + 底部导航"
```

---

### Task 9: 移动端 — 签到页面

**Files:**
- Create: `mobile/src/screens/CheckInScreen.tsx`
- Modify: `mobile/App.tsx`

- [ ] **Step 1: 创建签到页面**

创建 `mobile/src/screens/CheckInScreen.tsx`：

```tsx
import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, FlatList, Alert, ActivityIndicator } from 'react-native';
import { getCurrentBookings, checkIn } from '../api/client';

interface Booking {
  booking_id: string;
  room_name: string;
  seat_num: string;
  begin_time: string | null;
  end_time: string | null;
  status: string;
}

const statusMap: Record<string, string> = { '0': '待签到', '1': '已签到', '2': '已结束' };

export default function CheckInScreen() {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(false);
  const [checkingId, setCheckingId] = useState<string | null>(null);

  useEffect(() => { loadBookings(); }, []);

  const loadBookings = async () => {
    setLoading(true);
    try {
      const resp = await getCurrentBookings();
      setBookings(resp.data.bookings);
    } catch (e) {
      Alert.alert('错误', '获取预约失败');
    }
    setLoading(false);
  };

  const handleCheckIn = async (bookingId: string) => {
    setCheckingId(bookingId);
    try {
      const resp = await checkIn(bookingId);
      if (resp.data.success) {
        Alert.alert('成功', '签到成功！');
        loadBookings();
      } else {
        Alert.alert('失败', resp.data.message);
      }
    } catch (e) {
      Alert.alert('错误', '签到请求失败');
    }
    setCheckingId(null);
  };

  const renderItem = ({ item }: { item: Booking }) => (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <Text style={styles.roomName}>{item.room_name}</Text>
        <Text style={[styles.status, item.status === '0' ? styles.statusPending : styles.statusDone]}>
          {statusMap[item.status] || item.status}
        </Text>
      </View>
      <Text style={styles.seatInfo}>座位: {item.seat_num}</Text>
      <Text style={styles.timeInfo}>
        时间: {item.begin_time || '—'} ~ {item.end_time || '—'}
      </Text>
      {item.status === '0' && (
        <TouchableOpacity style={styles.checkinBtn}
          onPress={() => handleCheckIn(item.booking_id)}
          disabled={checkingId === item.booking_id}>
          {checkingId === item.booking_id ? (
            <ActivityIndicator color="#1e1e2e" />
          ) : (
            <Text style={styles.checkinBtnText}>签到</Text>
          )}
        </TouchableOpacity>
      )}
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>当前预约</Text>
        <TouchableOpacity onPress={loadBookings}>
          <Text style={styles.refreshBtn}>刷新</Text>
        </TouchableOpacity>
      </View>
      {loading ? (
        <ActivityIndicator size="large" color="#89b4fa" style={{ marginTop: 40 }} />
      ) : (
        <FlatList data={bookings} renderItem={renderItem}
          keyExtractor={item => item.booking_id}
          ListEmptyComponent={<Text style={styles.empty}>暂无预约</Text>}
          contentContainerStyle={{ paddingBottom: 20 }} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#1e1e2e', padding: 16 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  title: { fontSize: 20, fontWeight: 'bold', color: '#cdd6f4' },
  refreshBtn: { color: '#89b4fa', fontSize: 16 },
  card: { backgroundColor: '#313244', borderRadius: 12, padding: 16, marginBottom: 12 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  roomName: { fontSize: 16, fontWeight: 'bold', color: '#cdd6f4' },
  status: { fontSize: 14, fontWeight: 'bold' },
  statusPending: { color: '#f9e2af' },
  statusDone: { color: '#a6e3a1' },
  seatInfo: { fontSize: 14, color: '#a6adc8', marginBottom: 4 },
  timeInfo: { fontSize: 14, color: '#a6adc8', marginBottom: 12 },
  checkinBtn: { backgroundColor: '#a6e3a1', borderRadius: 8, padding: 12, alignItems: 'center' },
  checkinBtnText: { color: '#1e1e2e', fontSize: 16, fontWeight: 'bold' },
  empty: { color: '#a6adc8', textAlign: 'center', marginTop: 40, fontSize: 16 },
});
```

- [ ] **Step 2: 注册到导航**

修改 `mobile/App.tsx`，添加签到 Tab。

- [ ] **Step 3: 提交**

```bash
git add mobile/
git commit -m "移动端签到页面：预约列表 + 一键签到"
```

---

### Task 10: 移动端 — 好友页面

**Files:**
- Create: `mobile/src/screens/FriendsScreen.tsx`
- Modify: `mobile/App.tsx`

- [ ] **Step 1: 创建好友页面**

创建 `mobile/src/screens/FriendsScreen.tsx`：

```tsx
import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, FlatList, Alert, TextInput, Modal } from 'react-native';
import { getFriends, addFriend, deleteFriend, testFriendLogin } from '../api/client';

interface Friend {
  student_id: string;
  name: string;
  uid: string;
}

export default function FriendsScreen() {
  const [friends, setFriends] = useState<Friend[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [sid, setSid] = useState('');
  const [pwd, setPwd] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => { loadFriends(); }, []);

  const loadFriends = async () => {
    try {
      const resp = await getFriends();
      setFriends(resp.data.friends);
    } catch (e) { /* ignore */ }
  };

  const handleAdd = async () => {
    if (!sid || !pwd) { Alert.alert('提示', '请输入学号和密码'); return; }
    setLoading(true);
    try {
      const resp = await addFriend(sid, pwd);
      if (resp.data.success) {
        Alert.alert('成功', `已添加: ${resp.data.name}`);
        setShowAdd(false); setSid(''); setPwd('');
        loadFriends();
      } else {
        Alert.alert('失败', resp.data.message);
      }
    } catch (e) {
      Alert.alert('错误', '添加失败');
    }
    setLoading(false);
  };

  const handleDelete = (friend: Friend) => {
    Alert.alert('确认', `删除好友 ${friend.name}？`, [
      { text: '取消' },
      { text: '删除', style: 'destructive', onPress: async () => {
        await deleteFriend(friend.student_id);
        loadFriends();
      }},
    ]);
  };

  const handleTest = async (friend: Friend) => {
    try {
      const resp = await testFriendLogin(friend.student_id);
      Alert.alert(resp.data.success ? '成功' : '失败', resp.data.message);
    } catch (e) {
      Alert.alert('错误', '测试失败');
    }
  };

  const renderItem = ({ item }: { item: Friend }) => (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <Text style={styles.name}>{item.name}</Text>
        <Text style={styles.sid}>{item.student_id}</Text>
      </View>
      <Text style={styles.uid}>UID: {item.uid}</Text>
      <View style={styles.actions}>
        <TouchableOpacity style={styles.testBtn} onPress={() => handleTest(item)}>
          <Text style={styles.testBtnText}>测试登录</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.deleteBtn} onPress={() => handleDelete(item)}>
          <Text style={styles.deleteBtnText}>删除</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>好友列表</Text>
        <TouchableOpacity style={styles.addBtn} onPress={() => setShowAdd(true)}>
          <Text style={styles.addBtnText}>+ 添加</Text>
        </TouchableOpacity>
      </View>
      <FlatList data={friends} renderItem={renderItem}
        keyExtractor={item => item.student_id}
        ListEmptyComponent={<Text style={styles.empty}>暂无好友</Text>} />

      <Modal visible={showAdd} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>添加好友</Text>
            <TextInput style={styles.input} placeholder="学号" value={sid}
              onChangeText={setSid} placeholderTextColor="#666" />
            <TextInput style={styles.input} placeholder="密码" value={pwd}
              onChangeText={setPwd} secureTextEntry placeholderTextColor="#666" />
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => setShowAdd(false)}>
                <Text style={styles.cancelBtnText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handleAdd} disabled={loading}>
                <Text style={styles.confirmBtnText}>{loading ? '查询中...' : '添加'}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#1e1e2e', padding: 16 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  title: { fontSize: 20, fontWeight: 'bold', color: '#cdd6f4' },
  addBtn: { backgroundColor: '#89b4fa', borderRadius: 8, paddingHorizontal: 16, paddingVertical: 8 },
  addBtnText: { color: '#1e1e2e', fontWeight: 'bold' },
  card: { backgroundColor: '#313244', borderRadius: 12, padding: 16, marginBottom: 12 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  name: { fontSize: 16, fontWeight: 'bold', color: '#cdd6f4' },
  sid: { fontSize: 14, color: '#a6adc8' },
  uid: { fontSize: 13, color: '#a6adc8', marginBottom: 12 },
  actions: { flexDirection: 'row', gap: 8 },
  testBtn: { backgroundColor: '#45475a', borderRadius: 6, paddingHorizontal: 12, paddingVertical: 6 },
  testBtnText: { color: '#89b4fa', fontSize: 13 },
  deleteBtn: { backgroundColor: '#45475a', borderRadius: 6, paddingHorizontal: 12, paddingVertical: 6 },
  deleteBtnText: { color: '#f38ba8', fontSize: 13 },
  empty: { color: '#a6adc8', textAlign: 'center', marginTop: 40, fontSize: 16 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', padding: 20 },
  modal: { backgroundColor: '#313244', borderRadius: 16, padding: 24 },
  modalTitle: { fontSize: 18, fontWeight: 'bold', color: '#cdd6f4', marginBottom: 16 },
  input: { height: 48, backgroundColor: '#1e1e2e', borderRadius: 8, paddingHorizontal: 16,
           color: '#cdd6f4', fontSize: 16, marginBottom: 12, borderWidth: 1, borderColor: '#45475a' },
  modalActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 12, marginTop: 8 },
  cancelBtn: { paddingHorizontal: 20, paddingVertical: 10 },
  cancelBtnText: { color: '#a6adc8', fontSize: 16 },
  confirmBtn: { backgroundColor: '#89b4fa', borderRadius: 8, paddingHorizontal: 20, paddingVertical: 10 },
  confirmBtnText: { color: '#1e1e2e', fontSize: 16, fontWeight: 'bold' },
});
```

- [ ] **Step 2: 注册到导航并完善 App.tsx**

修改 `mobile/App.tsx`，添加好友 Tab，完整导航结构包含：首页、签到、好友。

- [ ] **Step 3: 提交**

```bash
git add mobile/
git commit -m "移动端好友页面：列表/添加/删除/测试登录"
```
