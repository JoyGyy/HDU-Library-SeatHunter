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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局状态实例（构造时自动加载配置）
state = AppState()

# 将 state 注入到 app 供路由使用
app.state.seathunter = state


@app.on_event("shutdown")
def on_shutdown() -> None:
    state.shutdown()


@app.get("/")
def root():
    return {"name": "HDU Library SeatHunter API", "version": "1.0.0"}


# 注册路由
from server.api import auth, bookings, checkin, friends, plans, schedules  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(bookings.router, prefix="/api/bookings", tags=["预约"])
app.include_router(checkin.router, prefix="/api/checkin", tags=["签到"])
app.include_router(friends.router, prefix="/api/friends", tags=["好友"])
app.include_router(plans.router, prefix="/api/plans", tags=["方案"])
app.include_router(schedules.router, prefix="/api/schedules", tags=["调度"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
