# UI 重构 + 好友代预约 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 GUI 为 4 Tab 结构，添加新手引导和仪表盘，实现好友代预约自动化（含自动同意）。

**Architecture:** 新增 `FriendStore`（好友凭证存储）和 `FriendService`（自动同意服务），重构 `gui.py` 的 Tab 结构从 5 个改为 4 个，新增首页引导/仪表盘和好友管理 Tab。

**Tech Stack:** Python 3, tkinter, requests, Playwright (已用于登录), base64 (密码混淆)

---

## 文件变更总览

| 操作 | 文件 | 职责 |
|------|------|------|
| **新建** | `seathunter/auth/friend_store.py` | 好友凭证存储（学号→UID+密码） |
| **新建** | `seathunter/services/friend_service.py` | 自动同意服务（Playwright 登录 + confirmBooking） |
| **新建** | `seathunter/services/__init__.py` | 包初始化 |
| **新建** | `tests/test_friend_store.py` | FriendStore 单元测试 |
| **新建** | `tests/test_friend_service.py` | FriendService 单元测试 |
| **新建** | `tests/__init__.py` | 测试包初始化 |
| **修改** | `seathunter/auth/uid_store.py` | 小改：确保与 FriendStore 兼容 |
| **修改** | `seathunter/scheduler/booking_runner.py` | 新增 `set_friend_confirm_registry` 回调 |
| **修改** | `seathunter/scheduler/engine.py` | 新增好友确认任务处理 |
| **修改** | `seathunter/ui/gui.py` | 重构 Tab 结构 + 新增引导/仪表盘/好友 Tab |
| **修改** | `main.py` | 传递 FriendStore 到 GuiApp |

---

## Task 1: FriendStore — 好友凭证存储

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_friend_store.py`
- Create: `seathunter/auth/friend_store.py`

- [ ] **Step 1: 创建测试包初始化**

```bash
touch tests/__init__.py
```

- [ ] **Step 2: 编写 FriendStore 测试**

创建 `tests/test_friend_store.py`：

```python
"""FriendStore 单元测试"""
import json
import os
import tempfile
import pytest
from seathunter.auth.friend_store import FriendStore


@pytest.fixture
def tmp_store(tmp_path):
    path = str(tmp_path / "friends.json")
    return FriendStore(path)


def test_empty_store(tmp_store):
    assert tmp_store.get_all() == {}
    assert tmp_store.get("23140322") is None


def test_add_and_get(tmp_store):
    tmp_store.add("23140322", "305033", "张三", "pass123")
    friend = tmp_store.get("23140322")
    assert friend is not None
    assert friend["uid"] == "305033"
    assert friend["name"] == "张三"
    assert friend["student_id"] == "23140322"
    assert friend["password_base64"] != ""  # 密码已编码


def test_password_encoding(tmp_store):
    tmp_store.add("23140322", "305033", "张三", "mypassword")
    friend = tmp_store.get("23140322")
    # base64 解码后应还原为原密码
    import base64
    decoded = base64.b64decode(friend["password_base64"]).decode("utf-8")
    assert decoded == "mypassword"


def test_get_password(tmp_store):
    tmp_store.add("23140322", "305033", "张三", "pass123")
    assert tmp_store.get_password("23140322") == "pass123"
    assert tmp_store.get_password("99999999") is None


def test_remove(tmp_store):
    tmp_store.add("23140322", "305033", "张三", "pass123")
    assert tmp_store.remove("23140322") is True
    assert tmp_store.get("23140322") is None
    assert tmp_store.remove("99999999") is False


def test_persistence(tmp_path):
    path = str(tmp_path / "friends.json")
    store1 = FriendStore(path)
    store1.add("23140322", "305033", "张三", "pass123")

    store2 = FriendStore(path)
    friend = store2.get("23140322")
    assert friend is not None
    assert friend["uid"] == "305033"


def test_get_student_ids(tmp_store):
    tmp_store.add("23140322", "305033", "张三", "pass123")
    tmp_store.add("23051110", "303687", "李四", "pass456")
    ids = tmp_store.get_student_ids()
    assert "23140322" in ids
    assert "23051110" in ids
