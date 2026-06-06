"""UID 记录持久化存储。

保存查询过的学号 → UID 映射，方便多人预约时使用。
"""

from __future__ import annotations

import json
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("seathunter.auth")


class UidStore:
    """管理 UID 记录的本地 JSON 文件。"""

    def __init__(self, store_path: str):
        self.store_path = store_path
        self._data: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        """加载 UID 记录。"""
        if not os.path.exists(self.store_path):
            self._data = {}
            return self._data
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception as e:
            logger.warning("加载 UID 记录失败: %s", e)
            self._data = {}
        return self._data

    def save(self):
        """保存 UID 记录到文件。"""
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, student_id: str) -> Optional[Dict[str, str]]:
        """根据学号查询 UID 记录。

        Returns:
            {"uid": "...", "name": "..."} 或 None
        """
        self.load()
        return self._data.get(student_id)

    def set(self, student_id: str, uid: str, name: str = ""):
        """保存一条 UID 记录。"""
        self.load()
        self._data[student_id] = {"uid": uid, "name": name}
        self.save()
        logger.info("UID 记录已保存: %s -> %s (%s)", student_id, uid, name)

    def get_all(self) -> Dict[str, Any]:
        """获取所有记录。"""
        self.load()
        return dict(self._data)
