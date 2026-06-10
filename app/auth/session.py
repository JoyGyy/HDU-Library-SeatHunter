"""Session 管理：登录、cookie 缓存、自动续期。"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import requests

from app.auth.cas_login import cas_login, LOGIN_ERR_NETWORK
from app.config import BASE_URL, DEFAULT_HEADERS, ORG_ID

logger = logging.getLogger("seathunter.auth")

COOKIE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "session.json")


class SessionManager:
    """管理 HTTP session，支持自动登录和 cookie 刷新。"""

    def __init__(self, student_id: str, password: str):
        self.student_id = student_id
        self.password = password
        self.session: Optional[requests.Session] = None
        self.uid: str = ""
        self.name: str = ""
        self._cookie_login_network_err = False

    def init_session(self) -> None:
        """初始化 requests session。"""
        import urllib3
        urllib3.disable_warnings()

        self.session = requests.Session()
        self.session.headers.clear()
        self.session.headers.update(DEFAULT_HEADERS)
        self.session.trust_env = False
        self.session.verify = False
        self.session.cookies.update({"org_id": ORG_ID})

    def login(self, debug=None) -> tuple[bool, Optional[str]]:
        """登录：先尝试缓存 cookies，失败则 Playwright 登录。"""
        self._cookie_login_network_err = False

        if self._login_with_cookies():
            return True, None

        if self._cookie_login_network_err:
            return False, LOGIN_ERR_NETWORK

        return self._login_with_playwright(debug)

    def relogin(self, debug=None) -> tuple[bool, Optional[str]]:
        """强制重新登录（跳过 cookie 缓存）。"""
        self._clear_cookies()
        return self._login_with_playwright(debug)

    def _login_with_cookies(self) -> bool:
        """尝试使用缓存 cookies 登录。"""
        cached = self._load_cookies()
        if not cached:
            return False

        logger.info("找到缓存 cookies，尝试使用...")
        cookie_dict = {c["name"]: c["value"] for c in cached["cookies"]}
        self.session.cookies.update(cookie_dict)

        try:
            params = {
                "space_category[category_id]": "591",
                "space_category[content_id]": "3",
            }
            url = BASE_URL + "/Seat/Index/searchSeats"
            resp = self.session.get(url=url, params=params, timeout=15)
            data = resp.json()
            if isinstance(data, dict) and data.get("data") and data["data"].get("uid"):
                self.uid = str(data["data"]["uid"])
                self.name = data["data"].get("uname", "")
                self.session.cookies.update({"org_id": ORG_ID})
                logger.info("Cookie 登录成功: uid=%s, name=%s", self.uid, self.name)
                return True
        except (ConnectionResetError, ConnectionError, requests.exceptions.ConnectionError) as e:
            logger.warning("Cookie 验证网络错误: %s", e)
            self._cookie_login_network_err = True
            return False
        except Exception as e:
            logger.warning("Cookie 验证失败: %s", e)

        logger.info("缓存 cookies 无效")
        return False

    def _login_with_playwright(self, debug=None) -> tuple[bool, Optional[str]]:
        """CAS 登录（HTTP 方式）。"""
        success, err_type, cookies, uid, name = cas_login(
            username=self.student_id,
            password=self.password,
            base_url=BASE_URL,
            debug=debug,
        )

        if not success:
            return False, err_type

        # 应用 cookies（cas_login 返回 dict）
        self.session.cookies.update(cookies)
        self.uid = uid or ""
        self.name = name or ""

        # 如果 uid 未获取，尝试 API
        if not self.uid:
            self._fetch_user_info()

        # 保存 cookies（转换为列表格式保存）
        cookies_list = [{"name": k, "value": v} for k, v in cookies.items()]
        self._save_cookies(cookies_list)
        logger.info("登录成功（cookies 已保存）")
        return True, None

    def _fetch_user_info(self) -> None:
        """通过 API 获取用户信息。"""
        try:
            params = {
                "space_category[category_id]": "591",
                "space_category[content_id]": "3",
            }
            url = BASE_URL + "/Seat/Index/searchSeats"
            resp = self.session.get(url=url, params=params, timeout=15)
            data = resp.json()
            if isinstance(data, dict) and data.get("data"):
                self.uid = str(data["data"].get("uid", ""))
                self.name = data["data"].get("uname", "")
        except Exception:
            pass

    def _load_cookies(self) -> Optional[dict]:
        """从文件加载缓存 cookies。"""
        try:
            if os.path.exists(COOKIE_FILE):
                with open(COOKIE_FILE, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _save_cookies(self, cookies: list[dict]) -> None:
        """保存 cookies 到文件。"""
        try:
            os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
            with open(COOKIE_FILE, "w") as f:
                json.dump({"cookies": cookies, "uid": self.uid, "name": self.name}, f)
        except Exception as e:
            logger.warning("保存 cookies 失败: %s", e)

    def _clear_cookies(self) -> None:
        """清除缓存 cookies。"""
        try:
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)
        except Exception:
            pass