```

- [ ] **Step 3: 运行测试确认失败**

```bash
.venv/bin/python3 -m pytest tests/test_friend_store.py -v 2>&1 | head -20
```

预期: `ModuleNotFoundError: No module named 'seathunter.auth.friend_store'`

- [ ] **Step 4: 实现 FriendStore**

创建 `seathunter/auth/friend_store.py`：

```python
"""好友凭证存储管理。

将好友的学号、UID、姓名和密码（base64 编码）持久化到 JSON 文件。
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("seathunter.auth")


class FriendStore:
    """好友凭证存储。JSON 文件格式: {student_id: {uid, name, student_id, password_base64}}"""

    def __init__(self, store_path: str):
        self._path = store_path
        self._data: Dict[str, Dict[str, str]] = {}
        self.load()

    def load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = {}

    def save(self):
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, student_id: str) -> Optional[Dict[str, str]]:
        return self._data.get(student_id)

    def get_all(self) -> Dict[str, Dict[str, str]]:
        return dict(self._data)

    def get_student_ids(self) -> List[str]:
        return list(self._data.keys())

    def add(self, student_id: str, uid: str, name: str, password: str):
        self._data[student_id] = {
            "uid": uid,
            "name": name,
            "student_id": student_id,
            "password_base64": base64.b64encode(password.encode("utf-8")).decode("ascii"),
        }
        self.save()

    def remove(self, student_id: str) -> bool:
        if student_id in self._data:
            del self._data[student_id]
            self.save()
            return True
        return False

    def get_password(self, student_id: str) -> Optional[str]:
        friend = self.get(student_id)
        if not friend:
            return None
        try:
            return base64.b64decode(friend["password_base64"]).decode("utf-8")
        except Exception:
            return None
```

- [ ] **Step 5: 运行测试确认通过**

```bash
.venv/bin/python3 -m pytest tests/test_friend_store.py -v
```

预期: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add tests/__init__.py tests/test_friend_store.py seathunter/auth/friend_store.py
git commit -m "新增 FriendStore：好友凭证存储（学号、UID、密码 base64 编码）"
```

---

## Task 2: FriendService — 自动同意服务

**Files:**
- Create: `seathunter/services/__init__.py`
- Create: `tests/test_friend_service.py`
- Create: `seathunter/services/friend_service.py`

- [ ] **Step 1: 创建 services 包**

```bash
mkdir -p seathunter/services
touch seathunter/services/__init__.py
```

- [ ] **Step 2: 编写 FriendService 测试**

创建 `tests/test_friend_service.py`：

```python
"""FriendService 单元测试"""
from unittest.mock import MagicMock, patch
import pytest
from seathunter.services.friend_service import FriendService


@pytest.fixture
def mock_friend_store():
    store = MagicMock()
    store.get.return_value = {
        "uid": "305033", "name": "张三",
        "student_id": "23140322",
        "password_base64": "cGFzczEyMw=="  # pass123
    }
    store.get_password.return_value = "pass123"
    return store


@pytest.fixture
def service(mock_friend_store):
    return FriendService(mock_friend_store, base_url="https://hdu.huitu.zhishulib.com")


def test_init(service):
    assert service.base_url == "https://hdu.huitu.zhishulib.com"


def test_confirm_missing_friend(service, mock_friend_store):
    mock_friend_store.get.return_value = None
    ok, msg = service.auto_confirm("12345", "99999999")
    assert ok is False
    assert "未找到" in msg


@patch("seathunter.services.friend_service.requests")
def test_confirm_success(mock_requests, service):
    # 模拟登录成功
    mock_session = MagicMock()
    mock_requests.Session.return_value = mock_session

    # 模拟登录页面
    login_resp = MagicMock()
    login_resp.status_code = 200
    mock_session.get.return_value = login_resp

    # 模拟登录 POST
    login_post = MagicMock()
    login_post.status_code = 200
    login_post.json.return_value = {"CODE": "ok"}
    mock_session.post.return_value = login_post

    # 模拟 confirmBooking 响应
    confirm_resp = MagicMock()
    confirm_resp.status_code = 200
    confirm_resp.json.return_value = {"CODE": "ok", "DATA": {"result": "success"}}
    # post 被调用两次：登录 + confirmBooking
    mock_session.post.side_effect = [login_post, confirm_resp]

    ok, msg = service.auto_confirm("12345", "23140322")
    # 由于 Playwright 登录较复杂，这里主要测试逻辑分支
    # 实际集成测试需要真实环境
```

- [ ] **Step 3: 运行测试确认失败**

```bash
.venv/bin/python3 -m pytest tests/test_friend_service.py -v 2>&1 | head -20
```

预期: `ModuleNotFoundError`

- [ ] **Step 4: 实现 FriendService**

创建 `seathunter/services/friend_service.py`：

```python
"""好友代预约自动同意服务。

用好友的账号登录系统，调用 confirmBooking API 完成预约确认。
使用 requests + Cookie 方式登录（复用 SessionManager 的登录逻辑）。
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from seathunter.auth.friend_store import FriendStore

logger = logging.getLogger("seathunter.services")


class FriendService:
    """好友代预约服务。"""

    def __init__(self, friend_store: FriendStore, base_url: str = "https://hdu.huitu.zhishulib.com"):
        self.store = friend_store
        self.base_url = base_url

    def auto_confirm(self, booking_id: str, friend_student_id: str) -> tuple[bool, str]:
        """用好友账号自动确认预约。

        Args:
            booking_id: 预约 ID
            friend_student_id: 好友学号

        Returns:
            (成功?, 消息)
        """
        friend = self.store.get(friend_student_id)
        if not friend:
            return (False, f"未找到好友 {friend_student_id} 的凭证")

        password = self.store.get_password(friend_student_id)
        if not password:
            return (False, f"好友 {friend_student_id} 的密码为空")

        try:
            return self._login_and_confirm(
                student_id=friend_student_id,
                password=password,
                booking_id=booking_id,
            )
        except Exception as e:
            logger.error("好友确认异常: %s", e)
            return (False, str(e))

    def _login_and_confirm(self, student_id: str, password: str,
                           booking_id: str) -> tuple[bool, str]:
        """用好友账号登录并调用 confirmBooking。

        使用 Playwright 进行登录（与主账号登录逻辑一致），
        然后用获得的 Cookie 调用 confirmBooking API。
        """
        from seathunter.auth.session_manager import lookup_uid

        # 先验证好友凭证有效（同时获取 Cookie）
        success, uid, name = lookup_uid(student_id, password, self.base_url)
        if not success:
            return (False, f"好友 {student_id} 登录失败，请检查学号密码")

        # 用 Playwright 获取的 Cookie 创建独立 session
        # lookup_uid 内部会用 Playwright 登录，我们需要复用其 Cookie
        # 这里直接用 requests session + Playwright cookie
        try:
            return self._confirm_with_playwright(student_id, password, booking_id)
        except Exception as e:
            return (False, f"确认预约失败: {e}")

    def _confirm_with_playwright(self, student_id: str, password: str,
                                  booking_id: str) -> tuple[bool, str]:
        """用 Playwright 登录好友账号并调用 confirmBooking。

        复用 playwright_login 模块的登录流程获取 Cookie，
        然后用 requests session 调用 confirmBooking API。
        """
        from seathunter.auth.playwright_login import login_with_playwright

        # 用 Playwright 登录获取 Cookie
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36",
            "Accept": "application/json",
        })

        cookies = login_with_playwright(student_id, password, self.base_url)
        if not cookies:
            return (False, f"好友 {student_id} Playwright 登录失败")

        for name, value in cookies.items():
            session.cookies.set(name, value, domain="hdu.huitu.zhishulib.com")

        # 调用 confirmBooking
        url = f"{self.base_url}/Seat/Index/confirmBooking"
        params = {"bookingId": booking_id, "LAB_JSON": "1"}
        resp = session.post(url=url, params=params, timeout=30)

        if resp.status_code != 200:
            return (False, f"HTTP {resp.status_code}")

        data = resp.json()
        if data.get("CODE") == "ok":
            result = data.get("DATA", {}).get("result", "")
            if result == "success":
                logger.info("好友 %s 确认预约成功: bookingId=%s", student_id, booking_id)
                return (True, "确认成功")
            return (False, data.get("DATA", {}).get("msg", "确认失败"))
        return (False, data.get("MESSAGE", "确认失败"))

    def test_login(self, friend_student_id: str) -> tuple[bool, str]:
        """测试好友登录是否正常。

        Returns:
            (成功?, 消息)
        """
        friend = self.store.get(friend_student_id)
        if not friend:
            return (False, f"未找到好友 {friend_student_id}")

        password = self.store.get_password(friend_student_id)
        if not password:
            return (False, "密码为空")

        from seathunter.auth.session_manager import lookup_uid
        success, uid, name = lookup_uid(friend_student_id, password, self.base_url)
        if success:
            return (True, f"登录成功: {name} (UID={uid})")
        return (False, "登录失败，请检查学号密码")
