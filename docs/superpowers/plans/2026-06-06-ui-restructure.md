# UI 重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 GUI 标签页布局，从 6 个 tab 精简到 5 个，按功能域分组，修复 3 个已知 Bug。

**Architecture:** 重写 gui.py 的 `_build_tabs` 方法和各 tab 构建方法，重新组织控件布局。CLI 同步调整菜单结构。

**Tech Stack:** Python, tkinter

---

## 文件变更总览

| 文件 | 操作 | 说明 |
|------|------|------|
| `seathunter/ui/gui.py` | 重写 | 重构标签页布局，修复 Bug |
| `seathunter/ui/cli.py` | 修改 | 调整菜单结构，精简选项 |

---

### Task 1: Bug 修复 — `_log()` 方法和签到回调

**Files:**
- Modify: `seathunter/ui/gui.py`

- [ ] **Step 1: 添加 `_log()` 方法**

在 `_center_on_parent` 方法之前（Utilities 区域）添加：

```python
    def _log(self, message: str, tag: str = "info"):
        """向预约日志区写入一条消息"""
        ts = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{ts}] {message}\n"
        try:
            self.root.after(0, self._append_booking_log, full_msg, tag)
        except RuntimeError:
            pass
```

- [ ] **Step 2: 修复 `_on_checkin_result` 回调**

找到 `_on_checkin_result` 方法，将 `self._log(...)` 改为带 tag 的调用：

```python
    def _on_checkin_result(self, success, message, plan_desc):
        """签到结果回调"""
        if success:
            self._log(f"自动签到成功: {plan_desc}", "success")
        else:
            self._log(f"自动签到失败: {plan_desc} - {message}", "error")
```

- [ ] **Step 3: 修复 `_manual_checkin` 中的 `_log` 调用**

找到 `_manual_checkin` 方法中调用 `self._log(...)` 的三处，改为带 tag：

```python
            self._log(f"正在签到 (bookingId={booking_id})...", "info")
            # ...
            self._log("签到成功！", "success")
            # ...
            self._log(f"签到失败: {msg}", "error")
```

- [ ] **Step 4: 验证语法**

```bash
.venv/bin/python3 -c "from seathunter.ui.gui import GuiApp; print('OK')"
```

- [ ] **Step 5: 提交**

```bash
git add seathunter/ui/gui.py
git commit -m "fix(gui): 修复 _log 方法缺失和签到回调 Bug

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 重构 `_build_tabs` — 新建 Tab 0「预约」

**Files:**
- Modify: `seathunter/ui/gui.py`

- [ ] **Step 1: 修改 `_build_tabs` 方法**

替换 `_build_tabs` 方法，去掉原 Tab 1「立即抢座」和 Tab 4「状态」，新建 5 个 tab：

```python
    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))

        self._build_booking_tab()      # Tab 0: 预约
        self._build_scheduler_tab()    # Tab 1: 调度
        self._build_tools_tab()        # Tab 2: 工具
        self._build_settings_tab()     # Tab 3: 设置
        self._build_help_tab()         # Tab 4: 帮助

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
```

- [ ] **Step 2: 修改 `_on_tab_changed` 方法**

```python
    def _on_tab_changed(self, event=None):
        idx = self.notebook.index(self.notebook.select())
        if idx == 0:
            self._refresh_plans_tree()
        elif idx == 1:
            self._refresh_schedules_tree()
