"""tkinter GUI for SeatHunter.

Provides a graphical interface as an alternative to the CLI.
All backend modules (config, auth, api, scheduler) are reused unchanged.
"""

from __future__ import annotations

import os
import logging
import re
import threading
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox

from seathunter.config.manager import ConfigManager
from seathunter.auth.session_manager import SessionManager, lookup_uid
from seathunter.auth.uid_store import UidStore
from seathunter.api.client import ApiClient
from seathunter.api.room_cache import RoomCache
from seathunter.scheduler.engine import SchedulerEngine
from seathunter.scheduler.booking_runner import BookingRunner
from seathunter.models.plan import Plan, SeatInfo
from seathunter.models.schedule import Schedule, DateMapping
from seathunter.models.booking_result import BookingResult
from seathunter.ui.display import format_countdown, WEEKDAY_NAMES
from seathunter.platform_.paths import get_app_dir, get_config_path
from seathunter.logging_.history import HistoryLogger

logger = logging.getLogger("seathunter.ui")


class GuiApp:
    """tkinter GUI main application for SeatHunter."""

    def __init__(self, root: tk.Tk, config_manager: ConfigManager,
                 session_manager: SessionManager, api_client: ApiClient,
                 room_cache: RoomCache):
        self.root = root
        self.config = config_manager
        self.session_mgr = session_manager
        self.api = api_client
        self.room_cache = room_cache

        # Create booking runner and scheduler engine
        settings = self.config.get_settings()
        self.runner = BookingRunner(
            api_client=self.api,
            session_manager=self.session_mgr,
            interval=settings["interval"],
            max_try_times=settings["max_try_times"],
        )
        self.engine = SchedulerEngine(
            config_manager=self.config,
            session_manager=self.session_mgr,
            booking_runner=self.runner,
        )
        self.history = HistoryLogger()

        # UID 记录存储
        self.uid_store = UidStore(get_config_path("uids.json"))

        # 好友存储与服务
        from seathunter.auth.friend_store import FriendStore
        from seathunter.services.friend_service import FriendService
        import os
        friend_store_path = os.path.join(os.path.dirname(self.config.config_path), "friends.json")
        self.friend_store = FriendStore(friend_store_path)
        self.friend_service = FriendService(self.friend_store, base_url=session_manager.base_url)

        # Engine callbacks
        self.engine.on_countdown_tick = self._on_countdown_tick
        self.engine.on_booking_result = self._on_booking_result
        self.engine.on_booking_start = self._on_booking_start
        self.engine.on_error = self._on_engine_error
        self.engine.on_checkin_result = self._on_checkin_result
        self.engine.on_friend_confirm = self._on_friend_confirm

        # Threading state
        self._booking_cancel = threading.Event()
        self._logged_in = False
        self._rooms_ready = False

        # Build GUI
        self._build_main_window()
        self._build_status_bar()
        self._build_tabs()

        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Start auto-login after GUI is shown
        self.root.after(200, self._auto_login)

    # ================================================================
    # GUI Building
    # ================================================================

    def _build_main_window(self):
        self.root.title("SeatHunter v2.0")
        self.root.geometry("900x650")
        self.root.minsize(800, 550)
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - 900) // 2
        y = (sh - 650) // 2
        self.root.geometry(f"900x650+{x}+{y}")

    def _build_status_bar(self):
        self.status_bar = ttk.Label(
            self.root, text="就绪", relief=tk.SUNKEN, anchor=tk.W, padding=(5, 2),
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))

        self._build_home_tab()         # Tab 0: 首页
        self._build_booking_tab()      # Tab 1: 预约（一体化）
        self._build_friends_tab()      # Tab 2: 好友
        self._build_settings_tab()     # Tab 3: 设置

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, event=None):
        idx = self.notebook.index(self.notebook.select())
        if idx == 1:
            self._refresh_plans_tree()

    # ─── 好友业务逻辑 ──────────────────────────────────────────

    def _refresh_friends_tree(self):
        """刷新好友列表 Treeview"""
        for item in self.friends_tree.get_children():
            self.friends_tree.delete(item)
        friends = self.friend_store.get_all()
        for sid, info in friends.items():
            self.friends_tree.insert("", tk.END, values=(
                sid, info.get("name", ""), info.get("uid", ""),
            ))

    def _add_friend(self):
        """添加好友：用 lookup_uid 查询，成功后存入 friend_store"""
        sid = self._friend_sid_entry.get().strip()
        pwd = self._friend_pwd_entry.get().strip()
        if not sid or not pwd:
            messagebox.showwarning("提示", "请输入学号和密码")
            return

        self._add_friend_btn.config(state=tk.DISABLED)
        self.status_bar.config(text="正在查询好友信息...")

        def worker():
            success, uid, name = lookup_uid(
                username=sid, password=pwd,
                base_url=self.session_mgr.base_url,
            )
            self.root.after(0, self._on_friend_lookup_done, success, uid, name, sid, pwd)

        threading.Thread(target=worker, daemon=True).start()

    def _on_friend_lookup_done(self, success, uid, name, sid, pwd):
        """lookup_uid 完成后的回调"""
        self._add_friend_btn.config(state=tk.NORMAL)
        if success:
            self.friend_store.add(sid, uid, name, pwd)
            self._on_friend_added(sid, name, uid)
        else:
            err = name  # 失败时 name 参数存放错误信息
            self.status_bar.config(text="好友查询失败")
            messagebox.showerror("添加失败", f"查询失败: {err}")

    def _on_friend_added(self, sid, name, uid):
        """添加成功后的 UI 更新"""
        self.status_bar.config(text=f"好友 {name} 添加成功")
        messagebox.showinfo("成功", f"好友添加成功\n学号: {sid}\n姓名: {name}\nUID: {uid}")
        self._refresh_friends_tree()
        self._friend_sid_entry.delete(0, tk.END)
        self._friend_pwd_entry.delete(0, tk.END)

    def _delete_selected_friend(self):
        """删除选中的好友"""
        selected = self.friends_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要删除的好友")
            return
        sids = [self.friends_tree.item(item, "values")[0] for item in selected]
        if not messagebox.askyesno("确认", f"确定要删除 {len(sids)} 个好友吗？"):
            return
        for sid in sids:
            self.friend_store.remove(sid)
        self._refresh_friends_tree()

    def _test_friend_login(self):
        """测试选中好友的登录"""
        selected = self.friends_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要测试的好友")
            return
        if len(selected) > 1:
            messagebox.showinfo("提示", "请只选择一个好友进行测试")
            return
        sid = self.friends_tree.item(selected[0], "values")[0]
        self.status_bar.config(text=f"正在测试好友 {sid} 的登录...")

        def worker():
            ok, msg = self.friend_service.test_login(sid)
            self.root.after(0, self._on_friend_test_done, ok, msg, sid)

        threading.Thread(target=worker, daemon=True).start()

    def _on_friend_test_done(self, success, msg, sid):
        """测试登录完成后的回调"""
        if success:
            self.status_bar.config(text=f"好友 {sid} 登录测试成功")
            messagebox.showinfo("测试结果", msg)
        else:
            self.status_bar.config(text=f"好友 {sid} 登录测试失败")
            messagebox.showerror("测试结果", msg)

    # ─── Tab 0: 预约 ─────────────────────────────────────────

    def _build_booking_tab(self):
        """Tab 1: 预约（一体化）— 方案管理 + 调度引擎 + 签到 + 预约日志"""
        frame = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(frame, text="预约")

        # ── 上半部分：方案管理 ──
        plans_frame = ttk.LabelFrame(frame, text="方案管理", padding=3)
        plans_frame.pack(fill=tk.BOTH, expand=True)

        tree_frame = ttk.Frame(plans_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("idx", "plan_id", "room", "floor", "seats", "time", "duration", "bookers")
        self.plans_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=5,
        )
        for col, text, width in [
            ("idx", "序号", 50), ("plan_id", "方案ID", 130),
            ("room", "房间名", 130), ("floor", "楼层", 80),
            ("seats", "座位号", 100), ("time", "开始时间", 100),
            ("duration", "时长", 60), ("bookers", "预约人", 120),
        ]:
            self.plans_tree.heading(col, text=text)
            self.plans_tree.column(col, width=width, anchor=tk.CENTER if col in ("idx", "time", "duration") else tk.W)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.plans_tree.yview)
        self.plans_tree.configure(yscrollcommand=scrollbar.set)
        self.plans_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(plans_frame)
        btn_frame.pack(fill=tk.X, pady=(3, 0))
        ttk.Button(btn_frame, text="添加方案", command=self._add_plan_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除选中", command=self._delete_selected_plans).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="批量修改时间", command=self._batch_change_time_dialog).pack(side=tk.LEFT, padx=2)

        # ── 中部：调度引擎 + 签到（左右分区）──
        mid_frame = ttk.Frame(frame)
        mid_frame.pack(fill=tk.X, pady=(5, 0))

        # 左侧：调度引擎
        sched_frame = ttk.LabelFrame(mid_frame, text="调度引擎", padding=3)
        sched_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sched_btn_frame = ttk.Frame(sched_frame)
        sched_btn_frame.pack(fill=tk.X, pady=(0, 3))

        self.scheduler_start_btn = ttk.Button(sched_btn_frame, text="启动调度", command=self._start_scheduler)
        self.scheduler_start_btn.pack(side=tk.LEFT, padx=2)
        self.scheduler_stop_btn = ttk.Button(sched_btn_frame, text="停止调度", command=self._stop_scheduler)
        self.scheduler_stop_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(sched_btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(sched_btn_frame, text="添加按星期调度", command=self._add_weekday_schedule_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(sched_btn_frame, text="添加按日期调度", command=self._add_date_schedule_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(sched_btn_frame, text="切换启用", command=self._toggle_schedule_enabled).pack(side=tk.LEFT, padx=2)
        ttk.Button(sched_btn_frame, text="删除选中", command=self._delete_selected_schedules).pack(side=tk.LEFT, padx=2)

        self.scheduler_status_label = tk.Label(sched_btn_frame, text="● 调度未运行", fg="red", font=("", 10))
        self.scheduler_status_label.pack(side=tk.RIGHT, padx=10)

        sched_tree_frame = ttk.Frame(sched_frame)
        sched_tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("idx", "type", "target", "status", "plans")
        self.schedules_tree = ttk.Treeview(sched_tree_frame, columns=cols, show="headings", height=5)
        for col, text, w in [
            ("idx", "序号", 50), ("type", "类型", 80),
            ("target", "目标", 200), ("status", "状态", 60),
            ("plans", "绑定方案", 300),
        ]:
            self.schedules_tree.heading(col, text=text)
            self.schedules_tree.column(col, width=w, anchor=tk.CENTER if col in ("idx", "status") else tk.W)

        self.schedules_tree.tag_configure("enabled", foreground="black")
        self.schedules_tree.tag_configure("disabled", foreground="gray")

        sb = ttk.Scrollbar(sched_tree_frame, orient=tk.VERTICAL, command=self.schedules_tree.yview)
        self.schedules_tree.configure(yscrollcommand=sb.set)
        self.schedules_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # 右侧：引擎状态 + 签到
        right_frame = ttk.Frame(mid_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        status_frame = ttk.LabelFrame(right_frame, text="引擎状态", padding=5)
        status_frame.pack(fill=tk.X)

        self.status_labels = {}
        for i, (key, label_text) in enumerate([
            ("engine", "引擎"),
            ("trigger", "下次触发"),
            ("remaining", "剩余时间"),
            ("plans", "目标方案"),
        ]):
            ttk.Label(status_frame, text=f"{label_text}:", font=("", 9, "bold")).grid(row=i, column=0, sticky=tk.W, pady=2)
            lbl = ttk.Label(status_frame, text="—", font=("", 9))
            lbl.grid(row=i, column=1, sticky=tk.W, padx=(10, 0), pady=2)
            self.status_labels[key] = lbl

        checkin_frame = ttk.LabelFrame(right_frame, text="手动签到", padding=5)
        checkin_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Label(checkin_frame, text="bookingId:").pack(anchor=tk.W)
        self._checkin_entry = ttk.Entry(checkin_frame, width=20)
        self._checkin_entry.pack(fill=tk.X, pady=2)

        checkin_btn_row = ttk.Frame(checkin_frame)
        checkin_btn_row.pack(fill=tk.X, pady=2)
        ttk.Button(checkin_btn_row, text="签到", command=self._manual_checkin_from_entry).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(checkin_btn_row, text="从历史选择", command=self._pick_booking_from_history).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        checkin_btn_row2 = ttk.Frame(checkin_frame)
        checkin_btn_row2.pack(fill=tk.X, pady=(2, 0))
        ttk.Button(checkin_btn_row2, text="获取当前预约", command=self._fetch_current_bookings).pack(fill=tk.X)

        self._checkin_result_label = ttk.Label(checkin_frame, text="", foreground="gray", wraplength=150)
        self._checkin_result_label.pack(fill=tk.X, pady=(5, 0))

        # ── 底部：预约日志 ──
        log_frame = ttk.LabelFrame(frame, text="预约日志", padding=3)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        self.booking_log = tk.Text(log_frame, state=tk.DISABLED, wrap=tk.WORD, height=6, font=("Consolas", 9))
        self.booking_log.tag_configure("success", foreground="green")
        self.booking_log.tag_configure("error", foreground="red")
        self.booking_log.tag_configure("info", foreground="#0066cc")
        self.booking_log.tag_configure("warning", foreground="#cc6600")

        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.pack(fill=tk.X, pady=(2, 0))
        ttk.Button(log_btn_frame, text="清空日志", command=self._clear_booking_log).pack(side=tk.RIGHT)
        self.booking_progress_label = ttk.Label(log_btn_frame, text="")
        self.booking_progress_label.pack(side=tk.LEFT, padx=5)
        self.booking_start_btn = ttk.Button(log_btn_frame, text="开始抢座", command=self._start_booking)
        self.booking_start_btn.pack(side=tk.RIGHT, padx=2)
        self.booking_stop_btn = ttk.Button(log_btn_frame, text="停止", command=self._cancel_booking, state=tk.DISABLED)
        self.booking_stop_btn.pack(side=tk.RIGHT, padx=2)

        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.booking_log.yview)
        self.booking_log.configure(yscrollcommand=log_scroll.set)
        self.booking_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._refresh_plans_tree()
        self._refresh_schedules_tree()
        self._update_status_display()

    # ─── Tab 0: 首页 — 新手引导 / 仪表盘 ────────────────────────

    def _build_home_tab(self):
        """Tab 0: 首页 — 新手引导 / 仪表盘"""
        self._home_frame = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(self._home_frame, text="首页")

        # 内容区域（由引导或仪表盘填充）
        self._home_content = ttk.Frame(self._home_frame)
        self._home_content.pack(fill=tk.BOTH, expand=True)

        # 判断是否首次使用
        is_first_time = not self.session_mgr.uid or len(self.config.get_plans()) == 0
        if is_first_time:
            self._wizard_step = 0
            self._show_wizard()
        else:
            self._show_dashboard()

    # ─── 新手引导 ─────────────────────────────────────────────

    def _show_wizard(self):
        """显示新手引导（4 步）"""
        # 清空内容区
        for w in self._home_content.winfo_children():
            w.destroy()

        # 步骤指示器
        indicator = ttk.Frame(self._home_content)
        indicator.pack(fill=tk.X, pady=(0, 10))
        step_names = ["登录", "添加好友", "创建方案", "设置调度"]
        for i, name in enumerate(step_names):
            if i == self._wizard_step:
                ttk.Label(indicator, text=f" [{i + 1}. {name}] ",
                          font=("", 10, "bold"), foreground="#0066cc").pack(side=tk.LEFT, padx=2)
            else:
                ttk.Label(indicator, text=f" {i + 1}. {name} ",
                          font=("", 10), foreground="gray").pack(side=tk.LEFT, padx=2)

        ttk.Separator(self._home_content, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 10))

        # 步骤内容区域
        self._wizard_body = ttk.Frame(self._home_content)
        self._wizard_body.pack(fill=tk.BOTH, expand=True)

        self._update_wizard_step()

    def _update_wizard_step(self):
        """根据当前步骤号显示对应内容"""
        for w in self._wizard_body.winfo_children():
            w.destroy()

        if self._wizard_step == 0:
            self._wizard_step_login()
        elif self._wizard_step == 1:
            self._wizard_step_friends()
        elif self._wizard_step == 2:
            self._wizard_step_plans()
        elif self._wizard_step == 3:
            self._wizard_step_scheduler()

    def _wizard_nav_buttons(self, parent, show_skip=True, next_text="下一步"):
        """在引导步骤底部添加导航按钮"""
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(15, 0))

        if show_skip:
            ttk.Button(btn_frame, text="跳过",
                       command=self._wizard_skip).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=next_text,
                   command=self._wizard_next).pack(side=tk.RIGHT, padx=5)

    def _wizard_skip(self):
        """跳过当前步骤"""
        self._wizard_step += 1
        if self._wizard_step >= 4:
            self._wizard_finish()
        else:
            self._update_wizard_step()

    def _wizard_next(self):
        """进入下一步"""
        self._wizard_step += 1
        if self._wizard_step >= 4:
            self._wizard_finish()
        else:
            self._update_wizard_step()

    def _wizard_finish(self):
        """引导完成，切换到仪表盘"""
        self._show_dashboard()

    # ─── 引导 Step 1: 登录 ────────────────────────────────────

    def _wizard_step_login(self):
        body = self._wizard_body

        ttk.Label(body, text="第 1 步：登录你的图书馆账号",
                  font=("", 13, "bold")).pack(anchor=tk.W, pady=(0, 10))

        if self.session_mgr.uid:
            # 已登录
            ttk.Label(body, text=f"已登录: {self.session_mgr.name} ({self.session_mgr.uid})",
                      font=("", 11), foreground="green").pack(anchor=tk.W, pady=5)
            self._wizard_nav_buttons(body, show_skip=False)
            return

        # 未登录 — 显示输入框
        user = self.config.get_user_info()

        ttk.Label(body, text="学号:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self._wiz_login_sid = tk.StringVar(value=user.get("login_name", ""))
        ttk.Entry(body, textvariable=self._wiz_login_sid, width=25).grid(row=0, column=1, pady=5)

        ttk.Label(body, text="密码:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self._wiz_login_pwd = tk.StringVar(value=user.get("password", ""))
        ttk.Entry(body, textvariable=self._wiz_login_pwd, width=25, show="*").grid(row=1, column=1, pady=5)

        self._wiz_login_status = ttk.Label(body, text="", foreground="blue")
        self._wiz_login_status.grid(row=2, column=0, columnspan=2, pady=5)

        ttk.Button(body, text="登录", command=self._wizard_do_login).grid(
            row=3, column=0, columnspan=2, pady=10,
        )

    def _wizard_do_login(self):
        sid = self._wiz_login_sid.get().strip()
        pwd = self._wiz_login_pwd.get().strip()
        if not sid or not pwd:
            self._wiz_login_status.config(text="请输入学号和密码", foreground="red")
            return

        self._wiz_login_status.config(text="登录中...", foreground="blue")
        self.config.update_user_info(login_name=sid, password=pwd)

        def worker():
            success, err_type = self.session_mgr.login()
            self.root.after(0, self._wizard_on_login_done, success, err_type)

        threading.Thread(target=worker, daemon=True).start()

    def _wizard_on_login_done(self, success, err_type):
        if success:
            self._logged_in = True
            self.config.save()
            self.room_cache.on_ready(self._on_rooms_ready)
            self.room_cache.start_background_refresh()
            # 自动进入下一步
            self._wizard_step += 1
            self._update_wizard_step()
        else:
            msg = "网络连接失败" if err_type == "network" else (
                self.session_mgr.last_error or "账号密码错误")
            self._wiz_login_status.config(text=f"登录失败: {msg}", foreground="red")

    # ─── 引导 Step 2: 添加好友 ────────────────────────────────

    def _wizard_step_friends(self):
        body = self._wizard_body

        ttk.Label(body, text="第 2 步：添加好友（可选）",
                  font=("", 13, "bold")).pack(anchor=tk.W, pady=(0, 5))
        ttk.Label(body, text="添加好友后，预约时可自动帮好友确认。",
                  foreground="gray").pack(anchor=tk.W, pady=(0, 10))

        form = ttk.Frame(body)
        form.pack(anchor=tk.W)

        ttk.Label(form, text="好友学号:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self._wiz_friend_sid = tk.StringVar()
        ttk.Entry(form, textvariable=self._wiz_friend_sid, width=25).grid(row=0, column=1, padx=5, pady=4)

        ttk.Label(form, text="好友密码:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self._wiz_friend_pwd = tk.StringVar()
        ttk.Entry(form, textvariable=self._wiz_friend_pwd, width=25, show="*").grid(row=1, column=1, padx=5, pady=4)

        self._wiz_friend_status = ttk.Label(body, text="", foreground="blue")
        self._wiz_friend_status.pack(anchor=tk.W, pady=5)

        self._wiz_friend_btn = ttk.Button(body, text="查询并添加", command=self._wizard_do_add_friend)
        self._wiz_friend_btn.pack(anchor=tk.W, pady=5)

        # 显示已有好友
        friends = self.friend_store.get_all()
        if friends:
            ttk.Label(body, text=f"已添加 {len(friends)} 位好友",
                      foreground="green").pack(anchor=tk.W, pady=(10, 0))

        self._wizard_nav_buttons(body, show_skip=True)

    def _wizard_do_add_friend(self):
        sid = self._wiz_friend_sid.get().strip()
        pwd = self._wiz_friend_pwd.get().strip()
        if not sid or not pwd:
            self._wiz_friend_status.config(text="请输入学号和密码", foreground="red")
            return

        self._wiz_friend_btn.config(state=tk.DISABLED)
        self._wiz_friend_status.config(text="查询中...", foreground="blue")

        def worker():
            success, uid, name = lookup_uid(
                username=sid, password=pwd,
                base_url=self.session_mgr.base_url,
            )
            self.root.after(0, self._wizard_on_friend_lookup, success, uid, name, sid, pwd)

        threading.Thread(target=worker, daemon=True).start()

    def _wizard_on_friend_lookup(self, success, uid, name, sid, pwd):
        self._wiz_friend_btn.config(state=tk.NORMAL)
        if success:
            self.friend_store.add(sid, uid, name, pwd)
            self._wiz_friend_status.config(text=f"添加成功: {name} (UID: {uid})", foreground="green")
            self._wiz_friend_sid.set("")
            self._wiz_friend_pwd.set("")
        else:
            err = name  # 失败时 name 存放错误信息
            self._wiz_friend_status.config(text=f"查询失败: {err}", foreground="red")

    # ─── 引导 Step 3: 创建方案 ────────────────────────────────

    def _wizard_step_plans(self):
        body = self._wizard_body

        ttk.Label(body, text="第 3 步：创建预约方案（可选）",
                  font=("", 13, "bold")).pack(anchor=tk.W, pady=(0, 5))
        ttk.Label(body, text="预约方案用于指定房间、座位、时间等信息。\n你也可以稍后在「预约」标签页中添加。",
                  foreground="gray").pack(anchor=tk.W, pady=(0, 10))

        ttk.Button(body, text="添加方案", command=self._add_plan_dialog).pack(anchor=tk.W, pady=5)

        plans = self.config.get_plans()
        if plans:
            ttk.Label(body, text=f"已创建 {len(plans)} 个方案",
                      foreground="green").pack(anchor=tk.W, pady=(10, 0))

        self._wizard_nav_buttons(body, show_skip=True)

    # ─── 引导 Step 4: 设置调度 ────────────────────────────────

    def _wizard_step_scheduler(self):
        body = self._wizard_body

        ttk.Label(body, text="第 4 步：设置调度（可选）",
                  font=("", 13, "bold")).pack(anchor=tk.W, pady=(0, 5))
        ttk.Label(body, text=(
            "调度功能可以在指定时间自动执行预约，无需手动操作。\n\n"
            "调度配置请前往「预约」标签页：\n"
            "  1. 确保已创建预约方案\n"
            "  2. 添加按星期或按日期的调度规则\n"
            "  3. 点击「启动调度」即可"
        ), foreground="gray", wraplength=500, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 10))

        ttk.Button(body, text="前往预约页",
                   command=lambda: self.notebook.select(1)).pack(anchor=tk.W, pady=5)

        self._wizard_nav_buttons(body, show_skip=False, next_text="完成")

    # ─── 日常仪表盘 ───────────────────────────────────────────

    def _show_dashboard(self):
        """显示日常仪表盘"""
        # 清空内容区
        for w in self._home_content.winfo_children():
            w.destroy()

        # ── 顶部：状态区 ──
        status_frame = ttk.LabelFrame(self._home_content, text="状态", padding=10)
        status_frame.pack(fill=tk.X, pady=(0, 8))

        row0 = ttk.Frame(status_frame)
        row0.pack(fill=tk.X, pady=2)
        ttk.Label(row0, text="登录状态:", font=("", 10, "bold")).pack(side=tk.LEFT)
        self._dash_login_label = ttk.Label(row0, text="—", font=("", 10))
        self._dash_login_label.pack(side=tk.LEFT, padx=(10, 0))

        row1 = ttk.Frame(status_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="调度引擎:", font=("", 10, "bold")).pack(side=tk.LEFT)
        self._dash_engine_label = ttk.Label(row1, text="—", font=("", 10))
        self._dash_engine_label.pack(side=tk.LEFT, padx=(10, 0))

        # ── 中部：今日预约区 ──
        bookings_frame = ttk.LabelFrame(self._home_content, text="今日预约", padding=5)
        bookings_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self._dash_bookings_text = tk.Text(
            bookings_frame, state=tk.DISABLED, wrap=tk.WORD,
            height=8, font=("Consolas", 9),
        )
        self._dash_bookings_text.tag_configure("success", foreground="green")
        self._dash_bookings_text.tag_configure("error", foreground="red")
        self._dash_bookings_text.tag_configure("info", foreground="#0066cc")

        sb = ttk.Scrollbar(bookings_frame, orient=tk.VERTICAL, command=self._dash_bookings_text.yview)
        self._dash_bookings_text.configure(yscrollcommand=sb.set)
        self._dash_bookings_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── 底部：快捷操作 ──
        action_frame = ttk.Frame(self._home_content)
        action_frame.pack(fill=tk.X)
        ttk.Button(action_frame, text="获取当前预约",
                   command=self._fetch_current_bookings).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="启动调度",
                   command=self._start_scheduler).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="停止调度",
                   command=self._stop_scheduler).pack(side=tk.LEFT, padx=5)

        # 初始刷新 + 启动定时刷新
        self._refresh_dashboard()

    def _refresh_dashboard(self):
        """刷新仪表盘数据（每 5 秒）"""
        try:
            if not self._home_content.winfo_exists():
                return

            # 更新登录状态
            if self.session_mgr.uid:
                self._dash_login_label.config(
                    text=f"已登录: {self.session_mgr.name or self.session_mgr.uid}",
                    foreground="green",
                )
            else:
                self._dash_login_label.config(text="未登录", foreground="red")

            # 更新引擎状态
            status = self.engine.get_status()
            if status["running"]:
                remaining = status.get("remaining_seconds")
                trigger = status.get("trigger_time")
                trigger_str = trigger.strftime("%m-%d %H:%M") if trigger else "—"
                remaining_str = format_countdown(remaining) if remaining is not None else "—"
                plans_str = ", ".join(status.get("plan_ids", [])) or "—"
                self._dash_engine_label.config(
                    text=f"运行中 | 下次触发: {trigger_str} | 剩余: {remaining_str} | 方案: {plans_str}",
                    foreground="green",
                )
            else:
                self._dash_engine_label.config(text="未运行", foreground="gray")

            # 更新今日预约（从日志中读取最近记录）
            self._dash_bookings_text.config(state=tk.NORMAL)
            self._dash_bookings_text.delete("1.0", tk.END)
            records = self.history.query(10)
            if records:
                for r in records:
                    result_str = "成功" if r.get("success") else "失败"
                    tag = "success" if r.get("success") else "error"
                    ts = r.get("timestamp", "")
                    plan_id = r.get("plan_id", "")
                    msg = r.get("message", "")
                    self._dash_bookings_text.insert(
                        tk.END, f"[{ts}] {plan_id} — {result_str}: {msg}\n", tag,
                    )
            else:
                self._dash_bookings_text.insert(tk.END, "暂无预约记录", "info")
            self._dash_bookings_text.config(state=tk.DISABLED)

            # 5 秒后再次刷新
            self.root.after(5000, self._refresh_dashboard)
        except tk.TclError:
            pass  # 控件已销毁

    # ─── Tab 2: 好友 ────────────────────────────────────────────

    def _build_friends_tab(self):
        """Tab 2: 好友管理 — 好友列表 + 添加好友"""
        frame = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(frame, text="好友")

        # ── 上半部分：好友列表 ──
        list_frame = ttk.LabelFrame(frame, text="好友列表", padding=3)
        list_frame.pack(fill=tk.BOTH, expand=True)

        tree_frame = ttk.Frame(list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("student_id", "name", "uid")
        self.friends_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=6,
        )
        for col, text, width in [
            ("student_id", "学号", 150),
            ("name", "姓名", 120),
            ("uid", "UID", 200),
        ]:
            self.friends_tree.heading(col, text=text)
            self.friends_tree.column(col, width=width, anchor=tk.W)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.friends_tree.yview)
        self.friends_tree.configure(yscrollcommand=scrollbar.set)
        self.friends_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=(3, 0))
        ttk.Button(btn_frame, text="删除选中", command=self._delete_selected_friend).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="测试登录", command=self._test_friend_login).pack(side=tk.LEFT, padx=2)

        # ── 下半部分：添加好友 ──
        add_frame = ttk.LabelFrame(frame, text="添加好友", padding=5)
        add_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Label(add_frame, text="学号:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self._friend_sid_entry = ttk.Entry(add_frame, width=25)
        self._friend_sid_entry.grid(row=0, column=1, padx=5, pady=4)

        ttk.Label(add_frame, text="密码:").grid(row=0, column=2, sticky=tk.W, pady=4, padx=(10, 0))
        self._friend_pwd_entry = ttk.Entry(add_frame, width=25, show="*")
        self._friend_pwd_entry.grid(row=0, column=3, padx=5, pady=4)

        self._add_friend_btn = ttk.Button(add_frame, text="查询并添加", command=self._add_friend)
        self._add_friend_btn.grid(row=0, column=4, padx=5, pady=4)

        self._refresh_friends_tree()

    # ─── Tab 3: 设置 ────────────────────────────────────────────

    def _build_settings_tab(self):
        """Tab 3: 设置 — 账号 + 请求参数 + 帮助"""
        frame = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(frame, text="设置")

        # 账号信息
        account_frame = ttk.LabelFrame(frame, text="账号信息", padding=15)
        account_frame.pack(fill=tk.X, pady=(0, 10))

        self.account_labels = {}
        for i, (key, label_text) in enumerate([
            ("login_name", "学号"),
            ("name", "姓名"),
        ]):
            ttk.Label(account_frame, text=f"{label_text}:", font=("", 10, "bold")).grid(row=i, column=0, sticky=tk.W, pady=4)
            lbl = ttk.Label(account_frame, text="—", font=("", 10))
            lbl.grid(row=i, column=1, sticky=tk.W, padx=(15, 0), pady=4)
            self.account_labels[key] = lbl

        ttk.Button(account_frame, text="重新登录", command=self._relogin).grid(row=2, column=0, columnspan=2, pady=(8, 0))

        # 请求设置
        s_frame = ttk.LabelFrame(frame, text="请求设置", padding=15)
        s_frame.pack(fill=tk.X)

        ttk.Label(s_frame, text="重试间隔（秒）:").grid(row=0, column=0, sticky=tk.W, pady=8)
        self.interval_var = tk.StringVar()
        self.interval_entry = ttk.Spinbox(s_frame, from_=1, to=300, textvariable=self.interval_var, width=10)
        self.interval_entry.grid(row=0, column=1, padx=10, pady=8)
        ttk.Label(s_frame, text="建议不小于5").grid(row=0, column=2, sticky=tk.W)

        ttk.Label(s_frame, text="最大重试次数:").grid(row=1, column=0, sticky=tk.W, pady=8)
        self.max_try_var = tk.StringVar()
        self.max_try_entry = ttk.Spinbox(s_frame, from_=1, to=999, textvariable=self.max_try_var, width=10)
        self.max_try_entry.grid(row=1, column=1, padx=10, pady=8)

        ttk.Button(frame, text="保存设置", command=self._save_settings).pack(pady=10)

        # 帮助
        help_frame = ttk.LabelFrame(frame, text="帮助", padding=5)
        help_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        help_text = tk.Text(help_frame, wrap=tk.WORD, state=tk.DISABLED, height=8)
        help_text.pack(fill=tk.BOTH, expand=True)
        help_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "docs", "help.md")
        if os.path.exists(help_path):
            with open(help_path, "r", encoding="utf-8") as f:
                content = f.read()
            help_text.config(state=tk.NORMAL)
            help_text.insert(tk.END, content)
            help_text.config(state=tk.DISABLED)

        self._load_settings()
        self._update_account_display()

    # ================================================================
    # Login
    # ================================================================

    def _auto_login(self):
        user = self.config.get_user_info()
        if user.get("login_name") and user.get("password"):
            self._start_login_thread(None, None)
        else:
            self._show_login_dialog()

    def _show_login_dialog(self, error_msg: str = None):
        dlg = tk.Toplevel(self.root)
        dlg.title("登录")
        dlg.geometry("380x220")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        # Center on parent
        dlg.update_idletasks()
        px = self.root.winfo_x() + (self.root.winfo_width() - 380) // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - 220) // 2
        dlg.geometry(f"+{px}+{py}")

        frame = ttk.Frame(dlg, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        user = self.config.get_user_info()

        ttk.Label(frame, text="学号:").grid(row=0, column=0, sticky=tk.W, pady=5)
        login_var = tk.StringVar(value=user.get("login_name", ""))
        ttk.Entry(frame, textvariable=login_var, width=25).grid(row=0, column=1, pady=5)

        ttk.Label(frame, text="密码:").grid(row=1, column=0, sticky=tk.W, pady=5)
        pwd_var = tk.StringVar(value=user.get("password", ""))
        ttk.Entry(frame, textvariable=pwd_var, width=25, show="*").grid(row=1, column=1, pady=5)

        status_label = ttk.Label(frame, text=error_msg or "", foreground="red")
        status_label.grid(row=2, column=0, columnspan=2, pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)

        login_btn = ttk.Button(
            btn_frame, text="登录",
            command=lambda: self._dialog_login(dlg, login_var, pwd_var, status_label),
        )
        # Store reference so login callback can update it directly
        dlg._status_label = status_label
        login_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(
            btn_frame, text="退出", command=lambda: self._exit_from_dialog(dlg),
        ).pack(side=tk.LEFT, padx=5)

        dlg.protocol("WM_DELETE_WINDOW", lambda: self._exit_from_dialog(dlg))

    def _dialog_login(self, dlg, login_var, pwd_var, status_label):
        login_name = login_var.get().strip()
        password = pwd_var.get().strip()
        if not login_name or not password:
            status_label.config(text="请输入学号和密码")
            return
        status_label.config(text="登录中...", foreground="blue")
        dlg.update_idletasks()
        self._start_login_thread(dlg, (login_name, password))

    def _start_login_thread(self, dlg, credentials):
        def worker():
            if credentials:
                login_name, password = credentials
                self.config.update_user_info(login_name=login_name, password=password)
            success, err_type = self.session_mgr.login()
            self.root.after(0, self._login_callback, success, err_type, dlg)

        threading.Thread(target=worker, daemon=True).start()

    def _login_callback(self, success, err_type, dlg):
        if success:
            self._logged_in = True
            self.config.save()
            self.status_bar.config(text="登录成功")
            if dlg and dlg.winfo_exists():
                dlg.destroy()
            # 更新用户信息显示
            self._update_account_display()
            self._update_user_info()
            # Start room data refresh
            self.room_cache.on_ready(self._on_rooms_ready)
            self.room_cache.start_background_refresh()
        else:
            if err_type == "network":
                msg = "网络连接失败，请检查校园网连接"
            else:
                err_detail = self.session_mgr.last_error
                msg = err_detail if err_detail else "账号密码错误，请重新输入"
            if dlg and dlg.winfo_exists():
                dlg._status_label.config(text=msg, foreground="red")
            else:
                self._show_login_dialog(msg)

    def _on_rooms_ready(self):
        self._rooms_ready = True
        self.root.after(0, self._refresh_plans_tree)

    def _exit_from_dialog(self, dlg):
        dlg.destroy()
        self._on_closing()

    # ================================================================
    # Plans Management
    # ================================================================

    def _refresh_plans_tree(self):
        for item in self.plans_tree.get_children():
            self.plans_tree.delete(item)
        plans = self.config.get_plans()
        for i, plan in enumerate(plans):
            seats_str = ",".join(
                f"{s.seat_num}({s.booker_uid})" if s.booker_uid else s.seat_num
                for s in plan.seats
            )
            # 计算预约人显示
            booker_names = []
            for s in plan.seats:
                if s.booker_uid and s.booker_uid != self.session_mgr.uid:
                    matched = False
                    for sid, info in self.friend_store.get_all().items():
                        if info["uid"] == s.booker_uid:
                            booker_names.append(info["name"])
                            matched = True
                            break
                    if not matched:
                        booker_names.append(f"UID:{s.booker_uid[:6]}")
                else:
                    booker_names.append("我")
            bookers_str = "+".join(booker_names)
            self.plans_tree.insert("", tk.END, iid=str(i), values=(
                i + 1, plan.id, plan.room_name, plan.floor_name,
                seats_str, plan.begin_time, f"{plan.duration_hours}小时", bookers_str,
            ))

    def _add_plan_dialog(self):
        if not self._rooms_ready:
            messagebox.showwarning("提示", "房间数据尚未加载完成，请稍后再试")
            return

        rooms = self.room_cache.rooms
        if not rooms:
            messagebox.showerror("错误", "无法获取房间信息，请检查网络连接")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("添加方案")
        dlg.geometry("500x460")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center_on_parent(dlg, 500, 460)

        frame = ttk.Frame(dlg, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        room_names = list(rooms.keys())

        # Room
        ttk.Label(frame, text="房间类型:").grid(row=0, column=0, sticky=tk.W, pady=4)
        room_var = tk.StringVar()
        room_combo = ttk.Combobox(frame, textvariable=room_var, values=room_names, state="readonly", width=22)
        room_combo.grid(row=0, column=1, pady=4)

        # Floor
        ttk.Label(frame, text="楼层:").grid(row=1, column=0, sticky=tk.W, pady=4)
        floor_var = tk.StringVar()
        floor_combo = ttk.Combobox(frame, textvariable=floor_var, state="readonly", width=22)
        floor_combo.grid(row=1, column=1, pady=4)

        # Hours hint
        hours_label = ttk.Label(frame, text="", foreground="gray")
        hours_label.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=2)

        # Date
        ttk.Label(frame, text="目标日期:").grid(row=3, column=0, sticky=tk.W, pady=4)
        date_var = tk.StringVar()
        ttk.Entry(frame, textvariable=date_var, width=25).grid(row=3, column=1, pady=4)
        ttk.Label(frame, text="YYYY-MM-DD，留空手动抢座时用今天", foreground="gray").grid(
            row=3, column=2, sticky=tk.W, padx=4,
        )

        # Time
        ttk.Label(frame, text="开始时间:").grid(row=4, column=0, sticky=tk.W, pady=4)
        time_var = tk.StringVar(value="08:00:00")
        ttk.Entry(frame, textvariable=time_var, width=25).grid(row=4, column=1, pady=4)

        # Duration
        ttk.Label(frame, text="使用时长(小时):").grid(row=5, column=0, sticky=tk.W, pady=4)
        dur_var = tk.StringVar(value="4")
        dur_spin = ttk.Spinbox(frame, from_=1, to=24, textvariable=dur_var, width=22)
        dur_spin.grid(row=5, column=1, pady=4)

        # Seats
        ttk.Label(frame, text="座位号(逗号分隔):").grid(row=6, column=0, sticky=tk.W, pady=4)
        seats_var = tk.StringVar()
        ttk.Entry(frame, textvariable=seats_var, width=25).grid(row=6, column=1, pady=4)

        # 代预约好友选项
        friend_row = ttk.Frame(frame)
        friend_row.grid(row=7, column=0, columnspan=3, sticky=tk.W, pady=4)
        self._plan_friend_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(friend_row, text="代预约好友", variable=self._plan_friend_var,
                        command=self._toggle_friend_seat).pack(side=tk.LEFT)
        self._plan_friend_combo = ttk.Combobox(friend_row, state="disabled", width=15)
        self._plan_friend_combo.pack(side=tk.LEFT, padx=5)
        # 填充好友列表
        friends = self.friend_store.get_all()
        friend_names = [f"{info['name']} ({sid})" for sid, info in friends.items()]
        self._plan_friend_combo["values"] = friend_names
        if friend_names:
            self._plan_friend_combo.set(friend_names[0])
        self._friend_sid_map = {f"{info['name']} ({sid})": sid for sid, info in friends.items()}

        # Booker UIDs
        ttk.Label(frame, text="预约人UID:").grid(row=8, column=0, sticky=tk.W, pady=4)
        bookers_var = tk.StringVar()
        bookers_entry = ttk.Entry(frame, textvariable=bookers_var, width=20)
        bookers_entry.grid(row=7, column=1, sticky=tk.W, pady=4)

        def pick_uid():
            records = self.uid_store.get_all()
            if not records:
                messagebox.showinfo("提示", "暂无已保存的UID记录，请先在「状态」页查询", parent=dlg)
                return
            # 弹出选择对话框
            pick_dlg = tk.Toplevel(dlg)
            pick_dlg.title("选择预约人")
            pick_dlg.geometry("350x280")
            pick_dlg.resizable(False, False)
            pick_dlg.transient(dlg)
            pick_dlg.grab_set()
            self._center_on_parent(pick_dlg, 350, 280)

            pf = ttk.Frame(pick_dlg, padding=10)
            pf.pack(fill=tk.BOTH, expand=True)

            ttk.Label(pf, text="点击选择，可多选", foreground="gray").pack(anchor=tk.W)

            # 复选框列表
            vars_map = {}
            for sid, info in records.items():
                var = tk.BooleanVar()
                uid = info.get("uid", "")
                name = info.get("name", "")
                ttk.Checkbutton(
                    pf, text=f"{sid}  UID:{uid}  {name}", variable=var,
                ).pack(anchor=tk.W, pady=2)
                vars_map[sid] = (var, uid)

            def confirm():
                selected_uids = [uid for sid, (var, uid) in vars_map.items() if var.get() and uid]
                if selected_uids:
                    current = bookers_var.get().strip()
                    new_val = ",".join(selected_uids)
                    if current:
                        bookers_var.set(current + "," + new_val)
                    else:
                        bookers_var.set(new_val)
                pick_dlg.destroy()

            bf = ttk.Frame(pf)
            bf.pack(fill=tk.X, pady=10)
            ttk.Button(bf, text="确认", command=confirm).pack(side=tk.LEFT, padx=5)
            ttk.Button(bf, text="取消", command=pick_dlg.destroy).pack(side=tk.LEFT, padx=5)

        ttk.Button(frame, text="从记录中选择", command=pick_uid).grid(row=8, column=2, padx=4, sticky=tk.W)

        # Plan ID
        ttk.Label(frame, text="方案ID:").grid(row=9, column=0, sticky=tk.W, pady=4)
        plan_id_var = tk.StringVar()
        ttk.Entry(frame, textvariable=plan_id_var, width=25).grid(row=8, column=1, pady=4)

        def on_room_selected(event):
            room_name = room_var.get()
            floors = self.room_cache.get_floor_names(room_name)
            floor_combo["values"] = floors
            floor_var.set("")
            if floors:
                floor_var.set(floors[0])
            range_info = rooms[room_name].get("range", {})
            min_h = range_info.get("minBeginTime", 0)
            max_h = range_info.get("maxEndTime", 24)
            hours_label.config(text=f"开放时间: {min_h}:00-{max_h}:00")
            dur_spin.config(to=max_h)

        room_combo.bind("<<ComboboxSelected>>", on_room_selected)
        if room_names:
            room_var.set(room_names[0])
            on_room_selected(None)

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=10, column=0, columnspan=2, pady=15)
        ttk.Button(
            btn_frame, text="确认",
            command=lambda: self._confirm_add_plan(dlg, room_var, floor_var, date_var, time_var, dur_var, seats_var, bookers_var, plan_id_var),
        ).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=10)

    def _toggle_friend_seat(self):
        """切换代预约好友状态下拉框的启用/禁用"""
        if self._plan_friend_var.get():
            self._plan_friend_combo.config(state="readonly")
        else:
            self._plan_friend_combo.config(state="disabled")

    def _confirm_add_plan(self, dlg, room_var, floor_var, date_var, time_var, dur_var, seats_var, bookers_var, plan_id_var):
        room_name = room_var.get().strip()
        floor_name = floor_var.get().strip()
        date_str = date_var.get().strip()
        time_str = time_var.get().strip()
        seats_input = seats_var.get().strip()
        bookers_input = bookers_var.get().strip()
        plan_id = plan_id_var.get().strip()

        # 验证日期格式
        if date_str:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("错误", "日期格式不正确，请使用 YYYY-MM-DD 格式", parent=dlg)
                return

        if not room_name or not floor_name:
            messagebox.showerror("错误", "请选择房间和楼层", parent=dlg)
            return

        # Validate time format
        if not re.match(r"^\d{2}:\d{2}:\d{2}$", time_str):
            messagebox.showerror("错误", "时间格式不正确，请使用 HH:MM:SS 格式", parent=dlg)
            return

        try:
            duration = int(dur_var.get())
        except ValueError:
            messagebox.showerror("错误", "请输入有效的时长", parent=dlg)
            return
        if duration < 1:
            messagebox.showerror("错误", "时长不能小于1小时", parent=dlg)
            return

        # Validate start_time + duration <= 22:00
        hour = int(time_str.split(":")[0])
        if hour + duration > 22:
            messagebox.showerror(
                "错误",
                f"开始时间({hour}:00) + 使用时长({duration}小时) = {hour + duration}:00，"
                f"超过了图书馆最晚预约时间22:00",
                parent=dlg,
            )
            return

        # Validate time within room hours
        rooms = self.room_cache.rooms
        range_info = rooms[room_name].get("range", {})
        min_hour = range_info.get("minBeginTime", 0)
        max_hour = range_info.get("maxEndTime", 24)
        if hour < min_hour or hour > max_hour:
            messagebox.showerror(
                "错误",
                f"开始时间不在房间开放时间内({min_hour}:00-{max_hour}:00)",
                parent=dlg,
            )
            return

        # Validate seats
        seat_nums = [s.strip() for s in seats_input.replace("，", ",").split(",") if s.strip()]
        if not seat_nums:
            messagebox.showerror("错误", "请输入至少一个座位号", parent=dlg)
            return

        # 解析预约人学号
        booker_uids = []
        if bookers_input:
            booker_uids = [b.strip() for b in bookers_input.replace("，", ",").split(",") if b.strip()]

        # 如果勾选了代预约好友，追加好友 UID
        if self._plan_friend_var.get():
            friend_combo_val = self._plan_friend_combo.get()
            friend_sid = self._friend_sid_map.get(friend_combo_val)
            if friend_sid:
                friend_info = self.friend_store.get(friend_sid)
                if friend_info and friend_info["uid"] not in booker_uids:
                    booker_uids.append(friend_info["uid"])

        seats_info = self.room_cache.get_seats(room_name, floor_name)
        seat_list = []
        for i, seat_num in enumerate(seat_nums):
            matched = [s for s in seats_info if s["title"] == seat_num]
            if not matched:
                messagebox.showerror("错误", f"{floor_name}中座位{seat_num}不存在", parent=dlg)
                return
            if len(matched) > 1:
                messagebox.showerror("错误", f"座位{seat_num}存在多个匹配", parent=dlg)
                return
            uid = booker_uids[i] if i < len(booker_uids) else ""
            seat_list.append(SeatInfo(
                seat_id=str(matched[0]["id"]),
                seat_num=matched[0]["title"],
                booker_uid=uid,
            ))

        if not plan_id:
            plan_id = f"plan_{datetime.now().strftime('%H%M%S')}"

        plan = Plan(
            id=plan_id, room_name=room_name, floor_name=floor_name,
            begin_time=time_str, duration_hours=duration, seats=seat_list,
            target_date=date_str,
        )
        self.config.add_plan(plan)
        self._refresh_plans_tree()
        dlg.destroy()

    def _delete_selected_plans(self):
        selected = self.plans_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要删除的方案")
            return

        plans = self.config.get_plans()
        indices = sorted(int(iid) for iid in selected)
        if any(idx < 0 or idx >= len(plans) for idx in indices):
            messagebox.showerror("错误", "选中的序号超出范围")
            return

        if not messagebox.askyesno("确认", f"确定要删除{len(indices)}个方案吗？"):
            return

        plan_ids = [plans[idx].id for idx in indices]
        for pid in plan_ids:
            self.config.delete_plan(pid)
        self._refresh_plans_tree()

    def _batch_change_time_dialog(self):
        selected = self.plans_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要修改的方案")
            return

        plans = self.config.get_plans()
        indices = [int(iid) for iid in selected]

        dlg = tk.Toplevel(self.root)
        dlg.title("批量修改时间")
        dlg.geometry("360x200")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center_on_parent(dlg, 360, 200)

        frame = ttk.Frame(dlg, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=f"已选择 {len(indices)} 个方案", foreground="blue").grid(
            row=0, column=0, columnspan=2, pady=5,
        )
        ttk.Label(frame, text="错误的时间可能导致封号一周，请仔细检查。", foreground="red").grid(
            row=1, column=0, columnspan=2, pady=2,
        )

        ttk.Label(frame, text="开始时间(HH:MM:SS):").grid(row=2, column=0, sticky=tk.W, pady=5)
        time_var = tk.StringVar(value="08:00:00")
        ttk.Entry(frame, textvariable=time_var, width=15).grid(row=2, column=1, pady=5)

        ttk.Label(frame, text="使用时长(小时):").grid(row=3, column=0, sticky=tk.W, pady=5)
        dur_var = tk.StringVar(value="4")
        ttk.Spinbox(frame, from_=1, to=24, textvariable=dur_var, width=13).grid(row=3, column=1, pady=5)

        def confirm():
            time_str = time_var.get().strip()
            if not re.match(r"^\d{2}:\d{2}:\d{2}$", time_str):
                messagebox.showerror("错误", "时间格式不正确", parent=dlg)
                return
            try:
                duration = int(dur_var.get())
            except ValueError:
                messagebox.showerror("错误", "请输入有效时长", parent=dlg)
                return
            if duration < 1:
                messagebox.showerror("错误", "时长不能小于1", parent=dlg)
                return

            # Validate start_time + duration <= 22:00
            batch_hour = int(time_str.split(":")[0])
            if batch_hour + duration > 22:
                messagebox.showerror(
                    "错误",
                    f"开始时间({batch_hour}:00) + 使用时长({duration}小时) = "
                    f"{batch_hour + duration}:00，超过了图书馆最晚预约时间22:00",
                    parent=dlg,
                )
                return

            all_plans = self.config.config.get("plans", [])
            for idx in indices:
                if idx < len(all_plans):
                    all_plans[idx]["begin_time"] = time_str
                    all_plans[idx]["duration_hours"] = duration
            self.config.save()
            self._refresh_plans_tree()
            dlg.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="确认", command=confirm).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=10)

    # ================================================================
    # Booking
    # ================================================================

    def _clear_booking_log(self):
        """清空预约日志"""
        self.booking_log.configure(state=tk.NORMAL)
        self.booking_log.delete("1.0", tk.END)
        self.booking_log.configure(state=tk.DISABLED)

    def _start_booking(self):
        if not self._logged_in:
            messagebox.showwarning("提示", "请先登录")
            return
        plans = self.config.get_plans()
        if not plans:
            messagebox.showwarning("提示", "没有预约方案，请先添加方案")
            return
        # Pre-run validation
        errors = []
        for plan in plans:
            errors.extend(plan.validate())
        if errors:
            messagebox.showerror("方案校验失败", "\n".join(errors))
            return

        self._booking_cancel.clear()
        self.booking_start_btn.config(state=tk.DISABLED)
        self.booking_stop_btn.config(state=tk.NORMAL)

        # Clear log
        self.booking_log.configure(state=tk.NORMAL)
        self.booking_log.delete("1.0", tk.END)
        self.booking_log.configure(state=tk.DISABLED)

        threading.Thread(target=self._booking_thread_func, daemon=True).start()

    def _cancel_booking(self):
        self._booking_cancel.set()

    def _booking_thread_func(self):
        plans = self.config.get_plans()
        settings = self.config.get_settings()

        for retry in range(settings["max_try_times"]):
            if self._booking_cancel.is_set():
                self.root.after(0, self._append_booking_log, "已取消", "warning")
                break

            ts = datetime.now().strftime("%H:%M:%S")
            self.root.after(
                0, self._append_booking_log,
                f"[{ts}] 第{retry + 1}次尝试...", "info",
            )
            self.root.after(
                0, self._update_booking_progress,
                f"第{retry + 1}次尝试 / 最大{settings['max_try_times']}次",
            )

            for plan in plans:
                if self._booking_cancel.is_set():
                    break

                now = datetime.now()
                # 使用方案中的目标日期（如有），否则用今天
                if plan.target_date:
                    plan_date = datetime.strptime(plan.target_date, "%Y-%m-%d")
                else:
                    plan_date = now
                h, m, s = (int(x) for x in plan.begin_time.split(":"))
                begin_time = plan_date.replace(hour=h, minute=m, second=s, microsecond=0)

                seat_ids = [seat.seat_id for seat in plan.seats]
                booker_uids = [
                    seat.booker_uid if seat.booker_uid else self.session_mgr.uid
                    for seat in plan.seats
                ]
                # 确保当前用户在预约人列表中
                if self.session_mgr.uid not in booker_uids:
                    booker_uids[0] = self.session_mgr.uid

                try:
                    resp = self.api.book_seat(begin_time, plan.duration_hours, seat_ids, booker_uids)
                    result = BookingResult.from_api_response(resp, plan_id=plan.id)
                except Exception as e:
                    result = BookingResult(
                        success=False, code="error", message=str(e), plan_id=plan.id,
                    )

                self.history.log(result)
                ts = datetime.now().strftime("%H:%M:%S")

                if result.success:
                    booking_id_info = f" | bookingId: {result.booking_id}" if result.booking_id else ""
                    self.root.after(
                        0, self._append_booking_log,
                        f"[{ts}] 方案 {plan.id} 预约成功！{booking_id_info}", "success",
                    )
                    seats_detail = ", ".join(
                        f"{s.seat_num}(学号:{s.booker_uid})" if s.booker_uid else s.seat_num
                        for s in plan.seats
                    )
                    self.root.after(
                        0, self._append_booking_log,
                        f"  房间: {plan.room_name} | 楼层: {plan.floor_name} | "
                        f"座位: {seats_detail} | "
                        f"时间: {plan.begin_time} | 时长: {plan.duration_hours}小时",
                        "success",
                    )
                    self.root.after(0, self._on_booking_complete, True)
                    return
                else:
                    self.root.after(
                        0, self._append_booking_log,
                        f"[{ts}] 方案 {plan.id} 预约失败: {result.message}", "error",
                    )

            if self._booking_cancel.is_set():
                break

            if retry < settings["max_try_times"] - 1:
                self.root.after(
                    0, self._append_booking_log,
                    f"等待{settings['interval']}秒后重试...", "info",
                )
                self._booking_cancel.wait(timeout=settings["interval"])

        self.root.after(0, self._on_booking_complete, False)

    def _append_booking_log(self, message, tag="info"):
        self.booking_log.configure(state=tk.NORMAL)
        self.booking_log.insert(tk.END, message + "\n", tag)
        self.booking_log.see(tk.END)
        self.booking_log.configure(state=tk.DISABLED)

    def _update_booking_progress(self, text):
        if self.booking_progress_label.winfo_exists():
            self.booking_progress_label.config(text=text)

    def _on_booking_complete(self, success):
        self.booking_start_btn.config(state=tk.NORMAL)
        self.booking_stop_btn.config(state=tk.DISABLED)
        if success:
            self.booking_progress_label.config(text="预约成功")
        else:
            self.booking_progress_label.config(text="预约结束")

    # ================================================================
    # Schedule Management
    # ================================================================

    def _refresh_schedules_tree(self):
        for item in self.schedules_tree.get_children():
            self.schedules_tree.delete(item)
        schedules = self.config.get_schedules()
        plan_map = {p.id: p for p in self.config.get_plans()}

        for i, s in enumerate(schedules):
            status = "● 启用" if s.enabled else "○ 禁用"
            if s.mode == "weekdays":
                s_type = "按星期"
                target = ", ".join(WEEKDAY_NAMES[w - 1] for w in s.target_weekdays)
                plan_descs = []
                for pid in s.plan_ids:
                    p = plan_map.get(pid)
                    if p:
                        seats_str = ",".join(seat.seat_num for seat in p.seats)
                        plan_descs.append(f"{pid}({p.room_name} {seats_str}号)")
                    else:
                        plan_descs.append(f"{pid}(不存在)")
                plans_str = ", ".join(plan_descs)
            elif s.mode == "dates":
                s_type = "按日期"
                dates_str = ", ".join(m.target_date for m in s.mappings)
                target = dates_str
                all_pids = set()
                for m in s.mappings:
                    all_pids.update(m.plan_ids)
                plan_descs = []
                for pid in all_pids:
                    p = plan_map.get(pid)
                    if p:
                        seats_str = ",".join(seat.seat_num for seat in p.seats)
                        plan_descs.append(f"{pid}({p.room_name} {seats_str}号)")
                    else:
                        plan_descs.append(f"{pid}(不存在)")
                plans_str = ", ".join(plan_descs)
            else:
                continue

            tag = "enabled" if s.enabled else "disabled"
            self.schedules_tree.insert("", tk.END, iid=str(i), values=(
                i + 1, s_type, target, status, plans_str,
            ), tags=(tag,))

    def _start_scheduler(self):
        if not self._logged_in:
            messagebox.showwarning("提示", "请先登录")
            return
        schedules = self.config.get_schedules()
        active = [s for s in schedules if s.enabled]
        if not active:
            messagebox.showwarning("提示", "没有启用的调度，请先添加调度")
            return
        plans = self.config.get_plans()
        if not plans:
            messagebox.showwarning("提示", "没有预约方案，请先添加方案")
            return
        # Pre-run validation
        errors = []
        for plan in plans:
            errors.extend(plan.validate())
        if errors:
            messagebox.showerror("方案校验失败", "\n".join(errors))
            return

        self.engine.start()
        self.runner.set_checkin_registry(self.engine.register_checkin)
        self.scheduler_status_label.config(text="● 调度运行中", fg="green")
        self.status_bar.config(text="调度引擎已启动")
        self._schedule_status_refresh()

    def _stop_scheduler(self):
        if self.engine.is_running:
            self.engine.stop()
            self.scheduler_status_label.config(text="● 调度未运行", fg="red")
            self.status_bar.config(text="调度引擎已停止")
        else:
            messagebox.showinfo("提示", "调度引擎未在运行")

    def _add_weekday_schedule_dialog(self):
        plans = self.config.get_plans()
        if not plans:
            messagebox.showwarning("提示", "请先添加方案")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("添加按星期调度")
        dlg.geometry("400x300")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center_on_parent(dlg, 400, 300)

        frame = ttk.Frame(dlg, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="选择星期:").grid(row=0, column=0, sticky=tk.W, pady=5)

        cb_frame = ttk.Frame(frame)
        cb_frame.grid(row=0, column=1, sticky=tk.W, pady=5)

        weekday_vars = []
        for i, name in enumerate(WEEKDAY_NAMES):
            var = tk.BooleanVar()
            ttk.Checkbutton(cb_frame, text=name, variable=var).grid(
                row=i // 4, column=i % 4, sticky=tk.W, padx=5,
            )
            weekday_vars.append(var)

        ttk.Label(frame, text="方案ID(逗号分隔):").grid(row=1, column=0, sticky=tk.W, pady=8)
        plan_ids_var = tk.StringVar()
        ttk.Entry(frame, textvariable=plan_ids_var, width=30).grid(row=1, column=1, pady=8)

        plan_ids_str = ", ".join(p.id for p in plans)
        ttk.Label(frame, text=f"可用方案: {plan_ids_str}", foreground="gray").grid(
            row=2, column=0, columnspan=2, sticky=tk.W,
        )

        def confirm():
            weekdays = [i + 1 for i, v in enumerate(weekday_vars) if v.get()]
            if not weekdays:
                messagebox.showerror("错误", "至少需要选择一天", parent=dlg)
                return
            pids = [p.strip() for p in plan_ids_var.get().replace("，", ",").split(",") if p.strip()]
            if not pids:
                messagebox.showerror("错误", "请输入方案ID", parent=dlg)
                return
            valid_ids = {p.id for p in plans}
            for pid in pids:
                if pid not in valid_ids:
                    messagebox.showerror("错误", f"方案ID '{pid}' 不存在", parent=dlg)
                    return
            schedule = Schedule(mode="weekdays", target_weekdays=sorted(set(weekdays)), plan_ids=pids)
            schedules = self.config.get_schedules()
            schedules.append(schedule)
            self.config.save_schedules(schedules)
            self._refresh_schedules_tree()
            dlg.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="确认", command=confirm).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=10)

    def _add_date_schedule_dialog(self):
        plans = self.config.get_plans()
        if not plans:
            messagebox.showwarning("提示", "请先添加方案")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("添加按日期调度")
        dlg.geometry("400x250")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center_on_parent(dlg, 400, 250)

        frame = ttk.Frame(dlg, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="日期(YYYY-MM-DD，逗号分隔):").grid(row=0, column=0, sticky=tk.W, pady=8)
        dates_var = tk.StringVar()
        ttk.Entry(frame, textvariable=dates_var, width=30).grid(row=0, column=1, pady=8)

        ttk.Label(frame, text="方案ID(逗号分隔):").grid(row=1, column=0, sticky=tk.W, pady=8)
        plan_ids_var = tk.StringVar()
        ttk.Entry(frame, textvariable=plan_ids_var, width=30).grid(row=1, column=1, pady=8)

        plan_ids_str = ", ".join(p.id for p in plans)
        ttk.Label(frame, text=f"可用方案: {plan_ids_str}", foreground="gray").grid(
            row=2, column=0, columnspan=2, sticky=tk.W,
        )

        def confirm():
            dates_input = dates_var.get().strip().replace("，", ",")
            dates = [d.strip() for d in dates_input.split(",") if d.strip()]
            if not dates:
                messagebox.showerror("错误", "请输入至少一个日期", parent=dlg)
                return
            for d in dates:
                try:
                    datetime.strptime(d, "%Y-%m-%d")
                except ValueError:
                    messagebox.showerror("错误", f"日期格式不正确: {d}", parent=dlg)
                    return
            pids = [p.strip() for p in plan_ids_var.get().replace("，", ",").split(",") if p.strip()]
            if not pids:
                messagebox.showerror("错误", "请输入方案ID", parent=dlg)
                return
            valid_ids = {p.id for p in plans}
            for pid in pids:
                if pid not in valid_ids:
                    messagebox.showerror("错误", f"方案ID '{pid}' 不存在", parent=dlg)
                    return

            mappings = [DateMapping(target_date=d, plan_ids=pids) for d in dates]
            schedule = Schedule(mode="dates", mappings=mappings)
            schedules = self.config.get_schedules()
            schedules.append(schedule)
            self.config.save_schedules(schedules)
            self._refresh_schedules_tree()
            dlg.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="确认", command=confirm).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=10)

    def _delete_selected_schedules(self):
        selected = self.schedules_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要删除的调度")
            return

        schedules = self.config.get_schedules()
        indices = sorted(int(iid) for iid in selected)
        if any(idx < 0 or idx >= len(schedules) for idx in indices):
            messagebox.showerror("错误", "选中的序号超出范围")
            return

        if not messagebox.askyesno("确认", f"确定要删除{len(indices)}个调度吗？"):
            return

        # Delete in reverse order
        for idx in reversed(indices):
            schedules.pop(idx)
        self.config.save_schedules(schedules)
        self._refresh_schedules_tree()

    def _toggle_schedule_enabled(self):
        selected = self.schedules_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要切换的调度")
            return

        schedules = self.config.get_schedules()
        indices = [int(iid) for iid in selected]
        if any(idx < 0 or idx >= len(schedules) for idx in indices):
            messagebox.showerror("错误", "选中的序号超出范围")
            return

        for idx in indices:
            schedules[idx].enabled = not schedules[idx].enabled

        self.config.save_schedules(schedules)
        self._refresh_schedules_tree()

    # ================================================================
    # Status
    # ================================================================

    def _refresh_uid_tree(self):
        """刷新 UID 记录列表"""
        if not hasattr(self, 'uid_tree'):
            return
        for item in self.uid_tree.get_children():
            self.uid_tree.delete(item)
        records = self.uid_store.get_all()
        for student_id, info in records.items():
            self.uid_tree.insert("", tk.END, values=(
                student_id, info.get("uid", ""), info.get("name", ""),
            ))

    def _delete_selected_uid(self):
        """删除选中的 UID 记录"""
        selected = self.uid_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要删除的记录")
            return
        if not messagebox.askyesno("确认", f"确定删除 {len(selected)} 条 UID 记录？"):
            return
        for item in selected:
            values = self.uid_tree.item(item, "values")
            student_id = values[0]
            self.uid_store.remove(student_id)
        self._refresh_uid_tree()

    def _refresh_history_tree(self):
        """刷新预约历史列表"""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        records = self.history.query(50)
        for r in records:
            result_str = "成功" if r.get("success") else "失败"
            self.history_tree.insert("", tk.END, values=(
                r.get("timestamp", ""),
                r.get("plan_id", ""),
                r.get("seat_num", ""),
                r.get("target_date", ""),
                result_str,
                r.get("message", ""),
            ))

    def _clear_history(self):
        """清空预约历史"""
        if not messagebox.askyesno("确认", "确定清空所有预约历史？"):
            return
        self.history.clear()
        self._refresh_history_tree()

    def _lookup_uid_dialog(self):
        """打开查询他人 UID 的对话框"""
        dlg = tk.Toplevel(self.root)
        dlg.title("查询 UID")
        dlg.geometry("380x250")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center_on_parent(dlg, 380, 250)

        frame = ttk.Frame(dlg, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="学号:").grid(row=0, column=0, sticky=tk.W, pady=5)
        user_var = tk.StringVar()
        ttk.Entry(frame, textvariable=user_var, width=25).grid(row=0, column=1, pady=5)

        ttk.Label(frame, text="密码:").grid(row=1, column=0, sticky=tk.W, pady=5)
        pwd_var = tk.StringVar()
        ttk.Entry(frame, textvariable=pwd_var, width=25, show="*").grid(row=1, column=1, pady=5)

        status_label = ttk.Label(frame, text="", foreground="blue")
        status_label.grid(row=2, column=0, columnspan=2, pady=5)

        result_label = ttk.Label(frame, text="", foreground="green", font=("", 10, "bold"))
        result_label.grid(row=3, column=0, columnspan=2, pady=5)

        def do_lookup():
            username = user_var.get().strip()
            password = pwd_var.get().strip()
            if not username or not password:
                status_label.config(text="请输入学号和密码", foreground="red")
                return
            status_label.config(text="正在查询，请稍候...", foreground="blue")
            result_label.config(text="")
            dlg.update_idletasks()

            def worker():
                success, uid, name = lookup_uid(username, password)
                self.root.after(0, on_done, success, uid, name, username)

            def on_done(success, uid, name, student_id):
                if success:
                    self.uid_store.set(student_id, uid, name)
                    result_label.config(text=f"UID: {uid}  姓名: {name}")
                    status_label.config(text="查询成功，已保存", foreground="green")
                    self._refresh_uid_tree()
                else:
                    err = name  # 失败时 name 参数存放错误信息
                    status_label.config(text=f"查询失败: {err}", foreground="red")

            threading.Thread(target=worker, daemon=True).start()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="查询", command=do_lookup).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="关闭", command=dlg.destroy).pack(side=tk.LEFT, padx=10)

    def _update_user_info(self):
        """更新用户信息显示"""
        if not hasattr(self, 'user_info_labels'):
            return
        uid = self.session_mgr.uid
        name = self.session_mgr.name
        self.user_info_labels["uid"].config(text=uid or "—")
        self.user_info_labels["name"].config(text=name or "—")

    def _update_status_display(self):
        """更新调度引擎状态显示"""
        if not hasattr(self, 'status_labels'):
            return
        status = self.engine.get_status()
        if status["running"]:
            self.status_labels["engine"].config(text="运行中", foreground="green")
            if status["trigger_time"]:
                self.status_labels["trigger"].config(text=status["trigger_time"].strftime("%m-%d %H:%M"))
            if status["remaining_seconds"] is not None:
                self.status_labels["remaining"].config(text=format_countdown(status["remaining_seconds"]))
            self.status_labels["plans"].config(text=", ".join(status["plan_ids"]))
        else:
            self.status_labels["engine"].config(text="未运行", foreground="red")
            self.status_labels["trigger"].config(text="—")
            self.status_labels["remaining"].config(text="—")
            self.status_labels["plans"].config(text="—")

    def _schedule_status_refresh(self):
        """Periodically refresh status display while engine runs."""
        try:
            self._update_status_display()
            if self.engine.is_running:
                self.scheduler_status_label.config(text="● 调度运行中", fg="green")
                self.root.after(1000, self._schedule_status_refresh)
        except tk.TclError:
            pass

    # ================================================================
    # Settings
    # ================================================================

    def _load_settings(self):
        settings = self.config.get_settings()
        self.interval_var.set(str(settings["interval"]))
        self.max_try_var.set(str(settings["max_try_times"]))

    def _save_settings(self):
        try:
            interval = int(self.interval_var.get())
            max_try = int(self.max_try_var.get())
        except ValueError:
            messagebox.showerror("错误", "请输入有效数字")
            return
        if interval < 1:
            messagebox.showerror("错误", "间隔不能小于1秒")
            return
        if max_try < 1:
            messagebox.showerror("错误", "重试次数不能小于1")
            return

        self.config.update_settings(interval=interval, max_try_times=max_try)
        self.runner.interval = interval
        self.runner.max_try_times = max_try
        messagebox.showinfo("成功", "设置已保存")

    def _update_account_display(self):
        """更新账号信息显示"""
        user = self.config.get_user_info()
        self.account_labels["login_name"].config(text=user.get("login_name", "—"))
        self.account_labels["name"].config(text=self.session_mgr.name or "—")

    def _relogin(self):
        """重新登录"""
        self._show_login_dialog()

    # ================================================================
    # Engine Callbacks (called from engine thread)
    # ================================================================

    def _on_friend_confirm(self, booking_id: str, friend_uid: str):
        """好友确认回调（从 engine 线程调用）"""
        friend_sid = None
        for sid, info in self.friend_store.get_all().items():
            if info.get("uid") == friend_uid:
                friend_sid = sid
                break
        if not friend_sid:
            self._log(f"未找到 UID={friend_uid} 对应的好友，跳过自动确认", "warning")
            return
        self._log(f"正在用好友 {friend_sid} 账号确认预约...", "info")
        def _do():
            ok, msg = self.friend_service.auto_confirm(booking_id, friend_sid)
            if ok:
                self._log(f"好友 {friend_sid} 确认预约成功", "success")
            else:
                self._log(f"好友 {friend_sid} 确认失败: {msg}", "warning")
        threading.Thread(target=_do, daemon=True).start()

    def _on_countdown_tick(self, remaining, trigger_time, plan_desc):
        try:
            self.root.after(0, self._update_countdown_display, remaining, trigger_time, plan_desc)
        except RuntimeError:
            pass  # root destroyed

    def _update_countdown_display(self, remaining, trigger_time, plan_desc):
        remaining_str = format_countdown(remaining)
        trigger_str = trigger_time.strftime("%m-%d %H:%M")
        # 更新调度 tab 的状态区
        if hasattr(self, 'status_labels'):
            self.status_labels["engine"].config(text="运行中", foreground="green")
            self.status_labels["trigger"].config(text=trigger_str)
            self.status_labels["remaining"].config(text=remaining_str)
            self.status_labels["plans"].config(text=plan_desc)
        # 状态栏只显示简要信息
        self.status_bar.config(text=f"调度运行中 | 剩余: {remaining_str}")

    def _on_booking_result(self, result: BookingResult):
        self.history.log(result)
        ts = datetime.now().strftime("%H:%M:%S")
        if result.success:
            msg = f"[{ts}] [调度] 预约成功: {result}"
            tag = "success"
        else:
            msg = f"[{ts}] [调度] 预约失败: {result.message}"
            tag = "warning"
        try:
            self.root.after(0, self._append_booking_log, msg, tag)
        except RuntimeError:
            pass

    def _on_booking_start(self, target_date, plan_ids):
        ts = datetime.now().strftime("%H:%M:%S")
        msg = (f"[{ts}] 预约开放时间已到达，正在为"
               f"{target_date.strftime('%Y-%m-%d')}执行预约...")
        try:
            self.root.after(0, self._append_booking_log, msg, "info")
        except RuntimeError:
            pass

    def _on_engine_error(self, error):
        ts = datetime.now().strftime("%H:%M:%S")
        msg = f"[{ts}] 调度引擎错误: {error}"
        try:
            self.root.after(0, self._append_booking_log, msg, "error")
        except RuntimeError:
            pass

    def _on_checkin_result(self, success, message, plan_desc):
        """签到结果回调（从引擎线程调用）"""
        if success:
            self._log(f"自动签到成功: {plan_desc}", "success")
            try:
                self.root.after(0, lambda: self._checkin_result_label.config(
                    text=f"✅ 签到成功: {plan_desc}", foreground="green"))
            except RuntimeError:
                pass
        else:
            self._log(f"自动签到失败: {plan_desc} - {message}", "error")
            try:
                self.root.after(0, lambda: self._checkin_result_label.config(
                    text=f"❌ 签到失败: {message}", foreground="red"))
            except RuntimeError:
                pass

    def _pick_booking_from_history(self):
        """从预约历史中选择 bookingId"""
        records = self.history.query(20)
        # 过滤出有 bookingId 的记录
        bookings = [r for r in records if r.get("booking_id")]
        if not bookings:
            messagebox.showinfo("提示", "没有找到含 bookingId 的预约记录。\n预约成功后会自动记录 bookingId。")
            return

        # 弹出选择对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("选择预约记录")
        dialog.geometry("500x300")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        self._center_on_parent(dialog, 500, 300)

        ttk.Label(dialog, text="选择一条预约记录进行签到：").pack(pady=5)

        tree_frame = ttk.Frame(dialog)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        cols = ("time", "booking_id", "seat", "date")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=8)
        for col, text, w in [
            ("time", "时间", 130), ("booking_id", "bookingId", 120),
            ("seat", "座位", 80), ("date", "日期", 90),
        ]:
            tree.heading(col, text=text)
            tree.column(col, width=w)

        for r in bookings:
            tree.insert("", tk.END, values=(
                r.get("timestamp", ""),
                r.get("booking_id", ""),
                r.get("seat_num", ""),
                r.get("target_date", ""),
            ))

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        def select():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先选择一条记录", parent=dialog)
                return
            values = tree.item(sel[0], "values")
            booking_id = values[1]
            self._checkin_entry.delete(0, tk.END)
            self._checkin_entry.insert(0, booking_id)
            dialog.destroy()

        ttk.Button(dialog, text="确定选择", command=select).pack(pady=5)

    def _fetch_current_bookings(self):
        """从服务器获取当前预约列表"""
        if not self._logged_in:
            messagebox.showwarning("提示", "请先登录")
            return

        self._log("正在获取当前预约...", "info")
        self._checkin_result_label.config(text="获取中...", foreground="gray")

        def _do():
            bookings = self.api.get_my_bookings()
            if bookings:
                self._log(f"获取到 {len(bookings)} 条预约", "success")
            else:
                self._log("未获取到预约，可查看日志了解详情", "error")
            self.root.after(0, lambda: self._show_bookings_dialog(bookings))

        threading.Thread(target=_do, daemon=True).start()

    def _show_bookings_dialog(self, bookings):
        """显示当前预约列表供选择"""
        if not bookings:
            messagebox.showinfo("提示", "没有找到当前预约。\n可能还没有预约，或预约已过期。")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("当前预约")
        dialog.geometry("580x320")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        self._center_on_parent(dialog, 580, 320)

        ttk.Label(dialog, text="选择一条预约进行签到：").pack(pady=5)

        tree_frame = ttk.Frame(dialog)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        cols = ("bid", "seat", "begin", "end", "status")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=8)
        for col, text, w in [
            ("bid", "bookingId", 100), ("seat", "座位", 120),
            ("begin", "开始时间", 110), ("end", "结束时间", 110),
            ("status", "状态", 80),
        ]:
            tree.heading(col, text=text)
            tree.column(col, width=w)

        status_map = {"0": "待签到", "1": "已签到", "2": "已结束"}
        for b in bookings:
            bid = b.get("bookingId", "")
            seat = f"{b.get('roomName', '')}-{b.get('seatNum', '')}"
            begin = b.get("beginTime")
            end = b.get("endTime")
            st = str(b.get("status", ""))
            status_text = status_map.get(st, st)
            begin_str = begin.strftime("%m-%d %H:%M") if begin else "—"
            end_str = end.strftime("%H:%M") if end else "—"
            tree.insert("", tk.END, values=(bid, seat, begin_str, end_str, status_text))

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        def select():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先选择一条预约", parent=dialog)
                return
            values = tree.item(sel[0], "values")
            booking_id = values[0]
            self._checkin_entry.delete(0, tk.END)
            self._checkin_entry.insert(0, booking_id)
            self._log(f"已选择 bookingId: {booking_id}", "info")
            dialog.destroy()

        ttk.Button(dialog, text="确定选择", command=select).pack(pady=5)

    def _manual_checkin_from_entry(self):
        """从输入框获取 bookingId 并签到"""
        if not self._logged_in:
            messagebox.showwarning("提示", "请先登录")
            return

        booking_id = self._checkin_entry.get().strip()
        if not booking_id:
            messagebox.showwarning("提示", "请输入 bookingId")
            return

        self._checkin_result_label.config(text="签到中...", foreground="gray")
        self._log(f"正在签到 (bookingId={booking_id})...", "info")

        def _do():
            success, msg, _ = self.api.check_in(booking_id)
            if success:
                self._log("签到成功！", "success")
                self.root.after(0, lambda: self._checkin_result_label.config(
                    text="✅ 签到成功！", foreground="green"))
            else:
                self._log(f"签到失败: {msg}", "error")
                self.root.after(0, lambda: self._checkin_result_label.config(
                    text=f"❌ 签到失败: {msg}", foreground="red"))

        threading.Thread(target=_do, daemon=True).start()

    # ================================================================
    # Utilities
    # ================================================================

    def _log(self, message: str, tag: str = "info"):
        """向预约日志区写入一条消息"""
        ts = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{ts}] {message}\n"
        try:
            self.root.after(0, self._append_booking_log, full_msg, tag)
        except RuntimeError:
            pass

    def _center_on_parent(self, dlg, w, h):
        dlg.update_idletasks()
        px = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{px}+{py}")

    # ================================================================
    # Lifecycle
    # ================================================================

    def _on_closing(self):
        if self.engine.is_running:
            self.engine.stop()
        if self.room_cache.is_ready:
            self.room_cache.stop_background_refresh()
        self.root.destroy()