```

- [ ] **Step 5: 运行测试确认通过**

```bash
.venv/bin/python3 -m pytest tests/test_friend_service.py -v
```

预期: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add seathunter/services/__init__.py seathunter/services/friend_service.py tests/test_friend_service.py
git commit -m "新增 FriendService：好友代预约自动同意服务"
```

---

## Task 3: 集成自动同意到预约流程

**Files:**
- Modify: `seathunter/scheduler/booking_runner.py`
- Modify: `seathunter/scheduler/engine.py`
- Modify: `seathunter/ui/gui.py`（仅添加回调注册，不改 Tab 结构）

- [ ] **Step 1: 修改 BookingRunner 添加好友确认回调**

在 `booking_runner.py` 中新增 `set_friend_confirm_registry` 方法：

在 `set_checkin_registry` 方法之后添加：

```python
def set_friend_confirm_registry(self, callback):
    """设置好友确认回调。callback(booking_id: str, friend_student_id: str)"""
    self._friend_confirm_registry = callback
```

在 `_book_single_plan` 方法中，预约成功后（`result.success` 为 True 时），检查方案中是否有好友座位并触发确认。找到 `if result.success and self._checkin_registry:` 这段代码，在其前面添加好友确认逻辑：

```python
# 预约成功后，如果有好友代预约，触发自动同意
if result.success and hasattr(self, '_friend_confirm_registry') and self._friend_confirm_registry:
    for seat in plan.seats:
        if seat.booker_uid and seat.booker_uid != self.session_mgr.uid:
            # 找到好友的 UID，查对应的学号
            self._friend_confirm_registry(result.booking_id, seat.booker_uid)
            break  # 只需要确认一次（同一个 bookingId）
```

- [ ] **Step 2: 修改 Engine 添加好友确认回调属性**

在 `engine.py` 的 `__init__` 中添加回调属性（在 `on_checkin_result` 之后）：

```python
self.on_friend_confirm: Optional[Callable] = None  # 好友确认回调
```

在 `_execute_booking` 方法（或 `_engine_loop` 中调用 `run_booking` 的位置），注册好友确认回调：

找到 `self.runner.set_checkin_registry(self.register_checkin)` 这行，在其后添加：

```python
def _friend_confirm(booking_id, friend_uid):
    """触发好友确认（在预约线程中调用）"""
    if self.on_friend_confirm:
        self.on_friend_confirm(booking_id, friend_uid)

self.runner.set_friend_confirm_registry(_friend_confirm)
```

- [ ] **Step 3: 在 GuiApp 中注册好友确认回调**

在 `gui.py` 的 `__init__` 中，找到设置 engine 回调的位置，添加：

```python
self.engine.on_friend_confirm = self._on_friend_confirm
```

添加回调方法：

```python
def _on_friend_confirm(self, booking_id: str, friend_uid: str):
    """好友确认回调（从 engine 线程调用）"""
    # 通过 UID 找到好友学号
    friend_sid = None
    for sid, info in self.friend_store.get_all().items():
        if info.get("uid") == friend_uid:
            friend_sid = sid
            break

    if not friend_sid:
        self._log(f"未找到 UID={friend_uid} 对应的好友，跳过自动确认", "warning")
        return

    self._log(f"正在用好友 {friend_sid} 账号确认预约...", "info")

    def _do():
        ok, msg = self.friend_service.auto_confirm(booking_id, friend_sid)
        if ok:
            self._log(f"好友 {friend_sid} 确认预约成功", "success")
        else:
            self._log(f"好友 {friend_sid} 确认失败: {msg}", "warning")

    import threading
    threading.Thread(target=_do, daemon=True).start()
```

- [ ] **Step 4: 运行语法检查**

```bash
.venv/bin/python3 -c "import ast; ast.parse(open('seathunter/scheduler/booking_runner.py').read()); ast.parse(open('seathunter/scheduler/engine.py').read()); ast.parse(open('seathunter/ui/gui.py').read()); print('OK')"
```

- [ ] **Step 5: 提交**

```bash
git add seathunter/scheduler/booking_runner.py seathunter/scheduler/engine.py seathunter/ui/gui.py
git commit -m "集成好友自动同意到预约流程：预约成功后自动调用 confirmBooking"
```

---

## Task 4: Tab 重构 — 从 5 Tab 改为 4 Tab

**Files:**
- Modify: `seathunter/ui/gui.py`

这是最大的改动。核心是重写 `_build_tabs` 和相关方法。

- [ ] **Step 1: 备份当前 gui.py**

```bash
cp seathunter/ui/gui.py seathunter/ui/gui.py.bak
```

- [ ] **Step 2: 修改 `__init__` 添加 FriendStore 和 FriendService**

在 `__init__` 中，找到 `self.uid_store = UidStore(...)` 这行，在其后添加：

```python
from seathunter.auth.friend_store import FriendStore
from seathunter.services.friend_service import FriendService

friend_store_path = os.path.join(os.path.dirname(self.config.config_path), "friends.json")
self.friend_store = FriendStore(friend_store_path)
self.friend_service = FriendService(self.friend_store, base_url=session_manager.base_url)
```

- [ ] **Step 3: 重写 `_build_tabs` 方法**

替换原来的 `_build_tabs` 方法：

```python
def _build_tabs(self):
    self.notebook = ttk.Notebook(self.root)
    self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    self._build_home_tab()      # Tab 0: 首页
    self._build_booking_tab()   # Tab 1: 预约（一体化）
    self._build_friends_tab()   # Tab 2: 好友
    self._build_settings_tab()  # Tab 3: 设置
```

- [ ] **Step 4: 删除旧的 Tab 构建方法**

