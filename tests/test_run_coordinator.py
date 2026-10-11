"""Offline contract tests. Fake builder/navigation never claim to train a village."""

import os
import threading
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.bot_engine import BotEngine
from cocmagic.modules.farm_module import (
    CardSlot,
    ComboProfile,
    FarmModule,
    FarmState,
    SpellProgress,
    T_HOME_ATTACK,
    T_FIND_MATCH,
    T_RETURN_HOME_NEW,
    T_USE,
)
from cocmagic.modules.wall_module import WallModule
from cocmagic.run_coordinator import RunCoordinator
from cocmagic.village_module import ModuleScreen


class FakeADB(ADBController):
    """Real template matching, in-memory frames, and recorded inputs only."""

    def __init__(self, serial="test:1", image=None, stop_event=None):
        super().__init__(serial=serial, settings={}, stop_event=stop_event)
        self.image = image
        self.inputs = []
        self.captures = []
        self._record_lock = threading.Lock()
        self.input_count = 0
        self.max_input_count = 0

    def screenshot(self, **kwargs):
        self.captures.append(kwargs)
        return self.image.copy() if self.image is not None else None

    def send(self, owner, action, entered=None, release=None):
        if self._stopping():
            return False
        with self._record_lock:
            self.input_count += 1
            self.max_input_count = max(self.max_input_count, self.input_count)
        try:
            self.inputs.append((owner, action))
            if entered is not None:
                entered.set()
            if release is not None and not release.wait(5):
                raise RuntimeError("Fake input timed out")
            return True
        finally:
            with self._record_lock:
                self.input_count -= 1

    def tap(self, x, y, **kwargs):
        return self.send("main", (x, y))

    def tap_many(self, points, **kwargs):
        return self.send("main", list(points))

    def back(self):
        return self.send("main", "back")


class FakeModule:
    def __init__(self, name, adb):
        self.name = name
        self.adb = adb
        self.device_serial = adb.device
        self.phase = "home"
        self.confirmed_screen = ModuleScreen.UNKNOWN
        self.halt_reason = None
        self.ready = False
        self.in_tick = False
        self.unconfirmed = False
        self.ticks = self.suspends = self.resumes = self.reloads = self.popups = 0
        self.on_tick = None

    def tick(self, *, yield_requested=None):
        self.ticks += 1
        self.in_tick = True
        try:
            self.ready = False
            if self.on_tick is not None:
                self.on_tick()
            self.confirmed_screen = (
                ModuleScreen.HOME
                if self.phase == "home"
                else ModuleScreen.MODAL
                if self.phase == "modal"
                else ModuleScreen.BATTLE
            )
            if self.phase == "home" and not self.unconfirmed and yield_requested():
                self.ready = True
            else:
                self.adb.send(self.name, self.phase)
            return self.halt_reason is None
        finally:
            self.in_tick = False

    @property
    def can_yield(self):
        return self.ready and not self.in_tick and not self.unconfirmed

    @property
    def metrics(self):
        return {"ticks": self.ticks, "wall_count": 3 if self.name == "main" else 0}

    @property
    def status_line(self):
        return f"{self.name}:{self.phase}"

    def suspend(self):
        assert self.can_yield
        self.suspends += 1

    def resume(self):
        self.resumes += 1
        self.ready = False
        self.confirmed_screen = ModuleScreen.UNKNOWN

    def reset_after_reload(self):
        self.reloads += 1
        self.ready = False
        self.confirmed_screen = ModuleScreen.UNKNOWN

    def invalidate_after_popup(self):
        self.popups += 1
        self.ready = False
        self.confirmed_screen = ModuleScreen.UNKNOWN


def home_frame():
    # Deliberately synthetic; exercises real Main Home template recognition.
    image = np.full((900, 1600, 3), (65, 125, 70), np.uint8)
    tpl = cv2.imread(T_HOME_ATTACK)
    h, w = tpl.shape[:2]
    image[730 : 730 + h, 20 : 20 + w] = tpl
    return image


