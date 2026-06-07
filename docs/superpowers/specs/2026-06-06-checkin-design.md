# 签到功能设计文档

## 概述

通过逆向 HDU 图书馆系统前端 JS 代码，发现了签到相关的 API 接口。本设计实现自动签到功能：预约成功后，系统在预约开始时间前自动调用签到 API，无需用户到图书馆机器扫码。

## 逆向发现的 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/Seat/Index/checkIn?bookingId={id}` | POST | 直接签到（核心接口） |
| `/Seat/Index/mySignQRCode` | GET | 获取签到二维码 token |
| `/Seat/Index/checkSignQRCode` | POST | 验证签到二维码 |
| `/Seat/Index/bookingStatus?bookingId={id}` | POST | 查询预约状态 |
| `/Seat/Index/stepOut?bookingId={id}` | POST | 暂离 |
| `/Seat/Index/comeBack?bookingId={id}` | POST | 返回 |
| `/Seat/Index/checkOut?bookingId={id}` | POST | 签退 |

### 签到 API 详情

```
POST /Seat/Index/checkIn?bookingId={bookingId}
Content-Type: application/x-www-form-urlencoded
Cookie: (已有 session cookies)
LAB_JSON=1

响应:
{
  CODE: "ok",
  DATA: {
    result: "success",  // 签到成功
    msg: "..."          // 失败时的错误信息
  }
}
```

来源：前端 JS `app.es6.min.js` 中 `_signOrderMain()` 方法：
```javascript
xH.post("/Seat/Index/checkIn?bookingId=" + this.state.id)
  .then(function(t) {
    "ok" == t.CODE
      ? "success" == t.DATA.result ? /* 成功 */ : /* 显示 t.DATA.msg */
      : /* 显示 t.MESSAGE */
  })
```

## 签到时间窗口

```
预约开始时间 = 10:00
签到窗口     = 09:35 ~ 10:25（前25分钟，后25分钟）
```

| 参数 | 值 | 说明 |
|------|-----|------|
| `CHECKIN_ADVANCE_MINUTES` | 25 | 签到提前时间（分钟） |
| 签到截止 | begin_time + 25min | 窗口关闭，停止重试 |
| 重试间隔 | `settings.interval` | 复用现有配置，默认 5 秒 |
| 最大重试次数 | `settings.max_try_times` | 复用现有配置，默认 10 次 |

## 整体流程

```
1. 用户创建方案 + 调度（现有流程）
2. 调度器在预约开放时间自动预约（现有流程）
3. 预约成功 → API 返回 bookingId
4. 保存 bookingId 到 Plan 配置
5. 注册签到任务：触发时间 = begin_time - 25min
6. 到签到时间 → 调用 checkIn API → 成功则结束
7. 失败则按 interval 重试，最多 max_try_times 次
8. 超过 begin_time + 25min 停止重试，通知用户
```

## 组件修改

### 1. `api/client.py` — 新增签到方法

```python
def check_in(self, booking_id: str) -> Tuple[bool, str, str]:
    """
    签到
    返回: (成功?, 错误信息, booking_id)
    """
    url = f"{self.base_url}/Seat/Index/checkIn"
    params = {"bookingId": booking_id, "LAB_JSON": "1"}
    resp = self.session.post(url, params=params)
    data = resp.json()
    if data.get("CODE") == "ok":
        result = data.get("DATA", {}).get("result", "")
        if result == "success":
            return (True, "", booking_id)
        return (False, data["DATA"].get("msg", "签到失败"), booking_id)
    return (False, data.get("MESSAGE", "签到失败"), booking_id)


def get_booking_status(self, booking_id: str) -> dict:
    """查询预约状态"""
    url = f"{self.base_url}/Seat/Index/bookingStatus"
    params = {"bookingId": booking_id, "LAB_JSON": "1"}
    resp = self.session.post(url, params=params)
    return resp.json()
```

### 2. `models/plan.py` — Plan 新增 booking_id 字段

