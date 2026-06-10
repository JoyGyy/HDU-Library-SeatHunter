# 座位预约系统完全重写设计文档

## 概述

完全重写 HDU 图书馆座位预约系统，使用 Python + FastAPI 后端 + 原生 HTML/JS/CSS 前端。保留所有真实 API 调用逻辑，代码结构全新。

## 技术栈

- **后端**: Python 3.8+ / FastAPI / Uvicorn / requests / Playwright
- **前端**: 原生 HTML / JS / CSS（暗色主题，卡片布局，移动端适配）
- **部署**: Docker / Railway

## 目录结构

```
project/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py             # 配置管理（硬编码）
│   ├── auth/
│   │   ├── cas_login.py      # Playwright CAS 登录
│   │   └── session.py        # Session 管理 + 自动续期
│   ├── api/
│   │   ├── client.py         # zhishulib API 封装
│   │   └── token.py          # Api-Token 签名
│   ├── core/
│   │   ├── booker.py         # 预约逻辑
│   │   ├── checker.py        # 签到逻辑
│   │   └── scheduler.py      # 定时调度器
│   ├── routes/
│   │   └── auto.py           # API 路由
│   └── static/
│       ├── index.html
│       ├── style.css
│       └── app.js
├── Dockerfile
├── Procfile
└── requirements.txt
```

## 核心模块

### 配置管理 (`app/config.py`)

硬编码配置，不读外部文件：

- 账号密码（用户 + 同伴）
- 目标座位号和座位 ID 映射
- 房间名、楼层名
- 时间配置（开始时长、预约触发时间、签到触发时间）
- 重试参数（最大重试次数、重试间隔、请求间隔）
- 状态码映射、不可重试错误关键词

### 认证模块

#### CAS 登录 (`app/auth/cas_login.py`)

Playwright 自动化浏览器登录：

1. 启动 Chromium（headless）
2. 访问图书馆首页，自动跳转 CAS 登录页
3. 填写学号和密码，点击登录
4. 等待跳转回 zhishulib.com
5. 提取 cookies、uid、name
6. 关闭浏览器，返回结果

错误处理：区分网络错误和认证错误。

#### Session 管理 (`app/auth/session.py`)

- `requests.Session` 持有 cookies 和请求头
- `login()`: 先尝试缓存 cookies，失败则 Playwright 登录
- `relogin()`: 强制 Playwright 重新登录
- `ensure_valid_session()`: 每次 API 调用前验证 session，过期自动 re-login
- `create_temp_session()`: 创建临时 session（用于签到同伴账号）

### API 模块

#### Api-Token 签名 (`app/api/token.py`)

签名算法：

1. 构造参数字典：`beginTime`, `duration`, `seats[i]`, `is_recommend`, `api_time`, `seatBookers[i]`
2. 参数按字母序排列拼接为字符串
3. MD5 哈希 → base64 编码

#### API 客户端 (`app/api/client.py`)

封装所有 zhishulib.com API 调用：

| 方法 | 端点 | 功能 |
|------|------|------|
| `query_rooms()` | GET `/Space/Category/list` | 获取房间列表 |
| `search_seats()` | POST `/Seat/Index/searchSeats` | 搜索座位 |
| `book_seat()` | POST `/Seat/Index/bookSeats` | 预约座位（带 Api-Token） |
| `get_my_bookings()` | GET `/Seat/Index/myBookingList` | 查询预约列表 |
| `check_in()` | POST 签到端点 | 签到 |

### 业务逻辑

#### 预约 (`app/core/booker.py`)

`book_for_all_dates()` 流程：

1. 确保 session 有效
2. 确定要预约的日期（今天、明天、后天）
3. 后天预约需在 20:00 后才能触发
4. 检查每个日期是否已预约
5. 未预约的逐个座位预约
6. 座位之间间隔 5 秒防封号
7. 带重试机制（最多 10 次，间隔 5 秒）
8. 遇到 CAS 重定向自动 re-login 后重试
9. 不可重试错误（已有预约、座位占用等）直接停止

#### 签到 (`app/core/checker.py`)

`checkin_for_all_users()` 流程：

1. 登录当前用户账号，查询今天的预约
2. 状态为"待签到"的自动签到（带重试）
3. 等待间隔后，登录同伴账号重复上述流程
4. 返回结果摘要

#### 调度器 (`app/core/scheduler.py`)

`AutoScheduler` 类：

- 两个独立线程：预约线程 + 签到线程
- 预约线程：每 30 秒检查，20:00 触发
- 签到线程：每 30 秒检查，9:30 触发
- `threading.Event` 实现可中断等待（1 秒粒度）
- 全局状态：运行中/停止、上次预约结果、上次签到结果、调试日志

### API 路由 (`app/routes/auto.py`)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/auto/status` | GET | 获取状态（调度器、座位、房间、结果、日志） |
| `/api/auto/bookings` | GET | 查询你和同伴的预约列表 |
| `/api/auto/book` | POST | 手动触发预约（异步线程） |
| `/api/auto/checkin` | POST | 手动触发签到（异步线程） |
| `/api/auto/start` | POST | 启动调度器 |
| `/api/auto/stop` | POST | 停止调度器 |

### 前端 (`app/static/`)

原生 HTML/JS/CSS，单页面：

**状态卡片**
- 调度器状态（运行中/已停止，绿色/红色徽章）
- 目标座位号、房间名
- 预约/签到时间表

**执行结果**
- 最近一次预约结果
- 最近一次签到结果

**预约列表**
- 表格：用户、房间、座位、时间段、状态
- 自动区分"我"和"同伴"

**操作按钮**
- 立即预约 / 立即签到 / 启动或停止调度器 / 刷新

**运行日志**
- 最近 20 条调试日志，带时间戳
- 每 5 秒自动轮询刷新

**样式**
- 暗色主题（深色背景 + 卡片阴影）
- 卡片布局，响应式适配移动端

### 启动流程

1. FastAPI 启动，挂载静态文件
2. `startup` 事件：后台线程自动登录 → 启动调度器
3. 前端访问 `/` 加载页面，轮询 `/api/auto/status` 获取状态

### 部署配置

- `Dockerfile`: Python 3.13-slim + Playwright Chromium
- `Procfile`: Railway 部署命令
- `requirements.txt`: fastapi, uvicorn, requests, playwright, pydantic
