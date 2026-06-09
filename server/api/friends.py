"""好友路由：列表、添加、删除、测试登录。"""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, Request

from seathunter.auth.session_manager import lookup_uid
from server.models.schemas import (
    AddFriendRequest,
    AddFriendResponse,
    FriendItem,
    FriendListResponse,
    MessageResponse,
    TestLoginResponse,
)

logger = logging.getLogger("seathunter.server")

router = APIRouter()


def _get_state(request: Request):
    """从 app.state 获取全局 AppState 实例。"""
    return request.app.state.seathunter


def _join_with_timeout(t: threading.Thread, timeout: float, label: str) -> bool:
    """等待线程结束，超时时记录警告。返回 True 表示超时。"""
    t.join(timeout=timeout)
    if t.is_alive():
        logger.warning("线程超时（%.0fs）: %s", timeout, label)
        return True
    return False


@router.get("", response_model=FriendListResponse)
def list_friends(request: Request):
    """获取好友列表。"""
    state = _get_state(request)
    records = state.friend_store.get_all()
    friends = [
        FriendItem(
            student_id=sid,
            name=r.get("name", ""),
            uid=r.get("uid", ""),
        )
        for sid, r in records.items()
    ]
    return FriendListResponse(success=True, friends=friends)


@router.post("", response_model=AddFriendResponse)
def add_friend(body: AddFriendRequest, request: Request):
    """添加好友：在后台线程中通过学号密码查询 UID。"""
    state = _get_state(request)

    result = {"success": False, "uid": "", "name": "", "message": ""}

    def _do_lookup():
        base_url = state.config.get_api_base_url()
        ok, uid, name = lookup_uid(body.student_id, body.password, base_url)
        result["success"] = ok
        result["uid"] = uid
        result["name"] = name
        if not ok:
            result["message"] = name  # lookup_uid 失败时 name 存的是错误信息

    t = threading.Thread(target=_do_lookup, daemon=True)
    t.start()

    if _join_with_timeout(t, 120, "add_friend"):
        return AddFriendResponse(success=False, message="查询超时（120秒）")

    if not result["success"]:
        return AddFriendResponse(success=False, message=result["message"])

    # 保存好友
    state.friend_store.add(body.student_id, result["uid"], result["name"], body.password)

    return AddFriendResponse(
        success=True,
        message="添加成功",
        name=result["name"],
        uid=result["uid"],
    )


@router.delete("/{student_id}", response_model=MessageResponse)
def remove_friend(student_id: str, request: Request):
    """删除好友。"""
    state = _get_state(request)
    removed = state.friend_store.remove(student_id)
    if removed:
        return MessageResponse(success=True, message="已删除")
    return MessageResponse(success=False, message="好友不存在")


@router.post("/{student_id}/test", response_model=TestLoginResponse)
def test_friend_login(student_id: str, request: Request):
    """测试好友登录是否正常。"""
    state = _get_state(request)

    result = {"success": False, "message": ""}

    def _do_test():
        result["success"], result["message"] = state.friend_service.test_login(
            student_id
        )

    t = threading.Thread(target=_do_test, daemon=True)
    t.start()

    if _join_with_timeout(t, 120, "test_friend_login"):
        return TestLoginResponse(success=False, message="测试超时（120秒）")

    return TestLoginResponse(success=result["success"], message=result["message"])