class CoordinatorTests(unittest.TestCase):
    def make_coordinator(self, switch=True, stop_event=None):
        adb = FakeADB(stop_event=stop_event)
        main, builder = FakeModule("main", adb), FakeModule("builder", adb)
        navigation = Mock(
            side_effect=lambda source, target: adb.send("navigator", target)
        )
        coordinator = RunCoordinator(
            adb.device,
            {"main": main, "builder": builder},
            "main",
            stop_event=stop_event,
            switch_village=navigation if switch else None,
        )
        return coordinator, main, builder, adb, navigation

    def test_handoff_checks_before_new_match_and_ticks_only_active(self):
        c, main, builder, adb, nav = self.make_coordinator()
        c.request_switch("builder", "daily check")
        self.assertTrue(c.tick())
        self.assertEqual(
            (1, 0, 1, 1), (main.ticks, builder.ticks, main.suspends, builder.resumes)
        )
        self.assertEqual([("navigator", "builder")], adb.inputs)
        self.assertEqual("builder", c.active_id)
        self.assertIsNone(c.pending)
        self.assertTrue(c.tick())
        self.assertEqual((1, 1), (main.ticks, builder.ticks))
        self.assertEqual("builder", adb.inputs[-1][0])

    def test_battle_modal_train_collect_wall_batch_keep_request_pending(self):
        for phase in ("battle", "modal", "train", "collect", "wall", "batch"):
            with self.subTest(phase=phase):
                c, main, builder, adb, nav = self.make_coordinator()
                main.phase = phase
                c.request_switch("builder", phase)
                c.tick()
                self.assertEqual("main", c.active_id)
                self.assertEqual("builder", c.pending.target)
                self.assertEqual(0, main.suspends + builder.ticks)
                nav.assert_not_called()
                main.phase = "home"
                c.tick()
                self.assertEqual("builder", c.active_id)

    def test_home_with_unconfirmed_work_does_not_yield(self):
        c, main, builder, adb, nav = self.make_coordinator()
        main.unconfirmed = True
        c.request_switch("builder", "pending confirmation")
        c.tick()
        nav.assert_not_called()
        self.assertIsNotNone(c.pending)

    def test_missing_navigation_does_not_fake_switch(self):
        c, main, builder, adb, nav = self.make_coordinator(switch=False)
        c.request_switch("builder", "not implemented")
        c.tick()
        c.tick()
        self.assertEqual("main", c.active_id)
        self.assertIsNotNone(c.pending)
        self.assertEqual([], adb.inputs)
        self.assertEqual(0, builder.ticks)
        with self.assertRaises(ValueError):
            c.request_switch("missing", "unavailable")

    def test_unconfirmed_destination_stops_with_request_intact(self):
        c, main, builder, adb, nav = self.make_coordinator()
        nav.side_effect = None
        nav.return_value = False
        c.request_switch("builder", "test")
        self.assertFalse(c.tick())
        self.assertFalse(c.tick())
        self.assertEqual("main", c.active_id)
        self.assertEqual(0, builder.resumes + builder.ticks)
        self.assertIsNotNone(c.pending)
        self.assertIn("chưa xác nhận", c.halt_reason)

    def test_request_arriving_during_tick_is_seen_at_match_boundary(self):
        c, main, builder, adb, nav = self.make_coordinator()
        main.on_tick = lambda: c.request_switch("builder", "arrived during tick")
        c.tick()
        self.assertEqual("builder", c.active_id)
        self.assertEqual([("navigator", "builder")], adb.inputs)

    def test_new_return_request_during_navigation_is_not_lost(self):
        c, main, builder, adb, nav = self.make_coordinator()
        nav.side_effect = lambda *args: (
            c.request_switch("main", "new return request") or True
        )
        c.request_switch("builder", "outbound")
        c.tick()
        self.assertEqual("builder", c.active_id)
        self.assertEqual("main", c.pending.target)
        nav.side_effect = None
        nav.return_value = True
        c.tick()
        self.assertEqual("main", c.active_id)
        self.assertIsNone(c.pending)

    def test_repeated_destination_request_during_navigation_is_satisfied_once(self):
        c, main, builder, adb, nav = self.make_coordinator()
        nav.side_effect = lambda *args: (
            c.request_switch("builder", "same target") or True
        )
        c.request_switch("builder", "outbound")
        c.tick()
        self.assertIsNone(c.pending)
        c.tick()
        nav.assert_called_once()

    def test_reload_resets_both_modules_and_cancels_unconfirmed_navigation(self):
        c, main, builder, adb, nav = self.make_coordinator()
        c.request_switch("builder", "test")
        c.tick()
        c.request_switch("main", "return later")
        c.exclusive(c.reset_after_reload)
        c.exclusive(c.invalidate_after_popup)
        self.assertEqual(
            (1, 0, 1, 1), (main.reloads, main.popups, builder.reloads, builder.popups)
        )
        self.assertIsNone(c.pending)
        self.assertEqual(ModuleScreen.UNKNOWN, builder.confirmed_screen)
        status = c.status()
        self.assertEqual("builder", status["active_module"])
        self.assertEqual(3, status["wall_count"])
        self.assertIsNone(status["switch_reason"])
        builder.halt_reason = "builder error"
        self.assertFalse(c.tick())
        self.assertEqual("builder error", c.halt_reason)

    def test_input_lock_covers_tick_batch_popup_and_handoff(self):
        c, main, builder, adb, nav = self.make_coordinator()
        entered, release, popup_started = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        main.phase = "batch"
        main.on_tick = lambda: adb.send("main", "batch in flight", entered, release)
        errors = []

        def run(action):
            try:
                action()
            except Exception as error:
                errors.append(error)

        tick_thread = threading.Thread(target=lambda: run(c.tick))

        def popup():
            popup_started.set()
            c.exclusive(lambda: adb.send("popup", "dismiss"))

        popup_thread = threading.Thread(target=lambda: run(popup))
        tick_thread.start()
        try:
            self.assertTrue(entered.wait(2))
            c.request_switch("builder", "while batch running")
            popup_thread.start()
            self.assertTrue(popup_started.wait(2))
            self.assertEqual([("main", "batch in flight")], adb.inputs)
            self.assertEqual("main", c.active_id)
        finally:
            release.set()
            tick_thread.join(5)
            if popup_thread.ident is not None:
                popup_thread.join(5)
        self.assertFalse(errors)
        self.assertFalse(tick_thread.is_alive() or popup_thread.is_alive())
        self.assertEqual(1, adb.max_input_count)
        main.on_tick = None
        main.phase = "home"
        c.tick()
        c.tick()
        self.assertEqual("builder", c.active_id)
        self.assertEqual(1, adb.max_input_count)

    def test_serial_isolation_and_cross_serial_registration_rejected(self):
        c, main, builder, adb, nav = self.make_coordinator()
        other_adb = FakeADB("test:2")
        other = FakeModule("main", other_adb)
        c2 = RunCoordinator(other_adb.device, {"main": other}, "main")
        c.request_switch("builder", "first only")
        c.tick()
        c2.tick()
        c.reset_after_reload()
        self.assertEqual(0, other.reloads)
        self.assertEqual("main", c2.active_id)
        self.assertEqual([("main", "home")], other_adb.inputs)
        with self.assertRaises(ValueError):
            RunCoordinator(adb.device, {"main": main, "builder": other}, "main")

    def test_concurrent_ticks_cannot_overlap_inputs_across_handoff(self):
        c, main, builder, adb, nav = self.make_coordinator()
        entered, release, second_started = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        main.on_tick = lambda: adb.send("main", "last batch", entered, release)
        errors = []

        def tick(second=False):
            try:
                if second:
                    second_started.set()
                c.tick()
            except Exception as error:
                errors.append(error)

        first = threading.Thread(target=tick)
        second = threading.Thread(target=lambda: tick(True))
        first.start()
        try:
            self.assertTrue(entered.wait(2))
            c.request_switch("builder", "during batch")
            second.start()
            self.assertTrue(second_started.wait(2))
            self.assertEqual(0, builder.ticks)
        finally:
            release.set()
            first.join(5)
            if second.ident is not None:
                second.join(5)
        self.assertFalse(errors)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(1, adb.max_input_count)
        self.assertEqual((1, 1), (main.ticks, builder.ticks))
        self.assertEqual(
            ["main", "navigator", "builder"], [owner for owner, _ in adb.inputs]
        )

    def test_stop_before_or_during_navigation_never_ticks_target(self):
        stop = threading.Event()
        c, main, builder, adb, nav = self.make_coordinator(stop_event=stop)
        c.request_switch("builder", "test")
        stop.set()
        c.tick()
        self.assertEqual(0, main.ticks)
        nav.assert_not_called()
        stop.clear()
        nav.side_effect = lambda *args: stop.set() or True
        c.tick()
        self.assertEqual(0, builder.resumes + builder.ticks)
        self.assertIsNotNone(c.pending)

    def test_stop_immediately_after_suspend_does_not_start_navigation(self):
        stop = threading.Event()
        c, main, builder, adb, nav = self.make_coordinator(stop_event=stop)
        main.suspend = stop.set
        c.request_switch("builder", "test")
        self.assertTrue(c.tick())
        nav.assert_not_called()
        self.assertEqual([], adb.inputs)
        self.assertIsNone(c.halt_reason)


