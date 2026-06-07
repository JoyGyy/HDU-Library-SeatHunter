"""好友代预约自动同意服务。

通过好友凭证登录图书馆系统，自动确认预约。
"""

from __future__ import annotations

import logging
from typing import Tuple

import requests

from seathunter.auth.friend_store import FriendStore
from seathunter.auth.session_manager import lookup_uid
from seathunter.auth.playwright_login import playwright_login

logger = logging.getLogger("seathunter.services")


class FriendService:
    """好友代预约服务，负责用好友身份完成预约确认。"""

    def __init__(self, friend_store: FriendStore, base_url: str = "https://hdu.huitu.zhishulib.com"):
        self.friend_store = friend_store
        self.base_url = base_url

    def auto_confirm(self, booking_id: str, friend_student_id: str) -> Tuple[bool, str]:
        """用好友账号自动确认预约。

        1. 从 store 获取好友凭证
        2. 用 Playwright 以好友身份登录（独立 session）
        3. 调用 /Seat/Index/confirmBooking?bookingId=xxx
        4. 返回 (成功?, 消息)

        Args:
            booking_id: 预约 ID
            friend_student_id: 好友学号

        Returns:
            (success, message) 成功时 message 包含确认结果
        """
        # 从 store 获取好友凭证
        record = self.friend_store.get(friend_student_id)
        if record is None:
            return (False, f"好友 {friend_student_id} 不存在于好友列表中")

        password = self.friend_store.get_password(friend_student_id)
        uid = record.get("uid", "")
        name = record.get("name", "")

        # 验证好友凭证有效
        logger.info("验证好友凭证: %s (%s)", friend_student_id, name)
        success, verified_uid, verified_name = lookup_uid(
            username=friend_student_id,
            password=password,
            base_url=self.base_url,
        )
        if not success:
            return (False, f"好友凭证验证失败: {verified_name}")

        # 用 Playwright 获取独立 session cookie
        logger.info("好友凭证验证通过，开始登录获取 Cookie")
        login_success, _, cookies, _, _, login_err = playwright_login(
            username=friend_student_id,
            password=password,
            library_url=self.base_url + "/",
            base_url=self.base_url,
        )
        if not login_success or not cookies:
            return (False, f"好友登录失败: {login_err}")

        # 创建独立 session 并调用 confirmBooking
        logger.info("好友登录成功，调用 confirmBooking: %s", booking_id)
        session = requests.Session()
        session.verify = False
        cookie_dict = {c["name"]: c["value"] for c in cookies}
        session.cookies.update(cookie_dict)
        session.cookies.update({"org_id": "104"})

        try:
            url = f"{self.base_url}/Seat/Index/confirmBooking"
            resp = session.post(
                url=url,
                data={"bookingId": booking_id, "LAB_JSON": 1},
                timeout=30,
            )
            result = resp.json()
            if result.get("CODE") == "ok" and result.get("DATA", {}).get("result") == "success":
                logger.info("预约确认成功: %s", booking_id)
                return (True, "预约确认成功")
            else:
                error_msg = result.get("MSG", result.get("DATA", {}).get("result", "未知错误"))
                logger.warning("预约确认失败: %s", error_msg)
                return (False, f"预约确认失败: {error_msg}")
        except Exception as e:
            logger.error("预约确认请求异常: %s", e)
            return (False, f"请求异常: {e}")

    def test_login(self, friend_student_id: str) -> Tuple[bool, str]:
        """测试好友登录是否正常。

        Args:
            friend_student_id: 好友学号

        Returns:
            (success, message)
        """
        record = self.friend_store.get(friend_student_id)
        if record is None:
            return (False, f"好友 {friend_student_id} 不存在于好友列表中")

        password = self.friend_store.get_password(friend_student_id)
        name = record.get("name", "")

        logger.info("测试好友登录: %s (%s)", friend_student_id, name)
        success, uid, result_name = lookup_uid(
            username=friend_student_id,
            password=password,
            base_url=self.base_url,
        )
        if success:
            return (True, f"好友 {result_name} 登录正常")
        return (False, f"好友登录失败: {result_name}")