```

- [ ] **Step 3: 重写 `_build_booking_tab` 为新的「预约」tab**

替换原 `_build_plans_tab` 和 `_build_booking_tab` 为新的合并版本：

```python
    def _build_booking_tab(self):
        """Tab 0: 预约 — 合并方案管理和立即抢座"""
        frame = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(frame, text="预约")

        # ── 上半部分：方案管理 ──
        plans_frame = ttk.LabelFrame(frame, text="方案管理", padding=3)
        plans_frame.pack(fill=tk.BOTH, expand=True)

        # Treeview
        tree_frame = ttk.Frame(plans_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("idx", "plan_id", "room", "floor", "seats", "time", "duration")
        self.plans_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=12,
        )
        for col, text, width in [
            ("idx", "序号", 50), ("plan_id", "方案ID", 130),
            ("room", "房间名", 130), ("floor", "楼层", 80),
            ("seats", "座位号", 100), ("time", "开始时间", 100),
            ("duration", "时长", 60),
        ]:
            self.plans_tree.heading(col, text=text)
            self.plans_tree.column(col, width=width, anchor=tk.CENTER if col in ("idx", "time", "duration") else tk.W)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.plans_tree.yview)
        self.plans_tree.configure(yscrollcommand=scrollbar.set)
        self.plans_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 方案管理按钮
        btn_frame = ttk.Frame(plans_frame)
        btn_frame.pack(fill=tk.X, pady=(3, 0))
        ttk.Button(btn_frame, text="添加方案", command=self._add_plan_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除选中", command=self._delete_selected_plans).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="批量修改时间", command=self._batch_change_time_dialog).pack(side=tk.LEFT, padx=2)

        # ── 下半部分：立即抢座 ──
        book_frame = ttk.LabelFrame(frame, text="立即抢座", padding=3)
        book_frame.pack(fill=tk.X, pady=(5, 0))

        # 进度和按钮行
        ctrl_frame = ttk.Frame(book_frame)
        ctrl_frame.pack(fill=tk.X, pady=3)

        self.booking_progress_label = ttk.Label(ctrl_frame, text="")
        self.booking_progress_label.pack(side=tk.LEFT, padx=5)

        self.booking_start_btn = ttk.Button(ctrl_frame, text="开始抢座", command=self._start_booking)
        self.booking_start_btn.pack(side=tk.RIGHT, padx=2)
        self.booking_stop_btn = ttk.Button(ctrl_frame, text="停止", command=self._cancel_booking, state=tk.DISABLED)
        self.booking_stop_btn.pack(side=tk.RIGHT, padx=2)

        # 日志区
        log_frame = ttk.LabelFrame(book_frame, text="结果日志", padding=3)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.booking_log = tk.Text(log_frame, state=tk.DISABLED, wrap=tk.WORD, height=8, font=("Consolas", 9))
        self.booking_log.tag_configure("success", foreground="green")
        self.booking_log.tag_configure("error", foreground="red")
        self.booking_log.tag_configure("info", foreground="#0066cc")
        self.booking_log.tag_configure("warning", foreground="#cc6600")

        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.pack(fill=tk.X, pady=(2, 0))
        ttk.Button(log_btn_frame, text="清空日志", command=self._clear_booking_log).pack(side=tk.RIGHT)

        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.booking_log.yview)
        self.booking_log.configure(yscrollcommand=log_scroll.set)
        self.booking_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._refresh_plans_tree()
```

- [ ] **Step 4: 添加 `_clear_booking_log` 方法**

在 Utilities 区域添加：

```python
    def _clear_booking_log(self):
        """清空预约日志"""
        self.booking_log.configure(state=tk.NORMAL)
        self.booking_log.delete("1.0", tk.END)
        self.booking_log.configure(state=tk.DISABLED)
```

- [ ] **Step 5: 删除原 `_build_plans_tab` 方法**

删除 `_build_plans_tab` 方法（原 Tab 0「方案管理」），其内容已合并到新的 `_build_booking_tab`。

- [ ] **Step 6: 验证语法**

```bash
.venv/bin/python3 -c "from seathunter.ui.gui import GuiApp; print('OK')"
```

- [ ] **Step 7: 提交**

```bash
git add seathunter/ui/gui.py
git commit -m "refactor(gui): 重构 Tab 0 预约 — 合并方案管理和立即抢座

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 重构 Tab 1「调度」— 合并引擎状态和签到

**Files:**
- Modify: `seathunter/ui/gui.py`

- [ ] **Step 1: 重写 `_build_scheduler_tab` 方法**

替换原 `_build_scheduler_tab`，加入引擎状态详情和签到区：

