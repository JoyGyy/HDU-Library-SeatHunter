"""CAS SSO 登录。

直接用 HTTP 请求登录，不依赖 Playwright。
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import requests

logger = logging.getLogger("seathunter.auth")

LOGIN_ERR_NETWORK = "network"
LOGIN_ERR_AUTH = "auth"


def cas_login(
    username: str,
    password: str,
    base_url: str,
    debug=None,
) -> tuple[bool, Optional[str], dict, str, str]:
    """HTTP 方式登录 CAS SSO。

    Args:
        username: 学号
        password: 密码
        base_url: API 基础 URL
        debug: 可选的 DebugLogger 实例

    Returns:
        (success, error_type, cookies_dict, uid, name)
    """
    def _log(msg: str):
        logger.info(msg)
        if debug:
            debug.log(msg)

    session = requests.Session()
    session.verify = False
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })

    try:
        # 1. 访问图书馆登录入口，获取 CAS 登录 URL
        _log("正在访问图书馆登录入口...")
        login_url = base_url + "/User/Index/hduCASLogin"
        resp = session.get(login_url, timeout=30, allow_redirects=False)

        # 从重定向中提取 CAS 登录 URL
        cas_url = resp.headers.get("Location", "")

        # 如果没有重定向，尝试允许重定向
        if not cas_url:
            _log(f"登录入口状态码: {resp.status_code}")
            resp2 = session.get(login_url, timeout=30, allow_redirects=True)
            _log(f"重定向后 URL: {resp2.url[:80]}...")

            # 检查是否已经跳转到 CAS
            if "sso.hdu.edu.cn" in resp2.url or "cas.hdu.edu.cn" in resp2.url:
                cas_url = resp2.url
            else:
                _log(f"页面内容片段: {resp2.text[:300]}")
                return False, LOGIN_ERR_AUTH, {}, "", ""

        _log(f"CAS 登录地址: {cas_url[:80]}...")

        # 2. 访问 CAS 登录页，获取表单参数
        _log("正在获取 CAS 登录页...")
        cas_resp = session.get(cas_url, timeout=30)
        cas_html = cas_resp.text

        # 提取隐藏字段
        execution = ""
        lt = ""
        _eventId = "submit"

        # 提取 execution 参数
        exec_match = re.search(r'name="execution"\s+value="([^"]*)"', cas_html)
        if exec_match:
            execution = exec_match.group(1)

        # 提取 lt 参数
        lt_match = re.search(r'name="lt"\s+value="([^"]*)"', cas_html)
        if lt_match:
            lt = lt_match.group(1)

        # 提取 login-croypto（加密参数）
        croypto = ""
        croypto_match = re.search(r'id="login-croypto">([^<]*)<', cas_html)
        if croypto_match:
            croypto = croypto_match.group(1)

        _log(f"表单参数: execution={execution[:20]}..., lt={lt[:20]}..., croypto={croypto[:20]}...")

        # 3. 提交登录表单
        _log("正在提交登录表单...")
        login_data = {
            "username": username,
            "password": password,
            "execution": execution,
            "lt": lt,
            "_eventId": _eventId,
            "loginType": "normal",
        }

        if croypto:
            login_data["croypto"] = croypto

        login_resp = session.post(
            cas_url,
            data=login_data,
            timeout=30,
            allow_redirects=True,
        )

        # 检查是否登录成功（应该跳转回 zhishulib.com）
        final_url = login_resp.url
        _log(f"登录后跳转到: {final_url[:80]}...")

        if "huitu.zhishulib.com" not in final_url:
            # 登录失败，检查错误信息
            if "用户名或密码" in login_resp.text or "密码错误" in login_resp.text:
                _log("用户名或密码错误")
                return False, LOGIN_ERR_AUTH, {}, "", ""
            elif "验证码" in login_resp.text:
                _log("需要验证码，无法自动登录")
                return False, LOGIN_ERR_AUTH, {}, "", ""
            else:
                _log(f"登录失败，页面内容: {login_resp.text[:200]}")
                return False, LOGIN_ERR_AUTH, {}, "", ""

        # 4. 提取 cookies
        cookies = dict(session.cookies)
        _log(f"获取到 {len(cookies)} 个 cookies")

        # 5. 获取用户信息
        uid = ""
        name = ""
        try:
            info_resp = session.get(
                base_url + "/Seat/Index/searchSeats",
                params={
                    "space_category[category_id]": "591",
                    "space_category[content_id]": "3",
                },
                timeout=15,
            )
            info_data = info_resp.json()
            if isinstance(info_data, dict) and info_data.get("data"):
                uid = str(info_data["data"].get("uid", ""))
                name = info_data["data"].get("uname", "")
                _log(f"获取用户信息: uid={uid}, name={name}")
        except Exception as e:
            _log(f"获取用户信息失败: {e}")

        if not uid:
            # 从 cookies 提取 uid
            for k, v in cookies.items():
                if k == "uid":
                    uid = v
                    break

        _log(f"CAS 登录成功: uid={uid}, name={name}")
        return True, None, cookies, uid, name

    except requests.exceptions.ConnectionError as e:
        _log(f"CAS 登录网络错误: {e}")
        return False, LOGIN_ERR_NETWORK, {}, "", ""
    except Exception as e:
        _log(f"CAS 登录失败: {e}")
        return False, LOGIN_ERR_AUTH, {}, "", ""
