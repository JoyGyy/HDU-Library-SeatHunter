"""Playwright CAS SSO 登录。

通过浏览器自动化登录杭电 CAS，提取 cookies。
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("seathunter.auth")

LOGIN_ERR_NETWORK = "network"
LOGIN_ERR_AUTH = "auth"


def playwright_login(
    username: str,
    password: str,
    library_url: str,
    base_url: str,
) -> tuple[bool, Optional[str], list[dict], str, str]:
    """Playwright 浏览器自动化登录。

    Args:
        username: 学号
        password: 密码
        library_url: 图书馆首页 URL
        base_url: API 基础 URL

    Returns:
        (success, error_type, cookies, uid, name)
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("playwright 未安装")
        return False, LOGIN_ERR_NETWORK, [], "", ""

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # 访问图书馆首页（会自动跳转 CAS）
            page.goto(library_url, wait_until="domcontentloaded", timeout=30000)

            # 填写账号密码
            page.fill('input[name="username"], #username', username)
            page.fill('input[name="password"], #password', password)

            # 点击登录按钮
            page.click('button[type="submit"], input[type="submit"], .login-btn')

            # 等待跳转回 zhishulib.com
            page.wait_for_url("**/huitu.zhishulib.com/**", timeout=30000)

            # 提取 cookies
            cookies = context.cookies()

            # 获取用户信息
            uid = ""
            name = ""
            try:
                result = page.evaluate("""() => {
                    return fetch('/Seat/Index/searchSeats?space_category[category_id]=591&space_category[content_id]=3&LAB_JSON=1')
                        .then(r => r.json())
                        .then(d => ({uid: d.data?.uid || '', name: d.data?.uname || ''}))
                }""")
                uid = str(result.get("uid", ""))
                name = result.get("name", "")
            except Exception as e:
                logger.warning("获取用户信息失败: %s", e)
                # 从 cookies 提取 uid
                for c in cookies:
                    if c["name"] == "uid":
                        uid = c["value"]
                        break

            browser.close()

            logger.info("CAS 登录成功: uid=%s, name=%s", uid, name)
            return True, None, cookies, uid, name

    except Exception as e:
        error_msg = str(e)
        if any(kw in error_msg for kw in ["CONNECTION_RESET", "CONNECTION_REFUSED", "ERR_NAME", "timeout"]):
            logger.error("CAS 登录网络错误: %s", e)
            return False, LOGIN_ERR_NETWORK, [], "", ""
        logger.error("CAS 登录失败: %s", e)
        return False, LOGIN_ERR_AUTH, [], "", ""
