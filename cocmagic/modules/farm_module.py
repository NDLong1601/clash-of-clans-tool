#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CocMagic — modules/farm_module.py
State machine farm Main Village:
  HOME → TRAIN (startup only) → COLLECT → HOME → FIND_MATCH →
  LOOT_CHECK → ATTACKING → BATTLE_WAIT → RESULT → COLLECT → HOME
"""

import sys
import time
import random
import math
import glob
import os
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
import cv2

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.battle_planner import BattlePlan, BattlePlanner
from cocmagic.attack_tactics import AttackTactics
from cocmagic.troop_vision import (
    count_badge_changed, detect_bar_cards, is_electro_card, is_siege_card, read_card_count,
)
from cocmagic.screen_reader import ScreenReader
from cocmagic.modules.hero_module import HeroModule
from cocmagic.ui_dialogs import find_confirmation_button
from cocmagic.event_rewards import find_reward_panel


# ════════════════════════════════════════════════════════════
#  TEMPLATES
# ════════════════════════════════════════════════════════════

T_HOME_ATTACK       = config.asset("home_attack.png")     # Nút Attack tại màn chính (không sao)
T_BASE_ATTACK       = config.asset("base.png")            # Nút Attack gốc tại màn chính
T_FIND_MATCH        = config.asset("find.png")            # Nút Next trên màn do thám đối thủ
T_FIND_MATCH2       = config.asset("findmatch.png")       # Nút "Find a Match" trên thẻ Battle
T_FIND_MATCH_BACKUP = config.asset("backupfindmatch.png") # Tab "Multiplayer"
T_ARMY_ATTACK       = config.asset("rank1.png")           # Nút "Attack!" xanh lá trên màn My Army
T_ARMY_ATTACK2      = config.asset("rank2.png")           # Biến thể nút "Attack!" xanh lá
T_OKAY              = config.asset("okay.png")
T_OKAY_STAR         = config.asset("okaystar.png")
T_OK_HOME           = config.asset("okhome.png")
T_RETURN_HOME_NEW   = config.asset("return_home_new.png") # Nút Return Home mới
T_RETURN_HOME       = config.asset("return_home.png")
T_RETURN_HOME1      = config.asset("return_home1.png")
T_END_BATTLE_BUTTON = config.asset("1star.png")           # Ảnh này thực tế là nút End Battle
T_2STAR             = config.asset("2star.png")
T_3STAR             = config.asset("3star.png")
STAR_TEMPLATES = {
    3: (config.asset("KinhDo/IMG_ClassOf_Clan/star3_white.png"),
        config.asset("KinhDo/IMG_ClassOf_Clan/3Sao/Annotation 2026-05-09 132441.png")),
    2: (T_2STAR,
        config.asset("KinhDo/IMG_ClassOf_Clan/Sao/Annotation 2026-05-02 202451.png")),
    1: (config.asset("KinhDo/IMG_ClassOf_Clan/Sao/1s-1.png"),
        config.asset("KinhDo/IMG_ClassOf_Clan/Sao/Annotation 2026-05-02 203715.png")),
}
T_4X                = config.asset("4x.png")              # Nút tăng tốc 4x
T_SURRENDER         = config.asset("surrender.png")       # Nút Surrender đỏ xác nhận bỏ trận
T_CHECK_TROOP       = config.asset("CheckTroop/CheckTroop.png") # Icon quân đội tại Home
T_USE               = config.asset("CheckTroop/Use.png")        # Nút Train/Use trên Quick Train
T_SAVE_ARMY         = config.asset("CheckTroop/Save_army.png")  # Nút Save Army

# Những vùng này chỉ áp dụng cho ảnh 1600x900 đã cấu hình trong config.py.
NEXT_REGION         = (1200, 540, 400, 200)
END_BATTLE_REGION   = (0, 580, 250, 150)
QUICK_TRAIN_SLOT_1  = (1100, 120, 500, 280)
SAVED_RECIPES_TAB   = (795, 95)
RETURN_HOME_REGION  = (500, 650, 600, 230)
HOME_ATTACK_REGION  = (10, 700, 180, 190)


@dataclass(frozen=True)
class CardSlot:
    x: int
    y: int
    role: str                 # "troop" | "siege" | "spell"
    name: str = ""


@dataclass
class ComboProfile:
    cards: List[CardSlot]
    heroes: List[Tuple[str, int, int]]
    resolution: Tuple[int, int]


@dataclass
class SpellProgress:
    cast_index: int = 0
    resume_attempts: int = 0
    retry_at: float = 0.0
    unconfirmed_before: Optional[np.ndarray] = None


# ════════════════════════════════════════════════════════════
#  STATE MACHINE
# ════════════════════════════════════════════════════════════

class FarmState(Enum):
    HOME        = auto()   # Đang ở màn hình chính làng
    FIND_MATCH  = auto()   # Đang tìm trận (Attack menu, My Army, mây trắng)
    LOOT_CHECK  = auto()   # Đang xem loot đối thủ, quyết định đánh hay bỏ
    ATTACKING   = auto()   # Đang thả quân và heroes
    BATTLE_WAIT = auto()   # Chờ trận đánh kết thúc
    RESULT      = auto()   # Màn hình tổng kết sao và tài nguyên
    TRAIN       = auto()   # Tự động luyện quân (Quick Train Slot 1)
    COLLECT     = auto()   # Thu thập / hoàn tất chu kỳ trước khi về HOME


class _GameReloaded(Exception):
    """Stop the current sequence of battle inputs after a connection dialog."""


class _BattleInputStopped(Exception):
    """Leave an unresolved reward panel open without sending more battle taps."""


class _BattleFinished(Exception):
    """Discard pending deployment inputs once the result or village appears."""


# ════════════════════════════════════════════════════════════
#  FARM MODULE
# ════════════════════════════════════════════════════════════

class FarmModule:
    """Main Village farming state machine."""

    def __init__(self, adb: ADBController, reader: ScreenReader,
                 hero_mod: HeroModule, settings: dict, recovery_handler=None):
        self.adb      = adb
        self.reader   = reader
        self.hero_mod = hero_mod
        self.settings = settings
        self.recovery_handler = recovery_handler

        self.state            = FarmState.HOME
        self.battle_start_ts  = 0.0
        self.skip_count       = 0       # Số lần bỏ qua loot
        self.attack_count     = 0       # Tổng số trận đã đánh
        self._initial_trained = False   # Cờ luyện quân lần đầu khi khởi động bot
        self._train_failures   = 0
        self.halt_reason: Optional[str] = None
        self.planner = BattlePlanner()
        self._battle_plan: Optional[BattlePlan] = None
        self._attack_tactics: Optional[AttackTactics] = None
        self._confirmed_main_points: List[Tuple[int, int]] = []
        self._electro_drop_points: List[Tuple[int, int]] = []
        self._hero_entry: Optional[Tuple[int, int]] = None
        self._warden_deployed_ts = 0.0
        self._hero_abilities_used = False
        self._warden_low_health_frames = 0
        self._warden_slot: Optional[Tuple[int, int]] = None
        self._deployed_hero_slots: dict = {}
        self._heroes_deployed_ts = 0.0
        self._deployment_rejected = False
        self._combo_profile: Optional[ComboProfile] = None
        self._button_cache: dict = {}
        self._button_templates: dict = {}
        self._find_phase = "menu"
        self._home_verified = False
        self._home_attack_failures = 0
        self._spell_templates = None
        self._selected_battle_card = None
        self._reward_generation = 0
        self._verified_battle_points = set()
        self._pending_ability_names = []
        self._pending_spells: dict[CardSlot, SpellProgress] = {}
        self._spell_check_frames = []
        self._vision_frame = None
        self._count_cache = {}
        self._depleted_cache = {}
        self._guarded_frame = None

    # ─── Main tick ──────────────────────────────────────────

    def tick(self) -> bool:
        """
        Gọi 1 lần mỗi vòng lặp bot chính.
        Trả về True nếu cần tiếp tục, False nếu cần dừng.
        """
        try:
            self._handle_state()
        except (_GameReloaded, _BattleInputStopped, _BattleFinished):
            pass
        except Exception as e:
            print(f"[Farm] ERROR trong state {self.state.name}: {e}")
            import traceback; traceback.print_exc()
            try:
                self._go_home_safe()
            except (_GameReloaded, _BattleFinished, _BattleInputStopped):
                pass
        return self.halt_reason is None

    def _screenshot(self, **kwargs):
        image = self._capture(**kwargs)
        if (self.settings.get("event_mode", False) and self.state in
                (FarmState.ATTACKING, FarmState.BATTLE_WAIT, FarmState.RESULT)):
            image = self._handle_event_rewards(image)
        self._guard_battle_frame(image)
        return image

    def _guard_battle_frame(self, image, before_input=False):
        in_battle = (self.state == FarmState.ATTACKING or
                     (before_input and self.state == FarmState.BATTLE_WAIT))
        if not in_battle or image is None or image is self._guarded_frame:
            return
        self._guarded_frame = image
        if self._is_result_screen(image) or self._is_home_screen(image):
            self._selected_battle_card = None
            self._pending_spells.clear()
            self._spell_check_frames.clear()
            self.state = FarmState.RESULT
            print("[Farm] Trận đã kết thúc; hủy các thao tác thả quân còn lại.")
            raise _BattleFinished()

    def _capture(self, **kwargs):
        """Capture a frame while keeping connection recovery ahead of rewards."""
        image = self.adb.screenshot(**kwargs)
        if image is not None and self.recovery_handler and self.recovery_handler(image):
            raise _GameReloaded()
        return image

    def _stop_reward_input(self, reason):
        self.halt_reason = reason
        print(f"[Event] {reason}")
        raise _BattleInputStopped()

    def _handle_event_rewards(self, image, depth=0):
        panel = find_reward_panel(image)
        if panel is None:
            return image
        if depth >= 4:
            self._stop_reward_input("Bảng bonus xuất hiện liên tục; dừng để kiểm tra giao diện.")
        priority = self.settings.get("event_resource_priority", "dark")
        # Wait for card/label animations before deciding that a resource is absent.
        for attempt in range(3):
            choice = panel.preferred(priority)
            if choice is not None:
                break
            if attempt < 2:
                time.sleep(.2)
                image = self._capture(use_cache=False)
                if image is None:
                    self._stop_reward_input("Mất ảnh khi đọc bảng bonus sự kiện.")
                panel = find_reward_panel(image)
                if panel is None:
                    return image
        else:
            self._stop_reward_input(
                "Không nhận diện được bonus tài nguyên; dừng để tránh chọn lính. "
                "Hãy chọn bonus thủ công rồi khởi động lại bot.")
        if not self.adb.tap(*choice.point, jitter=0, delay=.15):
            self._stop_reward_input("ADB không chọn được bonus tài nguyên.")
        print(f"[Event] Chọn bonus {choice.resource} tại {choice.point}.")
        self._reward_generation += 1
        # Never return an obscured frame to count OCR or a deployment routine.
        clear_frames = 0
        for attempt in range(8):
            image = self._capture(use_cache=False)
            if image is not None and find_reward_panel(image) is None:
                self._guard_battle_frame(image)
                clear_frames += 1
                if clear_frames < 2:
                    time.sleep(.1)
                    continue
                # A reward click can clear the selected troop/spell card.
                if self.state == FarmState.ATTACKING and self._selected_battle_card is not None:
                    if not self.adb.tap(*self._selected_battle_card, jitter=0, delay=.03):
                        self._stop_reward_input("ADB không chọn lại được ô quân/phép sau bonus.")
                    image = self._capture(use_cache=False)
                    if image is None:
                        self._stop_reward_input("Mất ảnh sau khi chọn lại ô quân/phép.")
                    if find_reward_panel(image) is not None:
                        return self._handle_event_rewards(image, depth + 1)
                return image
            clear_frames = 0
            if attempt < 7:
                time.sleep(.2)
        self._stop_reward_input("Bảng bonus chưa đóng sau khi chọn tài nguyên; dừng thao tác.")

    def _battle_tap(self, x, y, *, select=False, **kwargs):
        if self.settings.get("event_mode", False):
            image = self._screenshot(use_cache=False)
            if image is None:
                self._stop_reward_input("Mất ảnh trước thao tác trong trận sự kiện.")
            self._guard_battle_frame(image, before_input=True)
        success = self.adb.tap(x, y, **kwargs)
        if success and select:
            self._selected_battle_card = (x, y)
        return success

    @staticmethod
    def _reward_safe_point(point):
        # Army portraits and exterior deployment points cannot select a reward
        # while a modal interrupts a burst. Remaining counts/actions are then
        # reconciled from the first frame after resolving it.
        x, y = point
        return x < 325 or x > 1275 or y < 255 or y > 705

    def _battle_tap_many(self, targets, *, interval, select_first=False,
                         fast=False, screenshot=None):
        if not targets:
            return True
        if not self.settings.get("event_mode", False):
            return self.adb.tap_many(targets, interval=interval)
        if fast and all(self._reward_safe_point(p) for p in targets):
            image = (self._handle_event_rewards(screenshot) if screenshot is not None
                     else self._screenshot(use_cache=False))
            if image is None:
                self._stop_reward_input("Mất ảnh trước nhóm thao tác trong trận sự kiện.")
            self._guard_battle_frame(image, before_input=True)
            success = self.adb.tap_many(targets, interval=interval)
            if success and select_first:
                self._selected_battle_card = targets[0]
            return success
        # Check before each individual tap, including between card selection
        # and deployment; a queued batch could otherwise hit a reward card.
        for index, (x, y) in enumerate(targets):
            if not self._battle_tap(x, y, select=select_first and index == 0,
                                    jitter=0, delay=0):
                return False
            if index < len(targets) - 1:
                time.sleep(interval)
        return True

    def reset_after_reload(self):
        """Discard battle-specific state before rechecking Home after a reload."""
        self.invalidate_ui_cache()
        self._combo_profile = None
        self._attack_tactics = None
        self._confirmed_main_points = []
        self._electro_drop_points = []
        self._hero_entry = None
        self._warden_slot = None
        self._warden_deployed_ts = 0.0
        self._warden_low_health_frames = 0
        self._deployed_hero_slots.clear()
        self._heroes_deployed_ts = 0.0
        self._hero_abilities_used = False
        self._deployment_rejected = False
        self._selected_battle_card = None
        self._verified_battle_points.clear()
        self._pending_ability_names.clear()
        self._pending_spells.clear()
        self._spell_check_frames.clear()
        self._vision_frame = self._guarded_frame = None
        self._count_cache.clear()
        self._depleted_cache.clear()
        self.battle_start_ts = 0.0
        self.state = FarmState.HOME
        self.adb.invalidate_cache()

    # ─── State handlers ─────────────────────────────────────

    def _handle_state(self):
        if self.state == FarmState.HOME:
            self._state_home()
        elif self.state == FarmState.FIND_MATCH:
            self._state_find_match()
        elif self.state == FarmState.LOOT_CHECK:
            self._state_loot_check()
        elif self.state == FarmState.ATTACKING:
            self._state_attacking()
        elif self.state == FarmState.BATTLE_WAIT:
            self._state_battle_wait()
        elif self.state == FarmState.RESULT:
            self._state_result()
        elif self.state == FarmState.TRAIN:
            self._state_train()
        elif self.state == FarmState.COLLECT:
            self._state_collect()

    def _state_home(self):
        """Ở màn hình chính -- tìm nút Attack! góc dưới trái để mở menu."""
        # Tự động luyện quân lần đầu khi bật bot nếu bật auto_train
        if self.settings.get("auto_train", True) and not self._initial_trained:
            print("[Farm] 🛡️ Khởi động: nạp đầy hàng đợi quân đội (TRAIN)...")
            self._initial_trained = True
            self.state = FarmState.TRAIN
            return

        if self._home_verified and "home_attack" in self._button_cache:
            x, y = self._button_cache["home_attack"]
            if not self.adb.tap(x, y, delay=0.05):
                return
            print(f"[Farm] --> Bấm Attack tại ({x},{y}) từ cache")
            self._home_verified = False
            self._find_phase = "menu"
            self.state = FarmState.FIND_MATCH
            time.sleep(0.35)
            return

        print("[Farm] HOME -- Tìm nút Attack!...")
        img = self._screenshot()
        if img is None:
            return

        # The partial template confirms Home; the full artwork centers the tap.
        anchor = self.adb.find_template(T_HOME_ATTACK, 0.80, img,
                                        region=HOME_ATTACK_REGION)
        pos = (self.adb.find_template(T_BASE_ATTACK, 0.65, img,
                                      region=HOME_ATTACK_REGION) if anchor else None)
        home_template = T_BASE_ATTACK if pos else T_HOME_ATTACK
        pos = pos or anchor

        if pos:
            self._button_cache["home_attack"] = pos
            self._button_templates["home_attack"] = home_template
            if not self.adb.tap(pos[0], pos[1], jitter=4):
                return
            print(f"[Farm] --> Bấm nút Attack! tại ({pos[0]},{pos[1]}), chuyển FIND_MATCH")
            time.sleep(0.35)
            self._home_verified = False
            self._find_phase = "menu"
            self.state = FarmState.FIND_MATCH
            return

        if self._is_scout_screen(img):
            self.state = FarmState.LOOT_CHECK
            return

        if self._is_result_screen(img):
            self.state = FarmState.RESULT
            return

        if self._is_battle_screen(img):
            print("[Farm] Phát hiện trận đã bắt đầu, chuyển ATTACKING")
            self._battle_plan = self.planner.plan(img)
            self.battle_start_ts = time.time()
            self.state = FarmState.ATTACKING
            return

        print("[Farm] Không thấy nút Attack tại HOME; chờ màn hình ổn định.")
        time.sleep(0.8)

    def _state_find_match(self):
        """
        Tìm trận:
        1. Nếu đã thấy đối thủ (màn hình do thám) -> chuyển LOOT_CHECK
        2. Nếu đang ở màn hình My Army -> bấm Attack! (rank1.png / rank2.png)
        3. Nếu đang ở menu Attack -> bấm 'Find a Match' (findmatch.png)
        4. Nếu đang tải mây trắng -> chờ
        """
        print("[Farm] 🔍 FIND_MATCH — Đang kiểm tra giao diện tìm trận...")
        img = self._screenshot()
        if img is None:
            return

        # Compare only the small saved button area. A changed layout falls
        # back to a full lookup below, avoiding blind cached taps.
        if self._find_phase == "menu" and self._cached_button_visible("find_match", img):
            if self.adb.tap(*self._button_cache["find_match"], delay=0.05):
                print(f"[Farm] --> Bấm Find a Match từ cache tại {self._button_cache['find_match']}")
                self._home_attack_failures = 0
                self._find_phase = "army"
                time.sleep(0.35)
            return
        if self._find_phase == "menu":
            self._button_cache.pop("find_match", None)
            self._button_templates.pop("find_match", None)
        if self._find_phase == "army" and self._cached_button_visible("army_attack", img):
            if self.adb.tap(*self._button_cache["army_attack"], delay=0.05):
                print(f"[Farm] --> Bấm Army Attack từ cache tại {self._button_cache['army_attack']}")
                self._home_attack_failures = 0
                self._find_phase = "scout"
                time.sleep(0.65)
            return
        if self._find_phase == "army":
            self._button_cache.pop("army_attack", None)
            self._button_templates.pop("army_attack", None)

        # ADB success only means Android received the tap, not that the game
        # accepted it. A missed Home tap used to leave this state stuck forever.
        if self._is_home_screen(img):
            self._home_attack_failures += 1
            print(f"[Farm] Vẫn ở Home sau khi bấm Attack ({self._home_attack_failures}/4); thử lại.")
            if self._home_attack_failures >= 4:
                self.halt_reason = "Nút Attack không mở menu sau 4 lần thử; kiểm tra game hoặc ảnh mẫu."
                return
            # Recenter the learned point from the full button on failure.
            pos = self.adb.find_template(T_BASE_ATTACK, 0.65, img,
                                         region=HOME_ATTACK_REGION)
            if pos:
                self._button_cache["home_attack"] = pos
                self._button_templates["home_attack"] = T_BASE_ATTACK
            else:
                self._button_cache.pop("home_attack", None)
                self._button_templates.pop("home_attack", None)
            self._home_verified = True
            self._find_phase = "menu"
            self.state = FarmState.HOME
            return

        # 1. Kiểm tra đã vào màn hình do thám đối thủ chưa
        if self._is_scout_screen(img):
            self._home_attack_failures = 0
            print("[Farm] --> Đã vào màn hình đối thủ, chuyển LOOT_CHECK")
            self.state = FarmState.LOOT_CHECK
            return

        if self._is_battle_screen(img):
            self._home_attack_failures = 0
            print("[Farm] --> Thời gian do thám đã hết, trận bắt đầu; chuyển ATTACKING")
            self._battle_plan = self.planner.plan(img)
            self.battle_start_ts = time.time()
            self.state = FarmState.ATTACKING
            return

        if self._is_result_screen(img):
            self._home_attack_failures = 0
            self.state = FarmState.RESULT
            return

        # 2. Kiểm tra màn hình My Army (xác nhận quân trước khi tìm trận)
        for tpl in [T_ARMY_ATTACK, T_ARMY_ATTACK2]:
            if self._tap_ui("army_attack", tpl, 0.75, img):
                self._home_attack_failures = 0
                print("[Farm] --> Đã bấm 'Attack!' trên màn hình My Army")
                self._find_phase = "scout"
                time.sleep(0.65)
                return

        # 3. Kiểm tra nút 'Find a Match' trên thẻ Battle trong menu Attack
        for tpl in [T_FIND_MATCH2, T_FIND_MATCH_BACKUP]:
            if self._tap_ui("find_match", tpl, 0.75, img):
                self._home_attack_failures = 0
                print("[Farm] --> Đã bấm 'Find a Match'")
                self._find_phase = "army"
                time.sleep(0.35)
                return

        # Đang trong màn hình mây hoặc loading
        time.sleep(0.3)

    def _state_loot_check(self):
        """Kiểm tra loot của đối thủ — đánh hoặc bấm Next."""
        img = self._screenshot()
        if img is None:
            return

        # Kiểm tra còn ở màn hình do thám không
        if not self._is_scout_screen(img):
            # Nếu thời gian do thám trôi qua và trận tự bắt đầu:
            if self._is_battle_screen(img):
                print("[Farm] ⏱️ Hết thời gian do thám, trận đã tự bắt đầu -> TẤN CÔNG!")
                self.state = FarmState.ATTACKING
                self._battle_plan = self.planner.plan(img)
                self.battle_start_ts = time.time()
                return
            # Nếu văng khỏi màn hình do thám
            self.state = FarmState.FIND_MATCH
            return

        loot = self.reader.read_loot(img)
        print(f"[Farm] 💰 Loot: {self.reader.format_loot(loot)}")

        if not self.reader.loot_meets_threshold(loot, self.settings):
            self._skip_scout(img, "Loot chưa đủ")
            return

        self._battle_plan = self.planner.plan(img)
        if self._battle_plan is None:
            self._skip_scout(img, "Không xác định được vùng thả quân hợp lệ")
            return

        source = ("rìa vùng xây dựng, sẽ thử và xác nhận từng điểm" if self._battle_plan.requires_probe
                  else "đường viền đỏ")
        print(f"[Farm] ✅ Loot đạt yêu cầu; tìm thấy {len(self._battle_plan.troop_points)} "
              f"điểm ứng viên từ {source}.")
        self.state = FarmState.ATTACKING
        self.battle_start_ts = time.time()

    def _skip_scout(self, screenshot, reason: str):
        self.skip_count += 1
        self._battle_plan = None
        print(f"[Farm] ❌ {reason} (skip #{self.skip_count}) -> Bấm Next...")
        if self._tap_ui("next", T_FIND_MATCH, 0.75, screenshot,
                        region=NEXT_REGION, trust_cache=True):
            time.sleep(0.4)
        else:
            print("[Farm] Không thấy Next; chờ xác nhận màn hình trước khi thao tác.")
            time.sleep(0.5)

    def _state_attacking(self):
        """Deploy the calibrated combo into this opponent's safe areas."""
        print("[Farm] ⚔️ ATTACKING — Bắt đầu thả quân...")
        img = self._screenshot()
        if img is None:
            return
        if self._battle_plan is None:
            self._battle_plan = self.planner.plan(img)
        if self._battle_plan is None:
            print("[Farm] Không tìm được vùng thả an toàn; rút lui, không bấm tọa độ dự phòng.")
            if self._force_end_battle():
                self.state = FarmState.RESULT
            else:
                self.battle_start_ts = time.time() - self.settings.get("farm_battle_timeout", 85)
                self.state = FarmState.BATTLE_WAIT
            return

        self._attack_tactics = AttackTactics.from_battle(self._battle_plan, img)
        self._confirmed_main_points = []
        self._electro_drop_points = []
        self._hero_entry = None
        self._warden_deployed_ts = 0.0
        self._hero_abilities_used = False
        self._warden_low_health_frames = 0
        self._warden_slot = None
        self._deployed_hero_slots.clear()
        self._heroes_deployed_ts = 0.0
        self._selected_battle_card = None
        self._pending_spells.clear()
        self._spell_check_frames.clear()
        if self._battle_plan.requires_probe:
            print("[Farm] Viền đỏ không đủ tin cậy; dò các cạnh ngoài vùng xây dựng "
                  "(kể cả cây/trang trí) và xác nhận bằng số quân.")
        print(f"[Farm] Hướng tấn công chính: {self._attack_tactics.entry}; "
              f"{len(self._attack_tactics.main_points)} điểm thả quân, "
              f"{len(self._attack_tactics.hotspots)} vùng công trình ước lượng.")

        if self._combo_profile is None:
            self._combo_profile = self._calibrate_combo(img)
        if self._combo_profile is None:
            self.halt_reason = "Không định vị được thanh quân/phép cho combo hiện tại."
            return
        if self._combo_profile.resolution != img.shape[:2]:
            self.halt_reason = "Độ phân giải game đã đổi sau khi ghi nhớ combo; khởi động lại bot để quét lại."
            return

        img = self._ensure_deploy_bar_ready(img)
        if img is None:
            return

        speed_button = self.adb.find_template(T_4X, config.LOOSE_THRESHOLD, img)
        if speed_button:
            self._battle_tap(*speed_button, delay=0.05)

        self._deployment_rejected = False
        self._verified_battle_points.clear()
        self._pending_ability_names.clear()
        self._deploy_all_troops(img)
        if self.halt_reason:
            return
        if self._deployment_rejected:
            print("[Farm] Game không nhận điểm thả quân; rút khỏi trận và tiếp tục tìm base.")
            if self._force_end_battle():
                self.state = FarmState.RESULT
            else:
                self.battle_start_ts = time.time() - self.settings.get("farm_battle_timeout", 85)
                self.state = FarmState.BATTLE_WAIT
            return
        self._deploy_siege()
        if self.halt_reason:
            return
        self._deploy_cached_heroes()
        if self.halt_reason:
            return

        self._deploy_spells()
        if self.halt_reason:
            return

        self._maybe_activate_hero_abilities(None)

        self.state = FarmState.BATTLE_WAIT
        print(f"[Farm] Chờ trận kết thúc (timeout {self.settings.get('farm_battle_timeout', 85)}s)...")

    def _detect_troop_cards(self, img) -> List[Tuple[int, int]]:
        """Phát hiện động tất cả ô quân/phép trên thanh quân ở dưới màn hình."""
        return detect_bar_cards(img)

    def _calibrate_combo(self, image) -> Optional[ComboProfile]:
        """Locate cards and roles once per bot run; a restart reads a new combo."""
        cards = self._detect_troop_cards(image)
        if not cards:
            return None
        heroes = self.hero_mod.find_ready_heroes(image, enabled_only=False, cards=cards)
        hero_right = max((x for _, x, _ in heroes), default=None)
        slots = []
        for x, y in cards:
            if any(abs(x - hx) <= 50 for _, hx, _ in heroes):
                continue
            if is_siege_card(image, x, y):
                slots.append(CardSlot(x, y, "siege"))
                continue
            spell_name, score = self._identify_spell(image, x)
            role = "spell" if score >= 0.65 or (hero_right is not None and x > hero_right + 50) else "troop"
            slots.append(CardSlot(x, y, role,
                                  spell_name if role == "spell" and score >= 0.65 else ""))
        if not slots:
            return None
        if not any(slot.role == "troop" for slot in slots):
            return None
        print(f"[Farm] Ghi nhớ combo: {[(slot.role, slot.x) for slot in slots]}, "
              f"heroes={[(name, x) for name, x, _ in heroes]}")
        return ComboProfile(slots, heroes, image.shape[:2])

    def _ensure_deploy_bar_ready(self, first_image):
        """Wait for visible troop cards and repair a stale combo once if needed."""
        image = first_image
        for attempt in range(4):
            troop_slots = [slot for slot in self._combo_profile.cards if slot.role == "troop"]
            active = [slot for slot in troop_slots if not self._card_depleted(image, slot)]
            if active:
                return image
            print(f"[Farm] Chưa thấy quân sẵn sàng trên thanh ({attempt + 1}/4); chờ giao diện ổn định.")
            if attempt >= 1:
                candidate = self._calibrate_combo(image)
                if candidate and any(slot.role == "troop" and
                                     not self._card_depleted(image, slot)
                                     for slot in candidate.cards):
                    print("[Farm] Vị trí thanh quân đã đổi; cập nhật cache combo từ ảnh hiện tại.")
                    self._combo_profile = candidate
                    return image
            if attempt < 3:
                time.sleep(0.8)
                image = self._screenshot()
                if image is None:
                    self.halt_reason = "Mất ảnh màn hình khi chờ thanh quân sẵn sàng."
                    return None
        self.halt_reason = "Không thấy quân có thể thả sau 4 lần kiểm tra; bot dừng để tránh chờ trận rỗng."
        return None

    def _identify_spell(self, image, center_x: int) -> Tuple[str, float]:
        if self._spell_templates is None:
            paths = []
            for folder in ("Troop", "deploy-troop", "Use Troop/Main"):
                paths.extend(glob.glob(config.asset(f"TC_Hoi/Task_General/{folder}/*spell*.png")))
            self._spell_templates = []
            for path in paths:
                template = self.adb._load_template(path)
                if template is not None:
                    name = os.path.basename(path).removeprefix("use_main_use_").removesuffix("_spell.png")
                    self._spell_templates.append((name, template))
        roi = image[735:890, max(0, center_x - 58):min(image.shape[1], center_x + 58)]
        best_name, best_score = "", 0.0
        for name, template in self._spell_templates:
            if template.shape[0] > roi.shape[0] or template.shape[1] > roi.shape[1]:
                continue
            score = float(cv2.minMaxLoc(cv2.matchTemplate(roi, template,
                                                         cv2.TM_CCOEFF_NORMED))[1])
            if score > best_score:
                best_name, best_score = name, score
        return best_name, best_score

    def _use_vision_frame(self, image):
        if image is not self._vision_frame:
            self._vision_frame = image
            self._count_cache.clear()
            self._depleted_cache.clear()

    def _read_card_count(self, image, x, y):
        self._use_vision_frame(image)
        key = (x, y)
        if key not in self._count_cache:
            self._count_cache[key] = read_card_count(image, x, y)
        return self._count_cache[key]

    def _card_depleted(self, image, slot: CardSlot) -> bool:
        if image is None:
            return False
        self._use_vision_frame(image)
        key = (slot.x, slot.y, slot.role)
        if key in self._depleted_cache:
            return self._depleted_cache[key]
        if slot.role in ("troop", "spell") and self._read_card_count(image, slot.x, slot.y) == 0:
            self._depleted_cache[key] = True
            return True
        roi = image[slot.y-70:slot.y+35, slot.x-45:slot.x+45]
        depleted = roi.size > 0 and cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)[:, :, 1].mean() < 25
        self._depleted_cache[key] = depleted
        return depleted

    def _count_display_changed(self, before, after, slot: CardSlot) -> bool:
        return count_badge_changed(before, after, slot.x, slot.y)

    def _deploy_all_troops(self, first_image=None):
        """Deploy troop cards, keeping a confirmed main push for the heroes."""
        profile = self._combo_profile
        tactics = self._attack_tactics
        if tactics is None and self._battle_plan is not None:
            tactics = AttackTactics.from_battle(self._battle_plan, first_image)
            self._attack_tactics = tactics
            self._confirmed_main_points = []
        if profile is None or tactics is None:
            return
        image = first_image if first_image is not None else self._screenshot()
        if self._battle_plan is not None and self._battle_plan.requires_probe:
            self._deploy_perimeter_troops(image, profile, tactics)
            return
        confirmed_troop_slots = 0
        troop_slots = [slot for slot in profile.cards if slot.role == "troop"]
        for card_index, slot in enumerate(troop_slots):
            if self._card_depleted(image, slot):
                print(f"[Farm] Ô {slot.role} x={slot.x} đang xám; bỏ qua ô này.")
                continue
            if is_electro_card(image, slot.x, slot.y):
                image, points = self._deploy_electro_card(image, slot)
                if self.halt_reason:
                    return
                if points:
                    confirmed_troop_slots += 1
                continue
            around = self.settings.get("attack_around", True)
            candidates = list(dict.fromkeys(
                tactics.main_points + (tactics.flank_points if around else [])))
            if around and tactics.flank_points and len(tactics.main_points) >= 2:
                candidates = list(dict.fromkeys(tactics.main_points[:2] +
                                  tactics.flank_points[:1] + candidates))
            image, confirmed = self._deploy_regular_card(
                image, slot, candidates,
                lambda start, count: tactics.troop_targets(card_index, start, count, around))
            if self.halt_reason:
                return
            if not confirmed:
                self._deployment_rejected = True
                return
            confirmed_troop_slots += 1
            self._remember_main_drops(confirmed)
            if not self._confirmed_main_points:
                # If only a flank accepted troops, heroes must follow that
                # verified point instead of an untested main approach.
                self._confirmed_main_points.append(confirmed[0])
        if confirmed_troop_slots == 0:
            self._deployment_rejected = True
            return
        print(f"[Farm] Đã xác nhận thả quân từ {confirmed_troop_slots} ô; "
              f"hướng chính có {len(self._confirmed_main_points)} điểm đã dùng.")

    def _deploy_regular_card(self, image, slot, candidates, target_provider=None):
        """Learn a few points once, then send the remaining units as a burst."""
        candidates = list(dict.fromkeys(candidates))
        if self.settings.get("event_mode", False):
            safe = [p for p in candidates if self._reward_safe_point(p)]
            if safe:
                candidates = safe
        if not self._battle_tap_many([(slot.x, slot.y)], interval=0,
                                     select_first=True, fast=True, screenshot=image):
            self.halt_reason = "ADB không chọn được ô quân/phép."
            return image, []
        verified = [p for p in candidates if p in self._verified_battle_points]
        wanted = min(3 if target_provider else 1, len(candidates))
        for point in candidates:
            if len(verified) >= wanted:
                break
            if point in verified:
                continue
            if self._read_card_count(image, slot.x, slot.y) == 0 or self._card_depleted(image, slot):
                return image, verified
            if not self._battle_tap_many([point], interval=.02, fast=True, screenshot=image):
                self.halt_reason = "ADB không gửi được lệnh thử thả quân."
                return image, verified
            after, accepted = self._verify_card_use(image, slot)
            if after is None:
                return after, verified
            image = after
            if accepted:
                verified.append(point)
                self._verified_battle_points.add(point)
            else:
                print(f"[Farm] Ô {slot.x}: điểm {point} chưa làm giảm quân; đổi điểm thả.")
        if not verified:
            return image, []
        for burst in range(12):
            remaining = self._read_card_count(image, slot.x, slot.y)
            if remaining == 0 or self._card_depleted(image, slot):
                return image, verified
            # A modal may swallow part of a burst. It cannot receive reward
            # clicks from these exterior points; fresh counts decide what to
            # resume after choosing the resource.
            count = min(80, remaining) if remaining is not None else 20
            targets = [verified[index % len(verified)] for index in range(count)]
            generation = self._reward_generation
            if not self._battle_tap_many(targets, interval=.02, fast=True, screenshot=image):
                self.halt_reason = "ADB không gửi được nhóm lệnh thả quân."
                return image, verified
            after, accepted = self._verify_card_use(image, slot)
            if after is None:
                return after, verified
            image = after
            if not accepted and self._reward_generation == generation:
                print(f"[Farm] Ô {slot.x}: nhóm quân chưa được game nhận; dừng điểm này.")
                return image, verified
        self.halt_reason = "Chưa xác nhận thả hết quân sau nhiều nhóm lệnh; kiểm tra thanh quân."
        return image, verified

    def _deploy_electro_card(self, image, slot: CardSlot):
        """Confirm spaced directions first, then deploy the remainder together."""
        battle_image = image
        total = self._read_card_count(image, slot.x, slot.y)
        per_direction = max(1, int(self.settings.get("electro_per_direction", 3)))
        wanted = min(3, max(1, (total or 0) // per_direction))
        candidates = list(dict.fromkeys(self._battle_plan.troop_points))
        if self.settings.get("event_mode", False):
            safe = [p for p in candidates if self._reward_safe_point(p)]
            if safe:
                candidates = safe
        if self._confirmed_main_points:
            candidates.sort(key=lambda p: p not in self._confirmed_main_points)
        if not self._battle_tap_many([(slot.x, slot.y)], interval=0,
                                     select_first=True, fast=True, screenshot=image):
            self.halt_reason = "ADB không chọn được ô Electro."
            return image, []
        confirmed = []
        while candidates and len(confirmed) < wanted:
            if self._read_card_count(image, slot.x, slot.y) == 0 or self._card_depleted(image, slot):
                break
            ranked = (sorted(candidates, key=lambda p: min(math.dist(p, q) for q in confirmed),
                             reverse=True) if confirmed else candidates)
            if confirmed:
                ranked = [p for p in ranked if min(math.dist(p, q) for q in confirmed) >= 220]
            if not ranked:
                break
            point = ranked[0]
            candidates.remove(point)
            if point in self._verified_battle_points:
                confirmed.append(point)
                continue
            if not self._battle_tap_many([point], interval=.02, fast=True, screenshot=image):
                self.halt_reason = "ADB không gửi được lệnh thử thả Electro."
                return image, confirmed
            after, accepted = self._verify_card_use(image, slot)
            if after is None:
                return image, confirmed
            image = after
            if accepted:
                confirmed.append(point)
                self._verified_battle_points.add(point)
                print(f"[Farm] Electro: xác nhận hướng {len(confirmed)} tại {point}.")
        if not confirmed:
            return image, []
        # Track probe units per direction. Reusing a point verified by another
        # card does not itself consume an Electro Dragon.
        deployed = {p: 0 for p in confirmed}
        # A count is reliable enough to distribute the remaining group evenly;
        # uncertain counts use small bounded groups and the depletion check.
        for _ in range(12):
            remaining = self._read_card_count(image, slot.x, slot.y)
            if remaining == 0 or self._card_depleted(image, slot):
                break
            count = min(80, remaining) if remaining is not None else 9
            targets = []
            for index in range(count):
                point = min(confirmed, key=lambda p: deployed[p])
                targets.append(point)
                deployed[point] += 1
            generation = self._reward_generation
            if not self._battle_tap_many(targets, interval=.03, fast=True, screenshot=image):
                self.halt_reason = "ADB không gửi được nhóm Electro."
                return image, confirmed
            after, accepted = self._verify_card_use(image, slot)
            if after is None:
                return image, confirmed
            image = after
            if not accepted and self._reward_generation == generation:
                break
        for point in confirmed:
            if point not in self._confirmed_main_points:
                self._confirmed_main_points.append(point)
        self._electro_drop_points = confirmed
        self._hero_entry = confirmed[0]
        tactics = self._attack_tactics
        tactics.entry = confirmed[0]
        tactics.rage_entries = confirmed.copy()
        tactics.hotspots = AttackTactics._structure_hotspots(battle_image, self._battle_plan, confirmed[0])
        print(f"[Farm] Electro: {len(confirmed)} hướng; phần quân còn lại được thả theo nhóm.")
        return image, confirmed

    def _electro_side_points(self, anchor: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Pick nearby planned points on the same side of the base as an anchor."""
        plan = self._battle_plan
        if plan is None:
            return [anchor]
        center_x, center_y = plan.spell_center
        side = (anchor[0] >= center_x, anchor[1] >= center_y)
        nearby = sorted((point for point in plan.troop_points
                         if point != anchor and
                         (point[0] >= center_x, point[1] >= center_y) == side and
                         math.dist(point, anchor) <= 230),
                        key=lambda point: math.dist(point, anchor))
        selected = [anchor]
        for point in nearby:
            if all(math.dist(point, prior) >= 55 for prior in selected):
                selected.append(point)
            if len(selected) == 3:
                break
        return selected

    def _verify_card_use(self, before, slot: CardSlot):
        """Confirm a troop/spell count decrease from fresh frames, allowing UI lag."""
        before_count = self._read_card_count(before, slot.x, slot.y)
        frames = []
        for attempt in range(3):
            # A redraw may arrive after the first capture. Reusing the short
            # screenshot cache here would keep checking the same stale badge.
            after = self._screenshot(use_cache=False)
            if after is None:
                label = "phép" if slot.role == "spell" else "quân"
                self.halt_reason = f"Mất ảnh màn hình khi kiểm tra thả {label}."
                return None, False
            if slot.role == "spell":
                frames.append(after)
            after_count = self._read_card_count(after, slot.x, slot.y)
            depleted = self._card_depleted(after, slot)
            if before_count is not None and after_count is not None:
                accepted = after_count < before_count
            else:
                accepted = ((depleted and not self._card_depleted(before, slot)) or
                            self._count_display_changed(before, after, slot))
            if accepted:
                if slot.role == "spell":
                    self._spell_check_frames.clear()
                return after, True
            if attempt < 2:
                time.sleep(0.25)
        if slot.role == "spell":
            self._spell_check_frames = frames
        return after, False

    def _deploy_perimeter_troops(self, image, profile: ComboProfile,
                                tactics: AttackTactics):
        """Test outer construction edges, then reuse a confirmed troop point."""
        candidates = list(dict.fromkeys(self._battle_plan.troop_points))
        battle_image = image
        confirmed_point = None
        confirmed_slots = 0
        for slot in (card for card in profile.cards if card.role == "troop"):
            if self._card_depleted(image, slot):
                continue
            if is_electro_card(image, slot.x, slot.y):
                image, points = self._deploy_electro_card(image, slot)
                if self.halt_reason:
                    return
                if points:
                    confirmed_point = points[0]
                    confirmed_slots += 1
                continue
            probes = ([confirmed_point] + [p for p in candidates if p != confirmed_point]
                      if confirmed_point else candidates)
            image, confirmed = self._deploy_regular_card(image, slot, probes)
            if self.halt_reason:
                return
            if not confirmed:
                print(f"[Farm] Ô quân x={slot.x} chưa có điểm thả được xác nhận.")
                continue
            confirmed_point = confirmed[0]
            confirmed_slots += 1
            for point in confirmed:
                if point not in self._confirmed_main_points:
                    self._confirmed_main_points.append(point)
            print(f"[Farm] ✅ Game đã nhận quân tại rìa {confirmed_point}.")

        if confirmed_slots == 0:
            self._deployment_rejected = True
            return
        main_points = self._electro_drop_points or [confirmed_point]
        tactics.entry = main_points[0]
        tactics.main_points = main_points
        tactics.flank_points = []
        tactics.hotspots = AttackTactics._structure_hotspots(
            battle_image, self._battle_plan, main_points[0])
        print(f"[Farm] Đã xác nhận thả quân từ {confirmed_slots} ô; "
              f"hướng đã dùng: {main_points}.")

    def _remember_main_drops(self, targets: List[Tuple[int, int]]):
        for point in targets:
            if (point in self._attack_tactics.main_points and
                    point not in self._confirmed_main_points):
                self._confirmed_main_points.append(point)

    def _deploy_siege(self):
        """Deploy each available siege card once on the confirmed troop entry."""
        profile = self._combo_profile
        if profile is None:
            return
        siege_slots = [slot for slot in profile.cards if slot.role == "siege"]
        if not siege_slots:
            return
        if not self._confirmed_main_points:
            self.halt_reason = "Không có điểm thả quân được xác nhận cho xe công thành."
            return
        image = self._screenshot()
        if image is None:
            self.halt_reason = "Mất ảnh màn hình trước khi thả xe công thành."
            return
        target = self._hero_entry or self._confirmed_main_points[0]
        for slot in siege_slots:
            if self._card_depleted(image, slot):
                continue
            if not self._battle_tap_many([HeroModule.portrait_point(slot.x, slot.y), target],
                                         interval=.03, select_first=True,
                                         fast=True, screenshot=image):
                self.halt_reason = "ADB không gửi được lệnh thả xe công thành."
                return
            self._hero_entry = target
            self._selected_battle_card = None
            print(f"[Farm] Đã gửi lệnh thả xe công thành tại {target}; không bấm kỹ năng xe.")
            image = self._screenshot(use_cache=False)
            if image is None:
                self.halt_reason = "Mất ảnh màn hình sau khi thả xe công thành."
                return

    def _remember_deployed_hero(self, name, x, y):
        if name in self._deployed_hero_slots:
            return
        deployed_ts = time.time()
        self._deployed_hero_slots[name] = (x, y)
        if not self._heroes_deployed_ts:
            self._heroes_deployed_ts = deployed_ts
        if name == "warden":
            self._warden_deployed_ts = deployed_ts
            self._warden_slot = (x, y)

    def _deploy_cached_heroes(self):
        """Send the cached hero pairs together and reconcile interrupted pairs."""
        profile = self._combo_profile
        if profile is None or self._battle_plan is None:
            return
        allowed = set(self.hero_mod.get_enabled_heroes())
        if not any(name in allowed for name, _, _ in profile.heroes):
            return
        if self._attack_tactics is None or not self._confirmed_main_points:
            self.halt_reason = "Không có tọa độ thả hero an toàn."
            return
        image = self._screenshot()
        if image is None:
            self.halt_reason = "Mất ảnh màn hình trước khi thả hero."
            return
        targets = ([self._hero_entry] * len(profile.heroes) if self._hero_entry else
                   self._attack_tactics.hero_targets(len(profile.heroes), self._confirmed_main_points))
        pending = []
        for index, (name, x, y) in enumerate(profile.heroes):
            if name not in allowed or name in self._deployed_hero_slots:
                continue
            if HeroModule.has_deployed_health(image, x, y):
                self._remember_deployed_hero(name, x, y)
            elif not self._card_depleted(image, CardSlot(x, y, "hero")):
                pending.append((name, x, y, targets[index]))
        # A bonus can swallow a suffix of the commands. A health strip (or a
        # dead gray portrait) acknowledges deployment; retry only missing pairs.
        for attempt in range(4):
            if not pending:
                return
            generation = self._reward_generation
            self._selected_battle_card = None
            commands = [point for _, x, y, target in pending
                        for point in (HeroModule.portrait_point(x, y), target)]
            event = self.settings.get("event_mode", False)
            if event and not all(self._reward_safe_point(p) for p in commands):
                # Keep each selection paired with its map tap when an entry
                # overlaps a reward card and cannot be sent as a safe burst.
                success = True
                for _, x, y, target in pending:
                    success = self._battle_tap_many(
                        [HeroModule.portrait_point(x, y), target], interval=.03,
                        select_first=True)
                    self._selected_battle_card = None
                    if not success:
                        break
            else:
                success = self._battle_tap_many(commands, interval=.03,
                                                fast=True, screenshot=image)
            if not success:
                self.halt_reason = "ADB không gửi được nhóm lệnh thả hero."
                return
            image = self._screenshot(use_cache=False)
            if image is None:
                self.halt_reason = "Mất ảnh màn hình sau nhóm thả hero."
                return
            for check in range(2):
                unresolved = []
                for name, x, y, target in pending:
                    if (HeroModule.has_deployed_health(image, x, y) or
                            self._card_depleted(image, CardSlot(x, y, "hero"))):
                        self._remember_deployed_hero(name, x, y)
                        print(f"[Hero] {name} -> {target} (đã xác nhận trên thanh quân)")
                    else:
                        unresolved.append((name, x, y, target))
                pending = unresolved
                if not pending or check == 1 or self._reward_generation != generation:
                    break
                # The first health strip may lag behind the actual deployment.
                # Wait for its redraw before a retry can become an ability tap.
                time.sleep(.1)
                image = self._screenshot(use_cache=False)
                if image is None:
                    self.halt_reason = "Mất ảnh khi xác nhận thanh máu tướng."
                    return
            if pending:
                time.sleep(.1)
        if pending:
            self.halt_reason = "Chưa xác nhận thả tướng: " + ", ".join(p[0] for p in pending)

    def _reconcile_spell_use(self, before, slot):
        """Resolve an ambiguous cast before sending another map tap.

        Two fresh, matching counts distinguish a late redraw from a rejected
        cast. An unreadable or increasing count never authorizes a retry.
        """
        before_count = self._read_card_count(before, slot.x, slot.y)
        previous_count = None
        changed_frames = 0
        after = before
        for attempt in range(3):
            time.sleep(.25)
            after = self._screenshot(use_cache=False)
            if after is None:
                self.halt_reason = "Mất ảnh màn hình khi đối soát số phép."
                return None, "uncertain"
            count = self._read_card_count(after, slot.x, slot.y)
            if count is not None and count == previous_count:
                if count == 0 or (before_count is not None and count < before_count):
                    return after, "used"
                if before_count is not None and count == before_count:
                    return after, "unchanged"
            previous_count = count
            # Retain the glyph comparison fallback when numeric OCR is unclear.
            changed = ((count is None or before_count is None) and
                       ((self._card_depleted(after, slot) and
                         not self._card_depleted(before, slot)) or
                        self._count_display_changed(before, after, slot)))
            changed_frames = changed_frames + 1 if changed else 0
            if changed_frames >= 2:
                return after, "used"
        return after, "uncertain"

    def _log_spell_verification_failure(self, before, slot):
        frames = [before] + self._spell_check_frames
        counts = [self._read_card_count(frame, slot.x, slot.y) for frame in frames]
        print(f"[Spell] {slot.name} x={slot.x}: chưa xác nhận lần thả; "
              f"số trước/sau={counts}. Đối soát lại trước khi bấm tiếp.")
        try:
            folder = os.path.join(config.BASE_DIR, "diagnostics", "spell_failures",
                                  f"{time.time_ns()}-x{slot.x}")
            os.makedirs(folder, exist_ok=True)
            for index, frame in enumerate(frames):
                crop = frame[max(0, slot.y - 125):slot.y + 50,
                             max(0, slot.x - 65):slot.x + 80]
                if crop.size:
                    cv2.imwrite(os.path.join(folder, f"{index}-count-{counts[index]}.png"), crop)
            print(f"[Spell] Ảnh kiểm tra: {folder}")
        except (OSError, cv2.error) as error:
            print(f"[Spell] Không lưu được ảnh kiểm tra: {error}")
        finally:
            self._spell_check_frames.clear()

    def _defer_spell(self, slot, progress):
        if progress.resume_attempts >= 3:
            self._pending_spells.pop(slot, None)
            print(f"[Spell] {slot.name} x={slot.x}: dừng sau 3 lượt phục hồi chưa thành công.")
        else:
            progress.retry_at = time.monotonic() + 2.0
            print(f"[Spell] {slot.name} x={slot.x}: lưu phần chưa hoàn tất; kiểm tra tiếp khi chờ trận.")

    def _record_spell_use(self, before, after, slot, progress):
        old_count = self._read_card_count(before, slot.x, slot.y)
        remaining = self._read_card_count(after, slot.x, slot.y)
        used = max(1, old_count - remaining) if old_count is not None and remaining is not None else 1
        target = self._attack_tactics.spell_target(slot.name, progress.cast_index)
        progress.cast_index += used
        progress.resume_attempts = 0
        progress.unconfirmed_before = None
        count_text = f", còn x{remaining}" if remaining is not None else ""
        print(f"[Spell] Đã thả {slot.name} -> {target}{count_text}")

    def _deploy_spells(self, first_image=None, *, resume=False):
        profile = self._combo_profile
        tactics = self._attack_tactics
        if profile is None or tactics is None:
            return
        spells = (list(self._pending_spells) if resume else
                  [slot for slot in profile.cards if slot.role == "spell"])
        if not spells:
            return
        # Give troops and heroes time to cross the boundary before support casts.
        if not resume:
            time.sleep(1.5)
        image = first_image if first_image is not None else self._screenshot(use_cache=False)
        if image is None:
            self.halt_reason = "Mất ảnh màn hình trước khi thả spell."
            return
        self._maybe_activate_hero_abilities(image)
        for slot in spells:
            progress = self._pending_spells.get(slot)
            if resume:
                if progress is None or time.monotonic() < progress.retry_at:
                    continue
                progress.resume_attempts += 1
            if self._card_depleted(image, slot):
                self._pending_spells.pop(slot, None)
                continue
            if not slot.name or tactics.spell_target(slot.name, 0) is None:
                print(f"[Spell] Không nhận dạng chắc chắn ô x={slot.x}; giữ lại để tránh ném sai mục tiêu.")
                self._pending_spells.pop(slot, None)
                continue
            if progress is None:
                progress = SpellProgress()
                self._pending_spells[slot] = progress
            if progress.unconfirmed_before is not None:
                before = progress.unconfirmed_before
                image, status = self._reconcile_spell_use(before, slot)
                if image is None:
                    return
                if status == "uncertain":
                    self._defer_spell(slot, progress)
                    continue
                if status == "used":
                    self._record_spell_use(before, image, slot, progress)
                progress.unconfirmed_before = None
            failed_casts = 0
            for _ in range(30):
                if self._card_depleted(image, slot):
                    self._pending_spells.pop(slot, None)
                    break
                if (self.battle_start_ts and time.time() - self.battle_start_ts >=
                        self.settings.get("farm_battle_timeout", 85)):
                    return
                target = tactics.spell_target(slot.name, progress.cast_index)
                # Hero ability inputs can change the selected card. Select
                # this spell again in the same command as every single cast.
                if not self._battle_tap_many([(slot.x, slot.y), target], interval=.03,
                                             select_first=True, fast=True, screenshot=image):
                    self.halt_reason = "ADB không chọn và thả được spell."
                    return
                after, accepted = self._verify_card_use(image, slot)
                if after is None:
                    return
                self._maybe_activate_hero_abilities(after)
                if not accepted:
                    self._log_spell_verification_failure(image, slot)
                    progress.unconfirmed_before = image
                    after, status = self._reconcile_spell_use(image, slot)
                    if after is None:
                        return
                    if status != "used":
                        image = after
                        if status == "unchanged":
                            progress.unconfirmed_before = None
                            failed_casts += 1
                            if failed_casts < 3:
                                print(f"[Spell] {slot.name}: số phép chưa giảm; chọn lại và thử tiếp.")
                                continue
                        self._defer_spell(slot, progress)
                        break
                self._record_spell_use(image, after, slot, progress)
                image = after
                failed_casts = 0
                if self._card_depleted(after, slot):
                    self._pending_spells.pop(slot, None)
                    break
            else:
                self._defer_spell(slot, progress)

    def _resume_pending_spells(self, image):
        # Reuse active-deployment guards and reward/card restoration while
        # resuming a cast; keep RESULT/HOME/reload transitions from those guards.
        self.state = FarmState.ATTACKING
        try:
            self._deploy_spells(image, resume=True)
        finally:
            if self.state == FarmState.ATTACKING:
                self.state = FarmState.BATTLE_WAIT

    def _state_battle_wait(self):
        """Chờ trận kết thúc — kiểm tra Return Home, timeout hoặc Smart Surrender."""
        elapsed = time.time() - self.battle_start_ts
        min_farm = self.settings.get("min_farm", 45)
        battle_timeout = self.settings.get("farm_battle_timeout", 85)
        star_target = self.settings.get("star_target", 1)

        img = self._screenshot()
        if img is None:
            time.sleep(2)
            return

        if self._is_home_screen(img):
            self.state = FarmState.RESULT
            return

        # The End Battle confirmation also contains an Okay button. It is not
        # a result screen: accept the dialog before looking for Return Home.
        if find_confirmation_button(self.adb, img) is not None:
            if self._finish_end_battle(img):
                self.state = FarmState.RESULT
            return

        # 1. Kiểm tra trận đã kết thúc tự nhiên trước khi xét timeout.
        for tpl in [T_RETURN_HOME_NEW, T_RETURN_HOME, T_RETURN_HOME1, T_3STAR, T_OKAY_STAR, T_OK_HOME]:
            if self.adb.is_visible(tpl, 0.70, img, region=RETURN_HOME_REGION):
                stars = self._count_stars(img)
                print(f"[Farm] 🌟 Trận kết thúc tự nhiên — {stars} sao")
                self.state = FarmState.RESULT
                return

        self._maybe_activate_hero_abilities(img)

        # 2. Hết thời gian farm tối đa quy định.
        if elapsed >= battle_timeout:
            print(f"[Farm] ⏱️ Timeout farm ({int(elapsed)}s >= {battle_timeout}s) → Smart Surrender!")
            if self._force_end_battle(img):
                self.state = FarmState.RESULT
            return

        if self._pending_spells:
            if any(time.monotonic() >= progress.retry_at for progress in self._pending_spells.values()):
                self._resume_pending_spells(img)
            else:
                time.sleep(config.DELAY_BATTLE_CHECK)
            # Finish bounded recovery before early surrender, while retaining
            # the hard battle timeout above. Refresh elapsed time next tick.
            return

        # 3. Smart Surrender: Đã qua min_farm và đạt đủ số sao mục tiêu
        if elapsed >= min_farm:
            stars = self._count_stars(img)
            if stars >= star_target:
                print(f"[Farm] ⭐ Đã đạt mục tiêu {stars}/{star_target} sao sau {int(elapsed)}s → Smart Surrender rút lui sớm!")
                if self._force_end_battle(img):
                    self.state = FarmState.RESULT
                return

        time.sleep(config.DELAY_BATTLE_CHECK)

    def _maybe_activate_hero_abilities(self, image):
        if not self._deployed_hero_slots or self._hero_abilities_used:
            return
        health = (self.hero_mod.warden_health_fraction(image, *self._warden_slot)
                  if self._warden_slot else None)
        if health is not None and health < .35:
            self._warden_low_health_frames += 1
        else:
            self._warden_low_health_frames = 0
        danger = self._warden_low_health_frames >= 2
        delay = max(0, int(self.settings.get("warden_ability_delay", 10)))
        deployed_ts = self._warden_deployed_ts if self._warden_slot else self._heroes_deployed_ts
        elapsed = time.time() - deployed_ts
        if not self._pending_ability_names:
            if not danger and elapsed < delay:
                return
            names = list(self._deployed_hero_slots)
            if "warden" in names:
                names.remove("warden")
                names.insert(0, "warden")
            self._pending_ability_names = names
        self._selected_battle_card = None
        for attempt in range(4):
            generation = self._reward_generation
            targets = [HeroModule.portrait_point(*self._deployed_hero_slots[name])
                       for name in self._pending_ability_names]
            if not self._battle_tap_many(targets, interval=.02, fast=True, screenshot=image):
                return
            if self.settings.get("event_mode", False):
                image = self._screenshot(use_cache=False)
                if image is None:
                    return
                self._guard_battle_frame(image, before_input=True)
                if self._reward_generation != generation:
                    # Only deployed heroes enter this list. Their portrait
                    # clicks are idempotent after the one-use ability fires.
                    # Re-send the interrupted group; already-used abilities
                    # cannot fire twice, and the missing suffix now completes.
                    print("[Hero] Bonus ngắt nhóm kỹ năng; tiếp tục các tướng đã triển khai.")
                    continue
            names = self._pending_ability_names
            self._pending_ability_names = []
            self._hero_abilities_used = True
            reason = "Warden máu thấp" if danger else f"đã triển khai {int(elapsed)} giây"
            print(f"[Hero] Bật kỹ năng: {', '.join(names)} ({reason}).")
            return

    def _force_end_battle(self, screenshot=None) -> bool:
        """End the battle and accept its explicit Okay confirmation."""
        print("[Farm] 🏳️ Thực hiện End Battle / Surrender...")
        img = screenshot if screenshot is not None else self._screenshot()
        if img is None:
            return False

        if find_confirmation_button(self.adb, img) is not None:
            return self._finish_end_battle(img)

        # Trên một số màn, nút chính đã đổi từ End Battle sang Surrender.
        if self.adb.find_and_tap(T_SURRENDER, 0.70, img):
            return self._finish_end_battle(surrender_tapped=True)

        if not self.adb.find_and_tap(T_END_BATTLE_BUTTON, 0.70, img, region=END_BATTLE_REGION):
            print("[Farm] Chưa thấy nút End Battle; sẽ kiểm tra lại.")
            return False

        return self._finish_end_battle()

    def _finish_end_battle(self, image=None, surrender_tapped=False) -> bool:
        """Resolve a delayed Surrender/Okay prompt, then verify the result."""
        confirmed = False
        for attempt in range(6):
            if image is None:
                time.sleep(0.6)
                image = self._screenshot()
            if image is None:
                continue
            okay = find_confirmation_button(self.adb, image)
            if okay is not None:
                if not self.adb.tap(*okay, jitter=0, delay=0.1):
                    return False
                print("[Farm] --> Đã bấm Okay xác nhận End Battle")
                confirmed = True
            elif self._is_result_screen(image) or self._is_home_screen(image):
                return True
            elif not surrender_tapped and not confirmed and self.adb.find_and_tap(
                    T_SURRENDER, 0.70, image):
                surrender_tapped = True
                print("[Farm] --> Đã bấm Surrender; chờ hộp thoại Okay")
            image = None
        print("[Farm] Chưa xác nhận được màn kết thúc trận; sẽ kiểm tra lại.")
        return False

    def _count_stars(self, screenshot=None) -> int:
        """Đếm số sao đạt được trong trận đấu hoặc màn hình kết quả."""
        img = screenshot if screenshot is not None else self._screenshot()
        if img is None:
            return 0
        for count in (3, 2, 1):
            if any(self.adb.is_visible(path, 0.72, img,
                                       region=(1220, 575, 380, 155))
                   for path in STAR_TEMPLATES[count]):
                return count
        return 0

    def _state_result(self):
        """Xử lý màn hình kết quả: bấm Return Home để về làng."""
        self._pending_spells.clear()
        self._spell_check_frames.clear()
        img = self._screenshot()
        if img is None:
            return

        if self._is_home_screen(img):
            self.attack_count += 1
            print(f"[Farm] Đã về làng! Tổng số trận: {self.attack_count}")
            self._battle_plan = None
            self._home_verified = True
            self.state = FarmState.COLLECT
            return

        if find_confirmation_button(self.adb, img) is not None:
            self._finish_end_battle(img)
            return

        print("[Farm] 📊 RESULT — Đang bấm Return Home...")
        tapped = False
        if "return_home" in self._button_cache:
            if self._cached_button_visible("return_home", img):
                tapped = bool(self.adb.tap(*self._button_cache["return_home"], delay=0.05))
            else:
                self._button_cache.pop("return_home", None)
                self._button_templates.pop("return_home", None)
        if not tapped:
            for tpl in [T_RETURN_HOME_NEW, T_RETURN_HOME, T_RETURN_HOME1, T_3STAR]:
                if self._tap_ui("return_home", tpl, 0.70, img,
                                region=RETURN_HOME_REGION):
                    tapped = True
                    break
        if not tapped:
            for tpl in [T_OK_HOME, T_OKAY, T_OKAY_STAR]:
                if self.adb.find_and_tap(tpl, 0.70, img):
                    tapped = True
                    break

        if tapped:
            for _ in range(3):
                time.sleep(0.5)
                home_img = self._screenshot()
                if self._is_home_screen(home_img):
                    self.attack_count += 1
                    print(f"[Farm] Đã về làng! Tổng số trận: {self.attack_count}")
                    self._battle_plan = None
                    self._home_verified = True
                    self.state = FarmState.COLLECT
                    return

        print("[Farm] Chưa thấy nút Return Home; sẽ kiểm tra lại.")
        self._button_cache.pop("return_home", None)
        self._button_templates.pop("return_home", None)
        time.sleep(2)

    def _state_train(self):
        """Tự động luyện quân qua Quick Train Slot 1."""
        print("[Farm] 🛡️ TRAIN — Mở bảng quân đội và luyện quân Quick Train Slot 1...")
        img = self._screenshot()
        if img is None:
            self._train_failures += 1
            if self._train_failures >= 3:
                self.halt_reason = "Không chụp được màn hình khi luyện quân sau 3 lần thử. Kiểm tra ADB."
            return

        # 1. Mở Army panel từ Home nếu chưa mở (icon góc dưới trái)
        if not self.adb.find_and_tap(T_CHECK_TROOP, 0.65, img, region=(0, 550, 150, 200)):
            self._train_failures += 1
            print("[Farm] Chưa thấy biểu tượng quân đội ở HOME; sẽ thử lại.")
            if self._train_failures >= 3:
                self.halt_reason = "Không mở được bảng quân đội sau 3 lần thử. Kiểm tra màn hình game và độ phân giải 1600x900."
            return
        time.sleep(1.2)

        # 2. Chuyển sang tab Saved Recipes (Quick Train)
        # Ở giao diện 1600x900, (500, 95) là My Army; Saved Recipes ở (795, 95).
        self.adb.tap(*SAVED_RECIPES_TAB, jitter=5)
        time.sleep(1.0)

        # 3. Chỉ nút Use trong vùng Slot 1 mới thực sự luyện quân.
        img_panel = self._screenshot()
        trained = img_panel is not None and self.adb.find_and_tap(
            T_USE, 0.65, img_panel, region=QUICK_TRAIN_SLOT_1
        )
        if trained:
            print("[Farm] --> Đã bấm Use ở Quick Train Slot 1")
            time.sleep(0.8)
        elif img_panel is not None and self.adb.is_visible(T_SAVE_ARMY, 0.65, img_panel,
                                                           region=QUICK_TRAIN_SLOT_1):
            self.halt_reason = "Quick Train Slot 1 đang trống (Save Army). Hãy lưu đội hình vào Slot 1 rồi chạy lại."
        else:
            self._train_failures += 1
            print("[Farm] Không thấy Use ở Quick Train Slot 1; sẽ thử lại.")
            if self._train_failures >= 3:
                self.halt_reason = "Không tìm thấy Use ở Quick Train Slot 1 sau 3 lần thử. Kiểm tra tab Saved Recipes và ảnh mẫu."

        # 4. Đóng panel bằng nút X đỏ góc trên phải (1565, 85) hoặc Back
        self.adb.tap(1565, 85, jitter=4)
        time.sleep(1.0)

        if trained:
            self._train_failures = 0
            print("[Farm] ✅ Đã yêu cầu luyện quân -> chuyển COLLECT")
            self._home_verified = self._is_home_screen(self._screenshot())
            self.state = FarmState.COLLECT

    def _state_collect(self):
        """Thu thập tài nguyên và chuẩn bị chu kỳ mới."""
        print("[Farm] 🏠 COLLECT — Hoàn tất chu kỳ, trở về HOME...")
        self.state = FarmState.HOME

    # ─── Helpers ────────────────────────────────────────────

    def _tap_ui(self, key: str, template: str, threshold: float,
                screenshot=None, region=None, trust_cache: bool = False) -> bool:
        """Learn a button once, then tap its saved point on a verified screen."""
        if screenshot is not None and screenshot.shape[:2] != (config.ANDROID_H, config.ANDROID_W):
            self.invalidate_ui_cache()
            return False
        if trust_cache and key in self._button_cache:
            if self._cached_button_visible(key, screenshot):
                return bool(self.adb.tap(*self._button_cache[key], delay=0.05))
            self._button_cache.pop(key, None)
            self._button_templates.pop(key, None)
        pos = self.adb.find_template(template, threshold, screenshot, region=region)
        if pos is None:
            return False
        self._button_cache[key] = pos
        self._button_templates[key] = template
        return bool(self.adb.tap(*pos, delay=0.05))

    def _cached_button_visible(self, key: str, screenshot) -> bool:
        """Validate a saved button in a small crop before trusting its point."""
        if screenshot is None or key not in self._button_cache:
            return False
        path = self._button_templates.get(key)
        if path is None:
            return False
        template = self.adb._load_template(path)
        if template is None:
            return False
        x, y = self._button_cache[key]
        th, tw = template.shape[:2]
        pad = 18
        left = max(0, x - tw // 2 - pad)
        top = max(0, y - th // 2 - pad)
        right = min(screenshot.shape[1], x + (tw + 1) // 2 + pad)
        bottom = min(screenshot.shape[0], y + (th + 1) // 2 + pad)
        match = self.adb.find_template(path, 0.68, screenshot,
                                       region=(left, top, right - left, bottom - top))
        return match is not None and abs(match[0] - x) <= pad and abs(match[1] - y) <= pad

    def invalidate_ui_cache(self):
        """Force recalibration after a popup, reload, or layout change."""
        self._button_cache.clear()
        self._button_templates.clear()
        self._home_verified = False
        self._home_attack_failures = 0
        self._find_phase = "menu"
        self._battle_plan = None

    def _is_scout_screen(self, screenshot=None) -> bool:
        """Màn hình do thám còn nút Next; End Battle xuất hiện cả trong trận."""
        img = screenshot if screenshot is not None else self._screenshot()
        if img is None:
            return False
        return self.adb.is_visible(T_FIND_MATCH, 0.75, img, region=NEXT_REGION)

    def _is_battle_screen(self, screenshot=None) -> bool:
        """Nhận diện nút End Battle thật trong vùng góc trái của trận."""
        img = screenshot if screenshot is not None else self._screenshot()
        return img is not None and self.adb.is_visible(
            T_END_BATTLE_BUTTON, 0.70, img, region=END_BATTLE_REGION
        )

    def _is_result_screen(self, screenshot=None) -> bool:
        img = screenshot if screenshot is not None else self._screenshot()
        return img is not None and any(
            self.adb.is_visible(tpl, 0.70, img, region=RETURN_HOME_REGION) is True
            for tpl in [T_RETURN_HOME_NEW, T_RETURN_HOME, T_RETURN_HOME1, T_3STAR]
        )

    def _is_home_screen(self, screenshot=None) -> bool:
        img = screenshot if screenshot is not None else self._screenshot()
        return img is not None and self.adb.is_visible(
            T_HOME_ATTACK, 0.80, img, region=HOME_ATTACK_REGION
        ) is True

    def _go_home_safe(self):
        """Thoát về màn hình chính an toàn."""
        self.invalidate_ui_cache()
        for _ in range(3):
            img = self._screenshot()
            if img is None:
                time.sleep(2)
                continue
            for tpl in [T_RETURN_HOME_NEW, T_OK_HOME, T_RETURN_HOME, T_RETURN_HOME1, T_OKAY]:
                if self.adb.find_and_tap(tpl, 0.70, img):
                    time.sleep(2)
                    break
            else:
                self.adb.back()
                time.sleep(2)
        self.state = FarmState.HOME

    @property
    def recovering_home(self) -> bool:
        """True while retrying an Attack tap that did not leave Home."""
        return self._home_attack_failures > 0

    @property
    def status_line(self) -> str:
        """Dòng status ngắn để in ra terminal."""
        return (f"[Farm] State={self.state.name}  "
                f"Attacks={self.attack_count}  Skipped={self.skip_count}")
