# FastAPI 后端 + React Native 移动端设计

> 日期: 2026-06-07
> 状态: 已批准

## 背景

当前项目是 Python + tkinter 单体桌面应用。用户希望迁移到前后端分离架构：FastAPI 后端 + React Native 移动端，完全替换桌面 GUI。

## 设计目标

1. 后端：FastAPI REST API，运行在本地电脑
2. 前端：React Native 移动 App
3. 第一版功能：签到 + 好友代预约
4. 保留现有核心逻辑（api_client、booking_runner、checkin_runner、engine）

---

## 1. 整体架构

```
手机 App (React Native)
    │
    │ HTTP/JSON (局域网)
    ▼
FastAPI 后端 (本地电脑)
    │
    ├─ Auth 模块 (Playwright 登录)
    ├─ Booking 模块 (预约 API)
    ├─ Check-in 模块 (签到)
    ├─ Scheduler 模块 (调度引擎)
    ├─ Friends 模块 (好友管理 + 自动同意)
    └─ History 模块 (历史记录)
```

---

## 2. 后端 API 设计

### 2.1 基础信息

- 运行地址: `http://0.0.0.0:8000`
- 文档: `http://localhost:8000/docs` (FastAPI 自动生成)
- 手机通过电脑局域网 IP 访问 (如 `http://192.168.1.100:8000`)

### 2.2 API 端点

#### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录（学号+密码） |
| GET | `/api/auth/status` | 登录状态 |
| POST | `/api/auth/logout` | 退出登录 |

#### 预约

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/bookings` | 获取当前预约列表 |
| POST | `/api/bookings/book` | 立即预约 |
| GET | `/api/bookings/history` | 预约历史 |

#### 签到

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/checkin/{booking_id}` | 手动签到 |
| GET | `/api/checkin/status` | 签到状态 |

#### 调度

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/schedules` | 获取调度列表 |
| POST | `/api/schedules` | 添加调度 |
| DELETE | `/api/schedules/{id}` | 删除调度 |
| POST | `/api/scheduler/start` | 启动调度引擎 |
| POST | `/api/scheduler/stop` | 停止调度引擎 |
| GET | `/api/scheduler/status` | 引擎状态 |

#### 方案

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/plans` | 获取方案列表 |
| POST | `/api/plans` | 添加方案 |
| DELETE | `/api/plans/{id}` | 删除方案 |

#### 好友

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/friends` | 获取好友列表 |
| POST | `/api/friends` | 添加好友 |
| DELETE | `/api/friends/{student_id}` | 删除好友 |
| POST | `/api/friends/{student_id}/test` | 测试好友登录 |

---

## 3. 后端模块结构

```
server/
├── main.py                 # FastAPI 入口
├── api/
│   ├── auth.py            # 认证路由
│   ├── bookings.py        # 预约路由
│   ├── checkin.py         # 签到路由
│   ├── schedules.py       # 调度路由
│   ├── plans.py           # 方案路由
│   └── friends.py         # 好友路由
├── services/
│   ├── auth_service.py    # 登录/会话管理
│   ├── booking_service.py # 预约逻辑
│   ├── checkin_service.py # 签到逻辑
│   ├── scheduler_service.py # 调度引擎
│   └── friend_service.py  # 好友管理
└── models/
    ├── schemas.py         # Pydantic 请求/响应模型
    └── state.py           # 全局状态管理
```

---

## 4. 第一版移动端功能

### 4.1 签到页面

- 显示当前预约列表（从 `/api/bookings` 获取）
- 每条预约显示：座位、时间、状态
- 一键签到按钮
- 签到结果实时显示

### 4.2 好友页面

- 好友列表（从 `/api/friends` 获取）
- 添加好友（学号+密码）
- 删除好友
- 测试好友登录

### 4.3 首页/状态

- 登录状态
- 调度引擎状态
- 今日预约概览

---

## 5. 技术栈

### 后端
- Python 3.14 + FastAPI
- uvicorn (ASGI 服务器)
- Pydantic (数据校验)
- 现有模块复用 (api_client, booking_runner, checkin_runner, engine)

### 前端
- React Native (Expo)
- TypeScript
- React Navigation (导航)
- Axios (HTTP 客户端)

---

## 6. 不做的事情（第一版）

- 不做用户注册（复用现有学号登录）
- 不做推送通知（后续迭代）
- 不做预约和调度功能（后续迭代）
- 不做云端部署（本地运行）
- 不做 iOS/Android 原生模块