class MainContractTests(unittest.TestCase):
    def make_farm(self, **settings):
        adb = FakeADB(image=home_frame())
        farm = FarmModule(
            adb, None, None, {"auto_train": False, "upgrade_walls": False, **settings}
        )
        return farm, adb

    def test_pending_switch_catches_cached_home_before_attack(self):
        farm, adb = self.make_farm()
        farm._home_verified = True
        farm._button_cache["home_attack"] = (72, 820)
        farm.tick(yield_requested=lambda: True)
        self.assertTrue(farm.can_yield)
        self.assertEqual(ModuleScreen.HOME, farm.confirmed_screen)
        self.assertEqual([], adb.inputs)
        self.assertTrue(
            all(capture.get("use_cache") is False for capture in adb.captures)
        )

    def test_pending_switch_can_yield_after_missed_home_attack_without_running_wall(
        self,
    ):
        farm, adb = self.make_farm(upgrade_walls=True)
        farm._home_attack_failures = 2
        farm._home_verified = True
        wall = Mock()
        wall.blocks_handoff.return_value = False
        farm.wall_mod = wall
        farm.tick(yield_requested=lambda: True)
        self.assertTrue(farm.can_yield)
        self.assertEqual([], adb.inputs)
        wall.run.assert_not_called()

    def test_collect_finishes_wall_before_yield_and_next_match(self):
        farm, adb = self.make_farm(upgrade_walls=True)
        c = RunCoordinator(
            adb.device,
            {"main": farm, "builder": FakeModule("builder", adb)},
            "main",
            switch_village=lambda *args: adb.send("navigator", "builder"),
        )
        wall = Mock(last_interacted=True, walls_upgraded=4)
        wall.blocks_handoff.return_value = False

        def wall_run():
            c.request_switch("builder", "during wall purchase")
            self.assertFalse(farm.can_yield)
            adb.send("main", "wall confirmed")

        wall.run.side_effect = wall_run
        farm.wall_mod = wall
        farm.state = FarmState.COLLECT
        c.tick()
        self.assertEqual(
            [("main", "wall confirmed"), ("navigator", "builder")], adb.inputs
        )
        self.assertEqual(4, c.status()["wall_count"])

    def test_wall_or_event_modal_blocks_handoff_even_with_home_button(self):
        farm, adb = self.make_farm()
        wall = Mock()
        wall.blocks_handoff.return_value = True
        farm.wall_mod = wall
        farm.tick(yield_requested=lambda: True)
        self.assertFalse(farm.can_yield)
        self.assertEqual([], adb.inputs)
        wall.run.assert_not_called()
        farm, adb = self.make_farm()
        panel = cv2.resize(
            cv2.imread(
                os.path.join(
                    config.BASE_DIR, "tests", "fixtures", "event_reward_panel.png"
                )
            ),
            (1600, 900),
        )
        adb.image[100:705, 300:1275] = panel[100:705, 300:1275]
        farm.tick(yield_requested=lambda: True)
        self.assertFalse(farm.can_yield)
        self.assertEqual([], adb.inputs)

    def test_pending_spell_or_ability_prevents_yield_and_wall(self):
        for kind in ("spell", "ability"):
            with self.subTest(kind=kind):
                farm, adb = self.make_farm(upgrade_walls=True)
                farm.wall_mod = Mock()
                farm.wall_mod.blocks_handoff.return_value = False
                if kind == "spell":
                    farm._pending_spells[CardSlot(800, 840, "spell", "rage")] = (
                        SpellProgress(cast_index=2)
                    )
                else:
                    farm._pending_ability_names = ["warden"]
                farm.tick(yield_requested=lambda: True)
                self.assertFalse(farm.can_yield)
                self.assertTrue(farm._pending_spells or farm._pending_ability_names)
                farm.wall_mod.run.assert_not_called()
                self.assertEqual([], adb.inputs)
                with self.assertRaises(RuntimeError):
                    farm.suspend()

    def test_unclosed_quick_train_panel_blocks_handoff_with_home_button_visible(self):
        farm, adb = self.make_farm()
        tpl = cv2.imread(T_USE)
        h, w = tpl.shape[:2]
        adb.image[180 : 180 + h, 1150 : 1150 + w] = tpl
        farm.tick(yield_requested=lambda: True)
        self.assertFalse(farm.can_yield)
        self.assertEqual(FarmState.RECOVERING, farm.state)
        self.assertEqual([], adb.inputs)

    def test_real_wall_confirmation_blocks_handoff(self):
        farm, adb = self.make_farm()
        image = cv2.imread(
            os.path.join(
                config.BASE_DIR, "tests", "fixtures", "upgrade_walls_confirm.png"
            )
        )
        h, w = image.shape[:2]
        y, x = (900 - h) // 2, (1600 - w) // 2
        adb.image[y : y + h, x : x + w] = image
        tpl = cv2.imread(T_HOME_ATTACK)
        h, w = tpl.shape[:2]
        adb.image[730 : 730 + h, 20 : 20 + w] = tpl
        farm.wall_mod = WallModule(adb, None, farm.settings)
        farm.tick(yield_requested=lambda: True)
        self.assertFalse(farm.can_yield)
        self.assertEqual([], adb.inputs)

    def test_startup_train_once_and_suspend_resume_keeps_session(self):
        farm, adb = self.make_farm(auto_train=True)
        farm.tick(yield_requested=lambda: True)
        self.assertEqual(FarmState.TRAIN, farm.state)
        self.assertTrue(farm._initial_trained)
        self.assertFalse(farm.can_yield)
        # Simulated successful TRAIN; existing regression tests cover its inputs.
        farm.state = FarmState.COLLECT
        farm.attack_count, farm.skip_count = 7, 3
        farm.tick(yield_requested=lambda: True)
        farm.suspend()
        farm.resume()
        self.assertEqual(FarmState.RECOVERING, farm.state)
        self.assertEqual(ModuleScreen.UNKNOWN, farm.confirmed_screen)
        farm.tick(yield_requested=lambda: True)  # classify -> COLLECT
        farm.tick(yield_requested=lambda: True)  # COLLECT -> confirmed HOME
        farm.tick(yield_requested=lambda: True)  # no new TRAIN or Attack
        self.assertTrue(farm.can_yield)
        self.assertEqual(
            (7, 3, True), (farm.attack_count, farm.skip_count, farm._initial_trained)
        )
        self.assertEqual([], adb.inputs)

    def test_reload_routes_by_new_frame_instead_of_assigning_home(self):
        for expected, state, image in (
            (
                ModuleScreen.UNKNOWN,
                FarmState.RECOVERING,
                np.zeros((900, 1600, 3), np.uint8),
            ),
            (ModuleScreen.HOME, FarmState.COLLECT, home_frame()),
        ):
            with self.subTest(expected=expected):
                farm, adb = self.make_farm()
                farm.reset_after_reload()
                self.assertEqual(FarmState.RECOVERING, farm.state)
                adb.image = image
                with patch("cocmagic.modules.farm_module.time.sleep"):
                    farm.tick(yield_requested=lambda: True)
                self.assertEqual(expected, farm.confirmed_screen)
                self.assertEqual(state, farm.state)
                self.assertEqual([], adb.inputs)
                self.assertFalse(farm.can_yield)

    def test_reload_scout_and_result_are_classified_before_any_input(self):
        for template, xy, expected in (
            (T_FIND_MATCH, (1351, 590), FarmState.LOOT_CHECK),
            (T_RETURN_HOME_NEW, (650, 700), FarmState.RESULT),
        ):
            with self.subTest(template=template):
                farm, adb = self.make_farm()
                adb.image[:] = 0
                tpl = cv2.imread(template)
                h, w = tpl.shape[:2]
                x, y = xy
                adb.image[y : y + h, x : x + w] = tpl
                farm.reset_after_reload()
                farm.tick()
                self.assertEqual(expected, farm.state)
                self.assertEqual([], adb.inputs)

    def test_reload_battle_cancels_old_inputs_but_dismiss_popup_keeps_spell_progress(
        self,
    ):
        farm, adb = self.make_farm()
        battle = cv2.imread(
            os.path.join(config.BASE_DIR, "tests", "fixtures", "battle_screen.png")
        )
        slot = CardSlot(811, 840, "spell", "rage")
        progress = SpellProgress(cast_index=2, unconfirmed_before=battle)
        farm.state = FarmState.BATTLE_WAIT
        farm._pending_spells[slot] = progress
        farm._reward_generation = 4
        farm.invalidate_after_popup()
        self.assertIs(progress, farm._pending_spells[slot])
        adb.image = battle
        farm.tick()
        self.assertEqual(FarmState.BATTLE_WAIT, farm.state)
        self.assertIs(progress, farm._pending_spells[slot])
        self.assertEqual(4, farm._reward_generation)
        farm.reset_after_reload()
        self.assertEqual({}, farm._pending_spells)
        farm.tick()
        self.assertEqual(FarmState.BATTLE_WAIT, farm.state)
        self.assertEqual([], adb.inputs)

    def test_event_mode_never_runs_wall(self):
        farm, adb = self.make_farm(event_mode=True, upgrade_walls=True)
        wall = Mock(last_interacted=False, walls_upgraded=0)
        wall.blocks_handoff.return_value = False
        farm.wall_mod = wall
        farm.state = FarmState.COLLECT
        farm.tick(yield_requested=lambda: True)
        self.assertTrue(farm.can_yield)
        wall.run.assert_not_called()

    def test_unknown_reload_is_bounded_without_starting_train_or_attack(self):
        farm, adb = self.make_farm(auto_train=True)
        adb.image[:] = 0
        farm.reset_after_reload()
        farm._recovery_attempts = 29
        with patch("cocmagic.modules.farm_module.time.sleep"):
            self.assertFalse(farm.tick())
        self.assertEqual([], adb.inputs)
        self.assertFalse(farm._initial_trained)
        self.assertIn("Không xác định", farm.halt_reason)

    def test_village_resume_clears_coordinates_and_keeps_statistics(self):
        farm, adb = self.make_farm()
        farm._initial_trained = True
        farm.attack_count, farm.skip_count = 4, 9
        farm.tick(yield_requested=lambda: True)
        farm._combo_profile = ComboProfile(
            [CardSlot(811, 840, "spell", "rage")], [], (900, 1600)
        )
        farm._warden_slot = (700, 800)
        farm._deployed_hero_slots = {"warden": (700, 800)}
        farm._confirmed_main_points = [(300, 400)]
        farm.suspend()
        farm.resume()
        self.assertEqual(
            (4, 9, True), (farm.attack_count, farm.skip_count, farm._initial_trained)
        )
        self.assertIsNone(farm._combo_profile)
        self.assertIsNone(farm._warden_slot)
        self.assertEqual({}, farm._deployed_hero_slots)
        self.assertEqual([], farm._confirmed_main_points)
        self.assertEqual(FarmState.RECOVERING, farm.state)

    def test_stop_unwinds_train_wait_before_next_input(self):
        farm, adb = self.make_farm(auto_train=True)
        stop = threading.Event()
        farm.stop_event = adb.stop_event = stop
        farm.state = FarmState.TRAIN
        adb.find_and_tap = Mock(side_effect=lambda *args, **kwargs: stop.set() or True)
        farm.tick()
        self.assertEqual([], adb.inputs)
        self.assertFalse(farm.can_yield)
        adb.tap_many([(1, 2)])
        self.assertEqual([], adb.inputs)


