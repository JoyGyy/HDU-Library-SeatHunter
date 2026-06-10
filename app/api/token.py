"""API token 签名生成。

参数按字母序拼接 → MD5 → base64。
"""

from __future__ import annotations

import hashlib
import base64
import datetime as dt


def generate_booking_data(
    begin_time: dt.datetime,
    duration_hours: int,
    seat_ids: list[str],
    booker_uids: list[str],
) -> tuple[dict, str]:
    """生成预约 POST 数据和 API token。

    Args:
        begin_time: 预约开始时间
        duration_hours: 时长（小时）
        seat_ids: 座位 ID 列表
        booker_uids: 预约人 UID 列表

    Returns:
        (data_dict, api_token_string)
    """
    if not seat_ids or not booker_uids:
        raise ValueError("seat_ids 和 booker_uids 不能为空")

    data = {}
    data["beginTime"] = int(begin_time.timestamp())
    data["duration"] = duration_hours * 3600
    for i, sid in enumerate(seat_ids):
        data[f"seats[{i}]"] = sid
    data["is_recommend"] = 0
    data["api_time"] = int(dt.datetime.now().timestamp())
    for i, uid in enumerate(booker_uids):
        data[f"seatBookers[{i}]"] = uid

    # 参数按字母序拼接
    api_token_str = (
        f"post&/Seat/Index/bookSeats?LAB_JSON=1"
        f"&api_time{data['api_time']}"
        f"&beginTime{data['beginTime']}"
        f"&duration{data['duration']}"
        f"&is_recommend0"
        f"&seatBookers[0]{data['seatBookers[0]']}"
        f"&seats[0]{data['seats[0]']}"
    )
    md5 = hashlib.md5(api_token_str.encode("utf-8")).hexdigest()
    api_token = base64.b64encode(md5.encode("utf-8")).decode("utf-8")

    return data, api_token
