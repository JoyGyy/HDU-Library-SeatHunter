# 自动预约系统重写设计

日期：2026-06-09

## 目标

重写 `server/api/auto.py`（当前 752 行巨石文件），复用 `seathunter/` 核心组件，实现：
- 每天 20:00 自动预约（今天/明天/后天，智能补约）
- 每天 9:30 自动签到（你 + 同伴）
- 极简 Web 状态页 + 操作按钮
- Railway 云部署

## 架构

```
server/
  main.py             — FastAPI 入口 + 自动登录
  api/auto.py         — 路由层（~100 行）
  core/booker.py      — 预约逻辑（~80 行）
  core/checker.py     — 签到逻辑（~60 行）
  core/scheduler.py   — 调度逻辑（~80 行）
  core/session.py     — Session 管理（~40 行）
  static/index.html   — 前端页面
  static/app.js       — 前端逻辑
  static/style.css    — 样式
```

依赖 seathunter 核心库：
- `BookingRunner` — 预约重试（10 次，间隔 5 秒）
- `CheckInRunner` — 签到窗口（±25 分钟）
- `SessionManager` — cookie 管理 + re-login
- `ApiClient` — HTTP 请求

## 配置（硬编码）

```python
USER_STUDENT_ID = "23051110"
USER_PASSWORD = "@Krz201314"
USER_UID = "303687"

COMPANION_STUDENT_ID = "23140322"
COMPANION_PASSWORD = "Pangzidan0713#"
COMPANION_UID = "305033"

ROOM_NAME = "自习室"
FLOOR_NAME = "比特庭园（二楼西）"
TARGET_SEATS = ["99", "100"]
KNOWN_SEAT_IDS = {"99": "60810", "100": "60811"}

BEGIN_HOUR = 10
DURATION_HOURS = 12
AUTO_BOOK_HOUR = 20
AUTO_BOOK_MINUTE = 0
AUTO_CHECKIN_HOUR = 9
AUTO_CHECKIN_MINUTE = 30
```

## 预约逻辑（booker.py）

### 流程

```
book_for_all_dates(state):
  for date in [today, tomorrow, day_after_tomorrow]:
    if date == day_after_tomorrow and now < 20:00:
      skip  # 后天需 20:00 后才能约
    if already_booked(date):
      skip
    for seat in [99, 100]:
      if already_booked(seat, date):
        skip
      booker_uids = [companion_uid, user_uid] if seat==99 else [user_uid]
      BookingRunner.book(seat_id, booker_uids, date)
      sleep(5)  # 防封号
```

### 关键改进

- 用 `BookingRunner.run_booking()` 替代手动 `book_seat()`
- 自动重试 10 次，间隔 5 秒
- 不可重试错误自动跳过（"已有预约"、"座位不可用"）
- 预约人列表自动处理：确保当前用户在列
- 座位 ID 直接用硬编码，不做复杂搜索

## 签到逻辑（checker.py）

### 流程

```
checkin_for_all_users(state):
  # 签到你的预约
  login(user) → get_bookings() → for today's bookings → check_in()
  sleep(5)
  # 签到同伴的预约
  login(companion) → get_bookings() → for today's bookings → check_in()
```

### 关键改进

- 每个用户独立 session
- 签到失败自动重试（最多 10 次）
- 间隔 5 秒防封号

## 调度器（scheduler.py）

### 设计

```python
class AutoScheduler:
    def __init__(self, state):
        self._stop = threading.Event()
    
    def start(self):
        # 启动预约线程 + 签到线程
    
    def stop(self):
        # 设置 stop event，1秒内退出
```

### 触发逻辑

- 预约线程：每 30 秒检查，20:00 触发
- 签到线程：每 30 秒检查，9:30 触发
- 记录"今天已触发"，防止重复
- `threading.Event.wait()` 替代 `time.sleep()` — 可随时中断

## Session 管理（session.py）

```python
def ensure_valid_session(state) -> bool:
    """每次 API 调用前验证 session"""
    # 1. 调 /myBookingList 检查响应
    # 2. 如果 CAS 重定向 → relogin
    # 3. relogin 失败 → 返回 False
```

## Web 界面

单页面，包含：
- 状态卡片（登录状态、调度状态、目标座位）
- 执行结果（预约结果、签到结果）
- 操作按钮（立即预约、立即签到、启动/停止）
- 运行日志（后端 debug_log，30 秒自动刷新）

## API 路由

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/auto/status | 获取状态 + 日志 |
| GET | /api/auto/bookings | 获取预约列表 |
| POST | /api/auto/book | 手动预约 |
| POST | /api/auto/checkin | 手动签到 |
| POST | /api/auto/start | 启动调度器 |
| POST | /api/auto/stop | 停止调度器 |

## 部署

- Dockerfile：Python 3.13 + Playwright chromium
- Railway 自动部署
- 启动时自动登录 + 启动调度器
