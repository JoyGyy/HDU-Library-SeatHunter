"""FriendStore 单元测试。"""

from __future__ import annotations

import os
import tempfile

from seathunter.auth.friend_store import FriendStore


def _make_store() -> FriendStore:
    """创建临时文件的 FriendStore 实例。"""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)  # FriendStore 应在文件不存在时也能正常工作
    return FriendStore(path)


def test_empty_store():
    """空 store 查询返回 None。"""
    store = _make_store()
    assert store.get("99999999") is None
    assert store.get_all() == {}
    assert store.get_student_ids() == []


def test_add_and_get():
    """添加后能正确查询。"""
    store = _make_store()
    store.add("23140322", "305033", "张三", "pass123")
    result = store.get("23140322")
    assert result is not None
    assert result["uid"] == "305033"
    assert result["name"] == "张三"
    assert result["student_id"] == "23140322"
    assert "password_base64" in result


def test_password_encoding():
    """base64 编码/解码正确。"""
    import base64

    store = _make_store()
    password = "my_secret_pass"
    store.add("23140322", "305033", "张三", password)
    result = store.get("23140322")
    assert result is not None
    decoded = base64.b64decode(result["password_base64"]).decode("utf-8")
    assert decoded == password


def test_get_password():
    """获取解码后密码。"""
    store = _make_store()
    password = "hello_world"
    store.add("23140322", "305033", "张三", password)
    assert store.get_password("23140322") == password
    assert store.get_password("00000000") is None


def test_remove():
    """删除后查不到。"""
    store = _make_store()
    store.add("23140322", "305033", "张三", "pass123")
    assert store.remove("23140322") is True
    assert store.get("23140322") is None
    # 重复删除返回 False
    assert store.remove("23140322") is False


def test_persistence(tmp_path):
    """两个 FriendStore 实例共享同一文件，数据持久化。"""
    path = str(tmp_path / "friends.json")
    store1 = FriendStore(path)
    store1.add("23140322", "305033", "张三", "pass123")

    store2 = FriendStore(path)
    result = store2.get("23140322")
    assert result is not None
    assert result["name"] == "张三"


def test_get_student_ids():
    """返回所有学号列表。"""
    store = _make_store()
    store.add("23140322", "305033", "张三", "pass1")
    store.add("23140323", "305034", "李四", "pass2")
    ids = store.get_student_ids()
    assert set(ids) == {"23140322", "23140323"}
