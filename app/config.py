"""硬编码配置。所有固定参数集中管理。"""

# ─── 用户账号 ────────────────────────────────────────────────────────────────────
USER_STUDENT_ID = "23051110"
USER_PASSWORD = "@Krz201314"
USER_UID = "303687"

COMPANION_STUDENT_ID = "23140322"
COMPANION_PASSWORD = "Pangzidan0713#"
COMPANION_UID = "305033"

# ─── 座位 ────────────────────────────────────────────────────────────────────────
ROOM_NAME = "自习室"
FLOOR_NAME = "比特庭园（二楼西）"
TARGET_SEATS = ["100"]
KNOWN_SEAT_IDS = {"99": "60810", "100": "60811"}

# ─── 时间 ────────────────────────────────────────────────────────────────────────
BEGIN_HOUR = 10
DURATION_HOURS = 10
AUTO_BOOK_HOUR = 20
AUTO_BOOK_MINUTE = 1
AUTO_CHECKIN_HOUR = 9
AUTO_CHECKIN_MINUTE = 31

# ─── 重试 ────────────────────────────────────────────────────────────────────────
MAX_RETRY = 100
RETRY_INTERVAL = 6  # 秒
RELOGIN_EVERY = 20  # 每 N 次重试后重新登录
REQUEST_INTERVAL = 5  # 座位/日期之间的间隔，防封号

# ─── API ─────────────────────────────────────────────────────────────────────────
BASE_URL = "https://hdu.huitu.zhishulib.com"
ORG_ID = "104"

# ─── 状态码映射 ──────────────────────────────────────────────────────────────────
STATUS_MAP = {
    "0": "待签到",
    "1": "已签到",
    "2": "已结束",
    "3": "已取消",
    "4": "已过期",
    "5": "预约中",
    "6": "待确认",
    "7": "已确认",
}

# ─── 不可重试的错误关键词 ────────────────────────────────────────────────────────
NON_RETRYABLE_ERRORS = ["已有预约", "请勿重复", "无法预约", "不可用", "锁定", "占用", "不开放", "超出可预约"]

# ─── 请求头 ──────────────────────────────────────────────────────────────────────
DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.5",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Referer": "https://hdu.huitu.zhishulib.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
}
