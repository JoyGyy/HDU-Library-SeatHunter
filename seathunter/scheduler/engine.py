"""Non-blocking scheduler engine.

Core new module: runs in a dedicated thread, uses threading.Event
for interruptible waits instead of blocking sleep().
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import List, Optional, Callable, Dict, Any

from seathunter.models.schedule import Schedule
from seathunter.models.booking_result import BookingResult
from seathunter.scheduler.booking_runner import BookingRunner, WEEKDAY_NAMES
from seathunter.auth.session_manager import SessionManager
from seathunter.config.manager import ConfigManager

logger = logging.getLogger("seathunter.scheduler")


class SchedulerEngine:
    """Non-blocking scheduling engine that runs in a background thread.

    Replaces the old sleep()-based countdown with threading.Event-based waits,
    allowing clean shutdown within 1 second.

    Callbacks:
        on_countdown_tick(remaining_seconds, trigger_time, plan_desc)
        on_booking_result(result: BookingResult)
        on_booking_start(target_date, plan_ids)
        on_error(error: Exception)
        on_idle()  # called when no schedules are active
    """

    def __init__(self, config_manager: ConfigManager, session_manager: SessionManager,
                 booking_runner: BookingRunner):
        self.config = config_manager
        self.session_mgr = session_manager
        self.runner = booking_runner

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._cancel_booking = threading.Event()

        # Callbacks
        self.on_countdown_tick: Optional[Callable] = None
        self.on_booking_result: Optional[Callable] = None
        self.on_booking_start: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_idle: Optional[Callable] = None
        self.on_checkin_result: Optional[Callable] = None  # 新增：签到结果回调

        # Current state for status queries
        self._state_lock = threading.Lock()
        self._current_trigger: Optional[datetime] = None
        self._current_target: Optional[datetime] = None
        self._current_plan_ids: List[str] = []
        self._running = False
        # 新增：签到任务队列
        self._checkin_tasks: List[Dict[str, Any]] = []
        self._checkin_lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return self._running

    def get_status(self) -> Dict[str, Any]:
        """Get current engine status (thread-safe)."""
        with self._state_lock:
            return {
                "running": self._running,
                "trigger_time": self._current_trigger,
                "target_date": self._current_target,
                "plan_ids": list(self._current_plan_ids),
                "remaining_seconds": (
                    int((self._current_trigger - datetime.now()).total_seconds())
                    if self._current_trigger and self._current_trigger > datetime.now()
                    else None
                ),
            }

    def start(self):
        """Start the scheduler engine in a background thread."""
        with self._state_lock:
            if self._running:
                logger.warning("Engine already running")
                return

        self._stop_event.clear()
        self._cancel_booking.clear()
        with self._state_lock:
            self._running = True

        self._thread = threading.Thread(target=self._engine_loop, daemon=True, name="SchedulerEngine")
        self._thread.start()
        logger.info("Scheduler engine started")

    def stop(self):
        """Stop the engine (clean shutdown within ~1 second)."""
        with self._state_lock:
            if not self._running:
                return

        logger.info("Stopping scheduler engine...")
        self._stop_event.set()
        self._cancel_booking.set()
        self.runner.cancel()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        with self._state_lock:
            self._running = False
        logger.info("Scheduler engine stopped")

    def register_checkin(self, booking_id: str, begin_time: str, target_date: str,
                         plan_desc: str = ""):
        """注册一个签到任务

        Args:
            booking_id: 预约 ID
            begin_time: 预约开始时间 "HH:MM:SS"
            target_date: 预约日期 "YYYY-MM-DD"
            plan_desc: 方案描述（用于日志）
        """
        from seathunter.scheduler.checkin_runner import CheckInRunner, CHECKIN_ADVANCE_MINUTES

        # 计算签到窗口
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")
        hour, minute, second = (int(x) for x in begin_time.split(":"))
        begin_dt = date_obj.replace(hour=hour, minute=minute, second=second)
        window_start = begin_dt - timedelta(minutes=CHECKIN_ADVANCE_MINUTES)
        window_end = begin_dt + timedelta(minutes=CHECKIN_ADVANCE_MINUTES)

        task = {
            "booking_id": booking_id,
            "begin_time": begin_dt,
            "window_start": window_start,
            "window_end": window_end,
            "plan_desc": plan_desc,
        }

        with self._checkin_lock:
            self._checkin_tasks.append(task)

        logger.info("已注册签到任务: %s, 签到窗口 %s ~ %s",
                    plan_desc,
                    window_start.strftime("%H:%M"),
                    window_end.strftime("%H:%M"))

    def _process_pending_checkins(self):
        """处理待执行的签到任务（非阻塞，在引擎主循环中调用）"""
        from seathunter.scheduler.checkin_runner import CheckInRunner

        with self._checkin_lock:
            now = datetime.now()
            # 找到窗口内且未过期的任务
            ready_tasks = []
            remaining_tasks = []
            for task in self._checkin_tasks:
                if now > task["window_end"]:
                    # 已过期，丢弃
                    logger.info("签到任务已过期: %s", task["plan_desc"])
                    continue
                if now >= task["window_start"]:
                    ready_tasks.append(task)
                else:
                    remaining_tasks.append(task)
            self._checkin_tasks = remaining_tasks

        # 执行就绪的签到任务（在新线程中，不阻塞引擎）
        for task in ready_tasks:
            t = threading.Thread(
                target=self._execute_checkin,
                args=(task,),
                daemon=True,
                name=f"CheckIn-{task['booking_id'][:8]}"
            )
            t.start()

    def _execute_checkin(self, task: dict):
        """在独立线程中执行签到"""
        from seathunter.scheduler.checkin_runner import CheckInRunner

        checkin_runner = CheckInRunner(
            api_client=self.runner.api,
            interval=self.runner.interval,
            max_try_times=self.runner.max_try_times,
        )

        def on_result(success, message):
            if self.on_checkin_result:
                self.on_checkin_result(success, message, task["plan_desc"])

        logger.info("开始签到: %s (bookingId=%s)", task["plan_desc"], task["booking_id"])
        checkin_runner.run_checkin(
            booking_id=task["booking_id"],
            begin_time=task["begin_time"],
            on_result=on_result,
        )

    def _engine_loop(self):
        """Main engine loop running in background thread."""
        while not self._stop_event.is_set():
            try:
                schedules = self.config.get_schedules()
                plans_map = {p.id: p for p in self.config.get_plans()}

                # 收集所有调度的触发信息，按 (trigger_time, target_date) 分组
                now = datetime.now()
                all_triggers = []  # list of (trigger, target_date, plan_ids)
                for schedule in schedules:
                    result = schedule.next_trigger(now)
                    if result is not None:
                        all_triggers.append(result)

                if not all_triggers:
                    with self._state_lock:
                        self._current_trigger = None
                        self._current_target = None
                        self._current_plan_ids = []
                    if self.on_idle:
                        self.on_idle()
                    self._stop_event.wait(timeout=30.0)
                    continue

                # 按 (trigger_time, target_date) 分组合并 plan_ids
                grouped = {}  # (trigger, target_date) -> set of plan_ids
                for trigger, target_date, plan_ids in all_triggers:
                    key = (trigger, target_date.date())
                    if key not in grouped:
                        grouped[key] = (trigger, target_date, set())
                    grouped[key][2].update(plan_ids)

                # 找最早的触发时间
                earliest_key = min(grouped.keys(), key=lambda k: k[0])
                trigger_time, target_date, all_plan_ids = grouped[earliest_key]
                all_plan_ids = list(all_plan_ids)

                # Update state
                with self._state_lock:
                    self._current_trigger = trigger_time
                    self._current_target = target_date
                    self._current_plan_ids = all_plan_ids

                # Resolve plan objects
                active_plans = [plans_map[pid] for pid in all_plan_ids if pid in plans_map]
                if not active_plans:
                    logger.warning("No valid plans found for IDs: %s", all_plan_ids)
                    self._stop_event.wait(timeout=30.0)
                    continue

                plan_desc = ", ".join(f"{p.room_name}-{p.seats[0].seat_num}" for p in active_plans if p.seats)
                # 显示有多少个调度合并执行
                group_count = len(grouped[earliest_key][2])
                if group_count > 1:
                    plan_desc = f"[{group_count}个方案] " + plan_desc

                # Countdown phase (interruptible, 1-second ticks)
                while not self._stop_event.is_set():
                    now = datetime.now()
                    remaining = (trigger_time - now).total_seconds()
                    if remaining <= 0:
                        break
                    if self.on_countdown_tick:
                        self.on_countdown_tick(int(remaining), trigger_time, plan_desc)
                    self._stop_event.wait(timeout=1.0)

                if self._stop_event.is_set():
                    break

                # Booking phase - execute for each grouped trigger's plans
                logger.info("Trigger time reached (%d schedule(s)), booking for %s (%s)",
                           len(grouped),
                           target_date.strftime("%Y-%m-%d"),
                           WEEKDAY_NAMES[target_date.weekday()])

                if self.on_booking_start:
                    self.on_booking_start(target_date, all_plan_ids)

                def _on_result(result: BookingResult):
                    if self.on_booking_result:
                        self.on_booking_result(result)

                def _on_attempt(attempt_num, plan_idx):
                    pass  # Could add callback

                results = self.runner.run_booking(
                    plans=active_plans,
                    target_date=target_date,
                    on_result=_on_result,
                    on_attempt=_on_attempt,
                )

                # Log results
                for r in results:
                    if r.success:
                        logger.info("Booking result: %s", r)
                    else:
                        logger.warning("Booking result: %s", r)

                # 新增：预约成功后，检查是否需要执行签到任务
                self._process_pending_checkins()

                # After booking, loop back to find next trigger
                # Brief pause to avoid tight loop
                self._stop_event.wait(timeout=5.0)

            except Exception as e:
                logger.error("Engine loop error: %s", e, exc_info=True)
                if self.on_error:
                    self.on_error(e)
                self._stop_event.wait(timeout=10.0)

        with self._state_lock:
            self._running = False