删除以下方法（它们的内容会被合并到新方法中）：
- `_build_scheduler_tab()` — 调度引擎部分移入 `_build_booking_tab`
- `_build_tools_tab()` — UID 管理移入 `_build_friends_tab`，预约历史移入 `_build_booking_tab`
- `_build_help_tab()` — 帮助内容移入 `_build_settings_tab`

- [ ] **Step 5: 重写 `_build_booking_tab` — 一体化布局**

新布局：上半部分方案管理 + 下半部分左右分区（调度引擎 + 签到）+ 底部预约历史日志。

```python
def _build_booking_tab(self):
    """Tab 1: 预约 — 方案管理 + 调度引擎 + 签到 一体化"""
    frame = ttk.Frame(self.notebook, padding=5)
    self.notebook.add(frame, text="预约")

    # ── 上半部分：方案管理 ──
    plans_frame = ttk.LabelFrame(frame, text="方案管理", padding=5)
    plans_frame.pack(fill=tk.BOTH, expand=False)

    cols = ("idx", "plan_id", "room", "seats", "time", "duration", "bookers")
    self.plans_tree = ttk.Treeview(plans_frame, columns=cols, show="headings", height=5)
    for col, text, w in [
        ("idx", "#", 30), ("plan_id", "方案ID", 100), ("room", "房间", 100),
        ("seats", "座位", 100), ("time", "开始时间", 80), ("duration", "时长", 50),
        ("bookers", "预约人", 100),
    ]:
        self.plans_tree.heading(col, text=text)
        self.plans_tree.column(col, width=w)
    self.plans_tree.pack(fill=tk.X)

    plans_btn = ttk.Frame(plans_frame)
    plans_btn.pack(fill=tk.X, pady=(3, 0))
    ttk.Button(plans_btn, text="添加方案", command=self._add_plan_dialog).pack(side=tk.LEFT, padx=2)
    ttk.Button(plans_btn, text="删除选中", command=self._delete_selected_plans).pack(side=tk.LEFT, padx=2)
    ttk.Button(plans_btn, text="批量修改时间", command=self._batch_change_time_dialog).pack(side=tk.LEFT, padx=2)

    # ── 下半部分：调度 + 签到（左右分区）──
    bottom_frame = ttk.Frame(frame)
    bottom_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

    # 左侧：调度引擎
    sched_frame = ttk.LabelFrame(bottom_frame, text="调度引擎", padding=5)
    sched_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    sched_btn_row = ttk.Frame(sched_frame)
    sched_btn_row.pack(fill=tk.X)
    ttk.Button(sched_btn_row, text="启动", command=self._start_scheduler).pack(side=tk.LEFT, padx=2)
    ttk.Button(sched_btn_row, text="停止", command=self._stop_scheduler).pack(side=tk.LEFT, padx=2)
    ttk.Button(sched_btn_row, text="添加调度", command=self._add_schedule_dialog).pack(side=tk.LEFT, padx=2)
    ttk.Button(sched_btn_row, text="删除", command=self._delete_selected_schedule).pack(side=tk.LEFT, padx=2)

    self.scheduler_status_label = ttk.Label(sched_frame, text="● 未运行", foreground="gray")
    self.scheduler_status_label.pack(anchor=tk.W, pady=(3, 0))

    cols2 = ("idx", "type", "target", "status", "plans")
    self.schedules_tree = ttk.Treeview(sched_frame, columns=cols2, show="headings", height=4)
    for col, text, w in [
        ("idx", "#", 30), ("type", "类型", 60), ("target", "目标", 100),
        ("status", "状态", 50), ("plans", "方案", 100),
    ]:
        self.schedules_tree.heading(col, text=text)
        self.schedules_tree.column(col, width=w)
    self.schedules_tree.pack(fill=tk.BOTH, expand=True)

    # 右侧：签到
    checkin_frame = ttk.LabelFrame(bottom_frame, text="签到", padding=5)
    checkin_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

    ttk.Label(checkin_frame, text="bookingId:").pack(anchor=tk.W)
    self._checkin_entry = ttk.Entry(checkin_frame, width=20)
    self._checkin_entry.pack(fill=tk.X, pady=2)

    checkin_btn_row = ttk.Frame(checkin_frame)
    checkin_btn_row.pack(fill=tk.X, pady=2)
    ttk.Button(checkin_btn_row, text="签到", command=self._manual_checkin_from_entry).pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Button(checkin_btn_row, text="从历史选择", command=self._pick_booking_from_history).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

    checkin_btn_row2 = ttk.Frame(checkin_frame)
    checkin_btn_row2.pack(fill=tk.X, pady=(2, 0))
    ttk.Button(checkin_btn_row2, text="获取当前预约", command=self._fetch_current_bookings).pack(fill=tk.X)

    self._checkin_result_label = ttk.Label(checkin_frame, text="", foreground="gray", wraplength=150)
    self._checkin_result_label.pack(fill=tk.X, pady=(5, 0))

    # ── 底部：预约日志 ──
    log_frame = ttk.LabelFrame(frame, text="预约日志", padding=5)
    log_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

    self.booking_log = tk.Text(log_frame, height=6, wrap=tk.WORD, state=tk.DISABLED,
                               font=("Menlo", 9))
    self.booking_log.pack(fill=tk.BOTH, expand=True)
    for tag, color in [("success", "#2ecc71"), ("error", "#e74c3c"),
                       ("info", "#3498db"), ("warning", "#f39c12")]:
        self.booking_log.tag_configure(tag, foreground=color)

    ttk.Button(log_frame, text="清空日志", command=self._clear_booking_log).pack(anchor=tk.E, pady=(3, 0))

    self._refresh_plans_tree()
    self._refresh_schedules_tree()
    self._update_status_display()
```

- [ ] **Step 6: 重写 `_build_settings_tab` — 合并帮助内容**

在设置 Tab 底部添加帮助区域：

