"""Fake wall/monotonic clocks; real coordinator and BuilderFarmModule, no game input."""

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
import threading
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfoNotFoundError

import numpy as np
import cv2
import hashlib

from cocmagic import config
from cocmagic.builder_screen_reader import (
    Capture,
    ScreenObservation,
    ScreenKind,
    StarBonusObservation,
    StarBonusState,
    Village,
    BuilderScreenReader,
)
from cocmagic.builder_rewards import CartResult, RewardResult
from cocmagic.hybrid_coordinator import HybridCoordinator, vietnam_timezone
from cocmagic.hybrid_runtime import HybridRuntimeStore, HybridRuntime
from cocmagic.recovery import RuntimeWriteError
from cocmagic.modules.builder_farm_module import BuilderFarmModule
from cocmagic.village_module import ModuleScreen


class FakeClock:
    def __init__(self, value="2026-10-08T09:00:00+07:00"):
        self.wall = datetime.fromisoformat(value)
        self.elapsed = 100.0

    def now(self):
        return self.wall

    def monotonic(self):
        return self.elapsed

    def advance(self, seconds, *, wall=True, monotonic=True):
        if wall:
            self.wall += timedelta(seconds=seconds)
        if monotonic:
            self.elapsed += seconds


class MainContract:
    """Only test handoff gating. Production always constructs FarmModule."""

    def __init__(self, serial):
        self.device_serial = serial
        self.phase = "home"
        self.confirmed_screen = ModuleScreen.UNKNOWN
        self.halt_reason = None
        self.ready = False
        self.ticks = 0
        self.resumes = 0
        self.on_tick = None

    def tick(self, *, yield_requested):
        self.ticks += 1
        if self.on_tick:
            self.on_tick()
        request = yield_requested()
        self.ready = request and self.phase == "home"
        self.confirmed_screen = (
            ModuleScreen.HOME if self.phase == "home" else ModuleScreen.BATTLE
        )
        return True

    @property
    def can_yield(self):
        return self.ready

    @property
    def metrics(self):
        return {"wall_count": 0}

    status_line = "main"

    def suspend(self):
        assert self.can_yield

    def resume(self):
        self.resumes += 1
        self.ready = False
        self.confirmed_screen = ModuleScreen.UNKNOWN

    def reset_after_reload(self):
        self.ready = False

    def invalidate_after_popup(self):
        self.ready = False


class HybridTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.clock = FakeClock()
        self.store = HybridRuntimeStore(
            self.folder.name, "test:1", log=lambda _: None
        ).acquire()
        self.addCleanup(self.store.close)
        self.stop = threading.Event()
        self.adb = Mock(device="test:1", camera_revision=0, stop_event=self.stop)
        self.adb.input_lock = threading.RLock()
        self.adb.tap.return_value = True
        self.reader = Mock()
        self.frame = Capture(np.zeros((900, 1600, 3), np.uint8), 1, 100.0, 0)
        self.reader.capture.return_value = self.frame
        self.home()
        self.navigator = Mock()

        def proof(expected=None, **_):
            screen = self.reader.classify.return_value
            if screen.kind not in (ScreenKind.MAIN_HOME, ScreenKind.BUILDER_HOME):
                return None
            if expected is not None and screen.village != expected:
                return None
            return self.frame, screen

        self.navigator.confirmed_home.side_effect = proof
        self.transitions = []

        def switch(source, target):
            self.transitions.append((source, target))
            self.home(Village(target))
            return True

        self.navigator.switch_village.side_effect = switch

        def navigate(target, **kwargs):
            switch(kwargs.get("source"), target)
            return SimpleNamespace(success=True, reason="confirmed")

        self.navigator.navigate.side_effect = navigate
        self.rewards = Mock()
        self.bonus(StarBonusState.COMPLETE)
        self.rewards.collect_cart.return_value = CartResult(
            True, "verified", True, True
        )
        self.settings = config.validate_settings(
            {
                "run_mode": "hybrid",
                "builder_auto_setup_baby_dragons": False,
                "builder_collect_cart": False,
            }
        )
        self.builder = BuilderFarmModule(
            self.adb,
            self.settings,
            reader=self.reader,
            navigator=self.navigator,
            rewards=self.rewards,
            camera=Mock(),
            stop_event=self.stop,
            clock=self.clock.monotonic,
        )
        self.main = MainContract("test:1")
        self.coordinator = self.new_coordinator()

    def new_coordinator(self):
        return HybridCoordinator(
            "test:1",
            {"main": self.main, "builder": self.builder},
            self.store,
            self.settings,
            stop_event=self.stop,
            clock=self.clock,
        )

    def home(self, village=Village.BUILDER):
        kind = (
            ScreenKind.BUILDER_HOME
            if village == Village.BUILDER
            else ScreenKind.MAIN_HOME
        )
        self.reader.classify.return_value = ScreenObservation(
            kind, "home", village, points={"attack": (100, 800)}
        )

    def bonus(self, state, *, progress=None, claims=0, success=True):
        self.rewards.claim_star_bonus.return_value = RewardResult(
            success,
            state.value,
            StarBonusObservation(
                state, self.clock.monotonic(), state.value, progress=progress
            ),
            claims,
        )

    def startup_complete(self):
        self.assertTrue(self.coordinator.tick())
        self.assertEqual("main", self.coordinator.active_id)

    def test_0900_startup_runs_but_does_not_consume_daily(self):
        self.startup_complete()
        runtime = self.store.load()
        self.assertIsNotNone(runtime.last_valid_bonus_check_at)
        self.assertIsNone(runtime.last_daily_check_date)
        self.assertEqual("complete", runtime.last_bonus_state)
        self.assertFalse(runtime.builder_incomplete)
        self.rewards.collect_cart.assert_called_once()
        self.assertEqual(0, self.main.ticks)

    def test_1529_then_1531_schedules_once_without_exact_minute(self):
        self.clock.wall = self.clock.wall.replace(hour=15, minute=29)
        self.startup_complete()
        self.coordinator.tick()
        self.assertEqual(1, len(self.transitions))
        self.clock.advance(120)
        self.coordinator.tick()
        self.assertEqual("builder", self.coordinator.active_id)
        self.coordinator.tick()
        self.assertEqual("2026-10-08", self.store.load().last_daily_check_date)
        for _ in range(4):
            self.coordinator.tick()
        self.assertEqual(3, len(self.transitions))

    def test_1531_startup_also_satisfies_daily_without_duplicate(self):
        self.clock.wall = self.clock.wall.replace(hour=15, minute=31)
        self.startup_complete()
        for _ in range(5):
            self.coordinator.tick()
        self.assertEqual(1, len(self.transitions))
        self.assertEqual("2026-10-08", self.store.load().last_daily_check_date)

    def test_startup_training_across_cutoff_satisfies_daily_in_same_visit(self):
        self.clock.wall = self.clock.wall.replace(hour=15, minute=29)
        self.bonus(StarBonusState.AVAILABLE)
        self.coordinator.tick()
        self.assertIsNone(self.store.load().last_daily_check_date)
        self.clock.advance(120)
        self.home()
        self.bonus(StarBonusState.COMPLETE)
        self.coordinator.tick()
        self.assertEqual("2026-10-08", self.store.load().last_daily_check_date)
        self.coordinator.tick()
        self.assertEqual([("builder", "main")], self.transitions)

    def test_pending_during_battle_modal_and_wall_waits_for_handoff(self):
        for phase in ("battle", "modal", "wall"):
            with self.subTest(phase=phase):
                # A fresh startup returns main and clears the previous request.
                if self.coordinator.active_id == "builder":
                    self.coordinator.tick()
                self.coordinator.runtime.last_daily_check_date = None
                self.clock.wall = self.clock.wall.replace(hour=15, minute=31)
                self.main.phase = phase
                before = len(self.transitions)
                self.coordinator.tick()
                self.assertEqual("main", self.coordinator.active_id)
                self.assertEqual("builder", self.coordinator.pending.target)
                self.assertEqual(before, len(self.transitions))
                self.assertTrue(self.store.load().pending_builder_check)
                self.main.phase = "home"
                self.coordinator.tick()
                self.assertEqual("builder", self.coordinator.active_id)
                self.coordinator.tick()

    def test_schedule_can_arrive_inside_long_main_tick_before_attack(self):
        self.startup_complete()
        self.clock.wall = self.clock.wall.replace(hour=15, minute=29)
        self.main.on_tick = lambda: self.clock.advance(120)
        self.coordinator.tick()
        self.assertEqual("builder", self.coordinator.active_id)

    def test_date_rollover_waits_for_next_days_cutoff(self):
        self.clock.wall = self.clock.wall.replace(hour=15, minute=31)
        self.startup_complete()
        self.clock.wall = datetime.fromisoformat("2026-10-09T00:01:00+07:00")
        self.coordinator.tick()
        self.assertEqual("main", self.coordinator.active_id)
        self.clock.wall = self.clock.wall.replace(hour=16)
        self.coordinator.tick()
        self.coordinator.tick()
        self.assertEqual("2026-10-09", self.store.load().last_daily_check_date)
        self.assertEqual(3, len(self.transitions))

    def test_sleep_over_several_days_checks_only_current_day(self):
        self.startup_complete()
        # Windows monotonic may not include sleep. The daily clock still does.
        self.clock.advance(3 * 86400 + 7 * 3600, monotonic=False)
        self.coordinator.tick()
        self.coordinator.tick()
        self.assertEqual("2026-10-11", self.store.load().last_daily_check_date)
        self.assertEqual(3, len(self.transitions))
        self.coordinator.tick()
        self.assertEqual(3, len(self.transitions))

    def test_restart_with_persisted_complete_still_reads_real_bonus(self):
        self.clock.wall = self.clock.wall.replace(hour=16)
        self.startup_complete()
        self.home()
        self.builder.resume()
        self.bonus(StarBonusState.AVAILABLE, progress=(0, 8))
        count = self.rewards.claim_star_bonus.call_count
        self.coordinator = self.new_coordinator()
        self.coordinator.tick()
        self.assertEqual("builder", self.coordinator.active_id)
        self.assertGreater(self.rewards.claim_star_bonus.call_count, count)
        self.assertEqual("available", self.store.load().last_bonus_state)
        self.assertEqual("2026-10-08", self.store.load().last_daily_check_date)

    def test_startup_from_main_home_navigates_before_bonus_read(self):
        self.home(Village.MAIN)
        self.coordinator.tick()
        self.rewards.claim_star_bonus.assert_not_called()
        self.coordinator.tick()
        self.assertEqual("main", self.coordinator.active_id)
        self.assertEqual(
            [(Village.MAIN, Village.BUILDER), ("builder", "main")], self.transitions
        )

    def test_unknown_retries_on_monotonic_then_main_without_completing(self):
        self.clock.wall = self.clock.wall.replace(hour=16)
        self.bonus(StarBonusState.UNKNOWN, success=False)
        for _ in range(3):
            self.assertTrue(self.coordinator.tick())
            self.clock.advance(15, wall=False)
        self.assertEqual(3, self.rewards.claim_star_bonus.call_count)
        self.coordinator.tick()
        self.assertEqual("main", self.coordinator.active_id)
        runtime = self.store.load()
        self.assertEqual("unknown", runtime.last_bonus_state)
        self.assertIsNone(runtime.last_daily_check_date)
        self.assertIsNone(runtime.last_valid_bonus_check_at)
        self.assertTrue(runtime.builder_incomplete)
        self.assertTrue(runtime.pending_builder_check)
        self.assertIn("UNKNOWN", runtime.last_error)
        for _ in range(4):
            self.coordinator.tick()
        self.assertEqual("main", self.coordinator.active_id)
        self.clock.advance(300, wall=False)
        self.coordinator.tick()
        self.assertEqual("builder", self.coordinator.active_id)

    def test_unknown_cooldown_does_not_follow_wall_clock_jumps(self):
        self.bonus(StarBonusState.UNKNOWN, success=False)
        self.coordinator.tick()
        self.clock.advance(86400, monotonic=False)
        self.coordinator.tick()
        self.assertEqual(1, self.rewards.claim_star_bonus.call_count)
        self.clock.advance(15, wall=False)
        self.coordinator.tick()
        self.assertEqual(2, self.rewards.claim_star_bonus.call_count)

    def test_unknown_without_safe_home_stops_only_instance(self):
        self.bonus(StarBonusState.UNKNOWN, success=False)
        self.navigator.confirmed_home.side_effect = None
        self.navigator.confirmed_home.return_value = None
        self.coordinator.tick()
        self.clock.advance(80)
        self.assertFalse(self.coordinator.tick())
        self.navigator.navigate.assert_not_called()
        self.assertTrue(self.store.load().builder_incomplete)
        self.assertIsNone(self.store.load().last_daily_check_date)

    def test_builder_failure_at_proven_home_falls_back_with_error(self):
        self.builder.halt_reason = "Watchdog builder"
        self.assertTrue(self.coordinator.tick())
        self.assertEqual("main", self.coordinator.active_id)
        self.rewards.collect_cart.assert_called_once()
        self.assertIn("Watchdog", self.store.load().last_error)
        self.assertEqual("unknown", self.store.load().last_bonus_state)

    def test_failure_during_battle_never_navigates(self):
        self.reader.classify.return_value = ScreenObservation(
            ScreenKind.BATTLE, "battle", Village.BUILDER
        )
        self.builder.halt_reason = "Timeout trận"
        self.assertFalse(self.coordinator.tick())
        self.navigator.navigate.assert_not_called()
        self.assertEqual("builder", self.coordinator.active_id)

    def test_cart_failure_unknown_screen_cannot_return_main(self):
        self.rewards.collect_cart.return_value = CartResult(False, "close failed")
        self.rewards.collect_cart.side_effect = lambda: (
            setattr(self.navigator.confirmed_home, "side_effect", None)
            or setattr(self.navigator.confirmed_home, "return_value", None)
            or CartResult(False, "close failed")
        )
        self.coordinator.tick()
        self.assertFalse(self.coordinator.tick())
        self.assertEqual([], self.transitions)
        self.assertIn("Thu xe", self.store.load().last_error)

    def test_complete_then_cart_reveals_available_stays_builder(self):
        self.rewards.claim_star_bonus.side_effect = [
            RewardResult(
                True,
                "complete",
                StarBonusObservation(StarBonusState.COMPLETE, 100.0, "clear"),
            ),
            RewardResult(
                True,
                "more",
                StarBonusObservation(
                    StarBonusState.AVAILABLE, 100.0, "stars", progress=(0, 7)
                ),
            ),
        ]
        self.coordinator.tick()
        self.assertEqual("builder", self.coordinator.active_id)
        self.assertEqual([], self.transitions)
        self.adb.tap.assert_called_once()

    def test_rewards_followed_by_more_stars_continue_multiple_matches(self):
        self.bonus(StarBonusState.AVAILABLE, progress=(0, 8))
        self.coordinator.tick()  # Home -> Attack, actual module
        for claims, progress in ((1, (0, 7)), (2, (4, 8))):
            self.reader.match.return_value = (500, 500)
            self.reader.classify.return_value = ScreenObservation(
                ScreenKind.ATTACK_MENU, "menu", Village.BUILDER
            )
            self.coordinator.tick()  # Find Now -> clear the previous result ledger
            self.reader.classify.return_value = ScreenObservation(
                ScreenKind.RESULT,
                "result",
                Village.BUILDER,
                "builder_result",
                {"return": (800, 760)},
            )
            self.coordinator.tick()  # Return Home
            self.reader.classify.return_value = ScreenObservation(
                ScreenKind.MODAL, "reward", Village.BUILDER, "star_reward"
            )

            def claim(_claims=claims, _progress=progress):
                self.home()
                return RewardResult(
                    True,
                    "claimed, more stars",
                    StarBonusObservation(
                        StarBonusState.AVAILABLE, 100.0, "more", progress=_progress
                    ),
                    _claims,
                )

            self.rewards.claim_star_bonus.side_effect = claim
            self.coordinator.tick()  # Handle the panel, never navigate on claims alone
            self.rewards.claim_star_bonus.side_effect = None
            self.bonus(StarBonusState.AVAILABLE, progress=progress)
            self.coordinator.tick()  # Another real Attack
            self.assertEqual("builder", self.coordinator.active_id)
            self.assertEqual([], self.transitions)
        self.assertEqual(2, self.builder.metrics["attack_count"])
        self.assertEqual(2, self.builder.metrics["battle_count"])
        self.assertEqual(3, self.builder.metrics["reward_claims"])
        self.home()
        self.bonus(StarBonusState.COMPLETE)
        self.coordinator.tick()
        self.assertEqual("main", self.coordinator.active_id)
        self.rewards.collect_cart.assert_called_once()

    def test_cycle_budget_does_not_cut_a_battle_and_keeps_incomplete(self):
        self.bonus(StarBonusState.AVAILABLE)
        self.coordinator.tick()
        self.reader.classify.return_value = ScreenObservation(
            ScreenKind.BATTLE, "battle", Village.BUILDER
        )
        self.builder._battle = lambda frame: True  # No input, policy boundary only.
        self.clock.advance(self.settings["hybrid_builder_budget_seconds"])
        self.coordinator.tick()
        self.assertEqual([], self.transitions)
        self.home()
        self.coordinator.tick()
        self.assertEqual("main", self.coordinator.active_id)
        self.assertTrue(self.store.load().builder_incomplete)
        self.assertEqual("available", self.store.load().last_bonus_state)

    def test_stop_during_cart_never_navigates_or_launches_main(self):
        self.rewards.collect_cart.side_effect = lambda: (
            self.stop.set() or CartResult(True, "ok", True, True)
        )
        self.coordinator.tick()
        self.assertEqual([], self.transitions)
        self.assertEqual(0, self.main.ticks)

    def test_reload_clears_complete_and_preserves_trip_budget_until_fresh_check(self):
        self.startup_complete()
        started = self.coordinator._cycle_started
        self.coordinator.reset_after_reload()
        saved = self.store.load()
        self.assertEqual("unknown", saved.last_bonus_state)
        self.assertTrue(saved.builder_incomplete)
        self.assertEqual("recovery", saved.pending_reason)
        self.assertEqual(started, self.coordinator._cycle_started)
        self.assertEqual("builder", self.coordinator.pending.target)
        self.home(
            Village.BUILDER
        )  # Reload completed after a half-finished boat transition.
        self.bonus(StarBonusState.AVAILABLE, progress=(0, 7))
        self.assertTrue(self.coordinator.tick())
        self.assertEqual("builder", self.coordinator.active_id)
        self.assertEqual("available", self.store.load().last_bonus_state)
        self.assertTrue(self.store.load().builder_incomplete)

    def test_disk_failure_at_bonus_receipt_stops_before_attack_or_cart(self):
        self.bonus(StarBonusState.AVAILABLE, progress=(0, 7))
        before = self.store.path.read_bytes()
        with patch(
            "cocmagic.hybrid_runtime.os.replace", side_effect=OSError("disk full")
        ):
            with self.assertRaises(RuntimeWriteError):
                self.coordinator.tick()
        self.adb.tap.assert_not_called()
        self.rewards.collect_cart.assert_not_called()
        self.assertIn("disk full", self.coordinator.halt_reason)
        self.assertEqual(before, self.store.path.read_bytes())
        self.assertTrue(self.coordinator.runtime.builder_incomplete)

    def test_unchanged_bonus_across_battles_falls_back_incomplete_only_at_safe_home(
        self,
    ):
        self.bonus(StarBonusState.AVAILABLE, progress=(2, 8))
        for battle in range(5):
            self.builder._metrics["battle_count"] = battle
            self.coordinator._builder_home(self.builder)
        self.assertIn("không đổi", self.coordinator._return_error)
        self.assertTrue(self.coordinator._builder_home(self.builder))
        self.assertEqual("main", self.coordinator.pending.target)
        self.assertEqual("available", self.store.load().last_bonus_state)
        self.assertTrue(self.store.load().builder_incomplete)
        self.assertEqual(1, self.store.load().retry_count)

    def test_status_has_schedule_pending_error_and_nonfixed_star_progress(self):
        self.bonus(StarBonusState.AVAILABLE, progress=(4, 8))
        self.coordinator.tick()
        status = self.coordinator.status()
        self.assertEqual([4, 8], status["bonus_progress"])
        self.assertEqual("hybrid", status["run_mode"])
        self.assertEqual("2026-10-08T15:30:00+07:00", status["next_daily_check_at"])
        self.assertIn("last_valid_bonus_check_at", status)
        self.assertIn("last_error", status)

    def test_two_hybrid_instances_keep_schedules_and_pending_independent(self):
        other_clock = FakeClock()
        store = HybridRuntimeStore(
            self.folder.name, "test:2", log=lambda _: None
        ).acquire()
        self.addCleanup(store.close)
        adb = Mock(device="test:2", camera_revision=0, stop_event=threading.Event())
        reader = Mock()
        reader.capture.return_value = self.frame
        reader.classify.return_value = ScreenObservation(
            ScreenKind.BUILDER_HOME,
            "home",
            Village.BUILDER,
            points={"attack": (100, 800)},
        )
        navigator = Mock()
        navigator.confirmed_home.return_value = (
            self.frame,
            reader.classify.return_value,
        )
        navigator.switch_village.return_value = True
        other_builder = BuilderFarmModule(
            adb,
            self.settings,
            reader=reader,
            navigator=navigator,
            rewards=self.rewards,
            camera=Mock(),
            clock=other_clock.monotonic,
        )
        other = HybridCoordinator(
            "test:2",
            {"main": MainContract("test:2"), "builder": other_builder},
            store,
            self.settings,
            clock=other_clock,
        )
        self.startup_complete()
        other.tick()
        self.clock.wall = self.clock.wall.replace(hour=16)
        self.main.phase = "battle"
        self.coordinator.tick()
        other.tick()
        self.assertTrue(self.store.load().pending_builder_check)
        self.assertFalse(store.load().pending_builder_check)
        self.assertIsNone(store.load().last_daily_check_date)
        self.assertIsNone(other.pending)

    def test_three_failed_cycles_wait_until_next_day_then_allow_one_check(self):
        self.bonus(StarBonusState.UNKNOWN, success=False)
        self.clock.wall = self.clock.wall.replace(hour=16)
        for cycle in range(3):
            for _ in range(3):
                self.coordinator.tick()
                self.clock.advance(15)
            self.coordinator.tick()  # safe fallback
            self.assertEqual("main", self.coordinator.active_id)
            self.clock.advance(300)
            self.coordinator.tick()
            if cycle < 2:
                self.assertEqual("builder", self.coordinator.active_id)
        for _ in range(3):
            self.coordinator.tick()
        self.assertEqual("main", self.coordinator.active_id)
        self.assertEqual(3, self.store.load().retry_count)
        self.assertIsNone(self.store.load().last_daily_check_date)
        self.clock.advance(86400)
        self.coordinator.tick()
        self.assertEqual("builder", self.coordinator.active_id)

    def test_exhausted_morning_retries_do_not_consume_scheduled_daily_budget(self):
        self.startup_complete()
        runtime = self.coordinator.runtime
        runtime.pending_builder_check = True
        runtime.last_error = "Morning UNKNOWN budget exhausted"
        runtime.retry_count = 3
        runtime.retry_date = "2026-10-08"
        self.clock.wall = self.clock.wall.replace(hour=15, minute=29)
        self.coordinator.tick()
        self.assertEqual("main", self.coordinator.active_id)
        self.clock.advance(120)
        self.main.phase = "battle"
        self.coordinator.tick()
        self.assertEqual("main", self.coordinator.active_id)
        self.assertEqual("builder", self.coordinator.pending.target)
        self.assertIsNone(self.store.load().last_daily_check_date)
        self.assertEqual("2026-10-08", self.store.load().last_daily_request_date)
        self.assertEqual(0, self.store.load().retry_count)
        self.main.phase = "home"
        self.coordinator.tick()
        self.coordinator.tick()
        self.assertEqual("2026-10-08", self.store.load().last_daily_check_date)

    def test_engine_hybrid_constructs_both_real_modules_and_one_runtime_writer(self):
        from cocmagic.bot_engine import BotEngine
        from cocmagic.modules.farm_module import FarmModule

        engine = BotEngine(self.settings)
        engine.adb = self.adb
        with (
            patch.object(config, "DATA_DIR", self.folder.name),
            patch(
                "cocmagic.bot_engine.resolve_device_ownership",
                return_value=SimpleNamespace(
                    identity="boot:test",
                    runtime_serial=self.adb.device,
                    aliases=(self.adb.device,),
                ),
            ),
        ):
            engine._init_modules()
        self.addCleanup(engine.runtime_store.close)
        self.assertIsInstance(engine.farm_mod, FarmModule)
        self.assertIsInstance(engine.builder_mod, BuilderFarmModule)
        self.assertIsInstance(engine.coordinator, HybridCoordinator)
        self.assertEqual("builder", engine.coordinator.active_id)
        self.adb.tap.assert_not_called()

    def test_restart_during_main_battle_finishes_it_before_startup_builder(self):
        self.reader.classify.return_value = ScreenObservation(
            ScreenKind.BATTLE, "main battle"
        )
        self.main._classify_screen = lambda image: ModuleScreen.BATTLE
        self.main.phase = "battle"
        self.coordinator.tick()
        self.assertEqual("main", self.coordinator.active_id)
        self.assertEqual("builder", self.coordinator.pending.target)
        self.assertEqual([], self.transitions)
        self.rewards.claim_star_bonus.assert_not_called()
        self.main.phase = "home"
        self.coordinator.tick()
        self.assertEqual("builder", self.coordinator.active_id)


