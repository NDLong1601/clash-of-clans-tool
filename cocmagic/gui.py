"""Desktop control panel for CocMagic (Tkinter, no extra GUI dependency).

Modern, sleek, and high-performance dashboard for managing Clash of Clans
multi-instance bot sessions with real-time analytics, ADB auto-discovery,
and instant controls.
"""

import argparse
import ctypes
import multiprocessing
import os
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk

from PIL import Image, ImageTk

from cocmagic import config
from cocmagic.device_manager import discover_devices, normalize_serial
from cocmagic.instance_store import InstanceStore
from cocmagic.license_client import LicenseClient, LicenseError, normalize_key
from cocmagic.session_manager import BotSession


def format_run_details(event, selected_mode='main'):
    mode = config.RUN_MODE_LABELS.get(event.get('run_mode', selected_mode), selected_mode)
    village = config.RUN_MODE_LABELS.get(event.get('actual_village'), 'chưa xác nhận')
    progress = event.get('bonus_progress')
    state = event.get('builder_bonus_state')
    bonus = {'available':'còn sao', 'claimable':'chờ nhận thưởng',
             'complete':'đã xác nhận hết sao', 'unknown':'chưa xác nhận'}.get(state, 'chưa đọc')
    if progress is not None:
        bonus += f' ({progress[0]}/{progress[1]})'
    lines = [f'Chế độ: {mode} · Làng thực tế: {village} · Sao: {bonus}']
    reason = event.get('hybrid_reason') or event.get('switch_reason')
    if reason:
        lines.append('Lý do: '+reason)
    if event.get('run_mode') == 'hybrid':
        from datetime import datetime
        def local_time(value):
            try:
                return datetime.fromisoformat(value).strftime('%d/%m %H:%M:%S') if value else 'chưa có'
            except (TypeError, ValueError):
                return 'không hợp lệ'
        lines.append('Kiểm tra gần nhất: '+local_time(event.get('last_valid_bonus_check_at'))+
                     ' · Lịch tiếp: '+local_time(event.get('next_daily_check_at'))+' (UTC+7)')
        pending = event.get('pending_reason') or event.get('switch_target') or 'không'
        retry = local_time(event.get('next_retry_at'))
        lines.append(f'Pending: {pending} · Thử lại: {retry}')
        if event.get('builder_incomplete'):
            lines.append('Thưởng Làng đêm: chưa hoàn thành / cần kiểm tra lại')
        if event.get('last_error'):
            lines.append('Lỗi: '+event['last_error'])
    return '\n'.join(lines)

# Enable Windows High-DPI Awareness for razor-sharp typography and UI lines
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ============================================================================
# MODERN DESIGN SYSTEM PALETTE (Obsidian Slate + Cyber Sky / Emerald)
# ============================================================================
BG = "#0b0f19"              # Deep obsidian dark background
SURFACE = "#111827"         # Top header & toolbar container surface
CARD = "#161f30"            # Elevated card surface
CARD_BORDER = "#25334d"     # Crisp 1px card outline
CARD_HEADER = "#1a253a"     # Card top header container
FIELD = "#0c1322"           # Text entry & combobox background
FIELD_BORDER = "#2b3b57"    # Input borders
FIELD_FOCUS = "#38bdf8"     # Input focus border
TEXT = "#f8fafc"            # Primary text (crisp white)
MUTED = "#94a3b8"           # Secondary text (slate gray)
DIM = "#64748b"             # Captions & small hints
ACCENT = "#38bdf8"          # Vibrant sky blue / cyan
ACCENT_HOVER = "#0284c7"    # Deep cyan hover
ACCENT_BG = "#0c2842"       # Pill background for accent
SUCCESS = "#10b981"         # Vibrant emerald green
SUCCESS_HOVER = "#059669"   # Emerald hover
SUCCESS_BG = "#063726"      # Emerald soft badge background
WARNING = "#f59e0b"         # Amber gold
WARNING_BG = "#382405"      # Amber soft badge background
ERROR = "#f43f5e"           # Rose crimson red
ERROR_HOVER = "#e11d48"     # Rose hover
ERROR_BG = "#381018"        # Rose soft badge background
LOG_BG = "#070a14"          # Deep console terminal surface
LOG_FG = "#cbd5e1"          # Console default output

WALL_TYPE_LABELS = {
    "both": "Gold và Elixir",
    "gold": "Chỉ Gold",
    "elixir": "Chỉ Elixir",
}
EVENT_RESOURCE_LABELS = {
    "dark": "Dầu đen (Dark Elixir)",
    "elixir": "Dầu tím (Elixir)",
    "gold": "Vàng (Gold)",
}


