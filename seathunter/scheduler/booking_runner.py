"""Booking runner: execute bookings with retry logic.

Extracted from main.py:157-172 (startNow) and killer.py:416-422 (run).
"""

from __future__ import annotations

import logging
from datetime import datetime
from time import sleep
from typing import List, Callable, Optional

from seathunter.api.client import ApiClient
from seathunter.auth.session_manager import SessionManager
from seathunter.models.plan import Plan
from seathunter.models.booking_result import BookingResult

logger = logging.getLogger("seathunter.scheduler")

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class BookingRunner:
    """Executes booking attempts with retry logic."""

    def __init__(self, api_client: ApiClient, session_manager: SessionManager,
                 interval: int = 5, max_try_times: int = 10):
        self.api = api_client
        self.session_mgr = session_manager
        self.interval = interval
        self.max_try_times = max_try_times
        self._cancelled = False
        self._checkin_registry = None  # 新增：签到注册回调

    def cancel(self):
        """Cancel the current booking run."""
        self._cancelled = True

    def set_checkin_registry(self, callback):
        """设置签到注册回调

        callback(booking_id, begin_time, target_date, plan_desc)
        """
        self._checkin_registry = callback

    def run_booking(self, plans: List[Plan], target_date: datetime,
                    on_result: Optional[Callable[[BookingResult], None]] = None,
                    on_attempt: Optional[Callable[[int, int], None]] = None) -> List[BookingResult]:
        """Execute booking for all plans targeting a specific date.

        Args:
            plans: List of Plan objects to book.
            target_date: The date the seats are for.
            on_result: Callback for each booking result.
            on_attempt: Callback for each attempt (attempt_num, plan_index).

        Returns:
            List of BookingResult for all attempts.
        """
        self._cancelled = False
        results = []

        for retry in range(self.max_try_times):
            if self._cancelled:
                logger.info("Booking run cancelled")
                break

            if on_attempt:
                on_attempt(retry + 1, -1)
            logger.info("Booking attempt %d/%d for %s",
                       retry + 1, self.max_try_times,
                       target_date.strftime("%Y-%m-%d"))

            for i, plan in enumerate(plans):
                if self._cancelled:
                    break

                # 使用方案中的目标日期（如有），否则用调度传入的日期
                if plan.target_date:
                    from datetime import datetime as dt
                    plan_date = dt.strptime(plan.target_date, "%Y-%m-%d")
                else:
                    plan_date = target_date

                # Build the actual datetime for the plan
                hour, minute, second = (int(x) for x in plan.begin_time.split(":"))
                begin_time = plan_date.replace(hour=hour, minute=minute, second=second, microsecond=0)

                # Get seat IDs and booker UIDs (支持多人预约)
                seat_ids = [s.seat_id for s in plan.seats]
                booker_uids = [
                    s.booker_uid if s.booker_uid else self.session_mgr.uid
                    for s in plan.seats
                ]
                # 确保当前用户在预约人列表中（API 要求）
                if self.session_mgr.uid not in booker_uids:
                    booker_uids[0] = self.session_mgr.uid
                    logger.info("当前用户不在预约人列表中，已自动替换第一个预约人")

                result = self._book_single_plan(plan, begin_time, seat_ids, booker_uids, plan_date)
                results.append(result)

                if on_result:
                    on_result(result)

                if result.success:
                    logger.info("Booking successful: %s - %s", plan.id, plan.room_name)
                    # 保存 bookingId 到 plan
                    if result.booking_id:
                        plan.booking_id = result.booking_id
                        logger.info("已保存 bookingId: %s", result.booking_id)
                        # 注册签到任务
                        if self._checkin_registry:
                            plan_desc = f"{plan.room_name}-{','.join(s.seat_num for s in plan.seats)}"
                            target_date_str = plan_date.strftime("%Y-%m-%d")
                            self._checkin_registry(
                                result.booking_id,
                                plan.begin_time,
                                target_date_str,
                                plan_desc,
                            )
                    return results

                logger.warning("Plan %s failed: %s", plan.id, result.message)

                if self._cancelled:
                    break

            if not self._cancelled and retry < self.max_try_times - 1:
                logger.debug("Waiting %ds before retry...", self.interval)
                # Interruptible sleep
                for _ in range(self.interval):
                    if self._cancelled:
                        break
                    sleep(1)

        return results

    def _book_single_plan(self, plan: Plan, begin_time: datetime,
                          seat_ids: List[str], booker_uids: List[str],
                          target_date: datetime) -> BookingResult:
        """Execute a single booking attempt for one plan."""
        try:
            resp = self.api.book_seat(begin_time, plan.duration_hours, seat_ids, booker_uids)
            return BookingResult.from_api_response(
                resp,
                plan_id=plan.id,
                seat_num=",".join(s.seat_num for s in plan.seats),
                room_name=plan.room_name,
                target_date=target_date.strftime("%Y-%m-%d"),
            )
        except Exception as e:
            logger.error("Booking exception for plan %s: %s", plan.id, e)
            return BookingResult(
                success=False,
                code="error",
                message=str(e),
                plan_id=plan.id,
                target_date=target_date.strftime("%Y-%m-%d"),
            )
