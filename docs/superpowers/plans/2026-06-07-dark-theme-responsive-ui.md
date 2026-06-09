# 深色主题 + 响应式 UI 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 GUI 应用深色主题样式，增大窗口尺寸，统一字体和间距。

**Architecture:** 在 `gui.py` 的 `__init__` 中新增 `_setup_style()` 方法配置 ttk.Style，修改窗口尺寸参数，调整各 Tab 中控件的 height/padding/font 参数。所有改动集中在 `seathunter/ui/gui.py` 一个文件。

**Tech Stack:** Python 3, tkinter, ttk.Style

---

## 文件变更总览

| 操作 | 文件 | 职责 |
|------|------|------|
| **修改** | `seathunter/ui/gui.py` | 添加 `_setup_style`、修改窗口尺寸、更新控件参数 |

---

### Task 1: 深色主题 + 响应式 UI

**Files:**
- Modify: `seathunter/ui/gui.py`

- [ ] **Step 1: 添加颜色常量和 `_setup_style` 方法**

在 `gui.py` 文件顶部（`class GuiApp` 之前）添加颜色常量：

```python
# ── 深色主题配色 ──
BG = "#1e1e2e"          # 主背景
SURFACE = "#313244"      # 表面（卡片/框架）
BORDER = "#45475a"       # 边框
TEXT = "#cdd6f4"         # 主文字
TEXT_DIM = "#a6adc8"     # 次要文字
BLUE = "#89b4fa"         # 强调蓝
GREEN = "#a6e3a1"        # 成功绿
RED = "#f38ba8"          # 错误红
YELLOW = "#f9e2af"       # 警告黄
SELECT_BG = "#45475a"    # 选中行背景
FONT_FAMILY = "SF Pro Text"  # macOS 字体
MONO_FONT = "Menlo"          # macOS 等宽字体
```

在 `GuiApp` 类的 `__init__` 方法中，`self.root = root` 之后、`self.root.title(...)` 之前，添加调用：

```python
self._setup_style()
```

在 `GuiApp` 类中添加 `_setup_style` 方法（放在 `__init__` 之后）：

```python
def _setup_style(self):
    """配置深色主题样式"""
    style = ttk.Style()
    style.theme_use("clam")

    # ── 全局 ──
    style.configure(".", background=BG, foreground=TEXT,
                     fieldbackground=SURFACE, bordercolor=BORDER,
                     font=(FONT_FAMILY, 10))

    # ── TFrame / TLabel ──
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("TLabelFrame", background=BG, foreground=BLUE,
                     bordercolor=BORDER)
    style.configure("TLabelFrame.Label", background=BG, foreground=BLUE,
                     font=(FONT_FAMILY, 10, "bold"))

    # ── TButton ──
    style.configure("TButton", background=BORDER, foreground=TEXT,
                     bordercolor=BORDER, padding=(8, 4))
    style.map("TButton",
              background=[("active", BLUE), ("pressed", BLUE)],
              foreground=[("active", BG), ("pressed", BG)])

    # ── TEntry / TSpinbox / TCombobox ──
    style.configure("TEntry", fieldbackground=SURFACE, foreground=TEXT,
                     insertcolor=TEXT, bordercolor=BORDER)
    style.configure("TSpinbox", fieldbackground=SURFACE, foreground=TEXT,
                     arrowcolor=TEXT, bordercolor=BORDER)
    style.configure("TCombobox", fieldbackground=SURFACE, foreground=TEXT,
                     arrowcolor=TEXT, bordercolor=BORDER)
    style.map("TCombobox",
              fieldbackground=[("readonly", SURFACE)],
              foreground=[("readonly", TEXT)])

    # ── TNotebook (Tab) ──
    style.configure("TNotebook", background=BG, bordercolor=BORDER)
    style.configure("TNotebook.Tab", background=BG, foreground=TEXT_DIM,
                     padding=(12, 6))
    style.map("TNotebook.Tab",
              background=[("selected", SURFACE)],
              foreground=[("selected", BLUE)])

    # ── Treeview ──
    style.configure("Treeview", background=SURFACE, foreground=TEXT,
                     fieldbackground=SURFACE, bordercolor=BORDER,
                     rowheight=28, font=(FONT_FAMILY, 10))
    style.configure("Treeview.Heading", background=BORDER, foreground=TEXT,
                     font=(FONT_FAMILY, 10, "bold"))
    style.map("Treeview",
              background=[("selected", SELECT_BG)],
              foreground=[("selected", TEXT)])

    # ── Scrollbar ──
    style.configure("TScrollbar", background=SURFACE, troughcolor=BG,
                     bordercolor=BORDER, arrowcolor=TEXT_DIM)

    # ── Separator ──
    style.configure("TSeparator", background=BORDER)

    # ── Progressbar ──
    style.configure("TProgressbar", background=BLUE, troughcolor=SURFACE,
                     bordercolor=BORDER)

    # ── Checkbutton ──
    style.configure("TCheckbutton", background=BG, foreground=TEXT)
    style.map("TCheckbutton",
              background=[("active", BG)])

    # ── Radiobutton ──
    style.configure("TRadiobutton", background=BG, foreground=TEXT)
    style.map("TRadiobutton",
              background=[("active", BG)])

    # ── tk.Text 和 tk.Tk 需要单独配置（非 ttk）──
    self.root.configure(bg=BG)
```