class HybridVisionTests(unittest.TestCase):
    def test_native_hud_variant_recognizes_main_after_level_changes(self):
        root = Path(config.BASE_DIR)
        manifest = json.loads(
            (root / "tests/fixtures/dual_village/hybrid/manifest.json").read_text()
        )
        path = root / "tests/fixtures/dual_village/hybrid" / manifest["path"]
        self.assertEqual(
            manifest["sha256"], hashlib.sha256(path.read_bytes()).hexdigest()
        )
        image = cv2.imread(str(path))
        reader = BuilderScreenReader()
        self.assertIsNone(reader.match("profile", image))
        self.assertIsNone(reader.match("main_attack", image))
        self.assertEqual(ScreenKind.MAIN_HOME, reader.classify(image).kind)
        self.assertTrue(reader.home_is_clear(image, Village.MAIN))
        self.assertFalse(reader.home_is_clear(image, Village.BUILDER))
        # Different digits cannot change a Home decision, missing portrait can.
        image[38:80, 38:90] = 0
        self.assertEqual(ScreenKind.MAIN_HOME, reader.classify(image).kind)
        image[:115, 690:840] = 0
        self.assertEqual(ScreenKind.UNKNOWN, reader.classify(image).kind)

    def test_current_attack_alone_or_modal_never_confirms_home(self):
        image = cv2.imread(
            str(
                Path(config.BASE_DIR)
                / "tests/fixtures/dual_village/hybrid/main-home-level71.png"
            )
        )
        reader = BuilderScreenReader()
        attack_only = np.zeros_like(image)
        attack_only[735:882, 15:195] = image[735:882, 15:195]
        self.assertEqual(ScreenKind.UNKNOWN, reader.classify(attack_only).kind)
        image[240:540, 440:1160] = 110
        self.assertEqual(ScreenKind.MODAL, reader.classify(image).kind)
        self.assertFalse(reader.home_is_clear(image, Village.MAIN))


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def store(self, serial="test:1"):
        store = HybridRuntimeStore(self.folder.name, serial, log=Mock()).acquire()
        self.addCleanup(store.close)
        return store

    def test_missing_or_corrupt_runtime_recovers_unknown_with_log(self):
        store = self.store()
        for content in (
            None,
            "{broken",
            "[]",
            '{"version": 1}',
            json.dumps(
                {
                    "version": 1,
                    "serial": "test:1",
                    "runtime": {"last_bonus_state": "complete"},
                }
            ),
        ):
            if content is not None:
                store.path.write_text(content, encoding="utf-8")
            runtime = store.load()
            self.assertEqual("unknown", runtime.last_bonus_state)
            self.assertIsNone(runtime.last_daily_check_date)
            self.assertTrue(runtime.builder_incomplete)
        self.assertEqual(5, store.log.call_count)

    def test_atomic_replace_failure_retains_old_document_and_no_temp(self):
        store = self.store()
        store.save(HybridRuntime())
        before = store.path.read_bytes()
        with patch(
            "cocmagic.hybrid_runtime.os.replace", side_effect=OSError("disk error")
        ):
            with self.assertRaises(OSError):
                store.save(HybridRuntime(last_bonus_state="available"))
        self.assertEqual(before, store.path.read_bytes())
        self.assertEqual([], list(Path(self.folder.name).glob("*.tmp")))

    def test_two_serials_have_independent_runtime_and_same_serial_writer_is_rejected(
        self,
    ):
        first, second = self.store("a:1"), self.store("a/1")
        first.save(HybridRuntime(last_bonus_state="available"))
        second.save(
            HybridRuntime(
                last_bonus_state="complete", last_daily_check_date="2026-10-08"
            )
        )
        self.assertNotEqual(first.path, second.path)
        self.assertEqual("available", first.load().last_bonus_state)
        self.assertIsNone(first.load().last_daily_check_date)
        duplicate = HybridRuntimeStore(self.folder.name, "a:1")
        with self.assertRaisesRegex(RuntimeError, "writer"):
            duplicate.acquire()
        first.close()
        duplicate.acquire()
        duplicate.close()

    def test_windows_temporary_replace_denial_retries_atomic_write(self):
        store = self.store()
        store.save(HybridRuntime())
        replace = os.replace
        error = PermissionError("temporary sharing denial")
        error.winerror = 5
        with (
            patch("cocmagic.hybrid_runtime.os.replace") as move,
            patch("cocmagic.hybrid_runtime.time.sleep") as wait,
        ):
            # The final attempt still performs the real atomic replacement.
            def attempt(source, target):
                if move.call_count < 3:
                    raise error
                return replace(source, target)

            move.side_effect = attempt
            store.save(HybridRuntime(last_bonus_state="available"))
        self.assertEqual(3, move.call_count)
        self.assertEqual([(0.05,), (0.1,)], [call.args for call in wait.call_args_list])
        self.assertEqual("available", store.load().last_bonus_state)
        self.assertEqual([], list(Path(self.folder.name).glob("*.tmp")))

    def test_persistent_windows_replace_denial_stops_after_three_attempts(self):
        store = self.store()
        store.save(HybridRuntime())
        before = store.path.read_bytes()
        error = PermissionError("persistent sharing denial")
        error.winerror = 32
        with (
            patch("cocmagic.hybrid_runtime.os.replace", side_effect=error) as move,
            patch("cocmagic.hybrid_runtime.time.sleep"),
        ):
            with self.assertRaises(OSError):
                store.save(HybridRuntime(last_bonus_state="available"))
        self.assertEqual(3, move.call_count)
        self.assertEqual(before, store.path.read_bytes())
        self.assertEqual([], list(Path(self.folder.name).glob("*.tmp")))

    def test_another_thread_cannot_write_worker_runtime(self):
        store = self.store()
        errors = []

        def writer():
            try:
                store.save(HybridRuntime())
            except RuntimeError as error:
                errors.append(str(error))

        thread = threading.Thread(target=writer)
        thread.start()
        thread.join()
        self.assertEqual(1, len(errors))
        self.assertFalse(store.path.exists())

    def test_another_process_cannot_acquire_same_serial_writer(self):
        store = self.store()
        code = (
            "from cocmagic.hybrid_runtime import HybridRuntimeStore\n"
            f'HybridRuntimeStore({self.folder.name!r}, "test:1").acquire()'
        )
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("writer", result.stderr)
        store.save(HybridRuntime(last_bonus_state="available"))
        self.assertEqual("available", store.load().last_bonus_state)

    def test_windows_missing_tzdata_uses_fixed_plus_seven(self):
        with patch(
            "cocmagic.hybrid_coordinator.ZoneInfo", side_effect=ZoneInfoNotFoundError
        ):
            zone = vietnam_timezone()
        self.assertEqual(
            timedelta(hours=7), datetime(2026, 10, 8, tzinfo=zone).utcoffset()
        )


if __name__ == "__main__":
    unittest.main()