class EngineRoutingTests(unittest.TestCase):
    def make_engine(self):
        c, main, builder, adb, nav = CoordinatorTests().make_coordinator()
        engine = BotEngine({})
        engine.adb, engine.coordinator = adb, c
        engine.farm_mod = main
        engine.wall_mod = Mock(walls_upgraded=99)
        return engine, c, main, builder, adb

    def test_connection_loss_on_builder_clears_all_serial_caches_and_pending_switch(
        self,
    ):
        engine, c, main, builder, adb = self.make_engine()
        c.request_switch("builder", "test")
        c.tick()
        c.request_switch("main", "after recovery")
        adb.image = cv2.imread(
            os.path.join(config.BASE_DIR, "tests", "fixtures", "connection_lost.png")
        )
        with patch.object(engine, "_wait") as sleep:
            self.assertTrue(
                c.exclusive(lambda: engine._handle_connection_lost(adb.image))
            )
        sleep.assert_called_once_with(10)
        self.assertEqual((1, 1), (main.reloads, builder.reloads))
        self.assertIsNone(c.pending)

    def test_engine_loop_routes_tick_status_and_halt_through_active_module(self):
        engine, c, main, builder, adb = self.make_engine()
        c.request_switch("builder", "test")
        c.tick()
        engine._handle_popups = Mock(return_value=False)
        received = []

        def status(value):
            received.append(value)
            builder.halt_reason = "active module failed"

        engine.status_callback = status
        engine.running = True
        with patch("cocmagic.bot_engine.time.sleep"):
            engine._main_loop()
        self.assertEqual((1, 1), (main.ticks, builder.ticks))
        self.assertEqual("builder", received[0]["active_module"])
        self.assertEqual("builder:home", received[0]["status"])
        self.assertEqual(3, received[0]["wall_count"])
        self.assertFalse(engine.running)

    def test_dismiss_popup_routes_to_builder_without_main_home_assignment(self):
        engine, c, main, builder, adb = self.make_engine()
        c.request_switch("builder", "test")
        c.tick()
        adb.image = np.full((900, 1600, 3), 150, np.uint8)
        adb.is_visible = lambda path, *args, **kwargs: (
            path == config.asset("rate_coc.png")
        )
        adb.find_and_tap = lambda *args, **kwargs: True
        with patch("cocmagic.bot_engine.time.sleep"):
            self.assertTrue(c.exclusive(engine._handle_popups))
        self.assertEqual((0, 1), (main.popups, builder.popups))
        self.assertEqual(ModuleScreen.UNKNOWN, builder.confirmed_screen)

    def test_builder_never_uses_dark_background_inactivity_heuristic(self):
        engine, c, main, builder, adb = self.make_engine()
        c.request_switch("builder", "test")
        c.tick()
        adb.image = np.zeros((900, 1600, 3), np.uint8)
        engine._detect_inactivity_popup = Mock(return_value=True)
        engine._handle_popups()
        engine._detect_inactivity_popup.assert_not_called()
        self.assertEqual(0, builder.reloads)

    def test_stop_during_reload_wait_prevents_the_next_tick(self):
        engine, c, main, builder, adb = self.make_engine()
        stop = Mock(wraps=threading.Event())
        stop.wait.side_effect = lambda seconds: stop.set() or True
        engine.stop_event = c.stop_event = adb.stop_event = stop
        dialog = cv2.imread(
            os.path.join(config.BASE_DIR, "tests", "fixtures", "connection_lost.png")
        )
        with patch("cocmagic.bot_engine.time.sleep") as sleep:
            self.assertTrue(engine._handle_connection_lost(dialog))
            c.tick()
        stop.wait.assert_called_once_with(10)
        sleep.assert_not_called()
        self.assertEqual(0, main.ticks + builder.ticks)
        self.assertEqual(1, len(adb.inputs))


class ADBStopTests(unittest.TestCase):
    def test_stop_after_batch_preparation_prevents_shell_submission(self):
        stop = threading.Event()
        adb = ADBController(settings={}, stop_event=stop)
        adb.invalidate_cache = stop.set
        with patch("cocmagic.adb_controller.run_hidden") as run:
            self.assertFalse(adb.tap_many([(100, 200)]))
        run.assert_not_called()

    def test_stop_during_current_batch_allows_no_new_batch(self):
        stop = threading.Event()
        adb = ADBController(settings={}, stop_event=stop)

        def in_flight(*args, **kwargs):
            stop.set()
            return Mock(returncode=0)

        with patch("cocmagic.adb_controller.run_hidden", side_effect=in_flight) as run:
            self.assertFalse(adb.tap_many([(100, 200)]))
            self.assertFalse(adb.tap_many([(300, 400)]))
        self.assertEqual(3, run.call_count)  # Current batch, remote cleanup, CANCEL.


if __name__ == "__main__":
    unittest.main()
