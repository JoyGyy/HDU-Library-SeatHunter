"""
CAS SSO 登录模块
完全模拟 CAS SPA 的表单提交流程
"""
import re
import base64
import requests
from urllib.parse import urljoin
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

LOGIN_ERR_NETWORK = "network"
LOGIN_ERR_AUTH = "auth"


def _aes_encrypt(key_b64: str, plaintext: str) -> str:
    """
    AES-128-ECB 加密，PKCS7 填充。
    key_b64: base64 编码的密钥（croypto）
    plaintext: 明文密码
    """
    key_bytes = base64.b64decode(key_b64)
    plaintext_bytes = plaintext.encode("utf-8")
    cipher = AES.new(key_bytes, AES.MODE_ECB)
    padded = pad(plaintext_bytes, AES.block_size)
    encrypted = cipher.encrypt(padded)
    return base64.b64encode(encrypted).decode("utf-8")


def _log(msg: str, debug=None):
    if debug:
        debug.log(msg)


def cas_login(
    username: str,
    password: str,
    base_url: str,
    debug=None,
) -> tuple:
    """
    执行 CAS SSO 登录（模拟 SPA 表单提交）。

    返回: (success, error_type, cookies_dict, uid, name)
    """
    _log("开始 CAS 登录...", debug)

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    })

    # ---- 第一步：访问图书馆登录入口，获取 CAS 重定向 ----
    _log("正在访问图书馆登录入口...", debug)
    try:
        r = session.get(
            f"{base_url}/User/Index/hduCASLogin",
            allow_redirects=True,
            timeout=15,
        )
    except Exception as e:
        _log(f"访问图书馆登录入口失败: {e}", debug)
        return False, "network", {}, "", ""

    cas_url = r.url
    _log(f"CAS 登录地址: {cas_url[:80]}...", debug)

    if "sso.hdu.edu.cn" not in cas_url:
        _log("未能跳转到 CAS 登录页", debug)
        return False, "cas_redirect", {}, "", ""

    html = r.text

    # ---- 第二步：提取表单参数 ----
    croypto_match = re.search(r'id="login-croypto">\s*([^<]+)', html)
    croypto = croypto_match.group(1).strip() if croypto_match else ""
    _log(f"croypto: {croypto[:30]}...", debug)

    execution_match = re.search(r'name="execution"\s+value="([^"]+)"', html)
    execution = execution_match.group(1) if execution_match else ""

    if not croypto:
        _log("无法提取 croypto", debug)
        return False, "croypto", {}, "", ""

    if not execution:
        # 尝试从隐藏 input 提取
        execution_match = re.search(r'id="login-page-flowkey">\s*([^<]+)', html)
        execution = execution_match.group(1).strip() if execution_match else ""

    _log(f"execution: {execution[:40]}...", debug)

    # ---- 第三步：加密密码 ----
    encrypted_password = _aes_encrypt(croypto, password)
    _log(f"密码加密完成: {encrypted_password[:20]}...", debug)

    # ---- 第四步：提交表单 ----
    _log("正在提交登录表单...", debug)

    form_data = {
        "username": username,
        "type": "UsernamePassword",
        "_eventId": "submit",
        "execution": execution,
        "croypto": croypto,
        "password": encrypted_password,
    }

    try:
        login_resp = session.post(
            cas_url,
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": cas_url,
                "Origin": "https://sso.hdu.edu.cn",
            },
            allow_redirects=True,
            timeout=20,
        )
    except Exception as e:
        _log(f"登录请求失败: {e}", debug)
        return False, "network", {}, "", ""

    _log(f"登录后 URL: {login_resp.url[:80]}...", debug)

    # ---- 第五步：检查登录结果 ----
    if "huitu.zhishulib.com" not in login_resp.url:
        _log("登录失败，未跳转到图书馆", debug)
        # 检查是否有错误信息
        err_match = re.search(r'login-error-msg[^>]*>([^<]+)', login_resp.text)
        if err_match and err_match.group(1).strip():
            _log(f"错误信息: {err_match.group(1).strip()}", debug)
        return False, "auth", {}, "", ""

    _log("登录成功，已跳转到图书馆", debug)

    # ---- 第六步：获取 cookies 和用户信息 ----
    cookies = dict(session.cookies)
    _log(f"获取到 {len(cookies)} 个 cookies", debug)

    uid, name = "", ""

    # 尝试获取用户信息
    try:
        me_resp = session.get(
            f"{base_url}/User/Index/getUserInfo",
            timeout=10,
        )
        if me_resp.status_code == 200:
            me_data = me_resp.json()
            _log(f"用户信息: {str(me_data)[:200]}", debug)
            uid = str(me_data.get("data", {}).get("uid", ""))
            name = me_data.get("data", {}).get("name", "")
    except Exception:
        pass

    if not uid:
        # 尝试从搜索接口获取用户信息
        try:
            search_resp = session.get(
                f"{base_url}/Seat/Index/searchSeats",
                params={
                    "space_category[category_id]": 591,
                    "space_category[content_id]": 3,
                    "LAB_JSON": 1,
                },
                timeout=10,
            )
            if search_resp.status_code == 200:
                search_data = search_resp.json()
                uid = str(search_data.get("data", {}).get("uid", ""))
                name = search_data.get("data", {}).get("uname", "")
        except Exception:
            pass

    if uid:
        _log(f"CAS 登录成功: uid={uid}, name={name}", debug)
        return True, "", cookies, uid, name

    # cookies 中有 token 也算成功
    has_token = any(k in cookies for k in ["zhishulib_token", "token", "PHPSESSID", "laravel_session"])
    if has_token:
        _log("CAS 登录成功（有 token，但未获取到 uid）", debug)
        return True, "", cookies, "", ""

    _log("CAS 登录似乎成功，但未获取到有效用户信息", debug)
    return False, "user_info", {}, "", ""
