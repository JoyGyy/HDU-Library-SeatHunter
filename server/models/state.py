"""全局状态管理：AppState 持有所有核心组件实例。"""

from __future__ import annotations

import logging
from typing import Optional

from seathunter.api.client import ApiClient
from seathunter.api.room_cache import RoomCache
from seathunter.auth.friend_store import FriendStore
from seathunter.auth.session_manager import SessionManager
from seathunter.config.manager import ConfigManager
from seathunter.logging_.history import HistoryLogger
from seathunter.platform_.paths import get_config_path, get_data_dir, get_log_dir
from seathunter.scheduler.booking_runner import BookingRunner
from seathunter.scheduler.engine import SchedulerEngine
from seathunter.services.friend_service import FriendService

logger = logging.getLogger("seathunter.server")


class AppState:
    """单例式全局状态，持有所有核心组件。"""

    def __init__(self) -> None:
        # 配置（先加载，后续组件依赖配置）
        self.config: ConfigManager = ConfigManager(get_config_path())
        self.config.load()

        # 会话与存储
        self.session_mgr: SessionManager = SessionManager(self.config)
        self.history: HistoryLogger = HistoryLogger(get_log_dir())
        self.friend_store: FriendStore = FriendStore(
            get_config_path("friends.json")
        )
        self.friend_service: FriendService = FriendService(
            self.friend_store,
            self.config.get_api_base_url(),
        )

        # 登录后初始化的组件
        self.api_client: Optional[ApiClient] = None
        self.runner: Optional[BookingRunner] = None
        self.engine: Optional[SchedulerEngine] = None
        self.room_cache: Optional[RoomCache] = None

    # ── 生命周期 ────────────────────────────────────────

    def load_config(self) -> None:
        """重新加载配置文件。"""
        self.config.load()
        logger.info("配置已加载: %s", self.config.config_path)

    def init_after_login(self) -> None:
        """登录成功后初始化需要 session 的组件。"""
        # 清理之前的实例，避免重复初始化导致泄漏
        if self.engine:
            try:
                self.engine.stop()
            except Exception:
                pass
        if self.room_cache:
            try:
                self.room_cache.stop_background_refresh()
            except Exception:
                pass
        if self.runner:
            try:
                self.runner.cancel()
            except Exception:
                pass

        self.api_client = ApiClient(self.session_mgr)

        settings = self.config.get_settings()
        self.runner = BookingRunner(
            api_client=self.api_client,
            session_manager=self.session_mgr,
            interval=settings.get("interval", 5),
            max_try_times=settings.get("max_try_times", 10),
        )

        self.engine = SchedulerEngine(
            config_manager=self.config,
            session_manager=self.session_mgr,
            booking_runner=self.runner,
        )

        self.room_cache = RoomCache(self.api_client)
        self.room_cache.start_background_refresh()

        logger.info("登录后组件初始化完成")

    def shutdown(self) -> None:
        """关闭所有后台线程。"""
        if self.engine and self.engine.is_running:
            self.engine.stop()
        if self.room_cache:
            self.room_cache.stop_background_refresh()
        logger.info("AppState 已关闭")