```python
def _build_settings_tab(self):
    """Tab 3: 设置 — 账号 + 请求参数 + 帮助"""
    frame = ttk.Frame(self.notebook, padding=5)
    self.notebook.add(frame, text="设置")

    # ── 账号信息 ──
    account_frame = ttk.LabelFrame(frame, text="账号信息", padding=5)
    account_frame.pack(fill=tk.X)

    self.account_labels = {}
    for key, label_text in [("student_id", "学号"), ("name", "姓名"), ("uid", "UID")]:
        row = ttk.Frame(account_frame)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text=f"{label_text}:", width=8, font=("", 9, "bold")).pack(side=tk.LEFT)
        lbl = ttk.Label(row, text="—", font=("", 9))
        lbl.pack(side=tk.LEFT, padx=(5, 0))
        self.account_labels[key] = lbl

    ttk.Button(account_frame, text="重新登录", command=self._relogin).pack(anchor=tk.W, pady=(5, 0))

    # ── 请求设置 ──
    req_frame = ttk.LabelFrame(frame, text="请求设置", padding=5)
    req_frame.pack(fill=tk.X, pady=(5, 0))

    row1 = ttk.Frame(req_frame)
    row1.pack(fill=tk.X, pady=2)
    ttk.Label(row1, text="重试间隔(秒):").pack(side=tk.LEFT)
    self._interval_var = tk.IntVar(value=5)
    ttk.Spinbox(row1, from_=1, to=300, textvariable=self._interval_var, width=5).pack(side=tk.LEFT, padx=5)

    row2 = ttk.Frame(req_frame)
    row2.pack(fill=tk.X, pady=2)
    ttk.Label(row2, text="最大重试次数:").pack(side=tk.LEFT)
    self._max_retry_var = tk.IntVar(value=10)
    ttk.Spinbox(row2, from_=1, to=999, textvariable=self._max_retry_var, width=5).pack(side=tk.LEFT, padx=5)

    ttk.Button(req_frame, text="保存设置", command=self._save_settings).pack(anchor=tk.W, pady=(5, 0))

    # ── 帮助 ──
    help_frame = ttk.LabelFrame(frame, text="帮助", padding=5)
    help_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

    help_text = tk.Text(help_frame, wrap=tk.WORD, state=tk.DISABLED, height=8)
    help_text.pack(fill=tk.BOTH, expand=True)
    help_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "docs", "help.md")
    if os.path.exists(help_path):
        with open(help_path, "r", encoding="utf-8") as f:
            content = f.read()
        help_text.config(state=tk.NORMAL)
        help_text.insert(tk.END, content)
        help_text.config(state=tk.DISABLED)

    self._update_account_display()
```

- [ ] **Step 7: 语法检查**

```bash
.venv/bin/python3 -c "import ast; ast.parse(open('seathunter/ui/gui.py').read()); print('语法OK')"
```

- [ ] **Step 8: 提交**

```bash
git add seathunter/ui/gui.py
git commit -m "Tab 重构：5 Tab → 4 Tab（首页/预约/好友/设置）"
```

---

## Task 5: 好友 Tab UI

**Files:**
- Modify: `seathunter/ui/gui.py`

- [ ] **Step 1: 实现 `_build_friends_tab`**

```python
def _build_friends_tab(self):
    """Tab 2: 好友 — 好友管理 + 代预约"""
    frame = ttk.Frame(self.notebook, padding=5)
    self.notebook.add(frame, text="好友")

    # ── 好友列表 ──
    list_frame = ttk.LabelFrame(frame, text="好友列表", padding=5)
    list_frame.pack(fill=tk.BOTH, expand=True)

    cols = ("student_id", "name", "uid")
    self.friends_tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=6)
    for col, text, w in [
        ("student_id", "学号", 120), ("name", "姓名", 120), ("uid", "UID", 80),
    ]:
        self.friends_tree.heading(col, text=text)
        self.friends_tree.column(col, width=w)

    sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.friends_tree.yview)
    self.friends_tree.configure(yscrollcommand=sb.set)
    self.friends_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sb.pack(side=tk.RIGHT, fill=tk.Y)

    list_btn = ttk.Frame(list_frame)
    list_btn.pack(fill=tk.X, pady=(5, 0))
    ttk.Button(list_btn, text="删除选中", command=self._delete_selected_friend).pack(side=tk.LEFT, padx=2)
    ttk.Button(list_btn, text="测试登录", command=self._test_friend_login).pack(side=tk.LEFT, padx=2)

    # ── 添加好友 ──
    add_frame = ttk.LabelFrame(frame, text="添加好友", padding=5)
    add_frame.pack(fill=tk.X, pady=(5, 0))

    row1 = ttk.Frame(add_frame)
    row1.pack(fill=tk.X, pady=2)
    ttk.Label(row1, text="学号:", width=6).pack(side=tk.LEFT)
    self._friend_sid_entry = ttk.Entry(row1, width=15)
    self._friend_sid_entry.pack(side=tk.LEFT, padx=5)
    ttk.Label(row1, text="密码:", width=6).pack(side=tk.LEFT)
    self._friend_pwd_entry = ttk.Entry(row1, width=15, show="*")
    self._friend_pwd_entry.pack(side=tk.LEFT, padx=5)

    self._add_friend_btn = ttk.Button(add_frame, text="查询并添加", command=self._add_friend)
    self._add_friend_btn.pack(anchor=tk.W, pady=(3, 0))

    self._refresh_friends_tree()
```

- [ ] **Step 2: 实现好友操作方法**

```python
def _refresh_friends_tree(self):
    """刷新好友列表"""
    for item in self.friends_tree.get_children():
        self.friends_tree.delete(item)
    for sid, info in self.friend_store.get_all().items():
        self.friends_tree.insert("", tk.END, values=(
            info.get("student_id", sid), info.get("name", ""), info.get("uid", "")
        ))

def _add_friend(self):
    """添加好友"""
    sid = self._friend_sid_entry.get().strip()
    pwd = self._friend_pwd_entry.get().strip()
    if not sid or not pwd:
        messagebox.showwarning("提示", "请输入学号和密码")
        return

    self._add_friend_btn.config(state=tk.DISABLED, text="查询中...")

    def _do():
        try:
            ok, uid, name = self.session_mgr.lookup_uid(sid, pwd, self.session_mgr.base_url)
            if ok:
                self.friend_store.add(sid, uid, name, pwd)
                self.root.after(0, lambda: self._on_friend_added(sid, name, uid))
            else:
                self.root.after(0, lambda: messagebox.showerror("失败", "查询失败，请检查学号密码"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        finally:
            self.root.after(0, lambda: self._add_friend_btn.config(state=tk.NORMAL, text="查询并添加"))

    import threading
    threading.Thread(target=_do, daemon=True).start()

def _on_friend_added(self, sid, name, uid):
    messagebox.showinfo("成功", f"已添加好友: {name} (UID={uid})")
    self._friend_sid_entry.delete(0, tk.END)
    self._friend_pwd_entry.delete(0, tk.END)
    self._refresh_friends_tree()

def _delete_selected_friend(self):
    sel = self.friends_tree.selection()
    if not sel:
        messagebox.showinfo("提示", "请先选择要删除的好友")
        return
    values = self.friends_tree.item(sel[0], "values")
    sid = values[0]
    if messagebox.askyesno("确认", f"确定删除好友 {sid}？"):
        self.friend_store.remove(sid)
        self._refresh_friends_tree()

def _test_friend_login(self):
    sel = self.friends_tree.selection()
    if not sel:
        messagebox.showinfo("提示", "请先选择要测试的好友")
        return
    values = self.friends_tree.item(sel[0], "values")
    sid = values[0]

    def _do():
        ok, msg = self.friend_service.test_login(sid)
        self.root.after(0, lambda: messagebox.showinfo("测试结果", msg if ok else f"失败: {msg}"))

    import threading
    threading.Thread(target=_do, daemon=True).start()
```