```python
    def _build_scheduler_tab(self):
        """Tab 1: 调度 — 合并调度管理和签到"""
        frame = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(frame, text="调度")

        # ── 上半部分：调度管理 ──
        sched_frame = ttk.LabelFrame(frame, text="调度引擎", padding=3)
        sched_frame.pack(fill=tk.BOTH, expand=True)

        # 按钮栏
        btn_frame = ttk.Frame(sched_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 3))

        self.scheduler_start_btn = ttk.Button(btn_frame, text="启动调度", command=self._start_scheduler)
        self.scheduler_start_btn.pack(side=tk.LEFT, padx=2)
        self.scheduler_stop_btn = ttk.Button(btn_frame, text="停止调度", command=self._stop_scheduler)
        self.scheduler_stop_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(btn_frame, text="添加按星期调度", command=self._add_weekday_schedule_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="添加按日期调度", command=self._add_date_schedule_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="切换启用", command=self._toggle_schedule_enabled).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除选中", command=self._delete_selected_schedules).pack(side=tk.LEFT, padx=2)

        # 状态指示灯
        self.scheduler_status_label = tk.Label(btn_frame, text="● 调度未运行", fg="red", font=("", 10))
        self.scheduler_status_label.pack(side=tk.RIGHT, padx=10)

        # 调度列表
        tree_frame = ttk.Frame(sched_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("idx", "type", "target", "status", "plans")
        self.schedules_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=8)
        for col, text, w in [
            ("idx", "序号", 50), ("type", "类型", 80),
            ("target", "目标", 200), ("status", "状态", 60),
            ("plans", "绑定方案", 300),
        ]:
            self.schedules_tree.heading(col, text=text)
            self.schedules_tree.column(col, width=w, anchor=tk.CENTER if col in ("idx", "status") else tk.W)

        self.schedules_tree.tag_configure("enabled", foreground="black")
        self.schedules_tree.tag_configure("disabled", foreground="gray")

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.schedules_tree.yview)
        self.schedules_tree.configure(yscrollcommand=sb.set)
        self.schedules_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── 下半部分：引擎状态 + 签到 ──
        bottom_frame = ttk.Frame(frame)
        bottom_frame.pack(fill=tk.X, pady=(5, 0))

        # 引擎状态
        status_frame = ttk.LabelFrame(bottom_frame, text="引擎状态", padding=5)
        status_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

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

        # 签到区
        checkin_frame = ttk.LabelFrame(bottom_frame, text="手动签到", padding=5)
        checkin_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        ttk.Label(checkin_frame, text="bookingId:").pack(anchor=tk.W)
        self._checkin_entry = ttk.Entry(checkin_frame, width=20)
        self._checkin_entry.pack(fill=tk.X, pady=2)
        ttk.Button(checkin_frame, text="签到", command=self._manual_checkin_from_entry).pack(fill=tk.X)

        self._refresh_schedules_tree()
        self._update_status_display()
```

- [ ] **Step 2: 添加 `_manual_checkin_from_entry` 方法**

在签到相关方法区域添加：

```python
    def _manual_checkin_from_entry(self):
        """从输入框获取 bookingId 并签到"""
        if not self.session_mgr.is_logged_in:
            messagebox.showwarning("提示", "请先登录")
            return

        booking_id = self._checkin_entry.get().strip()
        if not booking_id:
            messagebox.showwarning("提示", "请输入 bookingId")
            return

        self._log(f"正在签到 (bookingId={booking_id})...", "info")
        success, msg, _ = self.session_mgr.api_client.check_in(booking_id)
        if success:
            self._log("签到成功！", "success")
            messagebox.showinfo("成功", "签到成功！")
        else:
            self._log(f"签到失败: {msg}", "error")
            messagebox.showerror("失败", f"签到失败: {msg}")
```

- [ ] **Step 3: 删除旧的 `_manual_checkin` 方法**

删除原来的 `_manual_checkin` 方法（弹出对话框版本），已被 `_manual_checkin_from_entry` 替代。

- [ ] **Step 4: 修改 `_on_checkin_result` 使用新的状态刷新**

