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


def parse_amount(raw: str) -> int:
    """Accept 9000000, 9.000.000, 9tr, 1,5tr or 500k."""
    value = raw.strip().lower().replace(" ", "").replace("_", "")
    suffixes = (
        ("triệu", 1_000_000),
        ("trieu", 1_000_000),
        ("tr", 1_000_000),
        ("m", 1_000_000),
        ("nghìn", 1_000),
        ("nghin", 1_000),
        ("k", 1_000),
    )
    for suffix, factor in suffixes:
        if value.endswith(suffix):
            number = value[:-len(suffix)].replace(",", ".")
            if not re.fullmatch(r"\d+(?:\.\d+)?", number):
                raise ValueError(f"Giá trị tài nguyên không hợp lệ: {raw}")
            return round(float(number) * factor)
    digits = value.replace(",", "").replace(".", "")
    if not digits.isdigit():
        raise ValueError(f"Giá trị tài nguyên không hợp lệ: {raw}")
    return int(digits)


def build_settings(existing: dict, fields: dict, upgrade_walls: bool) -> dict:
    """Validate panel values and preserve settings not shown in the panel."""
    updated = existing.copy()
    labels = {
        "min_gold": "Gold tối thiểu",
        "min_elixir": "Elixir tối thiểu",
        "wall_resource": "Ngưỡng nâng tường",
    }
    for key, label in labels.items():
        amount = parse_amount(fields[key])
        if not 0 <= amount <= 1_000_000_000_000:
            raise ValueError(f"{label} phải từ 0 đến 1 nghìn tỷ.")
        updated[key] = amount
    for key, label, low, high in (
        ("min_farm", "Thời gian surrender tối thiểu", 0, 3600),
        ("star_target", "Số sao tối thiểu", 1, 3),
        ("farm_battle_timeout", "Thời gian trận tối đa", 1, 3600),
    ):
        raw = fields[key].strip()
        if not raw.isdigit() or not low <= int(raw) <= high:
            raise ValueError(f"{label} phải là số nguyên từ {low} đến {high}.")
        updated[key] = int(raw)
    for key, label, low, high in (
        ("electro_per_direction", "Electro mỗi hướng", 1, 9),
        ("warden_ability_delay", "Độ trễ kỹ năng cả đội", 0, 120),
    ):
        if key not in fields:
            continue
        raw = fields[key].strip()
        if not raw.isdigit() or not low <= int(raw) <= high:
            raise ValueError(f"{label} phải là số nguyên từ {low} đến {high}.")
        updated[key] = int(raw)
    if updated["farm_battle_timeout"] < updated["min_farm"]:
        raise ValueError(
            "Thời gian trận tối đa phải bằng hoặc lớn hơn thời gian surrender tối thiểu."
        )
    wall_type = fields["wall_type"]
    if wall_type not in ("gold", "elixir", "both"):
        raise ValueError("Loại tài nguyên nâng tường không hợp lệ.")
    updated["wall_type"] = wall_type
    updated["upgrade_walls"] = bool(upgrade_walls)
    updated["event_mode"] = not bool(upgrade_walls)
    priority = fields.get("event_resource_priority", existing.get("event_resource_priority", "dark"))
    if priority not in EVENT_RESOURCE_LABELS:
        raise ValueError("Tài nguyên ưu tiên cho bonus không hợp lệ.")
    updated["event_resource_priority"] = priority
    return updated


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
        self.settings = profile["settings"].copy()
        self.session = BotSession(self.serial)
        self.online = False
        self.last_result = None

        self.frame = ttk.Frame(owner.notebook, style="Panel.TFrame")
        self.frame.rowconfigure(0, weight=1)
        self.frame.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self.frame, bg=BG, highlightthickness=0, width=820, height=620
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            self.frame,
            orient="vertical",
            command=self.canvas.yview,
            style="Vertical.TScrollbar",
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.page = ttk.Frame(self.canvas, style="Panel.TFrame", padding=(14, 12))
        content = self.canvas.create_window((0, 0), window=self.page, anchor="nw")

        self.page.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(content, width=event.width),
        )

        # Smooth mousewheel scrolling
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.canvas.bind(
            "<Enter>",
            lambda _e: self.canvas.bind_all("<MouseWheel>", _on_mousewheel),
        )
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

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
        self.vars["min_gold"].set(f"{int(self.settings['min_gold']):,}")
        self.vars["min_elixir"].set(f"{int(self.settings['min_elixir']):,}")
        self.vars["wall_resource"].set(f"{int(self.settings['wall_resource']):,}")

        self.status = tk.StringVar(value="Đang dò ADB…")
        self.wall_count = tk.StringVar(value="0 viên")
        self.wall_mode = tk.BooleanVar(
            value=bool(self.settings.get("upgrade_walls", True))
            and not bool(self.settings.get("event_mode", False))
        )
        self.event_mode = tk.BooleanVar(value=not self.wall_mode.get())
        self.event_resource_display = tk.StringVar(
            value=EVENT_RESOURCE_LABELS.get(
                self.settings.get("event_resource_priority", "dark"), EVENT_RESOURCE_LABELS["dark"])
        )
        self.wall_type_display = tk.StringVar(
            value=WALL_TYPE_LABELS.get(self.vars["wall_type"].get(), "Gold và Elixir")
        )

        self._build_ui()

    def _build_ui(self):
        page = self.page
        page.columnconfigure(0, weight=3)
        page.columnconfigure(1, weight=2)
        page.rowconfigure(3, weight=1)

        # --------------------------------------------------------------------
        # 1. INSTANCE SUB-HEADER (Device Info & Live Status Pill)
        # --------------------------------------------------------------------
        header_bar = tk.Frame(page, bg=CARD_HEADER, padx=14, pady=10)
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
            text="⚙  CHẾ ĐỘ HOẠT ĐỘNG",
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
        stat_border = tk.Frame(right, bg=CARD_BORDER, padx=1, pady=1)
        stat_border.grid(row=8, column=0, sticky="ew")
        stat_tile = tk.Frame(stat_border, bg="#0d1424", padx=14, pady=12)
        stat_tile.pack(fill="x")

        stat_header = tk.Frame(stat_tile, bg="#0d1424")
        stat_header.pack(fill="x")
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
            font=("Segoe UI Bold", 26),
        )
        self.wall_label.pack(anchor="w", pady=(2, 0))

        tk.Label(
            stat_tile,
            text="Tự động phát hiện và nâng cấp trong phiên farm",
            bg="#0d1424",
            fg=DIM,
            font=("Segoe UI", 8),
        ).pack(anchor="w")

        self._mode_changed("wall" if self.wall_mode.get() else "event")

        # --------------------------------------------------------------------
        # 3. ACTION BAR (Save, Start, Stop, Remove)
        # --------------------------------------------------------------------
        actions = tk.Frame(page, bg=BG)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 10))

        self.save_button = ttk.Button(
            actions,
            text="💾  Lưu cấu hình",
            style="Secondary.TButton",
            command=self._save,
        )
        self.save_button.pack(side="left")

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
        log_border = tk.Frame(page, bg=CARD_BORDER, padx=1, pady=1)
        log_border.grid(row=3, column=0, columnspan=2, sticky="nsew")
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
        if source == "wall":
            self.wall_mode.set(True)
            self.event_mode.set(False)
        else:
            self.wall_mode.set(False)
            self.event_mode.set(True)
        self.wall_threshold.configure(
            state="normal" if self.wall_mode.get() else "disabled"
        )
        self.wall_type.configure(
            state="readonly" if self.wall_mode.get() else "disabled"
        )
        self.event_resource.configure(
            state="readonly" if self.event_mode.get() else "disabled"
        )

    def _save(self):
        fields = {key: value.get() for key, value in self.vars.items()}
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
            messagebox.showerror("Cấu hình không hợp lệ", str(exc), parent=self.root)
            return False
        self.settings = updated
        self._append_log("[Panel] Đã lưu cấu hình thành công.\n")
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
            if running or not self.online or not self.owner.license_valid
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
        if not self._save():
            return
        try:
            self.session.start(self.settings)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror("Không khởi động được bot", str(exc), parent=self.root)
            return
        self.last_result = None
        self.wall_count.set("0 viên")
        self.status.set("Đang kết nối ADB…")
        self._set_running(True)

    def _stop(self):
        self.session.stop()
        self.status.set("Đang dừng sau thao tác hiện tại…")
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
            kind = event.get("kind")
            if kind == "log":
                chunks.append(event.get("text", ""))
            elif kind == "status" and self.session.is_alive():
                if not (self.session.stop_event and self.session.stop_event.is_set()):
                    self.status.set(event.get("status", "Đang chạy"))
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
        self.log.configure(state="normal")
        for line in value.splitlines(keepends=True):
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
                tab.start_button.configure(
                    state="normal"
                    if tab.online and self.license_valid
                    else "disabled"
                )

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
                self.discovery_error = value
                for tab in self.tabs.values():
                    tab.set_online(False)
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
