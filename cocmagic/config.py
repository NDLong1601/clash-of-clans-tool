#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CocMagic — config.py
Toàn bộ cấu hình mặc định. Người dùng chỉnh settings.json, không sửa file này.
"""

import os
import json
import re
from copy import deepcopy

# ═══════════════════════════════════════════════════════════
#  ĐƯỜNG DẪN GỐC
# ═══════════════════════════════════════════════════════════

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR  = os.path.join(BASE_DIR, "assets")
DATA_DIR    = os.path.join(BASE_DIR, "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# ═══════════════════════════════════════════════════════════
#  ADB — MuMu Player 12
# ═══════════════════════════════════════════════════════════

# ADB của MuMu Player 12 (nx_main/adb.exe)
ADB_PATH    = r"C:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe"
ADB_HOST    = "127.0.0.1"

# MuMu Player 12: instance đầu tiên = 16384, tiếp theo = 16384+32=16416, ...
# Để 0 → bot sẽ tự scan port khi khởi động
ADB_PORT    = 0

# Thứ tự scan: MuMu 12 ưu tiên, sau đó fallback MuMu 6 + LDPlayer + BlueStacks
ADB_SCAN_PORTS = [
    16384, 16416, 16448, 16480,   # MuMu Player 12 (instance 0,1,2,3)
    7555,                          # MuMu Player 6 / older
    5555, 5556, 5575, 5585,        # BlueStacks / LDPlayer fallback
]

# ═══════════════════════════════════════════════════════════
#  MÀN HÌNH ANDROID (BlueStacks resolution)
# ═══════════════════════════════════════════════════════════

ANDROID_W = 1600
ANDROID_H = 900

# ═══════════════════════════════════════════════════════════
#  TEMPLATE MATCHING
# ═══════════════════════════════════════════════════════════

DEFAULT_THRESHOLD    = 0.80   # Ngưỡng tin cậy mặc định (0-1)
STRICT_THRESHOLD     = 0.88   # Cho các nút quan trọng (confirm, okay)
LOOSE_THRESHOLD      = 0.70   # Cho nhận diện trạng thái

SCREENSHOT_TIMEOUT   = 10     # seconds
ADB_COMMAND_TIMEOUT  = 15     # seconds

# ═══════════════════════════════════════════════════════════
#  TIMING (seconds)
# ═══════════════════════════════════════════════════════════

DELAY_AFTER_TAP       = 0.3
DELAY_AFTER_SWIPE     = 0.5
DELAY_MAIN_LOOP       = 0.25
DELAY_FIND_MATCH      = 3.0    # Chờ sau khi tìm trận
DELAY_BATTLE_CHECK    = 1.0    # Kiểm tra kỹ năng, lỗi mạng và kết thúc trận
DELAY_DEPLOY_TROOP    = 0.08   # Giữa các lần thả quân (giây)
DELAY_BETWEEN_HEROES  = 0.5

# ═══════════════════════════════════════════════════════════
#  DEFAULTS (sẽ bị ghi đè bởi settings.json)
# ═══════════════════════════════════════════════════════════

DEFAULT_SETTINGS = {
    # Dual-village settings schema (instances.json keeps wrapper version 1).
    "settings_schema_version": 2,
    "run_mode": "main",
    "builder_deploy_mode": "around",
    "builder_auto_setup_baby_dragons": True,
    "builder_use_available_hero": True,
    "builder_collect_cart": True,
    "builder_prepare_timeout": 75,
    "builder_battle_timeout": 540,
    "builder_transition_timeout": 35,
    "builder_no_progress_timeout": 90,
    "builder_point_retries": 4,
    "builder_baby_ability_delay": 1.0,
    "builder_hero_ability_interval": 8.0,
    "hybrid_check_time": "15:30",
    "hybrid_timezone": "Asia/Ho_Chi_Minh",
    "hybrid_builder_budget_seconds": 1800,
    "hybrid_max_battles": 12,
    "camera_auto_adjust": False,

    # Farm
    "min_gold":         500_000,
    "min_elixir":       500_000,
    "min_dark":         0,
    "speed_factor":     1.0,

    # Heroes
    "use_king":         True,
    "use_queen":        True,
    "use_warden":       True,
    "use_royal_champ":  True,
    "use_prince":       True,
    "use_luke":         True,

    # Attack
    "attack_around":    True,   # Thả quân theo vòng quanh map
    "electro_per_direction": 3, # Khoảng 3 Electro cho một hướng; tối đa 3 hướng
    "warden_ability_delay": 10, # Cả đội bật cùng Warden sau 10s, hoặc khi Warden nguy hiểm
    "surrender_if_below": 0,    # 0 = không surrender
    "star_target":      1,      # Mục tiêu sao tối thiểu
    "min_farm":         45,     # Thời gian farm tối thiểu trong trận trước khi rút quân (giây)
    "farm_battle_timeout": 85,  # Thời gian tối đa 1 trận farm trước khi rút lui (giây)
    "auto_train":       True,   # Quick Train Slot 1 một lần khi khởi động; các trận sau dùng hàng đợi
    "event_mode":       False,  # Tự chọn bonus tài nguyên khi hiện bảng Pick a Reward
    "event_resource_priority": "dark",  # "dark" | "elixir" | "gold"; luôn bỏ qua bonus lính

    # Wall
    "upgrade_walls":    True,
    "wall_resource":    0,      # Ngưỡng bắt đầu cân nhắc nâng; 0 = đủ giá một viên
    "wall_type":        "gold",  # "gold" | "elixir" | "both"
    "wall_reserve":     0,      # Giữ lại ít nhất lượng tài nguyên này
    "wall_max_batch":   50,     # Giới hạn số viên trong một lần nâng

    # Misc
    "verbose":          False,
    "anti_detect":      False,   # Randomize delay nhẹ
}


RUN_MODE_LABELS = {"main": "Làng chính", "builder": "Làng đêm",
                   "hybrid": "Làng chính + Làng đêm"}
AVAILABLE_RUN_MODES = frozenset({"main", "builder", "hybrid"})
MAIN_AMOUNT_FIELDS = {"min_gold": "Gold tối thiểu", "min_elixir": "Elixir tối thiểu",
                      "wall_resource": "Ngưỡng nâng tường"}
MAIN_INTEGER_FIELDS = {
    "min_farm": ("Thời gian surrender tối thiểu", 0, 3600),
    "star_target": ("Số sao tối thiểu", 1, 3),
    "farm_battle_timeout": ("Thời gian trận tối đa", 1, 3600),
    "electro_per_direction": ("Electro mỗi hướng", 1, 9),
    "warden_ability_delay": ("Độ trễ kỹ năng cả đội", 0, 120),
}
BUILDER_BOOL_FIELDS = ("builder_auto_setup_baby_dragons", "builder_use_available_hero",
                       "builder_collect_cart")


def migrate_settings(saved: dict, defaults: dict | None = None) -> dict:
    """Read-only, idempotent migration; preserve values and unknown keys.

    Existing profiles without run_mode always remain main, even if their
    template defaults now select another mode. Deep-copy opaque extension data.
    """
    if not isinstance(saved, dict):
        raise ValueError("Settings phải là một dictionary JSON.")
    result = deepcopy(DEFAULT_SETTINGS)
    if defaults is not None:
        result.update(deepcopy(defaults))
    result.update(deepcopy(saved))
    result["run_mode"] = saved.get("run_mode", "main")
    version = saved.get("settings_schema_version", 1)
    if type(version) is int and version < 2:
        result["settings_schema_version"] = 2
    return result


def require_available_mode(mode: str) -> None:
    if not isinstance(mode, str) or mode not in RUN_MODE_LABELS:
        raise ValueError(f"run_mode không hợp lệ: {mode!r}; phải là main, builder hoặc hybrid.")
    if mode not in AVAILABLE_RUN_MODES:
        reason = 'đang kiểm chứng GĐ5' if mode == 'builder' else 'chưa triển khai GĐ6'
        choices = ', '.join(key for key in RUN_MODE_LABELS if key in AVAILABLE_RUN_MODES)
        raise ValueError(f"Chế độ {RUN_MODE_LABELS[mode]} ({mode}) chưa khả dụng: {reason}. "
                         f"Chế độ đang mở: {choices}.")


def validate_settings(settings: dict, *, require_available: bool = False) -> dict:
    """Shared GUI/engine/CLI contract; validate only the selected villages."""
    result = migrate_settings(settings)
    mode = result["run_mode"]
    if not isinstance(mode, str) or mode not in RUN_MODE_LABELS:
        raise ValueError(f"run_mode không hợp lệ: {mode!r}; phải là main, builder hoặc hybrid.")
    if require_available:
        require_available_mode(mode)
    if type(result["settings_schema_version"]) is not int or result["settings_schema_version"] < 2:
        raise ValueError("settings_schema_version phải là số nguyên từ 2.")
    if type(result["camera_auto_adjust"]) is not bool:
        raise ValueError("camera_auto_adjust phải là true hoặc false.")
    if mode in ("main", "hybrid"):
        for key, label in MAIN_AMOUNT_FIELDS.items():
            value = result[key]
            if type(value) is not int or not 0 <= value <= 1_000_000_000_000:
                raise ValueError(f"{label} phải từ 0 đến 1 nghìn tỷ.")
        for key, (label, low, high) in MAIN_INTEGER_FIELDS.items():
            value = result[key]
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{label} phải là số nguyên từ {low} đến {high}.")
        if result["farm_battle_timeout"] < result["min_farm"]:
            raise ValueError("Thời gian trận tối đa phải bằng hoặc lớn hơn thời gian surrender tối thiểu.")
        if result["wall_type"] not in ("gold", "elixir", "both"):
            raise ValueError("Loại tài nguyên nâng tường không hợp lệ.")
        if result["event_resource_priority"] not in ("dark", "elixir", "gold"):
            raise ValueError("Tài nguyên ưu tiên cho bonus không hợp lệ.")
        for key in ("upgrade_walls", "event_mode"):
            if type(result[key]) is not bool:
                raise ValueError(f"{key} phải là true hoặc false.")
    if mode in ("builder", "hybrid"):
        if result["builder_deploy_mode"] not in ("around", "single_point"):
            raise ValueError("builder_deploy_mode phải là around hoặc single_point.")
        for key in BUILDER_BOOL_FIELDS:
            if type(result[key]) is not bool:
                raise ValueError(f"{key} phải là true hoặc false.")
        for key, low, high in (
            ('builder_prepare_timeout', 10, 180), ('builder_battle_timeout', 180, 900),
            ('builder_transition_timeout', 5, 90), ('builder_no_progress_timeout', 15, 180),
            ('builder_point_retries', 1, 8), ('builder_baby_ability_delay', 0, 30),
            ('builder_hero_ability_interval', 3, 60),
        ):
            value=result[key]
            if type(value) not in (int, float) or not low <= value <= high:
                raise ValueError(f'{key} phải từ {low} đến {high}.')
            if key=='builder_point_retries' and type(value) is not int:
                raise ValueError('builder_point_retries phải là số nguyên.')
    if mode == "hybrid":
        for key, low, high in (('hybrid_builder_budget_seconds', 300, 7200),
                                ('hybrid_max_battles', 1, 50)):
            if type(result[key]) is not int or not low <= result[key] <= high:
                raise ValueError(f'{key} phải là số nguyên từ {low} đến {high}.')
        if not isinstance(result["hybrid_check_time"], str) or not re.fullmatch(
                r"(?:[01]\d|2[0-3]):[0-5]\d", result["hybrid_check_time"]):
            raise ValueError("Giờ kiểm tra phải có dạng HH:MM (00:00–23:59).")
        if result["hybrid_timezone"] != "Asia/Ho_Chi_Minh":
            raise ValueError("Lịch hai làng dùng Asia/Ho_Chi_Minh (UTC+7).")
    return result


def parse_amount(raw: str) -> int:
    """Accept 9000000, 9.000.000, 9tr, 1,5tr or 500k."""
    value = raw.strip().lower().replace(" ", "").replace("_", "")
    for suffix, factor in (("triệu", 1_000_000), ("trieu", 1_000_000),
                           ("tr", 1_000_000), ("m", 1_000_000),
                           ("nghìn", 1_000), ("nghin", 1_000), ("k", 1_000)):
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
    """Collect all tabs, retaining inactive-village drafts without blocking save."""
    updated = migrate_settings(existing)
    updated.update({key: deepcopy(value) for key, value in fields.items()
                    if key not in MAIN_AMOUNT_FIELDS and key not in MAIN_INTEGER_FIELDS})
    for key in MAIN_AMOUNT_FIELDS:
        if key in fields:
            try:
                updated[key] = parse_amount(str(fields[key]))
            except ValueError:
                updated[key] = fields[key]
    for key in MAIN_INTEGER_FIELDS:
        if key in fields:
            raw = str(fields[key]).strip()
            updated[key] = int(raw) if raw.isdigit() else fields[key]
    updated["upgrade_walls"] = bool(upgrade_walls)
    # Legacy panel API: infer the event toggle only for the main village.
    # The GUI supplies its explicit main event value, including both toggles off.
    if "event_mode" not in fields and updated["run_mode"] in ("main", "hybrid"):
        updated["event_mode"] = not bool(upgrade_walls)
    return validate_settings(updated)


def load_settings() -> dict:
    """Load settings từ file JSON, merge với defaults."""
    settings = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                user = json.load(f)
            if not isinstance(user, dict):
                raise ValueError("Settings phải là một dictionary JSON.")
            settings = user
        except Exception as e:
            print(f"[Config] WARN: Không đọc được settings.json: {e}")
    return migrate_settings(settings)


def save_settings(settings: dict):
    """Lưu settings ra file."""
    os.makedirs(os.path.dirname(os.path.abspath(SETTINGS_FILE)), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(migrate_settings(settings), f, indent=2, ensure_ascii=False)


def asset(relative_path: str) -> str:
    """Trả về đường dẫn tuyệt đối tới file asset."""
    return os.path.join(ASSETS_DIR, relative_path)