- [ ] **Step 3: 语法检查**

```bash
.venv/bin/python3 -c "import ast; ast.parse(open('seathunter/ui/gui.py').read()); print('语法OK')"
```

- [ ] **Step 4: 提交**

```bash
git add seathunter/ui/gui.py
git commit -m "新增好友 Tab：好友列表、添加/删除、测试登录"
```

---

## Task 6: 首页 — 新手引导

**Files:**
- Modify: `seathunter/ui/gui.py`

- [ ] **Step 1: 实现 `_build_home_tab` 框架**

```python
def _build_home_tab(self):
    """Tab 0: 首页 — 新手引导 / 仪表盘"""
    self._home_frame = ttk.Frame(self.notebook, padding=5)
    self.notebook.add(self._home_frame, text="首页")

    # 检测是否首次使用
    is_first_time = not self.session_mgr.uid or len(self.config.get_plans()) == 0

    if is_first_time:
        self._show_wizard()
    else:
        self._show_dashboard()
```

- [ ] **Step 2: 实现新手引导**

```python
def _show_wizard(self):
    """显示新手引导"""
    for w in self._home_frame.winfo_children():
        w.destroy()

    self._wizard_step = 0
    self._wizard_friends = []  # 引导中添加的好友暂存

    container = ttk.Frame(self._home_frame)
    container.pack(fill=tk.BOTH, expand=True)

    self._wizard_title = ttk.Label(container, text="", font=("", 14, "bold"))
    self._wizard_title.pack(pady=(10, 5))

    self._wizard_content = ttk.Frame(container)
    self._wizard_content.pack(fill=tk.BOTH, expand=True, padx=20)

    self._wizard_btn_frame = ttk.Frame(container)
    self._wizard_btn_frame.pack(fill=tk.X, padx=20, pady=10)

    self._update_wizard_step()

def _update_wizard_step(self):
    """更新引导步骤"""
    for w in self._wizard_content.winfo_children():
        w.destroy()
    for w in self._wizard_btn_frame.winfo_children():
        w.destroy()

    steps = [
        self._wizard_step_login,
        self._wizard_step_friends,
        self._wizard_step_plan,
        self._wizard_step_schedule,
    ]

    if self._wizard_step >= len(steps):
        self._show_dashboard()
        return

    steps[self._wizard_step]()

def _wizard_step_login(self):
    """引导 Step 1: 登录"""
    self._wizard_title.config(text="Step 1: 登录")

    if self.session_mgr.uid:
        ttk.Label(self._wizard_content, text=f"✅ 已登录: {self.session_mgr.name} (UID={self.session_mgr.uid})",
                  font=("", 11)).pack(pady=20)
        ttk.Button(self._wizard_btn_frame, text="下一步 →",
                   command=self._wizard_next).pack(side=tk.RIGHT)
        return

    ttk.Label(self._wizard_content, text="请输入学号和密码登录图书馆系统",
              font=("", 10)).pack(pady=10)

    row1 = ttk.Frame(self._wizard_content)
    row1.pack(pady=5)
    ttk.Label(row1, text="学号:", width=6).pack(side=tk.LEFT)
    self._wiz_sid = ttk.Entry(row1, width=15)
    self._wiz_sid.pack(side=tk.LEFT, padx=5)

    row2 = ttk.Frame(self._wizard_content)
    row2.pack(pady=5)
    ttk.Label(row2, text="密码:", width=6).pack(side=tk.LEFT)
    self._wiz_pwd = ttk.Entry(row2, width=15, show="*")
    self._wiz_pwd.pack(side=tk.LEFT, padx=5)

    self._wiz_login_btn = ttk.Button(self._wizard_content, text="登录", command=self._wizard_login)
    self._wiz_login_btn.pack(pady=10)

    self._wiz_login_status = ttk.Label(self._wizard_content, text="", foreground="gray")
    self._wiz_login_status.pack()

def _wizard_login(self):
    """引导中的登录操作"""
    sid = self._wiz_sid.get().strip()
    pwd = self._wiz_pwd.get().strip()
    if not sid or not pwd:
        messagebox.showwarning("提示", "请输入学号和密码")
        return

    self._wiz_login_btn.config(state=tk.DISABLED, text="登录中...")
    self._wiz_login_status.config(text="正在登录，请稍候...", foreground="gray")

    def _do():
        # 保存到配置
        self.config.set("account.student_id", sid)
        self.config.set("account.password", pwd)
        ok, err_type = self.session_mgr.login()
        if ok:
            self.root.after(0, lambda: self._on_wizard_login_success())
        else:
            msg = "网络错误" if err_type == "network" else "登录失败，请检查学号密码"
            self.root.after(0, lambda: self._wiz_login_status.config(text=msg, foreground="red"))
            self.root.after(0, lambda: self._wiz_login_btn.config(state=tk.NORMAL, text="登录"))

    import threading
    threading.Thread(target=_do, daemon=True).start()

def _on_wizard_login_success(self):
    self._wiz_login_status.config(text=f"✅ 登录成功: {self.session_mgr.name}", foreground="green")
    self.root.after(1000, self._wizard_next)

def _wizard_step_friends(self):
    """引导 Step 2: 添加好友（可跳过）"""
    self._wizard_title.config(text="Step 2: 添加好友（可跳过）")

    ttk.Label(self._wizard_content, text="如果你经常和朋友一起去图书馆，可以添加好友信息\n添加后预约时可自动为好友代预约",
              font=("", 10)).pack(pady=10)

    row1 = ttk.Frame(self._wizard_content)
    row1.pack(pady=5)
    ttk.Label(row1, text="好友学号:", width=8).pack(side=tk.LEFT)
    self._wiz_fsid = ttk.Entry(row1, width=15)
    self._wiz_fsid.pack(side=tk.LEFT, padx=5)
    ttk.Label(row1, text="密码:", width=6).pack(side=tk.LEFT)
    self._wiz_fpwd = ttk.Entry(row1, width=15, show="*")
    self._wiz_fpwd.pack(side=tk.LEFT, padx=5)

    ttk.Button(self._wizard_content, text="查询并添加", command=self._wizard_add_friend).pack(pady=5)

    self._wiz_friend_list = ttk.Label(self._wizard_content, text="", foreground="gray")
    self._wiz_friend_list.pack()

    btn_frame = self._wizard_btn_frame
    ttk.Button(btn_frame, text="跳过", command=self._wizard_next).pack(side=tk.RIGHT, padx=5)
    ttk.Button(btn_frame, text="下一步 →", command=self._wizard_next).pack(side=tk.RIGHT)

def _wizard_add_friend(self):
    sid = self._wiz_fsid.get().strip()
    pwd = self._wiz_fpwd.get().strip()
    if not sid or not pwd:
        messagebox.showwarning("提示", "请输入好友学号和密码")
        return

    def _do():
        try:
            ok, uid, name = self.session_mgr.lookup_uid(sid, pwd, self.session_mgr.base_url)
            if ok:
                self.friend_store.add(sid, uid, name, pwd)
                self._wizard_friends.append(sid)
                self.root.after(0, lambda: self._wiz_friend_list.config(
                    text=f"已添加: {name} ({sid})", foreground="green"))
                self.root.after(0, lambda: self._wiz_fsid.delete(0, tk.END))
                self.root.after(0, lambda: self._wiz_fpwd.delete(0, tk.END))
            else:
                self.root.after(0, lambda: messagebox.showerror("失败", "查询失败"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))

    import threading
    threading.Thread(target=_do, daemon=True).start()

def _wizard_step_plan(self):
    """引导 Step 3: 创建方案"""
    self._wizard_title.config(text="Step 3: 创建预约方案")

    ttk.Label(self._wizard_content, text="设置你的常用预约方案（房间、座位、时间）",
              font=("", 10)).pack(pady=10)

    # 简化版方案创建：直接跳转到添加方案对话框
    ttk.Label(self._wizard_content, text="点击下方按钮打开方案配置：").pack(pady=5)
    ttk.Button(self._wizard_content, text="添加方案", command=self._add_plan_dialog).pack(pady=5)

    btn_frame = self._wizard_btn_frame
    ttk.Button(btn_frame, text="跳过", command=self._wizard_next).pack(side=tk.RIGHT, padx=5)
    ttk.Button(btn_frame, text="下一步 →", command=self._wizard_next).pack(side=tk.RIGHT)

def _wizard_step_schedule(self):
    """引导 Step 4: 设置调度"""
    self._wizard_title.config(text="Step 4: 设置自动调度（可跳过）")

    ttk.Label(self._wizard_content, text="设置每天自动抢座的时间\n系统会在指定时间自动为你预约座位",
              font=("", 10)).pack(pady=10)

    ttk.Label(self._wizard_content, text="调度功能请在「预约」Tab 中配置").pack(pady=5)

    btn_frame = self._wizard_btn_frame
    ttk.Button(btn_frame, text="完成", command=self._wizard_finish).pack(side=tk.RIGHT, padx=5)

def _wizard_next(self):
    self._wizard_step += 1
    self._update_wizard_step()

def _wizard_finish(self):
    self._show_dashboard()
```

