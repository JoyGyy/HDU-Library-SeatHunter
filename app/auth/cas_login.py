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
    debug=None,
) -> tuple[bool, Optional[str], list[dict], str, str]:
    """Playwright 浏览器自动化登录。

    Args:
        username: 学号
        password: 密码
        library_url: 图书馆首页 URL
        base_url: API 基础 URL
        debug: 可选的 DebugLogger 实例，用于向前端输出日志

    Returns:
        (success, error_type, cookies, uid, name)
    """
    def _log(msg: str):
        logger.info(msg)
        if debug:
            debug.log(msg)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _log("playwright 未安装")
        return False, LOGIN_ERR_NETWORK, [], "", ""

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--single-process",
                ],
            )
            context = browser.new_context()
            page = context.new_page()

            # 访问图书馆首页（会自动跳转 CAS）
            _log("正在访问图书馆首页...")
            page.goto(library_url, wait_until="networkidle", timeout=60000)

            # 等待 SPA 表单渲染完成（#login-username 有子元素）
            _log("等待 CAS 表单渲染...")
            try:
                page.wait_for_selector("#login-username input", timeout=15000)
            except Exception:
                # 打印页面 URL 和部分内容用于调试
                _log(f"当前页面 URL: {page.url}")
                html = page.content()
                _log(f"页面标题: {page.title()}")
                if "login-username" in html:
                    _log(f"找到 login-username，内容片段: {html[html.find('login-username'):html.find('login-username')+300]}")
                else:
                    _log(f"未找到 login-username，页面前500字符: {html[:500]}")
                return False, LOGIN_ERR_AUTH, [], "", ""

            page.wait_for_timeout(1000)

            # 填写账号（在 #login-username 容器内查找）
            _log("填写账号...")
            username_input = page.query_selector('#login-username input[type="text"]')
            if not username_input:
                username_input = page.query_selector('#login-username input')
            if not username_input:
                # 打印所有 input 元素
                inputs = page.query_selector_all('input')
                _log(f"页面共有 {len(inputs)} 个 input 元素")
                for i, inp in enumerate(inputs):
                    _log(f"  input[{i}]: type={inp.get_attribute('type')}, name={inp.get_attribute('name')}, placeholder={inp.get_attribute('placeholder')}")
                return False, LOGIN_ERR_AUTH, [], "", ""

            username_input.click()
            username_input.fill(username)
            _log("账号填写成功")

            # 填写密码
            _log("填写密码...")
            password_input = page.query_selector('#login-username input[type="password"]')
            if not password_input:
                # 可能是第二个 input
                inputs = page.query_selector_all('#login-username input')
                if len(inputs) >= 2:
                    password_input = inputs[1]
            if not password_input:
                _log("找不到密码输入框")
                return False, LOGIN_ERR_AUTH, [], "", ""

            password_input.click()
            password_input.fill(password)
            _log("密码填写成功")

            # 点击登录按钮
            _log("点击登录按钮...")
            submit_btn = page.query_selector('#login-username button[type="submit"]')
            if not submit_btn:
                submit_btn = page.query_selector('#login-username button')
            if not submit_btn:
                submit_btn = page.query_selector('form button[type="submit"]')
            if not submit_btn:
                submit_btn = page.query_selector('button[type="submit"]')
            if not submit_btn:
                # 打印所有 button 元素
                buttons = page.query_selector_all('button')
                _log(f"页面共有 {len(buttons)} 个 button 元素")
                for i, btn in enumerate(buttons):
                    _log(f"  button[{i}]: type={btn.get_attribute('type')}, text={btn.inner_text()[:50]}")
                return False, LOGIN_ERR_AUTH, [], "", ""

            submit_btn.click()
            _log("登录按钮已点击")

            # 等待跳转回 zhishulib.com
            _log("等待跳转...")
            try:
                page.wait_for_url("**/huitu.zhishulib.com/**", timeout=30000)
            except Exception:
                _log(f"跳转超时，当前 URL: {page.url}")
                # 检查是否有错误提示
                error_el = page.query_selector('.error-message, .alert-danger, .login-error, [class*="error"]')
                if error_el:
                    _log(f"页面错误提示: {error_el.inner_text()}")
                return False, LOGIN_ERR_AUTH, [], "", ""

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
                _log(f"获取用户信息失败: {e}")
                # 从 cookies 提取 uid
                for c in cookies:
                    if c["name"] == "uid":
                        uid = c["value"]
                        break

            browser.close()

            _log(f"CAS 登录成功: uid={uid}, name={name}")
            return True, None, cookies, uid, name

    except Exception as e:
        error_msg = str(e)
        if any(kw in error_msg for kw in ["CONNECTION_RESET", "CONNECTION_REFUSED", "ERR_NAME", "timeout"]):
            _log(f"CAS 登录网络错误: {e}")
            return False, LOGIN_ERR_NETWORK, [], "", ""
        _log(f"CAS 登录失败: {e}")
        return False, LOGIN_ERR_AUTH, [], "", ""
