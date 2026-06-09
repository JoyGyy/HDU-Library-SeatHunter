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
            from server.api.auto import USER_CONFIG, _scheduler_running
            from server.api.auto import start_scheduler as _start_scheduler

            # 自动登录
            state.config.update_user_info(
                login_name=USER_CONFIG["student_id"],
                password=USER_CONFIG["password"],
            )
            state.session_mgr.init_session()
            success, err_type = state.session_mgr.login()
            if success:
                state.init_after_login()
                logger.info("自动登录成功: %s", state.session_mgr.name)
            else:
                logger.error("自动登录失败: %s", err_type)
        except Exception as e:
            logger.error("自动初始化失败: %s", e)

    threading.Thread(target=_auto_init, daemon=True, name="AutoInit").start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    from server.api.auto import stop_scheduler
    stop_scheduler()
    state.shutdown()


# 挂载静态文件
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def root():
    """返回前端页面。"""
    return FileResponse(os.path.join(static_dir, "index.html"))


# 注册路由
from server.api import auth, auto, bookings, checkin, friends, plans, rooms, schedules  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(auto.router, prefix="/api/auto", tags=["自动"])
app.include_router(bookings.router, prefix="/api/bookings", tags=["预约"])
app.include_router(checkin.router, prefix="/api/checkin", tags=["签到"])
app.include_router(friends.router, prefix="/api/friends", tags=["好友"])
app.include_router(plans.router, prefix="/api/plans", tags=["方案"])
app.include_router(rooms.router, prefix="/api/rooms", tags=["房间"])
app.include_router(schedules.router, prefix="/api/schedules", tags=["调度"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
