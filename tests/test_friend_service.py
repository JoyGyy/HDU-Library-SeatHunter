"""FriendService 单元测试。"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch, MagicMock

from seathunter.auth.friend_store import FriendStore
from seathunter.services.friend_service import FriendService


def _make_store() -> FriendStore:
    """创建临时文件的 FriendStore 实例。"""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)
    return FriendStore(path)


def test_init():
    """FriendService 初始化正常。"""
    store = _make_store()
    service = FriendService(store)
    assert service.friend_store is store
    assert service.base_url == "https://hdu.huitu.zhishulib.com"


def test_init_custom_base_url():
    """自定义 base_url 初始化正常。"""
    store = _make_store()
    service = FriendService(store, base_url="https://custom.url")
    assert service.base_url == "https://custom.url"


def test_confirm_missing_friend():
    """好友不存在时返回失败。"""
    store = _make_store()
    service = FriendService(store)
    success, msg = service.auto_confirm("12345", "99999999")
    assert success is False
    assert "好友" in msg or "不存在" in msg


def test_login_missing_friend():
    """好友不存在时 test_login 返回失败。"""
    store = _make_store()
    service = FriendService(store)
    success, msg = service.test_login("99999999")
    assert success is False
    assert "好友" in msg or "不存在" in msg


@patch("seathunter.services.friend_service.lookup_uid")
@patch("seathunter.services.friend_service.requests.Session")
@patch("seathunter.services.friend_service.playwright_login")
def test_auto_confirm_success(mock_playwright, mock_session_cls, mock_lookup):
    """自动确认预约成功。"""
    mock_lookup.return_value = (True, "305033", "张三")
    mock_playwright.return_value = (True, None, [{"name": "sid", "value": "abc"}], "305033", "张三", "")

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"CODE": "ok", "DATA": {"result": "success"}}
    mock_session.post.return_value = mock_resp
    mock_session_cls.return_value = mock_session

    store = _make_store()
    store.add("23140322", "305033", "张三", "pass123")
    service = FriendService(store)
    success, msg = service.auto_confirm("booking123", "23140322")
    assert success is True
    assert "success" in msg or "成功" in msg


@patch("seathunter.services.friend_service.lookup_uid")
@patch("seathunter.services.friend_service.requests.Session")
@patch("seathunter.services.friend_service.playwright_login")
def test_auto_confirm_api_failure(mock_playwright, mock_session_cls, mock_lookup):
    """API 返回失败。"""
    mock_lookup.return_value = (True, "305033", "张三")
    mock_playwright.return_value = (True, None, [{"name": "sid", "value": "abc"}], "305033", "张三", "")

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"CODE": "error", "MSG": "预约已过期"}
    mock_session.post.return_value = mock_resp
    mock_session_cls.return_value = mock_session

    store = _make_store()
    store.add("23140322", "305033", "张三", "pass123")
    service = FriendService(store)
    success, msg = service.auto_confirm("booking123", "23140322")
    assert success is False


@patch("seathunter.services.friend_service.lookup_uid")
def test_login_success(mock_lookup):
    """好友登录测试成功。"""
    mock_lookup.return_value = (True, "305033", "张三")
    store = _make_store()
    store.add("23140322", "305033", "张三", "pass123")
    service = FriendService(store)
    success, msg = service.test_login("23140322")
    assert success is True
    assert "张三" in msg


@patch("seathunter.services.friend_service.lookup_uid")
def test_login_failure(mock_lookup):
    """好友登录测试失败。"""
    mock_lookup.return_value = (False, "", "密码错误")
    store = _make_store()
    store.add("23140322", "305033", "张三", "wrong_pass")
    service = FriendService(store)
    success, msg = service.test_login("23140322")
    assert success is False
