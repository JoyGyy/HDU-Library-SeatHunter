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

logger = logging.getLogger("seathunter.server")

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