```python
class Plan:
    id: str
    room_name: str
    floor_name: str
    begin_time: str          # "HH:MM:SS"
    duration_hours: int
    target_date: str         # "YYYY-MM-DD"
    seats: List[SeatInfo]
    booking_id: str = ""     # 新增：预约成功后的 bookingId
```

`to_dict()` / `from_dict()` 需同步更新。

### 3. `models/booking_result.py` — 新增 booking_id

```python
@dataclass
class BookingResult:
    success: bool
    message: str
    seat_num: str
    booking_id: str = ""     # 新增：从 API 响应中提取
```

`from_api_response()` 需从响应中提取 `DATA.bookingId`。

### 4. `scheduler/checkin_runner.py` — 新建签到执行器

```python
class CheckInRunner:
    """签到执行器"""

    def __init__(self, api_client, log_callback=None):
        self.api_client = api_client
        self.log_callback = log_callback

    def run_checkin(self, booking_id: str, max_retries: int, interval: int,
                    deadline: datetime) -> bool:
        """
        执行签到，带重试
        booking_id: 预约 ID
        max_retries: 最大重试次数
        interval: 重试间隔（秒）
        deadline: 签到截止时间
        """
        for attempt in range(1, max_retries + 1):
            if datetime.now() > deadline:
                self._log(f"签到窗口已关闭，停止重试")
                return False

            success, msg, _ = self.api_client.check_in(booking_id)
            if success:
                self._log(f"签到成功！(第 {attempt} 次)")
                return True

            self._log(f"签到失败(第 {attempt} 次): {msg}")

            if attempt < max_retries:
                time.sleep(interval)

        self._log(f"签到失败，已达最大重试次数 ({max_retries})")
        return False
```

### 5. `scheduler/engine.py` — 支持签到调度

新增签到任务类型：

```python
# 现有：预约任务
# 新增：签到任务
# 触发时间 = plan.begin_time 对应的 datetime - CHECKIN_ADVANCE_MINUTES
```

签到任务触发逻辑：
1. 计算签到触发时间：`target_date + begin_time - 25min`
2. 如果签到触发时间已过（但截止时间未过），立即触发
3. 截止时间 = `target_date + begin_time + 25min`

### 6. `scheduler/booking_runner.py` — 预约成功后注册签到

```python
def run_booking(self, plans, target_date):
    for plan in plans:
        result = self.api_client.book_seat(...)
        if result.success and result.booking_id:
            # 保存 bookingId
            plan.booking_id = result.booking_id
            # 注册签到任务到 engine
            self.engine.register_checkin(
                booking_id=result.booking_id,
                begin_time=plan.begin_time,
                target_date=target_date
            )
```

### 7. `ui/gui.py` — 签到 UI

- 预约成功后显示 bookingId
- 「立即签到」按钮（对手动输入的 bookingId 签到）
- 签到状态显示（待签到/签到中/已签到/签到失败）
- 签到日志输出

### 8. `ui/cli.py` — 签到菜单

新增菜单项：
```
7. 手动签到（输入 bookingId）
8. 查询他人 UID
9. 帮助
10. 退出
```

## 配置变更

`config/config.yaml` 中 plan 新增字段：

```yaml
plans:
  - id: "plan_xxx"
    room_name: "..."
    begin_time: "10:00:00"
    duration_hours: 12
    target_date: ""
    booking_id: ""          # 新增：预约成功后自动填充
    seats: [...]
```

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| bookingId 为空 | 跳过签到，提示用户 |
| 签到 API 返回失败 | 按 interval 重试 |
| 网络错误 | 重试，记录日志 |
| 签到窗口关闭 | 停止重试，通知用户 |
| 预约已被取消 | 停止签到，通知用户 |

## 不在范围内

- 暂离/返回功能（stepOut/comeBack）
- 签退功能（checkOut）
- 二维码签到模式（生成二维码去机器扫码）
