#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CocMagic — bot_engine.py
Vòng lặp chính của bot:
  - Khởi động ADB
  - Xử lý popup bất ngờ (mất kết nối, thiết bị khác, lỗi client)
  - Gọi Farm, Wall, Hero modules
  - Logging và thống kê
"""

import time
import signal
import sys
import threading
from datetime import datetime
from typing import Optional

from cocmagic import config
from cocmagic.adb_controller import ADBController, find_adb_port
from cocmagic.screen_reader import ScreenReader
from cocmagic.modules.farm_module import FarmModule, FarmState
from cocmagic.modules.hero_module import HeroModule
from cocmagic.modules.wall_module import WallModule
from cocmagic.ui_dialogs import find_connection_retry
from cocmagic.event_rewards import find_reward_panel


# ════════════════════════════════════════════════════════════
#  POPUP TEMPLATES (xử lý sự cố)
# ════════════════════════════════════════════════════════════

POPUP_TEMPLATES = {
    # (template_path, tap_response_template_or_None, description)
    "another_device":    (config.asset("Another_devicee.png"),    config.asset("okay.png"),   "Thiet bi khac"),
    "client_error":      (config.asset("Client_error!.png"),      config.asset("okay.png"),   "Loi client"),
    "rate_coc":          (config.asset("rate_coc.png"),           config.asset("no.png"),     "Danh gia CoC"),
    "open_link":         (config.asset("openlink.png"),           config.asset("no.png"),     "Mo link"),
}

# Toa do tap de dong popup "Anyone there? / RELOAD GAME"
# Vi tri nut "RELOAD GAME" trong popup inactivity (1600x900)
RELOAD_GAME_POS = (447, 479)   # tap vao chu "RELOAD GAME"



# ════════════════════════════════════════════════════════════
#  BOT ENGINE
# ════════════════════════════════════════════════════════════

class BotEngine:
    """Điều phối toàn bộ bot: popup handler + farm + wall."""

    def __init__(self, settings: dict, device_serial: str = None,
                 stop_event=None, status_callback=None):
        self.settings    = settings
        self.device_serial = device_serial
        self.stop_event = stop_event
        self.status_callback = status_callback
        self.running     = False
        self.start_time  = 0.0
        self.loop_count  = 0

        # ADB
        self.adb: Optional[ADBController] = None

        # Modules
        self.reader:    Optional[ScreenReader] = None
        self.hero_mod:  Optional[HeroModule]   = None
        self.farm_mod:  Optional[FarmModule]   = None
        self.wall_mod:  Optional[WallModule]   = None

    # ─── Startup ────────────────────────────────────────────

    def start(self):
        """Khởi động bot."""
        if self._stopping():
            return False
        self._print_banner()

        # Xử lý Ctrl+C gracefully
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self._signal_handler)

        # Ket noi ADB
        if not self._connect_adb():
            print("[Engine] ERROR: Cannot connect to MuMu Player. Exiting.")
            return False
        if self._stopping():
            return False

        image = self.adb.screenshot()
        if image is None or image.shape[:2] != (config.ANDROID_H, config.ANDROID_W):
            print(f"[Engine] ERROR: Giả lập {self.adb.device} cần màn hình "
                  f"{config.ANDROID_W}x{config.ANDROID_H} và ảnh chụp ADB hợp lệ.")
            return False
        if self._stopping():
            return False

        # Khởi tạo modules
        self._init_modules()

        # Chạy vòng lặp chính
        if self._stopping():
            return False
        self.running    = True
        self.start_time = time.time()
        print("[Engine] 🚀 Bot bắt đầu chạy. Nhấn Ctrl+C để dừng.\n")
        try:
            self._main_loop()
        finally:
            self.running = False
        return not bool(self.farm_mod and self.farm_mod.halt_reason)

    def _connect_adb(self) -> bool:
        """Ket noi ADB -- tu dong scan port MuMu Player neu can."""
        import os
        if not os.path.exists(config.ADB_PATH):
            print(f"[Engine] ERROR: ADB not found: {config.ADB_PATH}")
            print(f"[Engine]   -> Make sure MuMu Player is installed")
            return False

        serial = self.device_serial
        if serial is None:
            port = config.ADB_PORT or find_adb_port(config.ADB_PATH)
            serial = f"{config.ADB_HOST}:{port}" if port else None
        if not serial:
            print("[Engine] ERROR: Cannot connect to MuMu Player ADB.")
            print("[Engine]   -> 1. Open MuMu Player 12")
            print("[Engine]   -> 2. Settings -> Other settings -> Enable ADB debug")
            print("[Engine]   -> 3. Default port for instance 0: 16384")
            return False

        self.adb = ADBController(adb_path=config.ADB_PATH, serial=serial,
                                 settings=self.settings, stop_event=self.stop_event)
        return self.adb.connect()

    def _init_modules(self):
        """Khởi tạo tất cả modules."""
        self.reader   = ScreenReader(self.adb)
        self.hero_mod = HeroModule(self.adb, self.settings)
        self.farm_mod = FarmModule(self.adb, self.reader, self.hero_mod, self.settings,
                                   recovery_handler=self._handle_connection_lost)
        self.wall_mod = WallModule(self.adb, self.reader, self.settings,
                                   stop_event=self.stop_event)
        print("[Engine] ✅ Đã khởi tạo: ScreenReader, HeroModule, FarmModule, WallModule")

    # ─── Main Loop ──────────────────────────────────────────

    def _main_loop(self):
        """Vòng lặp chính của bot."""
        last_popup_check = time.monotonic() - 5.0
        last_status_print = time.monotonic()
        last_status_event = 0.0

        while self.running and not self._stopping():
            self.loop_count += 1

            # Keep these intervals stable when the main loop is made faster.
            now = time.monotonic()
            if now - last_popup_check >= 5.0:
                handled = self._handle_popups()
                last_popup_check = now
                if handled:
                    continue

            # 2. Farm tick
            if not self.farm_mod.tick():
                print(f"[Engine] Dừng bot: {self.farm_mod.halt_reason}")
                self.running = False
                break
            if self._stopping():
                break

            # 3. Sau khi về HOME → thử nâng tường
            if (not self._stopping() and self.farm_mod.state == FarmState.HOME and
                    not self.farm_mod.recovering_home and
                    not self.settings.get("event_mode", False) and
                    self.settings.get("upgrade_walls", True)):
                self.wall_mod.run()
                if self.wall_mod.last_interacted:
                    self.farm_mod.invalidate_ui_cache()

            if now - last_status_print >= 10.0:
                self._print_status()
                last_status_print = now

            if self.status_callback and now - last_status_event >= 0.5:
                self.status_callback({
                    "status": self.farm_mod.status_line,
                    "wall_count": self.wall_mod.walls_upgraded,
                })
                last_status_event = now

            if self.stop_event is None:
                time.sleep(config.DELAY_MAIN_LOOP)
            else:
                self.stop_event.wait(config.DELAY_MAIN_LOOP)
        self.running = False

    def _stopping(self) -> bool:
        return self.stop_event is not None and self.stop_event.is_set()

    # ─── Popup Handler ──────────────────────────────────────

    def _handle_connection_lost(self, image) -> bool:
        retry = find_connection_retry(self.adb, image)
        if retry is None:
            return False
        print(f"[Popup] Mất kết nối: bấm Try Again tại {retry}; chờ game reload 10 giây.")
        if not self.adb.tap(*retry, jitter=0, delay=0):
            # The dialog is still present; abandon the current deployment and
            # retry from a fresh frame rather than sending more battle inputs.
            return True
        self.farm_mod.reset_after_reload()
        if self.status_callback:
            self.status_callback({"status": "Mất kết nối · chờ reload 10 giây",
                                  "wall_count": self.wall_mod.walls_upgraded})
        if self.stop_event is None:
            time.sleep(10)
        else:
            self.stop_event.wait(10)
        self.adb.invalidate_cache()
        return True

    def _handle_popups(self) -> bool:
        """
        Kiem tra va xu ly cac popup bat ngo:
        mat ket noi, loi client, dialog danh gia, inactivity, v.v.
        """
        img = self.adb.screenshot(use_cache=False)
        if img is None:
            return False

        if self._handle_connection_lost(img):
            return True
        if self.settings.get("event_mode", False) and find_reward_panel(img) is not None:
            # Farm resolves rewards before resuming deployment. This dark panel
            # must not be mistaken for the older inactivity popup below.
            return False

        # ── Kiem tra popup "Anyone there? / RELOAD GAME" ──────
        # Popup nay co nen toi (dark overlay), pixel tai (383,344) se rat toi
        # Va nut RELOAD GAME o vi tri co dinh (447, 479)
        if self._detect_inactivity_popup(img):
            print("[Popup] Phat hien: Inactivity popup (Anyone there?)")
            self.adb.tap(RELOAD_GAME_POS[0], RELOAD_GAME_POS[1], jitter=5)
            time.sleep(4)   # cho game reload
            self.farm_mod.invalidate_ui_cache()
            self.farm_mod.state = FarmState.HOME
            return True

        # ── Cac popup khac ────────────────────────────────────
        for name, (detect_tpl, response_tpl, desc) in POPUP_TEMPLATES.items():
            if self.adb.is_visible(detect_tpl, config.LOOSE_THRESHOLD, img):
                print("[Popup] Phat hien: " + desc)
                if response_tpl:
                    tapped = self.adb.find_and_tap(response_tpl, config.LOOSE_THRESHOLD, img)
                    if not tapped:
                        self.adb.tap(config.ANDROID_W // 2, config.ANDROID_H // 2)
                else:
                    self.adb.tap(config.ANDROID_W // 2, config.ANDROID_H // 2)

                time.sleep(2)
                self.farm_mod.invalidate_ui_cache()
                self.farm_mod.state = FarmState.HOME
                return True
        return False

    def _detect_inactivity_popup(self, img) -> bool:
        """
        Phat hien popup "Anyone there?" bang cach kiem tra:
        1. Vung trung tam man hinh co mau xam toi (dark overlay)
        2. Pixel tai vi tri text "Anyone there?" phai xam nhat
        """
        import numpy as np
        try:
            h, w = img.shape[:2]
            # Kiem tra vung trung tam popup (383,300) -> (1100,520)
            # Popup nay co nen xam toi #1a1a1a voi do trong ~85%
            cx, cy = w // 2, h // 2
            # Lay mau trung binh vung trung tam popup
            roi = img[300:520, 330:1100]
            mean_brightness = np.mean(roi)
            # Popup toi: trung binh < 80 (0-255)
            # Man hinh binh thuong: trung binh > 100
            if mean_brightness < 75:
                # Kiem tra them: pixel tai vi tri nen popup phai xam toi
                # Va phai co gi do sang hon o vung text (text la trang)
                text_roi = img[340:360, 380:600]
                if np.mean(text_roi) > 100:  # text trang sang
                    return True
        except Exception:
            pass
        return False



    # ─── Status & Banner ────────────────────────────────────

    def _print_status(self):
        elapsed  = time.time() - self.start_time
        h, m     = divmod(int(elapsed), 3600)
        m, s     = divmod(m, 60)
        uptime   = f"{h:02d}:{m:02d}:{s:02d}"
        now      = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{now}] ── Status ──────────────────────────────────")
        print(f"  Uptime:  {uptime}  |  Loops: {self.loop_count}")
        if self.farm_mod:
            print(f"  {self.farm_mod.status_line}")
        if self.wall_mod:
            print(f"  [Wall] Upgraded={self.wall_mod.walls_upgraded}")
        print("────────────────────────────────────────────────\n")

    def _print_banner(self):
        print()
        print("╔══════════════════════════════════════════════════════════╗")
        print("║         CocMagic — Open Source CoC Bot                  ║")
        print("║         Farm  •  Wall  •  Heroes  (Core v1.0)           ║")
        print("╚══════════════════════════════════════════════════════════╝")
        print()
        print(f"  ADB:        {config.ADB_PATH}")
        print(f"  Device:     {self.device_serial or f'{config.ADB_HOST}:{config.ADB_PORT}'}")
        print(f"  Resolution: {config.ANDROID_W}x{config.ANDROID_H}")
        print(f"  Assets:     {config.ASSETS_DIR}")
        print()
        s = self.settings
        print(f"  Min Gold:   {s.get('min_gold',0):,}")
        print(f"  Min Elixir: {s.get('min_elixir',0):,}")
        print(f"  Min Dark:   {s.get('min_dark',0):,}")
        if s.get("event_mode", False):
            print(f"  Event rewards: ON, ưu tiên {s.get('event_resource_priority', 'dark')}")
        print(f"  Wall Upgrade: {'ON' if s.get('upgrade_walls') else 'OFF'}")
        print(f"  Wall Resource: {s.get('wall_resource',0):,}")
        heroes = [h for h in ["king","queen","warden","royal_champ","prince","luke"]
                  if s.get(f"use_{h}")]
        print(f"  Heroes: {', '.join(heroes) if heroes else 'none'}")
        print()

    # ─── Graceful shutdown ──────────────────────────────────

    def _signal_handler(self, sig, frame):
        print("\n\n[Engine] 🛑 Ctrl+C — Đang dừng bot...")
        self.running = False
        self._print_status()
        print("[Engine] Bot đã dừng. Tạm biệt!")
        sys.exit(0)