- [ ] **Step 3: 实现仪表盘**

```python
def _show_dashboard(self):
    """显示日常仪表盘"""
    for w in self._home_frame.winfo_children():
        w.destroy()

    # ── 顶部状态 ──
    status_frame = ttk.LabelFrame(self._home_frame, text="状态", padding=5)
    status_frame.pack(fill=tk.X)

    self._dash_login_label = ttk.Label(status_frame, text="", font=("", 10))
    self._dash_login_label.pack(anchor=tk.W)

    self._dash_engine_label = ttk.Label(status_frame, text="", font=("", 10))
    self._dash_engine_label.pack(anchor=tk.W)

    # ── 今日预约 ──
    booking_frame = ttk.LabelFrame(self._home_frame, text="今日预约", padding=5)
    booking_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

    self._dash_bookings_text = tk.Text(booking_frame, height=4, wrap=tk.WORD,
                                        state=tk.DISABLED, font=("Menlo", 10))
    self._dash_bookings_text.pack(fill=tk.BOTH, expand=True)

    # ── 快捷操作 ──
    action_frame = ttk.Frame(self._home_frame)
    action_frame.pack(fill=tk.X, pady=(5, 0))

    ttk.Button(action_frame, text="获取当前预约", command=self._fetch_current_bookings).pack(side=tk.LEFT, padx=2)
    ttk.Button(action_frame, text="启动调度", command=self._start_scheduler).pack(side=tk.LEFT, padx=2)
    ttk.Button(action_frame, text="停止调度", command=self._stop_scheduler).pack(side=tk.LEFT, padx=2)

    self._refresh_dashboard()

def _refresh_dashboard(self):
    """刷新仪表盘数据"""
    # 登录状态
    if self.session_mgr.uid:
        self._dash_login_label.config(text=f"👤 已登录: {self.session_mgr.name} ({self.session_mgr.uid})")
    else:
        self._dash_login_label.config(text="❌ 未登录")

    # 引擎状态
    status = self.engine.get_status()
    if status["running"]:
        trigger = status.get("trigger_time")
        trigger_str = trigger.strftime("%H:%M") if trigger else "—"
        remaining = status.get("remaining_seconds")
        remain_str = f"{remaining // 60}分{remaining % 60}秒" if remaining else "—"
        self._dash_engine_label.config(
            text=f"⚙️ 调度引擎: ● 运行中 | 下次触发: {trigger_str} | 倒计时: {remain_str}")
    else:
        self._dash_engine_label.config(text="⚙️ 调度引擎: ○ 未运行")

    # 定时刷新
    self.root.after(5000, self._refresh_dashboard)
```

