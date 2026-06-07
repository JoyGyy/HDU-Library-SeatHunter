"""好友凭证持久化存储。

保存好友的学号、UID、姓名和密码（base64 编码），方便多人预约时使用。
"""

from __future__ import annotations

import base64
import json
import os
import logging
from typing import Optional, Dict, List

logger = logging.getLogger("seathunter.auth")


class FriendStore:
    """管理好友凭证的本地 JSON 文件。"""

    def __init__(self, store_path: str):
        self.store_path = store_path
        self._data: Dict[str, Dict[str, str]] = {}

    def load(self) -> Dict[str, Dict[str, str]]:
        """加载好友记录。"""
        if not os.path.exists(self.store_path):
            self._data = {}
            return self._data
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception as e:
            logger.warning("加载好友记录失败: %s", e)
            self._data = {}
        return self._data

    def save(self):
        """保存好友记录到文件。"""
        os.makedirs(os.path.dirname(self.store_path) or ".", exist_ok=True)
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, student_id: str) -> Optional[Dict[str, str]]:
        """根据学号查询好友记录。"""
        self.load()
        return self._data.get(student_id)

    def get_all(self) -> Dict[str, Dict[str, str]]:
        """获取所有好友记录。"""
        self.load()
        return dict(self._data)

    def get_student_ids(self) -> List[str]:
        """返回所有学号列表。"""
        self.load()
        return list(self._data.keys())

    def add(self, student_id: str, uid: str, name: str, password: str):
        """添加好友，密码经 base64 编码后存储。"""
        self.load()
        password_base64 = base64.b64encode(password.encode("utf-8")).decode("utf-8")
        self._data[student_id] = {
            "uid": uid,
            "name": name,
            "student_id": student_id,
            "password_base64": password_base64,
        }
        self.save()
        logger.info("好友记录已保存: %s -> %s (%s)", student_id, uid, name)

    def remove(self, student_id: str) -> bool:
        """删除好友记录。

        Returns:
            是否成功删除
        """
        self.load()
        if student_id in self._data:
            del self._data[student_id]
            self.save()
            logger.info("好友记录已删除: %s", student_id)
            return True
        return False

    def get_password(self, student_id: str) -> Optional[str]:
        """获取解码后的密码。"""
        record = self.get(student_id)
        if record is None or "password_base64" not in record:
            return None
        return base64.b64decode(record["password_base64"]).decode("utf-8")