确保 `_on_checkin_result` 写入预约 tab 的日志区（已在 Task 1 修复）。

- [ ] **Step 5: 验证语法**

```bash
.venv/bin/python3 -c "from seathunter.ui.gui import GuiApp; print('OK')"
```

- [ ] **Step 6: 提交**

```bash
git add seathunter/ui/gui.py
git commit -m "refactor(gui): 重构 Tab 1 调度 — 合并引擎状态和签到

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 新建 Tab 2「工具」— UID 管理 + 预约历史

**Files:**
- Modify: `seathunter/ui/gui.py`

- [ ] **Step 1: 创建 `_build_tools_tab` 方法**

在 `_build_scheduler_tab` 方法之后添加：

```python
    def _build_tools_tab(self):
        """Tab 2: 工具 — UID 管理 + 预约历史"""
        frame = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(frame, text="工具")

        # ── 上半部分：UID 管理 ──
        uid_frame = ttk.LabelFrame(frame, text="UID 管理", padding=5)
        uid_frame.pack(fill=tk.BOTH, expand=True)

        # 当前用户信息
        user_row = ttk.Frame(uid_frame)
        user_row.pack(fill=tk.X, pady=(0, 5))
        self.user_info_labels = {}
        for key, label_text in [("uid", "UID"), ("name", "姓名")]:
            ttk.Label(user_row, text=f"{label_text}:", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(0, 5))
            lbl = ttk.Label(user_row, text="—", font=("", 9))
            lbl.pack(side=tk.LEFT, padx=(0, 15))
            self.user_info_labels[key] = lbl

        ttk.Button(user_row, text="查询他人UID", command=self._lookup_uid_dialog).pack(side=tk.RIGHT)

        # UID 记录列表
        uid_tree_frame = ttk.Frame(uid_frame)
        uid_tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("student_id", "uid", "name")
        self.uid_tree = ttk.Treeview(uid_tree_frame, columns=cols, show="headings", height=5)
        for col, text, w in [("student_id", "学号", 120), ("uid", "UID", 120), ("name", "姓名", 120)]:
            self.uid_tree.heading(col, text=text)
            self.uid_tree.column(col, width=w, anchor=tk.CENTER)
        self.uid_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        uid_sb = ttk.Scrollbar(uid_tree_frame, orient=tk.VERTICAL, command=self.uid_tree.yview)
        self.uid_tree.configure(yscrollcommand=uid_sb.set)
        uid_sb.pack(side=tk.RIGHT, fill=tk.Y)

        uid_btn_frame = ttk.Frame(uid_frame)
        uid_btn_frame.pack(fill=tk.X, pady=(3, 0))
        ttk.Button(uid_btn_frame, text="删除选中记录", command=self._delete_selected_uid).pack(side=tk.LEFT)

        # ── 下半部分：预约历史 ──
        history_frame = ttk.LabelFrame(frame, text="预约历史", padding=5)
        history_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        hist_tree_frame = ttk.Frame(history_frame)
        hist_tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("time", "plan_id", "seat", "date", "result", "message")
        self.history_tree = ttk.Treeview(hist_tree_frame, columns=cols, show="headings", height=6)
        for col, text, w in [
            ("time", "时间", 130), ("plan_id", "方案ID", 100),
            ("seat", "座位", 80), ("date", "日期", 90),
            ("result", "结果", 60), ("message", "消息", 200),
        ]:
            self.history_tree.heading(col, text=text)
            self.history_tree.column(col, width=w, anchor=tk.CENTER if col in ("time", "date", "result") else tk.W)

        hist_sb = ttk.Scrollbar(hist_tree_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=hist_sb.set)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        hist_sb.pack(side=tk.RIGHT, fill=tk.Y)

        hist_btn_frame = ttk.Frame(history_frame)
        hist_btn_frame.pack(fill=tk.X, pady=(3, 0))
        ttk.Button(hist_btn_frame, text="清空历史", command=self._clear_history).pack(side=tk.LEFT)

        self._refresh_uid_tree()
        self._refresh_history_tree()