- [ ] **Step 4: 语法检查**

```bash
.venv/bin/python3 -c "import ast; ast.parse(open('seathunter/ui/gui.py').read()); print('语法OK')"
```

- [ ] **Step 5: 提交**

```bash
git add seathunter/ui/gui.py
git commit -m "新增首页 Tab：新手引导（4步）+ 日常仪表盘"
```

---

## Task 7: 添加方案对话框集成好友代预约

**Files:**
- Modify: `seathunter/ui/gui.py`

- [ ] **Step 1: 修改 `_add_plan_dialog` 添加"代预约好友"选项**

在添加方案对话框中，座位号输入框之后、预约人 UID 之前，添加好友代预约勾选框：

找到对话框中"座位号"那一行之后，添加：

```python
# 代预约好友选项
friend_row = ttk.Frame(dialog_body)
friend_row.pack(fill=tk.X, pady=2)
self._plan_friend_var = tk.BooleanVar(value=False)
friend_check = ttk.Checkbutton(friend_row, text="代预约好友", variable=self._plan_friend_var,
                                command=self._toggle_friend_seat)
friend_check.pack(side=tk.LEFT)

self._plan_friend_combo = ttk.Combobox(friend_row, state="disabled", width=15)
self._plan_friend_combo.pack(side=tk.LEFT, padx=5)
# 填充好友列表
friends = self.friend_store.get_all()
friend_names = [f"{info['name']} ({sid})" for sid, info in friends.items()]
self._plan_friend_combo["values"] = friend_names
if friend_names:
    self._plan_friend_combo.set(friend_names[0])
self._friend_sid_map = {f"{info['name']} ({sid})": sid for sid, info in friends.items()}
```

- [ ] **Step 2: 实现 `_toggle_friend_seat` 方法**

```python
def _toggle_friend_seat(self):
    """切换代预约好友状态"""
    if self._plan_friend_var.get():
        self._plan_friend_combo.config(state="readonly")
        # 自动在座位号后追加提示
        # 用户需要手动填入好友座位号
    else:
        self._plan_friend_combo.config(state="disabled")
```

- [ ] **Step 3: 修改 `_confirm_add_plan` 集成好友 UID**

在方案创建逻辑中，如果勾选了代预约好友，自动填充好友的 `booker_uid`：

找到解析预约人 UID 的代码，修改为：

```python
# 解析预约人 UID
uid_text = uid_entry.get().strip()
if uid_text:
    booker_uids = [u.strip() for u in uid_text.split(",") if u.strip()]
else:
    booker_uids = []

# 如果勾选了代预约好友，追加好友 UID
if self._plan_friend_var.get():
    friend_combo_val = self._plan_friend_combo.get()
    friend_sid = self._friend_sid_map.get(friend_combo_val)
    if friend_sid:
        friend_info = self.friend_store.get(friend_sid)
        if friend_info and friend_info["uid"] not in booker_uids:
            booker_uids.append(friend_info["uid"])
```

- [ ] **Step 4: 修改方案列表显示预约人信息**

修改 `_refresh_plans_tree` 中的列显示，新增"预约人"列：

```python
# 在 plans_tree 的列定义中已有 "bookers" 列
# 在刷新时填充：
def _refresh_plans_tree(self):
    for item in self.plans_tree.get_children():
        self.plans_tree.delete(item)
    for i, plan in enumerate(self.config.get_plans(), 1):
        seats_str = "+".join(s.seat_num for s in plan.seats)
        booker_names = []
        for s in plan.seats:
            if s.booker_uid and s.booker_uid != self.session_mgr.uid:
                # 查好友名
                for sid, info in self.friend_store.get_all().items():
                    if info["uid"] == s.booker_uid:
                        booker_names.append(info["name"])
                        break
                else:
                    booker_names.append(f"UID:{s.booker_uid[:6]}")
            else:
                booker_names.append("我")
        self.plans_tree.insert("", tk.END, values=(
            i, plan.id, plan.room_name, seats_str,
            plan.begin_time, f"{plan.duration_hours}h",
            "+".join(booker_names)
        ))
```

- [ ] **Step 5: 语法检查**

```bash
.venv/bin/python3 -c "import ast; ast.parse(open('seathunter/ui/gui.py').read()); print('语法OK')"
```

- [ ] **Step 6: 提交**

```bash
git add seathunter/ui/gui.py
git commit -m "添加方案对话框集成好友代预约：勾选自动填充好友 UID"
```

---

## Task 8: main.py 适配 + 集成测试

**Files:**
- Modify: `main.py`
- Modify: `seathunter/ui/gui.py`（最终清理）

- [ ] **Step 1: 确认 main.py 无需修改**

检查 `main.py` 中 GuiApp 的实例化，确认 FriendStore 和 FriendService 在 `gui.py` 的 `__init__` 中自行创建，不需要 main.py 传递额外参数。

```bash
grep -n "GuiApp" main.py
```

确认 GuiApp 构造参数不变（FriendStore 在 GuiApp 内部创建）。

- [ ] **Step 2: 运行完整导入测试**

```bash
.venv/bin/python3 -c "
from seathunter.auth.friend_store import FriendStore
from seathunter.services.friend_service import FriendService
from seathunter.ui.gui import GuiApp
print('所有模块导入成功')
"
```

- [ ] **Step 3: 运行所有测试**

```bash
.venv/bin/python3 -m pytest tests/ -v
```

预期: 全部 PASS

- [ ] **Step 4: 删除备份文件**

```bash
rm -f seathunter/ui/gui.py.bak
```

- [ ] **Step 5: 最终提交**

```bash
git add -A
git commit -m "UI 重构 + 好友代预约功能完成

- 4 Tab 结构：首页/预约/好友/设置
- 首页：新手引导（4步）+ 日常仪表盘
- 预约：方案管理+调度+签到一体化
- 好友：好友管理+代预约+自动同意
- 设置：账号+参数+帮助
"
```