- [ ] **Step 2: 修改窗口尺寸**

找到 `self.root.geometry("900x650")` 和 `self.root.minsize(800, 550)`，改为：

```python
self.root.geometry("1200x800")
self.root.minsize(1000, 700)
```

- [ ] **Step 3: 更新 Treeview height**

找到所有 `height=5` 或 `height=6` 的 Treeview 创建，改为 `height=8`：

- `self.plans_tree` 的 `height=5` → `height=8`
- `self.schedules_tree` 的 `height=5` → `height=8`
- `self.friends_tree` 的 `height=6` → `height=8`

- [ ] **Step 4: 更新 tk.Text 控件的深色样式**

找到所有 `tk.Text(...)` 创建，在其后添加颜色配置：

**booking_log:**
```python
self.booking_log = tk.Text(log_frame, height=6, wrap=tk.WORD, state=tk.DISABLED,
                           font=(MONO_FONT, 10), bg=SURFACE, fg=TEXT,
                           insertbackground=TEXT, selectbackground=SELECT_BG,
                           relief=tk.FLAT, bd=0)
```

**dashboard bookings_text:**
```python
self._dash_bookings_text = tk.Text(bookings_frame, height=4, wrap=tk.WORD,
                                    state=tk.DISABLED, font=(MONO_FONT, 10),
                                    bg=SURFACE, fg=TEXT,
                                    insertbackground=TEXT, selectbackground=SELECT_BG,
                                    relief=tk.FLAT, bd=0)
```

**help_text:**
```python
help_text = tk.Text(help_frame, wrap=tk.WORD, state=tk.DISABLED, height=8,
                    bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                    selectbackground=SELECT_BG, relief=tk.FLAT, bd=0,
                    font=(MONO_FONT, 10))
```

- [ ] **Step 5: 更新 booking_log 的 tag 颜色**

找到 `tag_configure` 调用，更新颜色值：

```python
for tag, color in [("success", GREEN), ("error", RED),
                   ("info", BLUE), ("warning", YELLOW)]:
    self.booking_log.tag_configure(tag, foreground=color)
```

- [ ] **Step 6: 更新 LabelFrame padding**

找到所有 `padding=5` 的 LabelFrame 创建，改为 `padding=8`。

- [ ] **Step 7: 更新日志字体**

找到 `booking_log` 的 `font=("Consolas", 9)` 或 `font=("Menlo", 9)`，统一为 `font=(MONO_FONT, 10)`。

- [ ] **Step 8: 语法检查**

```bash
.venv/bin/python3 -c "import ast; ast.parse(open('seathunter/ui/gui.py').read()); print('OK')"
```

- [ ] **Step 9: 提交**

```bash
git add seathunter/ui/gui.py
git commit -m "深色主题 + 响应式 UI：ttk.Style 深色配置、1200x800 窗口、统一字体间距"
```