```

- [ ] **Step 2: 添加 `_delete_selected_uid` 方法**

```python
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
```

- [ ] **Step 3: 添加 `_refresh_history_tree` 方法**

```python
    def _refresh_history_tree(self):
        """刷新预约历史列表"""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        records = self.history.query(50)
        for i, r in enumerate(records):
            result_str = "成功" if r.get("success") else "失败"
            self.history_tree.insert("", tk.END, values=(
                r.get("time", ""),
                r.get("plan_id", ""),
                r.get("seat_num", ""),
                r.get("target_date", ""),
                result_str,
                r.get("message", ""),
            ))
```

- [ ] **Step 4: 添加 `_clear_history` 方法**

```python
    def _clear_history(self):
        """清空预约历史"""
        if not messagebox.askyesno("确认", "确定清空所有预约历史？"):
            return
        self.history.clear()
        self._refresh_history_tree()
```

- [ ] **Step 5: 删除原 `_build_status_tab` 方法**

删除原 Tab 4「状态」的 `_build_status_tab` 方法，其内容已拆分到调度 tab 和工具 tab。

- [ ] **Step 6: 验证语法**

```bash
.venv/bin/python3 -c "from seathunter.ui.gui import GuiApp; print('OK')"
```

- [ ] **Step 7: 提交**

```bash
git add seathunter/ui/gui.py
git commit -m "feat(gui): 新建 Tab 2 工具 — UID 管理和预约历史

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 扩充 Tab 3「设置」— 账号信息

**Files:**
- Modify: `seathunter/ui/gui.py`

- [ ] **Step 1: 重写 `_build_settings_tab` 方法**

替换原设置 tab，添加账号信息区：

```python
    def _build_settings_tab(self):
        """Tab 3: 设置"""
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

        ttk.Button(frame, text="保存设置", command=self._save_settings).pack(pady=20)

        self._load_settings()
        self._update_account_display()
```

- [ ] **Step 2: 添加 `_update_account_display` 方法**

```python
    def _update_account_display(self):
        """更新账号信息显示"""
        user = self.config.get_user_info()
        self.account_labels["login_name"].config(text=user.get("login_name", "—"))
        self.account_labels["name"].config(text=self.session_mgr.name or "—")
```

- [ ] **Step 3: 添加 `_relogin` 方法**

```python
    def _relogin(self):
        """重新登录"""
        self._show_login_dialog()
```

- [ ] **Step 4: 在 `_auto_login` 成功后更新账号显示**

找到 `_start_login_thread` 或登录成功的回调，在成功后调用 `self._update_account_display()`。

- [ ] **Step 5: 验证语法**

```bash
.venv/bin/python3 -c "from seathunter.ui.gui import GuiApp; print('OK')"
```

- [ ] **Step 6: 提交**

```bash
git add seathunter/ui/gui.py
git commit -m "refactor(gui): 扩充 Tab 3 设置 — 添加账号信息和重新登录

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: 清理旧代码和状态栏

**Files:**
- Modify: `seathunter/ui/gui.py`

- [ ] **Step 1: 简化状态栏**

修改 `_update_countdown_display`，只在调度 tab 的状态区更新，不在底部状态栏显示详细信息：

```python
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
```

- [ ] **Step 2: 添加 `_update_status_display` 方法（如果不存在）**

确保有统一的状态刷新方法：

```python
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
```

- [ ] **Step 3: 删除 `_refresh_booking_plans_tree` 方法**

原 Tab 1 的只读方案列表已被删除，删除对应的刷新方法。

- [ ] **Step 4: 删除所有对已删除 tab 的引用**

搜索代码中对原 tab 索引的引用（如 `if idx == 3` 等），确保没有残留引用。

- [ ] **Step 5: 验证语法**

```bash
.venv/bin/python3 -c "from seathunter.ui.gui import GuiApp; print('OK')"
```

- [ ] **Step 6: 提交**

```bash
git add seathunter/ui/gui.py
git commit -m "refactor(gui): 清理旧代码和简化状态栏

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: CLI 菜单精简

