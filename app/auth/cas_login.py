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
            logger.info("正在访问图书馆首页...")
            page.goto(library_url, wait_until="networkidle", timeout=60000)

            # 等待 SPA 表单渲染完成（#login-username 有子元素）
            logger.info("等待 CAS 表单渲染...")
            page.wait_for_selector("#login-username input", timeout=15000)
            page.wait_for_timeout(1000)

            # 填写账号（在 #login-username 容器内查找）
            logger.info("填写账号...")
            username_input = page.query_selector('#login-username input[type="text"]')
            if not username_input:
                username_input = page.query_selector('#login-username input')
            if not username_input:
                # 打印页面内容用于调试
                html = page.content()
                logger.error("找不到账号输入框，页面片段: %s", html[html.find("login-username"):html.find("login-username")+500] if "login-username" in html else "未找到 login-username")
                return False, LOGIN_ERR_AUTH, [], "", ""

            username_input.click()
            username_input.fill(username)
            logger.info("账号填写成功")

            # 填写密码
            logger.info("填写密码...")
            password_input = page.query_selector('#login-username input[type="password"]')
            if not password_input:
                # 可能是第二个 input
                inputs = page.query_selector_all('#login-username input')
                if len(inputs) >= 2:
                    password_input = inputs[1]
            if not password_input:
                logger.error("找不到密码输入框")
                return False, LOGIN_ERR_AUTH, [], "", ""

            password_input.click()
            password_input.fill(password)
            logger.info("密码填写成功")

            # 点击登录按钮
            logger.info("点击登录按钮...")
            submit_btn = page.query_selector('#login-username button[type="submit"]')
            if not submit_btn:
                submit_btn = page.query_selector('#login-username button')
            if not submit_btn:
                submit_btn = page.query_selector('form button[type="submit"]')
            if not submit_btn:
                submit_btn = page.query_selector('button[type="submit"]')
            if not submit_btn:
                logger.error("找不到登录按钮")
                return False, LOGIN_ERR_AUTH, [], "", ""

            submit_btn.click()
            logger.info("登录按钮已点击")

            # 等待跳转回 zhishulib.com
            logger.info("等待跳转...")
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