def set_window_icon(window):
    """Set the modern window icon from the assets directory."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for icon_name in ("logobot.ico", "logolauncher.ico"):
        icon_path = os.path.join(base_dir, "assets", icon_name)
        if os.path.isfile(icon_path):
            try:
                window.iconbitmap(icon_path)
                return
            except Exception:
                pass


# Compatibility imports; the contract is shared with engine and CLI.
parse_amount = config.parse_amount
build_settings = config.build_settings


# ============================================================================
# MODERN LICENSE ACTIVATION MODAL
# ============================================================================
class LicenseDialog(tk.Toplevel):
    """Focused modern activation window with instant validation and character feedback."""

    def __init__(self, owner):
        super().__init__(owner.root)
        self.owner = owner
        self.title("Kích hoạt bản quyền · CocMagic Pro")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(owner.root)
        set_window_icon(self)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _event: self._close())
        self.key_var = tk.StringVar()
        self.revealed = False
        self.busy = False

        # Glowing accent header bar
        accent_strip = tk.Frame(self, bg=ACCENT, height=4)
        accent_strip.pack(fill="x")

        body = tk.Frame(self, bg=BG, padx=30, pady=24)
        body.pack(fill="both", expand=True)

        # Header Title with Icon Badge
        heading = tk.Frame(body, bg=BG)
        heading.pack(fill="x", pady=(0, 20))

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(base_dir, "assets", "logobot.png")
        if os.path.isfile(logo_path):
            try:
                lic_img = Image.open(logo_path).resize((44, 44), Image.Resampling.LANCZOS)
                self._lic_photo = ImageTk.PhotoImage(lic_img)
                badge = tk.Label(heading, image=self._lic_photo, bg=BG)
                badge.pack(side="left")
            except Exception:
                badge = tk.Label(
                    heading,
                    text="🔑",
                    bg=ACCENT_BG,
                    fg=ACCENT,
                    font=("Segoe UI", 16),
                    padx=12,
                    pady=8,
                )
                badge.pack(side="left")
        else:
            badge = tk.Label(
                heading,
                text="🔑",
                bg=ACCENT_BG,
                fg=ACCENT,
                font=("Segoe UI", 16),
                padx=12,
                pady=8,
            )
            badge.pack(side="left")

        heading_text = tk.Frame(heading, bg=BG)
        heading_text.pack(side="left", padx=(14, 0))
        tk.Label(
            heading_text,
            text="BẢN QUYỀN HỆ THỐNG",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 8),
        ).pack(anchor="w")
        tk.Label(
            heading_text,
            text="Kích hoạt CocMagic Pro",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI Bold", 16),
        ).pack(anchor="w", pady=(2, 0))

        tk.Label(
            body,
            text="Nhập khóa cấp phép (50 ký tự) để mở khóa toàn bộ tính năng tự động trên máy này.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
            wraplength=480,
            justify="left",
        ).pack(anchor="w", pady=(0, 18))

        # Input label row + character counter pill
        label_row = tk.Frame(body, bg=BG)
        label_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            label_row,
            text="MÃ KHÓA BẢN QUYỀN",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI Semibold", 9),
        ).pack(side="left")

        self.counter = tk.Label(
            label_row,
            text="0/50 ký tự",
            bg="#172338",
            fg=ACCENT,
            font=("Consolas", 8),
            padx=8,
            pady=2,
        )
        self.counter.pack(side="right")

        # Entry field container with subtle border
        border = tk.Frame(body, bg=CARD_BORDER, padx=1, pady=1)
        border.pack(fill="x")
        field = tk.Frame(border, bg=FIELD, padx=10, pady=6)
        field.pack(fill="x")

        self.entry = tk.Entry(
            field,
            textvariable=self.key_var,
            show="•",
            bg=FIELD,
            fg=TEXT,
            insertbackground=ACCENT,
            selectbackground="#0284c7",
            disabledbackground=FIELD,
            disabledforeground=MUTED,
            relief="flat",
            borderwidth=0,
            font=("Consolas", 11),
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)

        self.reveal_button = ttk.Button(
            field, text="Hiện", style="Inline.TButton", command=self._toggle_reveal
        )
        self.reveal_button.pack(side="right", padx=(8, 0))

        self.paste_button = ttk.Button(
            field, text="Dán", style="Inline.TButton", command=self._paste
        )
        self.paste_button.pack(side="right", padx=(6, 0))

        self.key_var.trace_add("write", self._key_changed)
        self.entry.bind("<Return>", lambda _event: self._activate())

        tk.Label(
            body,
            text="Định dạng: CM và 48 ký tự HEX. Bạn có thể dán trực tiếp mã có dấu gạch ngang.",
            bg=BG,
            fg=DIM,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(8, 0))

        # Status feedback pill container
        self.feedback_box = tk.Frame(body, bg="#111827", padx=10, pady=8)
        self.feedback_box.pack(fill="x", pady=(14, 0))
        self.feedback = tk.Label(
            self.feedback_box,
            text="Khóa bản quyền sẽ được lưu an toàn trên máy sau khi kích hoạt.",
            bg="#111827",
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.feedback.pack(fill="x")

        # Bottom Actions
        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x", pady=(22, 0))
        ttk.Button(
            actions, text="Để sau", style="Secondary.TButton", command=self._close
        ).pack(side="right")
        self.activate_button = ttk.Button(
            actions,
            text="Kích hoạt ngay",
            style="Accent.TButton",
            command=self._activate,
        )
        self.activate_button.pack(side="right", padx=(0, 10))

        self.update_idletasks()
        width, height = 560, max(420, self.winfo_reqheight() + 10)
        x = owner.root.winfo_rootx() + max(0, (owner.root.winfo_width() - width) // 2)
        y = owner.root.winfo_rooty() + max(0, (owner.root.winfo_height() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.grab_set()
        self.entry.focus_set()

    def _key_changed(self, *_args):
        compact = re.sub(r"[\s-]", "", self.key_var.get())
        self.counter.configure(text=f"{len(compact)}/50 ký tự")
        if not self.busy:
            self.feedback.configure(
                text="Khóa bản quyền sẽ được lưu an toàn trên máy sau khi kích hoạt.",
                fg=MUTED,
            )

    def _toggle_reveal(self):
        self.revealed = not self.revealed
        self.entry.configure(show="" if self.revealed else "•")
        self.reveal_button.configure(text="Ẩn" if self.revealed else "Hiện")

    def _paste(self):
        try:
            self.key_var.set(self.clipboard_get().strip())
            self.entry.icursor("end")
            self.entry.focus_set()
        except tk.TclError:
            self.feedback.configure(
                text="Bộ nhớ tạm chưa có nội dung để dán.", fg=WARNING
            )

    def _activate(self):
        if self.busy:
            return
        try:
            key = normalize_key(self.key_var.get())
        except LicenseError:
            self.feedback.configure(
                text="Định dạng chưa đúng. Khóa cần đủ 50 ký tự (CM + 48 ký tự).",
                fg=ERROR,
            )
            self.entry.focus_set()
            return
        if not self.owner._check_license(key, remember=True):
            self.feedback.configure(
                text="Đang kiểm tra khóa cấp phép, vui lòng đợi…", fg=WARNING
            )
            return
        self.busy = True
        self.entry.configure(state="disabled")
        self.activate_button.configure(state="disabled", text="Đang xác thực…")
        self.paste_button.configure(state="disabled")
        self.feedback.configure(
            text="Đang kết nối dịch vụ cấp phép máy chủ…", fg=WARNING
        )

    def show_error(self, error):
        self.busy = False
        self.entry.configure(state="normal")
        self.activate_button.configure(state="normal", text="Kích hoạt ngay")
        self.paste_button.configure(state="normal")
        self.feedback.configure(text=f"Lỗi: {error}", fg=ERROR)
        self.entry.focus_set()

    def _close(self):
        self.owner.license_dialog = None
        self.destroy()


# ============================================================================
# INSTANCE TAB (SINGLE EMULATOR WORKSPACE)
# ============================================================================
class InstanceTab:
    """The control panel scoped to one ADB serial and process with modern styling."""

    def __init__(self, owner, profile: dict):
        self.owner = owner
        self.root = owner.root
        self.serial = profile["serial"]
        self.name = profile["name"]
        self.settings = config.migrate_settings(profile["settings"])
        self.session = BotSession(self.serial)
        self.online = False
        self.last_result = None
        self._log_pending = ''
        self._last_log_line = None

        self.frame = ttk.Frame(owner.notebook, style="Panel.TFrame")
        self.frame.rowconfigure(0, weight=1)
        self.frame.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self.frame)
        self.notebook.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.notebook.enable_traversal()
        self.pages = {}
        self.canvases = {}
        for key, title in (("main", "Làng chính"), ("builder", "Làng đêm"), ("run", "Run")):
            shell = ttk.Frame(self.notebook, style="Panel.TFrame")
            self.notebook.add(shell, text=title)
            self.pages[key], self.canvases[key] = self._scroll_page(shell)
        self.page = self.pages["main"]
        self.canvas = self.canvases["main"]
        # Scope wheel/focus handling to this instance, without bind_all/unbind_all.
        self._wheel_binding = self.root.bind("<MouseWheel>", self._mousewheel, add="+")
        self._focus_binding = self.root.bind("<FocusIn>", self._focus_visible, add="+")

        self.inputs = []
        self.vars = {}
        for key in (
            "min_gold",
            "min_elixir",
            "min_farm",
            "star_target",
            "farm_battle_timeout",
            "wall_resource",
            "wall_type",
            "electro_per_direction",
            "warden_ability_delay",
        ):
            self.vars[key] = tk.StringVar(value=str(self.settings.get(key, 0)))
        for key in config.MAIN_AMOUNT_FIELDS:
            value = self.settings[key]
            self.vars[key].set(f"{value:,}" if type(value) is int else str(value))
        for key in ("run_mode", "builder_deploy_mode", "hybrid_check_time", "hybrid_timezone"):
            self.vars[key] = tk.StringVar(value=str(self.settings[key]))
        for key in (*config.BUILDER_BOOL_FIELDS, "camera_auto_adjust"):
            self.vars[key] = tk.BooleanVar(value=self.settings[key])
        self.run_mode = self.vars["run_mode"]

        self.status = tk.StringVar(value="Đang dò ADB…")
        self.wall_count = tk.StringVar(value="0 viên")
        self.run_details = tk.StringVar(value="Làng thực tế: chưa xác nhận · Sao: chưa đọc")
        self.wall_mode = tk.BooleanVar(
            value=bool(self.settings.get("upgrade_walls", True))
            and not bool(self.settings.get("event_mode", False))
        )
        self.event_mode = tk.BooleanVar(value=bool(self.settings["event_mode"]))
        self.event_resource_display = tk.StringVar(
            value=EVENT_RESOURCE_LABELS.get(
                self.settings.get("event_resource_priority", "dark"), EVENT_RESOURCE_LABELS["dark"])
        )
        self.wall_type_display = tk.StringVar(
            value=WALL_TYPE_LABELS.get(self.vars["wall_type"].get(), "Gold và Elixir")
        )

        self._build_ui()
        self._build_builder_ui()
        self._build_run_modes()
        self.save_button = ttk.Button(
            self.frame, text="Lưu cấu hình cả ba tab", style="Secondary.TButton", command=self._save)
        self.save_button.grid(row=1, column=0, sticky="w", padx=14, pady=8)
        self.inputs.append(self.save_button)
        self.save_state = tk.StringVar(value='Đã đọc cấu hình')
        ttk.Label(self.frame, textvariable=self.save_state, style='Muted.TLabel',
                  wraplength=380).grid(row=1, column=1, sticky='e', padx=14, pady=8)
        for variable in (*self.vars.values(), self.wall_mode, self.event_mode,
                         self.event_resource_display, self.wall_type_display):
            variable.trace_add('write', lambda *_: self.save_state.set('Có thay đổi chưa lưu'))
        self._run_mode_changed()

    def _scroll_page(self, shell):
        shell.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)
        canvas = tk.Canvas(shell, bg=BG, highlightthickness=0, width=820, height=500,
                           takefocus=False)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        page = ttk.Frame(canvas, style="Panel.TFrame", padding=(14, 12))
        content = canvas.create_window((0, 0), window=page, anchor="nw")

        def resize(_event):
            canvas.itemconfigure(content, width=canvas.winfo_width(),
                                 height=max(page.winfo_reqheight(), canvas.winfo_height()))
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", resize)
        page.bind("<Configure>", resize)
        return page, canvas

    def _page_for_widget(self, widget):
        while widget is not None:
            # Text has its own wheel scrolling. Leave it to the Tk class binding.
            if widget is getattr(self, "log", None):
                return None
            for key, page in self.pages.items():
                if widget is page or widget is self.canvases[key]:
                    return key
            widget = getattr(widget, "master", None)
        return None

    def _mousewheel(self, event):
        key = self._page_for_widget(event.widget)
        if key is not None and event.delta:
            units = -int(event.delta / 120) or (-1 if event.delta > 0 else 1)
            self.canvases[key].yview_scroll(units, "units")
            return "break"

    def _focus_visible(self, event):
        # Tk also delivers FocusIn to ancestor frames/canvases when entering a
        # notebook page. Scrolling those would jump to the bottom of the page.
        if event.widget.winfo_class() not in (
                "TEntry", "TCombobox", "TCheckbutton", "TRadiobutton", "TButton"):
            return
        key = self._page_for_widget(event.widget)
        if key is None:
            return
        canvas = self.canvases[key]
        widget = event.widget
        top = widget.winfo_rooty() - canvas.winfo_rooty()
        bottom = top + widget.winfo_height()
        height = canvas.winfo_height()
        shift = top - 8 if top < 0 else (bottom - height + 8 if bottom > height else 0)
        if shift:
            bounds = canvas.bbox("all")
            if bounds and bounds[3]:
                canvas.yview_moveto((canvas.canvasy(0) + shift) / bounds[3])

    def _build_builder_ui(self):
        page = self.pages["builder"]
        page.columnconfigure(0, weight=1)
        card = tk.Frame(page, bg=FIELD, padx=16, pady=14)
        card.grid(row=0, column=0, sticky="ew")
        tk.Label(card, text="LÀNG ĐÊM · RỒNG CON VÀ HAI KHU", bg=FIELD,
                 fg=ACCENT, font=("Segoe UI Bold", 10)).pack(anchor="w", pady=(0, 8))
        tk.Label(card, text=("Train Làng đêm độc lập · English 1600×900 · tiếp tục dù hết sao."
                            if 'builder' in config.AVAILABLE_RUN_MODES else
                            "Train Làng đêm đang kiểm chứng GĐ5. Có thể lưu cấu hình; Start chưa mở."),
                 bg=FIELD, fg=MUTED, font=("Segoe UI", 9), wraplength=700,
                 justify="left").pack(anchor="w", pady=(0, 12))
        for key, title in (
            ("builder_auto_setup_baby_dragons", "Tự thiết lập Rồng con cho các ô quân và tiếp viện khả dụng"),
            ("builder_use_available_hero", "Dùng tướng khi sẵn sàng; không chờ tướng đang nâng cấp"),
            ("builder_collect_cart", "Thu phần tài nguyên khả dụng trong Xe Tiên dược"),
        ):
            widget = ttk.Checkbutton(card, text=title, variable=self.vars[key],
                                     style="Mode.TCheckbutton")
            widget.pack(anchor="w", pady=5)
            self.inputs.append(widget)
        tk.Label(card, text="Cách thả Rồng con", bg=FIELD, fg=TEXT,
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(14, 4))
        for key, title in (("around", "Thả xung quanh"),
                           ("single_point", "Thả toàn bộ tại một điểm hợp lệ")):
            widget = ttk.Radiobutton(card, text=title, value=key,
                                     variable=self.vars["builder_deploy_mode"],
                                     style="Mode.TRadiobutton")
            widget.pack(anchor="w", pady=4)
            self.inputs.append(widget)
        tk.Label(card, text="Kỹ năng quân và tướng được xử lý tự động theo trạng thái thực tế.",
                 bg=FIELD, fg=MUTED, font=("Segoe UI", 9), wraplength=700,
                 justify="left").pack(anchor="w", pady=(8, 14))
        schedule = tk.Frame(card, bg=FIELD)
        schedule.pack(fill="x")
        tk.Label(schedule, text="Giờ kiểm tra khi chạy kết hợp", bg=FIELD, fg=TEXT,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 12))
        check_time = ttk.Entry(schedule, textvariable=self.vars["hybrid_check_time"], width=7)
        check_time.pack(side="left")
        self.inputs.append(check_time)
        tk.Label(schedule, text="  UTC+7 · Asia/Ho_Chi_Minh", bg=FIELD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Label(card, text="Mặc định 15:30 hằng ngày (UTC+7). Startup luôn kiểm tra thưởng trên màn hình thật.",
                 bg=FIELD, fg=MUTED, font=("Segoe UI", 9), wraplength=700,
                 justify="left").pack(anchor="w", pady=(6, 14))
        camera = ttk.Checkbutton(card, text="Tự điều chỉnh camera (English 1600×900; mặc định tắt)",
                                 variable=self.vars["camera_auto_adjust"], style="Mode.TCheckbutton")
        camera.pack(anchor="w", pady=4)
        self.inputs.append(camera)

    def _build_run_modes(self):
        box = tk.Frame(self.pages["run"], bg=FIELD, padx=14, pady=10)
        box.grid(row=1, column=0, sticky="ew")
        tk.Label(box, text="CHẾ ĐỘ CHẠY", bg=FIELD, fg=ACCENT,
                 font=("Segoe UI Bold", 10)).pack(anchor="w", pady=(0, 4))
        self.mode_buttons = {}
        for key, title in config.RUN_MODE_LABELS.items():
            suffix = " · chưa khả dụng" if key not in config.AVAILABLE_RUN_MODES else ""
            widget = ttk.Radiobutton(box, text=title + suffix, value=key,
                                     variable=self.run_mode, style="Mode.TRadiobutton")
            widget.pack(anchor="w", pady=3)
            self.inputs.append(widget)
            self.mode_buttons[key] = widget
        self.mode_hint = tk.StringVar()
        tk.Label(box, textvariable=self.mode_hint, bg=FIELD, fg=MUTED, justify="left",
                 font=("Segoe UI", 9), wraplength=700).pack(anchor="w", pady=(8, 0))
        self.run_mode.trace_add("write", self._run_mode_changed)

    def _run_mode_changed(self, *_args):
        mode = self.run_mode.get()
        available = mode in config.AVAILABLE_RUN_MODES
        self.mode_hint.set(("Train Làng đêm liên tục; kỹ năng theo trạng thái thật, hết sao vẫn train."
                            if mode == 'builder' else
                            "Startup kiểm tra thưởng Làng đêm, sau đó ưu tiên Làng chính. Lịch 15:30 UTC+7; "
                            "đến hạn giữa trận sẽ chờ điểm chuyển an toàn."
                            if mode == 'hybrid' else
                            "Chạy luồng Làng chính hiện có. Cấu hình bị khóa trong phiên chạy.")
                           if available else "Chế độ đã chọn chưa khả dụng trong bản này. "
                           "Có thể lưu cấu hình; chỉ bắt đầu khi chế độ được hỗ trợ.")
        if available and not self.session.is_alive() and self.status.get() == "Chế độ chưa khả dụng":
            self.status.set("Sẵn sàng" if self.online else "Giả lập chưa kết nối")
        self.start_button.configure(state="normal" if available and self.online and
                                    self.owner.license_valid and not self.session.is_alive()
                                    else "disabled")

    def _build_ui(self):
        page = self.page
        run = self.pages["run"]
        run.columnconfigure(0, weight=1)
        run.rowconfigure(4, weight=1)
        page.columnconfigure(0, weight=3)
        page.columnconfigure(1, weight=2)
        page.rowconfigure(3, weight=1)

        # --------------------------------------------------------------------
        # 1. INSTANCE SUB-HEADER (Device Info & Live Status Pill)
        # --------------------------------------------------------------------
        header_bar = tk.Frame(run, bg=CARD_HEADER, padx=14, pady=10)
        header_bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # Device info left
        dev_left = tk.Frame(header_bar, bg=CARD_HEADER)
        dev_left.pack(side="left")
        tk.Label(
            dev_left, text="🖥", bg=CARD_HEADER, fg=ACCENT, font=("Segoe UI", 12)
        ).pack(side="left", padx=(0, 6))
        tk.Label(
            dev_left,
            text=f"{self.name}",
            bg=CARD_HEADER,
            fg=TEXT,
            font=("Segoe UI Bold", 12),
        ).pack(side="left")
        tk.Label(
            dev_left,
            text=f" · {self.serial}",
            bg=CARD_HEADER,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(side="left")

        # Live Status Capsule right
        self.status_pill = tk.Label(
            header_bar,
            text=f"⏳  {self.status.get()}",
            bg=WARNING_BG,
            fg=WARNING,
            font=("Segoe UI Semibold", 9),
            padx=10,
            pady=3,
        )
        self.status_pill.pack(side="right")
        self.status.trace_add("write", self._update_status_pill)

        # --------------------------------------------------------------------
        # 2. TWO-COLUMN CARD GRID
        # --------------------------------------------------------------------
        # Left Card: FARMING & ATTACK TACTICS
        left_border = tk.Frame(page, bg=CARD_BORDER, padx=1, pady=1)
        left_border.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        left = tk.Frame(left_border, bg=CARD, padx=16, pady=14)
        left.pack(fill="both", expand=True)
        left.columnconfigure(1, weight=1)

        # Right Card: WALL UPGRADE & LIVE SESSION STATS
        right_border = tk.Frame(page, bg=CARD_BORDER, padx=1, pady=1)
        right_border.grid(row=1, column=1, sticky="nsew")
        right = tk.Frame(right_border, bg=CARD, padx=16, pady=14)
        right.pack(fill="both", expand=True)
        right.columnconfigure(0, weight=1)

        # --- LEFT CARD CONTENT ---
        row = 0
        # Group 1: Resource Filter
        tk.Label(
            left,
            text="💰  LỌC TÀI NGUYÊN MỤC TIÊU",
            bg=CARD,
            fg=ACCENT,
            font=("Segoe UI Bold", 10),
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 6))
        row += 1
        row = self._entry(
            left, row, "Vàng (Gold) tối thiểu", "min_gold", hint="Ví dụ: 800k, 1.2tr"
        )
        row = self._entry(
            left, row, "Dầu (Elixir) tối thiểu", "min_elixir", hint="Ví dụ: 800k, 1.2tr"
        )
        tk.Label(
            left,
            text="💡 Chỉ cần Gold HOẶC Elixir đạt ngưỡng là tấn công; nhập 0 để bỏ qua.",
            bg=CARD,
            fg=DIM,
            font=("Segoe UI", 8),
            wraplength=380,
            justify="left",
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 10))
        row += 1

        # Divider
        tk.Frame(left, bg=CARD_BORDER, height=1).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(4, 10)
        )
        row += 1

        # Group 2: Smart Surrender
        tk.Label(
            left,
            text="⏱  ĐIỀU KIỆN RÚT LUI AN TOÀN",
            bg=CARD,
            fg=ACCENT,
            font=("Segoe UI Bold", 10),
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 6))
        row += 1
        row = self._entry(
            left, row, "Thời gian trong trận tối thiểu", "min_farm", unit="giây"
        )
        row = self._entry(
            left, row, "Số sao tối thiểu cần đạt", "star_target", unit="sao (1–3)"
        )
        row = self._entry(
            left, row, "Giới hạn thời gian trận tối đa", "farm_battle_timeout", unit="giây"
        )
        tk.Label(
            left,
            text="💡 Đạt đủ thời gian VÀ số sao sẽ rút lui; giới hạn trận là phương án an toàn.",
            bg=CARD,
            fg=DIM,
            font=("Segoe UI", 8),
            wraplength=380,
            justify="left",
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 10))
        row += 1

        # Divider
        tk.Frame(left, bg=CARD_BORDER, height=1).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(4, 10)
        )
        row += 1

        # Group 3: Attack Tactics
        tk.Label(
            left,
            text="⚔  CHIẾN THUẬT ELECTRO DRAGON",
            bg=CARD,
            fg=ACCENT,
            font=("Segoe UI Bold", 10),
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 6))
        row += 1
        row = self._entry(
            left, row, "Electro mỗi hướng thả", "electro_per_direction", unit="con (1–9)"
        )
        row = self._entry(
            left, row, "Warden và cả đội bật sau", "warden_ability_delay", unit="giây"
        )

        # --- RIGHT CARD CONTENT ---
        # Group 1: Operational Mode
        tk.Label(
            right,
            text="⚙  CHẾ ĐỘ LÀNG CHÍNH",
            bg=CARD,
            fg=ACCENT,
            font=("Segoe UI Bold", 10),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        mode_box = tk.Frame(right, bg=FIELD, padx=10, pady=8)
        mode_box.grid(row=1, column=0, sticky="ew")

        wall_check = ttk.Checkbutton(
            mode_box,
            text="Nâng tường khi farm (Khuyên dùng)",
            variable=self.wall_mode,
            command=lambda: self._mode_changed("wall"),
            style="Mode.TCheckbutton",
        )
        wall_check.pack(anchor="w", pady=2)

        event_check = ttk.Checkbutton(
            mode_box,
            text="Đánh sự kiện · không nâng tường",
            variable=self.event_mode,
            command=lambda: self._mode_changed("event"),
            style="Mode.TCheckbutton",
        )
        event_check.pack(anchor="w", pady=2)
        self.inputs.extend((wall_check, event_check))
        tk.Label(mode_box, text="Ưu tiên bonus tài nguyên", bg=FIELD, fg=TEXT,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 3))
        self.event_resource = ttk.Combobox(
            mode_box, textvariable=self.event_resource_display,
            values=list(EVENT_RESOURCE_LABELS.values()), state="readonly", width=25)
        self.event_resource.pack(fill="x")
        self.inputs.append(self.event_resource)
        tk.Label(mode_box, text="Tự chọn bonus khi bảng xuất hiện; bỏ qua bonus lính.",
                 bg=FIELD, fg=MUTED, font=("Segoe UI", 8), wraplength=310,
                 justify="left").pack(anchor="w", pady=(4, 0))

        # Group 2: Wall Threshold & Resource Type
        tk.Label(
            right,
            text="Bắt đầu nâng tường khi kho đạt",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI Semibold", 9),
        ).grid(row=2, column=0, sticky="w", pady=(14, 4))

        self.wall_threshold = ttk.Entry(right, textvariable=self.vars["wall_resource"])
        self.wall_threshold.grid(row=3, column=0, sticky="ew")
        self.inputs.append(self.wall_threshold)

        tk.Label(
            right,
            text="Ví dụ: 9.000.000 hoặc 9tr; Gold hoặc Elixir đạt là nâng.",
            bg=CARD,
            fg=DIM,
            font=("Segoe UI", 8),
            wraplength=270,
            justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(3, 10))

        tk.Label(
            right,
            text="Tài nguyên dùng để nâng",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI Semibold", 9),
        ).grid(row=5, column=0, sticky="w", pady=(0, 4))

        self.wall_type = ttk.Combobox(
            right,
            textvariable=self.wall_type_display,
            values=tuple(WALL_TYPE_LABELS.values()),
            state="readonly",
        )
        self.wall_type.grid(row=6, column=0, sticky="ew")
        self.inputs.append(self.wall_type)

        # Divider
        tk.Frame(right, bg=CARD_BORDER, height=1).grid(
            row=7, column=0, sticky="ew", pady=(14, 12)
        )

        # Group 3: Real-Time Session KPI Stat Tile
        stat_border = tk.Frame(run, bg=CARD_BORDER, padx=1, pady=1)
        stat_border.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        stat_tile = tk.Frame(stat_border, bg="#0d1424", padx=14, pady=8)
        stat_tile.pack(fill="x")

        stat_header = tk.Frame(stat_tile, bg="#0d1424")
        stat_header.pack(side="left")
        tk.Label(
            stat_header, text="🧱", bg="#0d1424", fg=SUCCESS, font=("Segoe UI", 12)
        ).pack(side="left")
        tk.Label(
            stat_header,
            text=" TƯỜNG ĐÃ NÂNG TRONG PHIÊN",
            bg="#0d1424",
            fg=SUCCESS,
            font=("Segoe UI Bold", 8),
        ).pack(side="left")

        self.wall_label = tk.Label(
            stat_tile,
            textvariable=self.wall_count,
            bg="#0d1424",
            fg="#52d6a4",
            font=("Segoe UI Bold", 18),
        )
        self.wall_label.pack(side="right")
        tk.Label(stat_border, textvariable=self.run_details, bg=CARD, fg=TEXT,
                 font=("Segoe UI", 9), justify="left", anchor="w", wraplength=730,
                 padx=14, pady=8).pack(fill="x")

        self._sync_main_inputs()

        # --------------------------------------------------------------------
        # 3. ACTION BAR (Save, Start, Stop, Remove)
        # --------------------------------------------------------------------
        actions = tk.Frame(run, bg=BG)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 10))

        self.start_button = ttk.Button(
            actions,
            text="▶  Bắt đầu bot",
            style="Accent.TButton",
            command=self._start,
            state="disabled",
        )
        self.start_button.pack(side="left", padx=8)

        self.stop_button = ttk.Button(
            actions,
            text="⏹  Dừng bot",
            style="Danger.TButton",
            command=self._stop,
            state="disabled",
        )
        self.stop_button.pack(side="left")

        ttk.Button(
            actions,
            text="✕  Quên giả lập",
            style="Secondary.TButton",
            command=self._remove,
        ).pack(side="right")

        # --------------------------------------------------------------------
        # 4. LIVE CONSOLE / LOG TERMINAL
        # --------------------------------------------------------------------
        log_border = tk.Frame(run, bg=CARD_BORDER, padx=1, pady=1)
        log_border.grid(row=4, column=0, sticky="nsew")
        log_border.rowconfigure(1, weight=1)
        log_border.columnconfigure(0, weight=1)

        log_card = tk.Frame(log_border, bg=CARD, padx=14, pady=10)
        log_card.pack(fill="both", expand=True)
        log_card.rowconfigure(1, weight=1)
        log_card.columnconfigure(0, weight=1)

        # Log Top Toolbar
        log_header = tk.Frame(log_card, bg=CARD)
        log_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        tk.Label(
            log_header,
            text="🖥  NHẬT KÝ HOẠT ĐỘNG (LIVE CONSOLE)",
            bg=CARD,
            fg=ACCENT,
            font=("Segoe UI Bold", 9),
        ).pack(side="left")

        ttk.Button(
            log_header,
            text="🧹 Xóa log",
            style="Inline.TButton",
            command=self._clear_log,
        ).pack(side="right")
        ttk.Button(
            log_header,
            text="📋 Sao chép log",
            style="Inline.TButton",
            command=self._copy_log,
        ).pack(side="right", padx=(0, 8))

        # Scrolled text terminal
        self.log = scrolledtext.ScrolledText(
            log_card,
            wrap="word",
            bg=LOG_BG,
            fg=LOG_FG,
            insertbackground=ACCENT,
            selectbackground="#0284c7",
            selectforeground=TEXT,
            relief="flat",
            borderwidth=0,
            font=("Consolas", 9),
            state="disabled",
            height=7,
        )
        self.log.grid(row=1, column=0, sticky="nsew")

        # Tag configurations for rich colored log outputs
        self.log.tag_config("ok", foreground="#34d399")
        self.log.tag_config("err", foreground="#f87171")
        self.log.tag_config("warn", foreground="#fbbf24")
        self.log.tag_config("info", foreground="#38bdf8")
        self.log.tag_config("engine", foreground="#c084fc")

    def _entry(self, parent, row, label, key, unit=None, hint=None):
        lbl = tk.Label(parent, text=label, bg=CARD, fg=TEXT, font=("Segoe UI", 9))
        lbl.grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))

        entry_frame = tk.Frame(parent, bg=CARD)
        entry_frame.grid(row=row, column=1, sticky="ew", pady=4)
        entry_frame.columnconfigure(0, weight=1)

        entry = ttk.Entry(entry_frame, textvariable=self.vars[key], width=14)
        entry.grid(row=0, column=0, sticky="ew")
        self.inputs.append(entry)

        if unit:
            tk.Label(
                entry_frame, text=f" {unit}", bg=CARD, fg=MUTED, font=("Segoe UI", 8)
            ).grid(row=0, column=1, sticky="w")
        return row + 1

    def _update_status_pill(self, *_args):
        val = self.status.get().lower()
        if any(k in val for k in ("đang chạy", "train", "farm", "battle", "tấn công")):
            bg_col, fg_col = SUCCESS_BG, SUCCESS
            icon = "⚡"
        elif "sẵn sàng" in val:
            bg_col, fg_col = ACCENT_BG, ACCENT
            icon = "●"
        elif any(k in val for k in ("lỗi", "bất thường", "không kết nối")):
            bg_col, fg_col = ERROR_BG, ERROR
            icon = "✕"
        elif any(k in val for k in ("đã dừng", "offline", "chưa kết nối")):
            bg_col, fg_col = "#1e293b", MUTED
            icon = "○"
        else:
            bg_col, fg_col = WARNING_BG, WARNING
            icon = "⏳"
        self.status_pill.configure(
            text=f"{icon}  {self.status.get()}", bg=bg_col, fg=fg_col
        )

    def _mode_changed(self, source):
        if self.session.is_alive():
            return
        if source == "wall":
            self.wall_mode.set(True)
            self.event_mode.set(False)
        else:
            self.wall_mode.set(False)
            self.event_mode.set(True)
        self._sync_main_inputs()

    def _sync_main_inputs(self):
        running = self.session.is_alive()
        self.wall_threshold.configure(
            state="normal" if self.wall_mode.get() and not running else "disabled"
        )
        self.wall_type.configure(
            state="readonly" if self.wall_mode.get() and not running else "disabled"
        )
        self.event_resource.configure(
            state="readonly" if self.event_mode.get() and not running else "disabled"
        )

    def _save(self):
        if self.session.is_alive():
            return False
        fields = {key: value.get() for key, value in self.vars.items()}
        fields["event_mode"] = self.event_mode.get()
        fields["wall_type"] = next(
            (
                key
                for key, label in WALL_TYPE_LABELS.items()
                if label == self.wall_type_display.get()
            ),
            "",
        )
        fields["event_resource_priority"] = next(
            (key for key, label in EVENT_RESOURCE_LABELS.items()
             if label == self.event_resource_display.get()), "")
        try:
            updated = build_settings(self.settings, fields, self.wall_mode.get())
            self.owner.store.update_settings(self.serial, updated)
        except (ValueError, OSError, KeyError) as exc:
            self.save_state.set('Lưu thất bại: '+str(exc))
            self._append_log(f'[Panel] Lưu cấu hình {self.serial} thất bại: {exc}\n')
            messagebox.showerror("Cấu hình không hợp lệ", str(exc), parent=self.root)
            return False
        self.settings = updated
        self.save_state.set('Đã lưu cả ba tab · '+config.RUN_MODE_LABELS[updated['run_mode']])
        self._append_log(f"[Panel] Đã lưu cấu hình {self.serial} thành công.\n")
        return True

    def _set_running(self, running):
        for widget in self.inputs:
            widget.configure(state="disabled" if running else "normal")
        if not running:
            self.event_resource.configure(
                state="readonly" if self.event_mode.get() else "disabled"
            )
            self.wall_type.configure(
                state="readonly" if self.wall_mode.get() else "disabled"
            )
            self.wall_threshold.configure(
                state="normal" if self.wall_mode.get() else "disabled"
            )
        self.save_button.configure(state="disabled" if running else "normal")
        self.start_button.configure(
            state="disabled"
            if running or not self.online or not self.owner.license_valid or
            self.run_mode.get() not in config.AVAILABLE_RUN_MODES
            else "normal"
        )
        self.stop_button.configure(state="normal" if running else "disabled")

    def _start(self):
        if not self.online or self.session.is_alive():
            return
        if not self.owner.license_valid:
            messagebox.showerror(
                "Chưa có quyền sử dụng",
                "Hãy nhập key hợp lệ trước khi chạy bot.",
                parent=self.root,
            )
            return
        try:
            config.require_available_mode(self.run_mode.get())
        except ValueError as exc:
            self.notebook.select(2)
            self._append_log(f"[Panel] {exc}\n")
            self.status.set("Chế độ chưa khả dụng")
            return
        if not self._save():
            return
        try:
            self.session.start(self.settings)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror("Không khởi động được bot", str(exc), parent=self.root)
            return
        self.last_result = None
        self.notebook.select(2)
        self.wall_count.set("0 viên")
        self.status.set("Đang kết nối ADB…")
        self._set_running(True)

    def _stop(self):
        self.session.stop()
        self.status.set("Đang dừng · chờ command hiện tại và release…")
        self.run_details.set('Stop không gửi batch mới. Timeout command ADB 15s; cleanup có thể thêm 6–9s. '
                             'Chụp ảnh tối đa 10s/command; probe/pinch tối đa 5s/command.')
        self.stop_button.configure(state="disabled")

    def _remove(self):
        if self.session.is_alive():
            messagebox.showinfo(
                "Giả lập đang chạy",
                "Hãy dừng bot trước khi quên giả lập.",
                parent=self.root,
            )
            return
        if self.online:
            messagebox.showinfo(
                "Giả lập đang mở",
                "Hãy đóng giả lập trước khi quên tab này.",
                parent=self.root,
            )
            return
        try:
            self.owner.store.remove(self.serial)
        except OSError as exc:
            messagebox.showerror("Không lưu được", str(exc), parent=self.root)
            return
        self.owner.notebook.forget(self.frame)
        self.root.unbind("<MouseWheel>", self._wheel_binding)
        self.root.unbind("<FocusIn>", self._focus_binding)
        self.frame.destroy()
        del self.owner.tabs[self.serial]
        self.owner._show_empty_state()
        self.owner._update_summary()

    def set_online(self, online: bool):
        if self.online == online:
            return
        self.online = online
        if not online and self.session.is_alive():
            self.session.stop()
            self.status.set("Mất kết nối ADB; đang dừng bot…")
        elif not self.session.is_alive():
            self.status.set("Sẵn sàng" if online else "Giả lập chưa kết nối")
            self._set_running(False)
        tab_prefix = "⚡ " if self.session.is_alive() else ("🟢 " if online else "⚪ ")
        self.owner.notebook.tab(
            self.frame, text=f"{tab_prefix}{self.name}" + ("" if online else " · offline")
        )

    def poll(self):
        chunks = []
        for event in self.session.poll():
            if event.get('serial', self.serial) != self.serial:
                continue
            kind = event.get("kind")
            if kind == "log":
                chunks.append(event.get("text", ""))
            elif kind == "status" and self.session.is_alive():
                if not (self.session.stop_event and self.session.stop_event.is_set()):
                    self.status.set(event.get("status", "Đang chạy"))
                    self.run_details.set(format_run_details(event, self.run_mode.get()))
                self.wall_count.set(f"{event.get('wall_count', 0)} viên")
            elif kind == "done":
                self.last_result = event
            elif kind == "exited":
                if self.last_result is None:
                    self.status.set(f"Worker dừng bất thường (mã {event.get('code')})")
                    chunks.append("[Panel] Worker kết thúc mà không gửi trạng thái cuối.\n")
                elif self.last_result.get("stopped"):
                    self.status.set("Đã dừng")
                elif self.last_result.get("ok"):
                    self.status.set("Đã dừng")
                else:
                    self.status.set("Bot dừng do lỗi; xem nhật ký")
                self._set_running(False)
        if chunks:
            self._append_log("".join(chunks))

    def _append_log(self, value: str):
        value = self._log_pending + value
        parts = value.splitlines(keepends=True)
        self._log_pending = ''
        if parts and not parts[-1].endswith(('\n', '\r')):
            self._log_pending = parts.pop()[-8000:]
        self.log.configure(state="normal")
        for line in parts:
            if line == self._last_log_line:
                continue
            self._last_log_line = line
            lower = line.lower()
            if any(k in lower for k in ("[ok]", "thành công", "success")):
                tag = "ok"
            elif any(k in lower for k in ("[error]", "[lỗi]", "fail", "thất bại")):
                tag = "err"
            elif any(k in lower for k in ("[warn]", "cảnh báo")):
                tag = "warn"
            elif any(k in lower for k in ("[adb]", "device")):
                tag = "engine"
            elif any(k in lower for k in ("[panel]", "[engine]", "[bot]")):
                tag = "info"
            else:
                tag = None
            if tag:
                self.log.insert("end", line, tag)
            else:
                self.log.insert("end", line)

        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 2500:
            self.log.delete("1.0", f"{lines - 2000}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _copy_log(self):
        text = self.log.get("1.0", "end-1c")
        if text.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(text)

    def _clear_log(self):
        self._log_pending = ''
        self._last_log_line = None
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")


# ============================================================================
# BOT PANEL (MAIN APPLICATION WINDOW)
# ============================================================================
class BotPanel:
    def __init__(self, root: tk.Tk, initial_port: int = None):
        self.root = root
        self.root.title("CocMagic Pro · Trung tâm điều khiển tự động")
        set_window_icon(self.root)

        width, height = 980, min(840, root.winfo_screenheight() - 44)
        x = max(0, (root.winfo_screenwidth() - width) // 2)
        y = max(0, (root.winfo_screenheight() - height - 45) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(880, 680)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.license_client = LicenseClient.from_config()
        self.license_valid = not self.license_client.policy.enabled
        self.license_events = queue.SimpleQueue()
        self.license_checking = False
        self.license_retry = False
        self.license_last_ok = None
        self.license_expires_at = None
        self.license_expiry_deadline = None
        self.license_next_check = 0.0
        self.license_dialog = None
        self.discovery_events = queue.SimpleQueue()

        self.store = InstanceStore(
            os.path.join(
                os.path.dirname(os.path.abspath(config.SETTINGS_FILE)), "instances.json"
            ),
            config.load_settings(),
        )
        self.store.load()
        self.tabs = {}
        self.discovering = False
        self.refresh_job = None
        self.discovery_error = None
        self.closing = False
        self.close_started = None
        self.force_prompted = False
        self._logo_photo = None

        self._build_style()
        self._build_ui()

        for profile in self.store.instances.values():
            self._add_tab(profile)
        if initial_port is not None:
            serial = normalize_serial(initial_port)
            self._add_tab(self.store.add(serial))
            self.notebook.select(self.tabs[serial].frame)

        self._refresh()
        self.root.after(150, self._poll)
        if self.license_client.policy.enabled:
            self._check_license()

    def _build_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        # Dropdown popup styling
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_HOVER)
        self.root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
        self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 9))

        # Base Frame & Label styles
        style.configure("Panel.TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("Hero.TFrame", background=SURFACE)

        style.configure(
            "Panel.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10)
        )
        style.configure(
            "Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9)
        )
        style.configure(
            "Hero.TLabel", background=SURFACE, foreground=TEXT, font=("Segoe UI", 10)
        )
        style.configure(
            "HeroMuted.TLabel", background=SURFACE, foreground=MUTED, font=("Segoe UI", 9)
        )
        style.configure(
            "Card.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI", 9)
        )
        style.configure(
            "CardMuted.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9)
        )
        style.configure(
            "Hint.TLabel", background=CARD, foreground=DIM, font=("Segoe UI", 8)
        )
        style.configure(
            "Section.TLabel",
            background=CARD,
            foreground=ACCENT,
            font=("Segoe UI Bold", 10),
        )
        style.configure(
            "Title.TLabel",
            background=SURFACE,
            foreground=TEXT,
            font=("Segoe UI Bold", 20),
        )
        style.configure(
            "Eyebrow.TLabel",
            background=SURFACE,
            foreground=ACCENT,
            font=("Segoe UI Semibold", 8),
        )
        style.configure(
            "Instance.TLabel",
            background=BG,
            foreground=TEXT,
            font=("Segoe UI Bold", 13),
        )
        style.configure(
            "Count.TLabel",
            background=CARD,
            foreground=SUCCESS,
            font=("Segoe UI Bold", 28),
        )

        # Entry inputs
        style.configure(
            "TEntry",
            padding=6,
            fieldbackground=FIELD,
            foreground=TEXT,
            insertcolor=ACCENT,
            bordercolor=FIELD_BORDER,
            lightcolor=FIELD_BORDER,
            darkcolor=FIELD_BORDER,
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", ACCENT)],
            lightcolor=[("focus", ACCENT)],
            darkcolor=[("focus", ACCENT)],
            foreground=[("disabled", DIM)],
        )

        # Combobox
        style.configure(
            "TCombobox",
            padding=6,
            fieldbackground=FIELD,
            foreground=TEXT,
            background=CARD_HEADER,
            arrowcolor=ACCENT,
            bordercolor=FIELD_BORDER,
            lightcolor=FIELD_BORDER,
            darkcolor=FIELD_BORDER,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", FIELD)],
            foreground=[("readonly", TEXT), ("disabled", DIM)],
            bordercolor=[("focus", ACCENT)],
        )

        # Buttons
        style.configure(
            "TButton",
            font=("Segoe UI Semibold", 9),
            padding=(14, 7),
            background="#1e293b",
            foreground=TEXT,
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "TButton",
            background=[("active", "#334155"), ("disabled", "#141c2b")],
            foreground=[("disabled", "#475569")],
        )

        style.configure("Secondary.TButton", background="#1e293b", foreground=TEXT)
        style.map(
            "Secondary.TButton",
            background=[("active", "#334155"), ("disabled", "#141c2b")],
            foreground=[("disabled", "#475569")],
        )

        style.configure(
            "Inline.TButton",
            background="#1c2538",
            foreground=ACCENT,
            font=("Segoe UI Semibold", 8),
            padding=(6, 3),
        )
        style.map(
            "Inline.TButton",
            background=[("active", "#25334d")],
            foreground=[("active", "#8be3fb"), ("disabled", DIM)],
        )

        style.configure("Accent.TButton", background="#0284c7", foreground="#ffffff")
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT), ("disabled", "#1e293b")],
            foreground=[("active", BG), ("disabled", "#475569")],
        )

        style.configure("Danger.TButton", background="#9f1239", foreground="#ffe4e6")
        style.map(
            "Danger.TButton",
            background=[("active", ERROR), ("disabled", "#1e293b")],
            foreground=[("active", "#ffffff"), ("disabled", "#475569")],
        )

        # Checkbutton
        style.configure(
            "Mode.TCheckbutton",
            background=FIELD,
            foreground=TEXT,
            font=("Segoe UI", 9),
        )
        style.map(
            "Mode.TCheckbutton",
            background=[("active", FIELD)],
            foreground=[("disabled", DIM)],
        )
        style.configure("Mode.TRadiobutton", background=FIELD, foreground=TEXT,
                        font=("Segoe UI", 9))
        style.map("Mode.TRadiobutton", background=[("active", FIELD)],
                  foreground=[("disabled", DIM)])

        # Notebook Tabs
        style.configure(
            "TNotebook",
            background=BG,
            borderwidth=0,
            relief="flat",
            bordercolor=BG,
            lightcolor=BG,
            darkcolor=BG,
        )
        style.configure(
            "TNotebook.Tab",
            background="#111827",
            foreground=MUTED,
            padding=(18, 9),
            font=("Segoe UI Semibold", 9),
            borderwidth=0,
            bordercolor=BG,
            lightcolor=BG,
            darkcolor=BG,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", CARD), ("active", "#1e2638")],
            foreground=[("selected", ACCENT), ("active", TEXT)],
        )

        # Modern Scrollbar
        style.configure(
            "Vertical.TScrollbar",
            background="#1e293b",
            troughcolor=BG,
            bordercolor=BG,
            arrowcolor=MUTED,
            relief="flat",
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", "#334155"), ("pressed", ACCENT)],
        )
        style.configure("TSeparator", background=CARD_BORDER)

    def _build_ui(self):
        page = ttk.Frame(self.root, style="Panel.TFrame", padding=(16, 14))
        page.pack(fill="both", expand=True)
        page.rowconfigure(3, weight=1)
        page.columnconfigure(0, weight=1)

        # --------------------------------------------------------------------
        # 1. TOP HEADER / BRAND HERO BANNER
        # --------------------------------------------------------------------
        header_border = tk.Frame(page, bg=CARD_BORDER, padx=1, pady=1)
        header_border.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        header = tk.Frame(header_border, bg=SURFACE, padx=16, pady=12)
        header.pack(fill="x")

        # App Brand Left
        brand = tk.Frame(header, bg=SURFACE)
        brand.pack(side="left")

        # Try loading brand logo
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(base_dir, "assets", "logobot.png")
        if os.path.isfile(logo_path):
            try:
                img = Image.open(logo_path).resize((46, 46), Image.Resampling.LANCZOS)
                self._logo_photo = ImageTk.PhotoImage(img)
                logo_lbl = tk.Label(brand, image=self._logo_photo, bg=SURFACE)
                logo_lbl.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        brand_text = tk.Frame(brand, bg=SURFACE)
        brand_text.pack(side="left")

        title_row = tk.Frame(brand_text, bg=SURFACE)
        title_row.pack(anchor="w")
        tk.Label(
            title_row, text="CocMagic", bg=SURFACE, fg=TEXT, font=("Segoe UI Bold", 16)
        ).pack(side="left")
        tk.Label(
            title_row,
            text="PRO v2.5",
            bg=ACCENT_BG,
            fg=ACCENT,
            font=("Segoe UI Bold", 8),
            padx=6,
            pady=1,
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            brand_text,
            text="Hệ Thống Tự Động Hóa Clash of Clans Đa Giả Lập",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(1, 0))

        # Real-time Status Chips Right
        stats_box = tk.Frame(header, bg=SURFACE)
        stats_box.pack(side="right")

        self.summary = tk.StringVar(value="Đang dò giả lập…")

        self.sim_pill = tk.Label(
            stats_box,
            text="📱  0 Giả lập",
            bg="#172338",
            fg=TEXT,
            font=("Segoe UI Semibold", 9),
            padx=10,
            pady=4,
        )
        self.sim_pill.pack(side="left", padx=(0, 6))

        self.bot_pill = tk.Label(
            stats_box,
            text="⚡  0 Đang chạy",
            bg="#172338",
            fg=MUTED,
            font=("Segoe UI Semibold", 9),
            padx=10,
            pady=4,
        )
        self.bot_pill.pack(side="left")

        # --------------------------------------------------------------------
        # 2. LICENSE BANNER (Optional Pilot Licensing)
        # --------------------------------------------------------------------
        if self.license_client.policy.enabled:
            lic_border = tk.Frame(page, bg=CARD_BORDER, padx=1, pady=1)
            lic_border.grid(row=1, column=0, sticky="ew", pady=(0, 10))

            license_bar = tk.Frame(lic_border, bg=CARD, padx=14, pady=9)
            license_bar.pack(fill="x")

            license_info = tk.Frame(license_bar, bg=CARD)
            license_info.pack(side="left", fill="x", expand=True)

            self.license_dot = tk.Label(
                license_info, text="●", bg=CARD, fg=WARNING, font=("Segoe UI", 13)
            )
            self.license_dot.pack(side="left", padx=(0, 8))

            license_copy = tk.Frame(license_info, bg=CARD)
            license_copy.pack(side="left", fill="x", expand=True)

            tk.Label(
                license_copy,
                text="TRẠNG THÁI BẢN QUYỀN",
                bg=CARD,
                fg=ACCENT,
                font=("Segoe UI Bold", 8),
            ).pack(anchor="w")

            self.license_status = tk.StringVar(value="Đang kiểm tra key…")
            tk.Label(
                license_copy,
                textvariable=self.license_status,
                bg=CARD,
                fg=TEXT,
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=(1, 0))

            ttk.Button(
                license_bar,
                text="🔑 Nhập / đổi key",
                style="Accent.TButton",
                command=self._enter_license,
            ).pack(side="right", padx=(8, 0))

            self.copy_btn = ttk.Button(
                license_bar,
                text="📋 Sao chép mã máy",
                style="Secondary.TButton",
                command=self._copy_machine_id,
            )
            self.copy_btn.pack(side="right")

        # --------------------------------------------------------------------
        # 3. TOOLBAR (Multi-Instance Action Bar)
        # --------------------------------------------------------------------
        toolbar = tk.Frame(page, bg=BG)
        toolbar.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        tb_left = tk.Frame(toolbar, bg=BG)
        tb_left.pack(side="left")

        tk.Label(
            tb_left,
            text="DANH SÁCH GIẢ LẬP",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI Bold", 9),
        ).pack(side="left")

        self.instance_count_badge = tk.Label(
            tb_left,
            text="0",
            bg=CARD,
            fg=ACCENT,
            font=("Segoe UI Bold", 8),
            padx=6,
            pady=1,
        )
        self.instance_count_badge.pack(side="left", padx=(6, 0))

        # Right Action Buttons
        ttk.Button(
            toolbar,
            text="⏹ Dừng tất cả",
            style="Danger.TButton",
            command=self._stop_all,
        ).pack(side="right")
        ttk.Button(
            toolbar,
            text="▶ Chạy tất cả",
            style="Accent.TButton",
            command=self._start_all,
        ).pack(side="right", padx=(0, 6))
        ttk.Button(
            toolbar,
            text="➕ Thêm cổng ADB",
            style="Secondary.TButton",
            command=self._add_port,
        ).pack(side="right", padx=(0, 6))
        ttk.Button(
            toolbar,
            text="🔄 Quét lại",
            style="Secondary.TButton",
            command=self._refresh,
        ).pack(side="right", padx=(0, 6))

        # --------------------------------------------------------------------
        # 4. NOTEBOOK & EMPTY STATE
        # --------------------------------------------------------------------
        self.notebook = ttk.Notebook(page)
        self.notebook.grid(row=3, column=0, sticky="nsew")

        # Empty Tab Screen
        self.empty_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=24)
        self.empty_tab.columnconfigure(0, weight=1)
        self.empty_tab.rowconfigure(0, weight=1)

        empty_border = tk.Frame(self.empty_tab, bg=CARD_BORDER, padx=1, pady=1)
        empty_border.grid(row=0, column=0)

        welcome = tk.Frame(empty_border, bg=CARD, padx=36, pady=32)
        welcome.pack()

        if os.path.isfile(logo_path):
            try:
                welcome_img = Image.open(logo_path).resize((76, 76), Image.Resampling.LANCZOS)
                self._welcome_logo = ImageTk.PhotoImage(welcome_img)
                tk.Label(welcome, image=self._welcome_logo, bg=CARD).pack(pady=(0, 10))
            except Exception:
                tk.Label(welcome, text="⚡", bg=CARD, fg=ACCENT, font=("Segoe UI", 32)).pack(pady=(0, 8))
        else:
            tk.Label(welcome, text="⚡", bg=CARD, fg=ACCENT, font=("Segoe UI", 32)).pack(pady=(0, 8))

        tk.Label(
            welcome,
            text="CHÀO MỪNG ĐẾN COCMAGIC",
            bg=CARD,
            fg=ACCENT,
            font=("Segoe UI Bold", 9),
        ).pack()

        tk.Label(
            welcome,
            text="Chưa phát hiện giả lập nào",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI Bold", 18),
        ).pack(pady=(4, 8))

        guide_text = (
            "1. Khởi động giả lập MuMu Player hoặc LDPlayer.\n"
            "2. Đảm bảo cổng ADB đã được bật trong cài đặt giả lập (cổng 16384 hoặc 5555).\n"
            "3. Nhấn 'Quét lại giả lập' bên dưới hoặc thêm cổng kết nối thủ công."
        )
        tk.Label(
            welcome,
            text=guide_text,
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            justify="left",
        ).pack(pady=(0, 20))

        welcome_actions = tk.Frame(welcome, bg=CARD)
        welcome_actions.pack()

        ttk.Button(
            welcome_actions,
            text="🔄  Quét lại ngay",
            style="Accent.TButton",
            command=self._refresh,
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            welcome_actions,
            text="➕  Thêm cổng ADB",
            style="Secondary.TButton",
            command=self._add_port,
        ).pack(side="left")

        self._show_empty_state()

    def _show_empty_state(self):
        empty_id = str(self.empty_tab)
        if self.tabs:
            if empty_id in self.notebook.tabs():
                self.notebook.forget(self.empty_tab)
        elif empty_id not in self.notebook.tabs():
            self.notebook.add(self.empty_tab, text="Bắt đầu")

    def _set_license_visual(self, color):
        if hasattr(self, "license_dot") and self.license_dot.winfo_exists():
            self.license_dot.configure(fg=color)

    def _copy_machine_id(self):
        try:
            identifier = self.license_client.device_id
        except LicenseError as error:
            messagebox.showerror("Không đọc được mã máy", str(error), parent=self.root)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(identifier)
        previous = self.license_status.get()
        self.license_status.set("Đã sao chép mã máy")
        if hasattr(self, "copy_btn"):
            self.copy_btn.configure(text="✓ Đã sao chép!")
            self.root.after(
                2000, lambda: self.copy_btn.configure(text="📋 Sao chép mã máy")
            )
        self.root.after(
            2500,
            lambda: self.license_status.set(previous)
            if self.license_status.get() == "Đã sao chép mã máy"
            else None,
        )

    def _enter_license(self):
        if self.license_dialog is not None and self.license_dialog.winfo_exists():
            self.license_dialog.lift()
            self.license_dialog.entry.focus_set()
            return
        self.license_dialog = LicenseDialog(self)

    def _check_license(self, key=None, *, remember=False):
        if self.license_checking or self.closing:
            return False
        self.license_checking = True
        self.license_status.set("Đang kiểm tra key…")
        self._set_license_visual(WARNING)

        def check():
            try:
                result = self.license_client.check(key, remember=remember)
                self.license_events.put((result, None, remember))
            except LicenseError as error:
                self.license_events.put((None, error, remember))

        threading.Thread(
            target=check, name="CocMagic-license-check", daemon=True
        ).start()
        return True

    def _license_result(self, result, error, candidate):
        self.license_checking = False
        if self.closing:
            return
        if error and candidate:
            self.license_status.set(
                "Key hiện tại vẫn hợp lệ"
                if self.license_valid
                else "Chưa kích hoạt · kiểm tra lại key"
            )
            self._set_license_visual(SUCCESS if self.license_valid else ERROR)
            if self.license_dialog is not None and self.license_dialog.winfo_exists():
                self.license_dialog.show_error(error)
            return
        if result is not None:
            self.license_valid = True
            self.license_retry = False
            self.license_last_ok = time.monotonic()
            self.license_expires_at = result.expires_at
            self.license_expiry_deadline = (
                None
                if result.expires_at is None
                else self.license_last_ok + result.expires_at - result.server_time
            )
            self.license_next_check = (
                self.license_last_ok
                + self.license_client.policy.check_interval_seconds
            )
            self.license_status.set(result.label())
            self._set_license_visual(SUCCESS)
            if (
                candidate
                and self.license_dialog is not None
                and self.license_dialog.winfo_exists()
            ):
                self.license_dialog._close()
        elif (
            error.temporary
            and self.license_valid
            and self.license_last_ok is not None
            and time.monotonic() - self.license_last_ok
            <= self.license_client.policy.offline_grace_seconds
            and (
                self.license_expiry_deadline is None
                or time.monotonic() < self.license_expiry_deadline
            )
        ):
            self.license_retry = True
            self.license_next_check = time.monotonic() + 60
            self.license_status.set(
                "Mất kết nối dịch vụ key; đang dùng thời gian ân hạn"
            )
            self._set_license_visual(WARNING)
        else:
            self.license_valid = False
            self.license_retry = bool(error.temporary)
            self.license_next_check = time.monotonic() + 60
            self.license_status.set(str(error))
            self._set_license_visual(ERROR)
            self._stop_all()
        for tab in self.tabs.values():
            if not tab.session.is_alive():
                tab._run_mode_changed()

    def _add_tab(self, profile):
        serial = profile["serial"]
        if serial in self.tabs:
            return self.tabs[serial]
        tab = InstanceTab(self, profile)
        self.tabs[serial] = tab
        self._show_empty_state()
        self.notebook.add(tab.frame, text=f"⚪ {tab.name} · offline")
        self._update_summary()
        return tab

    def _add_port(self):
        value = simpledialog.askstring(
            "Thêm cổng ADB",
            "Nhập cổng MuMu Player hoặc LDPlayer (ví dụ 16416 hoặc 5555):",
            parent=self.root,
        )
        if value is None:
            return
        try:
            serial = normalize_serial(value)
            tab = self._add_tab(self.store.add(serial))
        except (ValueError, OSError) as exc:
            messagebox.showerror("Cổng không hợp lệ", str(exc), parent=self.root)
            return
        self.notebook.select(tab.frame)
        self._refresh()

    def _refresh(self):
        if self.closing or self.discovering:
            return
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
            self.refresh_job = None
        self.discovering = True
        serials = tuple(self.store.instances)

        def scan():
            try:
                devices = discover_devices(config.ADB_PATH, serials)
                self.discovery_events.put(("devices", devices))
            except Exception as exc:
                self.discovery_events.put(("error", str(exc)))

        threading.Thread(target=scan, name="CocMagic-ADB-scan", daemon=True).start()

    def _start_all(self):
        if not self.license_valid:
            messagebox.showerror(
                "Chưa có quyền sử dụng",
                "Hãy nhập key hợp lệ trước khi chạy bot.",
                parent=self.root,
            )
            return
        for tab in self.tabs.values():
            if tab.online and not tab.session.is_alive():
                tab._start()
        self._update_summary()

    def _stop_all(self):
        for tab in self.tabs.values():
            if tab.session.is_alive():
                tab._stop()

    def _on_close(self):
        if any(tab.session.is_alive() for tab in self.tabs.values()):
            self.closing = True
            self.close_started = time.monotonic()
            self.force_prompted = False
            self._stop_all()
        else:
            self.root.destroy()

    def _update_summary(self):
        if hasattr(self, "instance_count_badge"):
            self.instance_count_badge.configure(text=str(len(self.tabs)))
        if self.discovery_error:
            self.summary.set(f"Lỗi dò ADB: {self.discovery_error}")
            return
        online = sum(tab.online for tab in self.tabs.values())
        running = sum(tab.session.is_alive() for tab in self.tabs.values())
        self.summary.set(f"{online} giả lập · {running} bot đang chạy")

        if hasattr(self, "sim_pill"):
            self.sim_pill.configure(
                text=f"📱  {online}/{len(self.tabs)} Giả lập",
                bg="#172338" if online == 0 else "#0c2842",
                fg=TEXT if online > 0 else MUTED,
            )
        if hasattr(self, "bot_pill"):
            self.bot_pill.configure(
                text=f"⚡  {running} Đang chạy",
                bg=SUCCESS_BG if running > 0 else "#172338",
                fg=SUCCESS if running > 0 else MUTED,
            )

    def _poll(self):
        if self.license_client.policy.enabled:
            try:
                while True:
                    result, error, candidate = self.license_events.get_nowait()
                    self._license_result(result, error, candidate)
            except queue.Empty:
                pass
            if (
                self.license_valid
                and self.license_expiry_deadline is not None
                and time.monotonic() >= self.license_expiry_deadline
            ):
                self._license_result(None, LicenseError("expired"), False)
            if (
                (self.license_valid or self.license_retry)
                and not self.license_checking
                and time.monotonic() >= self.license_next_check
            ):
                self._check_license()
        for _ in range(10):
            try:
                kind, value = self.discovery_events.get_nowait()
            except queue.Empty:
                break
            self.discovering = False
            if self.closing:
                continue
            if kind == "devices":
                self.discovery_error = None
                online = {device.serial for device in value}
                for serial in online:
                    try:
                        self._add_tab(self.store.add(serial))
                    except OSError as exc:
                        messagebox.showerror(
                            "Không lưu được giả lập", str(exc), parent=self.root
                        )
                        continue
                for serial, tab in self.tabs.items():
                    tab.set_online(serial in online)
            else:
                previous_error = self.discovery_error
                self.discovery_error = value
                if value != previous_error:
                    for tab in self.tabs.values():
                        tab._append_log(f'[Panel] Scan ADB lỗi, giữ trạng thái instance: {value}\n')
            if not self.closing:
                self.refresh_job = self.root.after(5000, self._refresh)
        for tab in list(self.tabs.values()):
            tab.poll()
        if not self.closing:
            self._update_summary()
        elif not any(tab.session.is_alive() for tab in self.tabs.values()):
            self.root.destroy()
            return
        elif (
            not self.force_prompted
            and self.close_started is not None
            and time.monotonic() - self.close_started > 20
        ):
            self.force_prompted = True
            if messagebox.askyesno(
                "Bot chưa dừng",
                "Một bot chưa dừng sau 20 giây. Buộc đóng worker và thoát?",
                parent=self.root,
            ):
                for tab in self.tabs.values():
                    tab.session.terminate()
                self.root.destroy()
                return
            self.closing = False
            self.close_started = None
        self.root.after(150, self._poll)


def main():
    multiprocessing.freeze_support()
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CocMagic.Bot")
        except (AttributeError, OSError):
            pass
    parser = argparse.ArgumentParser(description="CocMagic control panel")
    parser.add_argument("--port", "-p", type=int, default=None)
    parser.add_argument("--settings", "-s", default=None)
    args = parser.parse_args()
    if args.settings:
        config.SETTINGS_FILE = args.settings
    root = tk.Tk()
    try:
        BotPanel(root, initial_port=args.port)
    except (ValueError, OSError, LicenseError) as exc:
        messagebox.showerror("Không mở được bảng điều khiển", str(exc), parent=root)
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