**Files:**
- Modify: `seathunter/ui/cli.py`

- [ ] **Step 1: 修改 `show_menu` 方法**

精简菜单，将选项 2 合并到选项 1，选项 5 合并到选项 4：

```python
    def show_menu(self):
        """Display main menu."""
        print("\n" + "=" * 40)
        status = ""
        if self.engine.is_running:
            status = colorize(" [调度运行中]", Color.GREEN)
        print(colorize(f"SeatHunter 主菜单{status}", Color.BOLD))
        print("=" * 40)
        print("1. 方案管理")
        print("2. 立即开始抢座")
        print("3. 调度管理")
        print("4. 修改请求间隔和次数")
        print("5. 手动签到")
        print("6. 查询他人 UID")
        print("7. 使用帮助")
        print("8. 退出")
```

- [ ] **Step 2: 修改 `_manage_plans` 子菜单**

在方案管理子菜单中添加「批量修改时间」和「查看方案」选项：

```python
    def _manage_plans(self):
        """方案管理子菜单"""
        while True:
            print("\n── 方案管理 ──")
            print("1. 查看方案")
            print("2. 添加方案")
            print("3. 删除方案")
            print("4. 批量修改预约时间")
            print("5. 返回主菜单")
            try:
                choice = int(input("请输入选项：").strip())
                if choice == 1:
                    self._show_plans()
                elif choice == 2:
                    self._add_plan()
                elif choice == 3:
                    self._delete_plan()
                elif choice == 4:
                    self._change_time()
                elif choice == 5:
                    break
            except (ValueError, IndexError):
                print_warning("无效输入")
```

- [ ] **Step 3: 修改 `_manage_schedules` 子菜单**

在调度管理子菜单中添加「查看调度状态」选项：

```python
    # 在子菜单中添加:
    # 7. 查看调度状态
    # 8. 返回主菜单
```

- [ ] **Step 4: 修改 `run` 方法的分发逻辑**

更新选项编号映射：

```python
    def run(self):
        while True:
            self.show_menu()
            try:
                choice = int(input("请输入选项：").strip())
                if choice == 1:
                    self._manage_plans()
                elif choice == 2:
                    self._start_now()
                elif choice == 3:
                    self._manage_schedules()
                elif choice == 4:
                    self._set_settings()
                elif choice == 5:
                    self._manual_checkin()
                elif choice == 6:
                    self._lookup_uid()
                elif choice == 7:
                    self._help()
                elif choice == 8:
                    self._exit()
                    break
            except (ValueError, IndexError):
                print_warning("无效输入，请输入数字")
```

- [ ] **Step 5: 验证语法**

```bash
.venv/bin/python3 -c "from seathunter.ui.cli import CliUI; print('OK')"
```

- [ ] **Step 6: 提交**

```bash
git add seathunter/ui/cli.py
git commit -m "refactor(cli): 精简主菜单从 10 个选项到 8 个

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 端到端验证

- [ ] **Step 1: 验证所有模块可导入**

```bash
.venv/bin/python3 -c "
from seathunter.ui.gui import GuiApp
from seathunter.ui.cli import CliUI
print('All imports OK')
"
```

- [ ] **Step 2: 为 HistoryLogger 添加 `clear` 方法**

在 `seathunter/logging_/history.py` 的 `HistoryLogger` 类末尾添加：

```python
    def clear(self):
        """清空历史记录文件。"""
        with open(self.log_path, "w", encoding="utf-8") as f:
            pass
```

- [ ] **Step 3: 为 UidStore 添加 `remove` 方法**

在 `seathunter/auth/uid_store.py` 的 `UidStore` 类末尾添加：

```python
    def remove(self, student_id: str) -> bool:
        """删除一条 UID 记录。

        Returns:
            是否成功删除
        """
        self.load()
        if student_id in self._data:
            del self._data[student_id]
            self.save()
            logger.info("UID 记录已删除: %s", student_id)
            return True
        return False
```

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat: UI 重构完成 — 5 个标签页按功能域分组

Co-Authored-By: Claude <noreply@anthropic.com>"
```
