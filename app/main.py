"""FastAPI 后端入口。"""

from __future__ import annotations

import logging
import os
import sys
import threading

# 将项目根目录加入 sys.path
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

logger = logging.getLogger("seathunter")

from app.config import USER_STUDENT_ID, USER_PASSWORD
from app.auth.session import SessionManager
from app.api.client import ApiClient
from app.routes.auto import router as auto_router


class AppState:
    """全局状态：持有 session 和 API 客户端。"""

    def __init__(self):
        self.session_mgr: SessionManager | None = None
        self.api_client: ApiClient | None = None
        self.companion_api: ApiClient | None = None

    def init_after_login(self) -> None:
        """登录成功后初始化 API 客户端。"""
        self.api_client = ApiClient(self.session_mgr)


app = FastAPI(title="HDU Library SeatHunter", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局状态
state = AppState()
app.state.app_state = state

# 注册路由
app.include_router(auto_router, prefix="/api/auto", tags=["自动"])

# 挂载静态文件
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def root():
    """返回前端页面。"""
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.on_event("startup")
def on_startup() -> None:
    """启动时自动登录并启动调度器。"""

    def _auto_init():
        import time
        time.sleep(2)  # 等待服务器完全启动
        try:
            from app.core.scheduler import init_scheduler, get_debug_log

            debug = get_debug_log()

            # 自动登录
            state.session_mgr = SessionManager(USER_STUDENT_ID, USER_PASSWORD)
            state.session_mgr.init_session()
            success, err = state.session_mgr.login(debug=debug)
            if success:
                state.init_after_login()
                logger.info("自动登录成功: %s", state.session_mgr.name)

                # 启动调度器
                scheduler = init_scheduler(state)
                scheduler.start()
            else:
                logger.error("自动登录失败: %s", err)
                debug.log(f"自动登录失败: {err}")
        except Exception as e:
            logger.error("自动初始化失败: %s", e)

    threading.Thread(target=_auto_init, daemon=True, name="AutoInit").start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    from app.core.scheduler import get_scheduler
    scheduler = get_scheduler()
    if scheduler:
        scheduler.stop()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
