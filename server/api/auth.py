"""认证路由：登录、状态查询、登出。"""

from __future__ import annotations

import threading

from fastapi import APIRouter, Request

from server.models.schemas import (
    AuthStatusResponse,
    LoginRequest,
    LoginResponse,
    MessageResponse,
)

router = APIRouter()


def _get_state(request: Request):
    """从 app.state 获取全局 AppState 实例。"""
    return request.app.state.seathunter


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request):
    """登录：在后台线程中执行 Playwright 登录。"""
    state = _get_state(request)
    session_mgr = state.session_mgr

    # 保存请求的学号密码到配置
    user_info = state.config.get_user_info()
    user_info["login_name"] = body.student_id
    user_info["password"] = body.password
    state.config.set_user_info(user_info)

    # 重新初始化 session（使用新凭证）
    session_mgr.init_session()

    # 在后台线程中执行登录（Playwright 是同步阻塞的）
    result = {"success": False, "err_type": None}

    def _do_login():
        result["success"], result["err_type"] = session_mgr.login()

    t = threading.Thread(target=_do_login, daemon=True)
    t.start()
    t.join(timeout=120)

    if t.is_alive():
        return LoginResponse(success=False, message="登录超时（120秒）")

    if not result["success"]:
        err = session_mgr.last_error or "登录失败"
        return LoginResponse(success=False, message=err)

    # 登录成功，初始化后续组件
    state.init_after_login()

    return LoginResponse(
        success=True,
        message="登录成功",
        uid=session_mgr.uid,
        name=session_mgr.name,
    )


@router.get("/status", response_model=AuthStatusResponse)
def status(request: Request):
    """查询当前认证状态。"""
    state = _get_state(request)
    session_mgr = state.session_mgr
    logged_in = bool(session_mgr.uid)
    return AuthStatusResponse(
        logged_in=logged_in,
        uid=session_mgr.uid or "",
        name=session_mgr.name or "",
        student_id=session_mgr.user_info.get("login_name", ""),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request):
    """登出：清空会话信息。"""
    state = _get_state(request)
    session_mgr = state.session_mgr
    session_mgr.uid = ""
    session_mgr.name = ""
    session_mgr.session = None
    return MessageResponse(success=True, message="已登出")
