"""签到执行器：在预约开始时间前后自动签到。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from time import sleep
from typing import Optional, Callable

from seathunter.api.client import ApiClient

logger = logging.getLogger("seathunter.scheduler")

# 签到时间窗口配置
CHECKIN_ADVANCE_MINUTES = 25  # 签到提前时间（分钟）


class CheckInRunner:
    """签到执行器，在预约开始时间前25分钟到后25分钟内执行签到。"""

    def __init__(self, api_client: ApiClient,
                 interval: int = 5, max_try_times: int = 10):
        self.api = api_client
        self.interval = interval
        self.max_try_times = max_try_times
        self._cancelled = False

    def cancel(self):
        """取消当前签到任务。"""
        self._cancelled = True

    def get_checkin_window(self, begin_time: datetime) -> tuple[datetime, datetime]:
        """计算签到时间窗口

        Args:
            begin_time: 预约开始时间（完整的 datetime）

        Returns:
            (窗口开始时间, 窗口结束时间)
        """
        window_start = begin_time - timedelta(minutes=CHECKIN_ADVANCE_MINUTES)
        window_end = begin_time + timedelta(minutes=CHECKIN_ADVANCE_MINUTES)
        return (window_start, window_end)

    def run_checkin(self, booking_id: str, begin_time: datetime,
                    on_result: Optional[Callable] = None) -> bool:
        """执行签到，带重试。

        Args:
            booking_id: 预约 ID
            begin_time: 预约开始时间（完整的 datetime）
            on_result: 签到结果回调 (success: bool, message: str)

        Returns:
            签到是否成功
        """
        self._cancelled = False
        window_start, window_end = self.get_checkin_window(begin_time)
        now = datetime.now()

        # 如果还没到签到窗口，等待（可中断）
        if now < window_start:
            wait_seconds = int((window_start - now).total_seconds())
            logger.info("签到窗口未到，等待 %d 秒后开始签到", wait_seconds)
            for _ in range(wait_seconds):
                if self._cancelled:
                    return False
                sleep(1)

        # 在窗口内重试签到
        for attempt in range(1, self.max_try_times + 1):
            if self._cancelled:
                logger.info("签到任务已取消")
                return False

            now = datetime.now()
            if now > window_end:
                logger.warning("签到窗口已关闭（%s），停止重试",
                              window_end.strftime("%H:%M:%S"))
                if on_result:
                    on_result(False, "签到窗口已关闭")
                return False

            success, msg, _ = self.api.check_in(booking_id)
            if success:
                logger.info("签到成功！(第 %d 次尝试)", attempt)
                if on_result:
                    on_result(True, "签到成功")
                return True

            logger.warning("签到失败(第 %d/%d 次): %s", attempt, self.max_try_times, msg)
            if on_result:
                on_result(False, f"签到失败(第{attempt}次): {msg}")

            # 重试间隔（可中断）
            if attempt < self.max_try_times:
                for _ in range(self.interval):
                    if self._cancelled:
                        return False
                    sleep(1)

        logger.error("签到失败，已达最大重试次数 (%d)", self.max_try_times)
        return False
