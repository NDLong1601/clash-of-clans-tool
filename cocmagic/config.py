#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CocMagic — config.py
Toàn bộ cấu hình mặc định. Người dùng chỉnh settings.json, không sửa file này.
"""

import os
import json

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


def load_settings() -> dict:
    """Load settings từ file JSON, merge với defaults."""
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                user = json.load(f)
            settings.update(user)
        except Exception as e:
            print(f"[Config] WARN: Không đọc được settings.json: {e}")
    return settings


def save_settings(settings: dict):
    """Lưu settings ra file."""
    os.makedirs(os.path.dirname(os.path.abspath(SETTINGS_FILE)), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def asset(relative_path: str) -> str:
    """Trả về đường dẫn tuyệt đối tới file asset."""
    return os.path.join(ASSETS_DIR, relative_path)
