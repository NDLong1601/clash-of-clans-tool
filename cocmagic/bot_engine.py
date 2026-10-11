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
import threading
import os
from copy import deepcopy
from datetime import datetime
from typing import Optional

from cocmagic import config
from cocmagic.adb_controller import ADBController, find_adb_port
from cocmagic.screen_reader import ScreenReader
from cocmagic.modules.farm_module import FarmModule
from cocmagic.modules.hero_module import HeroModule
from cocmagic.modules.wall_module import WallModule
from cocmagic.modules.builder_farm_module import BuilderFarmModule
from cocmagic.ui_dialogs import find_connection_retry, find_inactivity_reload
from cocmagic.event_rewards import find_reward_panel
from cocmagic.run_coordinator import RunCoordinator
from cocmagic.hybrid_coordinator import HybridCoordinator
from cocmagic.hybrid_runtime import HybridRuntimeStore
from cocmagic.device_manager import resolve_device_ownership
from cocmagic.village_module import ModuleScreen
from cocmagic.recovery import RecoveryInterrupted


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

# ════════════════════════════════════════════════════════════
#  BOT ENGINE
# ════════════════════════════════════════════════════════════

class BotEngine:
    """Điều phối toàn bộ bot: popup handler + farm + wall."""

    def __init__(self, settings: dict, device_serial: str = None,
                 stop_event=None, status_callback=None):
        self.settings    = deepcopy(settings)
        self.device_serial = device_serial
        self.stop_event = stop_event
        self.stop_event = self.stop_event or threading.Event()
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
        self.builder_mod: Optional[BuilderFarmModule] = None
        self.wall_mod:  Optional[WallModule]   = None
        self.coordinator: Optional[RunCoordinator] = None
        self.runtime_store = None
        self._missing_frames = 0
        self._blocked_frames = 0
        self._callback_error = False
        self._reload_attempts = 0
        self._main_navigation = False
        self.village_reader = None
        self.navigator = None
        self._owns_input = False

    def _emit_status(self, value):
        if self.status_callback is None:
            return
        try:
            self.status_callback({**value, 'serial': self.device_serial or getattr(self.adb, 'device', None)})
            self._callback_error = False
        except Exception as error:
            if not self._callback_error:
                print(f'[Status] Callback lỗi trên {self.device_serial}: {error}')
            self._callback_error = True

    # ─── Startup ────────────────────────────────────────────

    def start(self):
        """Khởi động bot."""
        if self._stopping():
            return False
        try:
            self.settings = config.validate_settings(self.settings, require_available=True)
        except ValueError as error:
            print(f"[Engine] ERROR: {error}")
            self._emit_status({"status": str(error), "wall_count": 0})
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

        try:
            if not self._acquire_input_runtime():
                return False
            self._init_modules()
            self.adb.frame_guard = self._guard_frame
            self.adb.input_failure_handler = self._input_failed
            if self._stopping():
                return False
            self.running = True
            self.start_time = time.time()
            print("[Engine] 🚀 Bot bắt đầu chạy. Nhấn Ctrl+C để dừng.\n")
            self._main_loop()
        finally:
            self.running = False
            self.adb.frame_guard = None
            self.adb.input_failure_handler = None
            if self._owns_input:
                released = self.adb.release_touch()
                if not released:
                    print(f'[Engine] {self.adb.device}: đã dừng, release chưa xác nhận (ADB/thiết bị).')
                self._owns_input = False
            if self.runtime_store is not None:
                self.runtime_store.close()
        return not bool(self.coordinator and self.coordinator.halt_reason)

    def _acquire_input_runtime(self):
        ownership = resolve_device_ownership(self.adb.adb, self.adb.device)
        if self._stopping():
            return False
        self.runtime_store = HybridRuntimeStore(
            os.path.join(config.DATA_DIR, 'runtime'), self.adb.device,
            device_identity=ownership.identity, runtime_serial=ownership.runtime_serial,
            legacy_serials=ownership.aliases)
        self.runtime_store.acquire()
        self._owns_input = True
        return True

    def _connect_adb(self) -> bool:
        """Ket noi ADB -- tu dong scan port MuMu Player neu can."""
        import os
        if not os.path.exists(config.ADB_PATH):
            print(f"[Engine] ERROR: ADB not found: {config.ADB_PATH}")
            print("[Engine]   -> Make sure MuMu Player is installed")
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
        if self.settings.get('run_mode') == 'builder':
            self.builder_mod=BuilderFarmModule(self.adb,self.settings,
                stop_event=self.stop_event,recovery_handler=self._handle_connection_lost)
            self.coordinator=RunCoordinator(self.adb.device,{'builder':self.builder_mod},'builder',
                                             stop_event=self.stop_event)
            print('[Engine] ✅ Đã khởi tạo: BuilderFarmModule')
            return
        self.reader   = ScreenReader(self.adb)
        self.hero_mod = HeroModule(self.adb, self.settings)
        self.wall_mod = WallModule(self.adb, self.reader, self.settings,
                                   stop_event=self.stop_event)
        self.farm_mod = FarmModule(self.adb, self.reader, self.hero_mod, self.settings,
                                   recovery_handler=self._handle_connection_lost,
                                   wall_mod=self.wall_mod, stop_event=self.stop_event)
        self.coordinator = RunCoordinator(self.adb.device, {"main": self.farm_mod}, "main",
                                          stop_event=self.stop_event)
        if self.settings.get('run_mode', 'main') == 'main':
            from cocmagic.builder_vision import BuilderBattleReader
            from cocmagic.village_navigator import VillageNavigator
            self.village_reader = BuilderBattleReader(self.adb)
            self.navigator = VillageNavigator(self.adb, self.village_reader, self.farm_mod.camera,
                                              stop_event=self.stop_event)
        if self.settings.get('run_mode') == 'hybrid':
            self.builder_mod = BuilderFarmModule(self.adb, self.settings,
                stop_event=self.stop_event, recovery_handler=self._handle_connection_lost)
            if self.runtime_store is None:
                if not self._acquire_input_runtime():
                    return
            self.coordinator = HybridCoordinator(self.adb.device,
                {'main': self.farm_mod, 'builder': self.builder_mod}, self.runtime_store,
                self.settings, stop_event=self.stop_event)
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
            try:
                if now - last_popup_check >= 5.0:
                    handled = self.coordinator.exclusive(self._handle_popups)
                    last_popup_check = now
                    if handled:
                        continue
                # Only the coordinator's active module can tick on this serial.
                okay = self.coordinator.tick()
            except RecoveryInterrupted:
                if self.coordinator.halt_reason:
                    okay = False
                else:
                    self._wait(.5)
                    continue
            except Exception as error:
                self.coordinator._halt_reason = f'Lỗi worker {self.adb.device}: {error}'
                okay = False
            if not okay:
                print(f"[Engine] Dừng bot: {self.coordinator.halt_reason}")
                if self.status_callback:
                    self._emit_status(self.coordinator.status())
                self.running = False
                break
            if self._stopping():
                break

            if now - last_status_print >= 10.0:
                self._print_status()
                last_status_print = now

            if self.status_callback and now - last_status_event >= 0.5:
                self._emit_status(self.coordinator.status())
                last_status_event = now

            self._wait(config.DELAY_MAIN_LOOP)
        self.running = False

    def _stopping(self) -> bool:
        return self.stop_event is not None and self.stop_event.is_set()

    def _wait(self, seconds):
        if self.stop_event is None:
            time.sleep(seconds)
        else:
            self.stop_event.wait(seconds)

    # ─── Popup Handler ──────────────────────────────────────

    def _input_failed(self, reason='Input ADB thất bại; chờ ảnh mới và phân loại lại', fatal=False):
        try:
            self.coordinator.reset_after_reload()
        except Exception as error:
            fatal = True
            reason += f'; reset cache thất bại: {error}'
        if fatal:
            self.coordinator._halt_reason = reason
        self._emit_status({**self.coordinator.status(), 'status': reason})

    def _guard_frame(self, image):
        """Runs for every capture, including rewards, cart and navigation."""
        if self._stopping():
            raise RecoveryInterrupted('Đang dừng')
        if image is None or image.shape[:2] != (config.ANDROID_H, config.ANDROID_W):
            if self._missing_frames == 0:
                self._input_failed('Mất ảnh/ADB · hủy input, chờ game và phân loại lại')
            self._missing_frames += 1
            if self._missing_frames >= 6:
                self.coordinator._halt_reason = 'Không lấy được ảnh ADB hợp lệ sau 6 lần; dừng riêng instance'
            raise RecoveryInterrupted('Ảnh chưa dùng được')
        self._missing_frames = 0
        if self._handle_connection_lost(image):
            raise RecoveryInterrupted('Connection lost; bỏ giao dịch cũ')
        title = self.adb.find_template(config.asset('connection_lost_title.png'), .80, image,
                                       region=(330, 280, 700, 200))
        if isinstance(title, tuple):
            if self._blocked_frames == 0:
                self._input_failed('Connection lost · chưa thấy nút retry, không bấm mù')
            self._blocked_frames += 1
            if self._blocked_frames >= 6:
                self.coordinator._halt_reason = 'Popup connection chưa đủ nút sau 6 ảnh; dừng riêng instance'
            raise RecoveryInterrupted('Connection modal chưa có handler an toàn')
        self._blocked_frames = 0
        reload = find_inactivity_reload(image)
        if reload:
            self._reload_attempts += 1
            if self._reload_attempts > 3:
                self.coordinator._halt_reason = 'Reload inactivity không phục hồi sau 3 lần; dừng riêng instance'
                raise RecoveryInterrupted(self.coordinator.halt_reason)
            self.coordinator.reset_after_reload()
            self._emit_status({**self.coordinator.status(), 'status': 'Inactivity · chờ reload và nhận diện lại'})
            self.adb.tap(*reload, jitter=0, delay=0)
            self._wait(4)
            self.adb.invalidate_cache()
            raise RecoveryInterrupted('Inactivity; bỏ giao dịch cũ')
        for name in ('another_device', 'client_error'):
            title, response, description = POPUP_TEMPLATES[name]
            if self.adb.is_visible(title, .85, image) is True:
                self._reload_attempts += 1
                self.coordinator.reset_after_reload()
                point = self.adb.find_template(response, .85, image)
                if self._reload_attempts > 3 or not isinstance(point, tuple):
                    self.coordinator._halt_reason = description+'; không xác nhận reload an toàn'
                else:
                    self.adb.tap(*point, jitter=0, delay=0)
                    self._wait(4)
                raise RecoveryInterrupted(description)
        if self._reload_attempts:
            reader = self.builder_mod.reader if self.builder_mod is not None else self.village_reader
            if reader is not None:
                from cocmagic.builder_screen_reader import ScreenKind
                if reader.classify(image).kind in (ScreenKind.MAIN_HOME, ScreenKind.BUILDER_HOME,
                        ScreenKind.BATTLE, ScreenKind.RESULT, ScreenKind.ATTACK_MENU):
                    self._reload_attempts = 0
        if (self.coordinator.active_id == 'main' and self.farm_mod is not None and
                self.farm_mod.state.name in ('ATTACKING', 'BATTLE_WAIT') and
                self.farm_mod._classify_screen(image) == ModuleScreen.UNKNOWN):
            self._input_failed('Màn trận main mất nhận diện; hủy input và phân loại lại')
            raise RecoveryInterrupted('Không tiếp tục input trên ảnh trận không rõ')
        if (self.village_reader is not None and not self._main_navigation and
                self.farm_mod.state.name in ('HOME', 'RECOVERING')):
            from cocmagic.builder_screen_reader import ScreenKind, Village
            screen = self.village_reader.classify(image)
            if screen.kind == ScreenKind.BUILDER_HOME:
                self._main_navigation = True
                try:
                    result = self.navigator.navigate(Village.MAIN, source=Village.BUILDER)
                finally:
                    self._main_navigation = False
                self.coordinator.reset_after_reload()
                if not result.success and not self._stopping():
                    self.coordinator._halt_reason = 'Main chưa chuyển được từ builder Home: '+result.reason
                raise RecoveryInterrupted('Đã đối soát lại làng cho chế độ main')

    def _handle_connection_lost(self, image) -> bool:
        retry = find_connection_retry(self.adb, image)
        if retry is None:
            return False
        if self._stopping():
            return True
        self._reload_attempts += 1
        if self._reload_attempts > 3:
            self.coordinator._halt_reason = 'Connection lost chưa phục hồi sau 3 lần; dừng riêng instance'
            return True
        print(f"[Popup] Mất kết nối: bấm Try Again tại {retry}; chờ game reload 10 giây.")
        self.coordinator.reset_after_reload()
        self._emit_status({**self.coordinator.status(), "status": "Mất kết nối · chờ reload 10 giây"})
        self.adb.tap(*retry, jitter=0, delay=0)
        self._wait(10)
        self.adb.invalidate_cache()
        return True

    def _handle_popups(self) -> bool:
        """
        Kiem tra va xu ly cac popup bat ngo:
        mat ket noi, loi client, dialog danh gia, inactivity, v.v.
        """
        img = self.adb.screenshot(use_cache=False)
        if img is None or self._stopping():
            return False

        if self._handle_connection_lost(img):
            return True
        if find_reward_panel(img) is not None:
            # The active module owns rewards. A dark reward panel must not be
            # mistaken for the older inactivity popup below.
            return False

        # ── Kiem tra popup "Anyone there? / RELOAD GAME" ──────
        # Require the native title and Reload button together.
        reload = find_inactivity_reload(img)
        if reload:
            print("[Popup] Phat hien: Inactivity popup (Anyone there?)")
            self.coordinator.reset_after_reload()
            if self.adb.tap(*reload, jitter=0):
                self._wait(4)
                self.adb.invalidate_cache()
            return True

        # ── Cac popup khac ────────────────────────────────────
        for name, (detect_tpl, response_tpl, desc) in POPUP_TEMPLATES.items():
            if name in ('another_device', 'client_error'):
                continue  # Recovery modals belong to the strict capture guard.
            if self.adb.is_visible(detect_tpl, config.LOOSE_THRESHOLD, img):
                print("[Popup] Phat hien: " + desc)
                tapped = self.adb.find_and_tap(response_tpl, config.LOOSE_THRESHOLD, img)

                if tapped:
                    self.coordinator.invalidate_after_popup()
                    self._wait(2)
                    self.adb.invalidate_cache()
                return True
        return False

    def _detect_inactivity_popup(self, img) -> bool:
        return find_inactivity_reload(img) is not None



    # ─── Status & Banner ────────────────────────────────────

    def _print_status(self):
        elapsed  = time.time() - self.start_time
        h, m     = divmod(int(elapsed), 3600)
        m, s     = divmod(m, 60)
        uptime   = f"{h:02d}:{m:02d}:{s:02d}"
        now      = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{now}] ── Status ──────────────────────────────────")
        print(f"  Uptime:  {uptime}  |  Loops: {self.loop_count}")
        if self.coordinator:
            status = self.coordinator.status()
            print(f"  {status['active_module']}: {status['status']}")
            print(f"  [Wall] Upgraded={status['wall_count']}")
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
        if s.get('run_mode') == 'builder':
            print(f"  Builder:    {s['builder_deploy_mode']} · Rồng con · tướng theo trạng thái")
            print(f"  Cart:       {'ON' if s['builder_collect_cart'] else 'OFF'}")
            return
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
        self.stop_event.set()
        self.running = False
        print('[Engine] Đang dừng sau command hiện tại và giải phóng input…')
