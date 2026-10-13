"""User video vision and stateful input replay; these are offline tests."""

from pathlib import Path
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.bot_engine import BotEngine
from cocmagic.builder_vision import BuilderBattleReader
from cocmagic.event_chests import EventChestOpener, find_chest_screen
from cocmagic.modules.builder_farm_module import BuilderFarmModule, BuilderPhase
from cocmagic.modules.farm_module import FarmModule, FarmState
from cocmagic.recovery import RecoveryInterrupted
from cocmagic.village_module import ModuleScreen


FIXTURES = Path(config.BASE_DIR) / "tests/fixtures/event_chest"


def fixture(name, size=(1600, 900)):
    return cv2.resize(cv2.imread(str(FIXTURES / f"{name}.png")), size)


def home():
    return cv2.imread(str(Path(config.BASE_DIR) / "tests/fixtures/dual_village/hybrid/main-home-level71.png"))


class ChestVisionTests(unittest.TestCase):
    def test_video_claim_requires_chest_button_and_battle_result_label(self):
        for size in ((1050, 591), (1280, 720), (1600, 900)):
            with self.subTest(size=size):
                scene = find_chest_screen(fixture("claim", size))
                self.assertEqual("claim", scene.kind)
                self.assertAlmostEqual(.503, scene.point[0] / size[0], delta=.003)
                image = fixture("claim", size)
                image[round(340*size[1]/591):round(440*size[1]/591)] = 0
                self.assertIsNone(find_chest_screen(image))

    def test_native_adb_claim_with_different_text_antialiasing_is_recognized(self):
        scene = find_chest_screen(fixture("claim_native"))
        self.assertEqual("claim", scene.kind)
        self.assertAlmostEqual(800, scene.point[0], delta=8)

    def test_video_hammer_progress_and_arrival_without_chest(self):
        for name, count in (("room_loading", 0), ("closed", 4), ("hit_1", 4),
                            ("hit_2", 3), ("hit_3", 2), ("hit_3_flash", 1), ("opening", 0)):
            with self.subTest(name=name):
                scene = find_chest_screen(fixture(name))
                self.assertEqual("room", scene.kind)
                self.assertEqual(count, scene.remaining)
        self.assertIsNone(find_chest_screen(fixture("room_loading")).point)
        self.assertIsNotNone(find_chest_screen(fixture("closed")).point)

    def test_native_sour_elixir_claim_requires_both_button_and_result_text(self):
        image = fixture("claim_native_sour")
        self.assertEqual("claim", find_chest_screen(image).kind)
        image[550:640] = 0
        self.assertIsNone(find_chest_screen(image))

    def test_continue_needs_the_reward_room_not_a_generic_green_button(self):
        image = fixture("reward", (1050, 591))
        self.assertEqual("reward", find_chest_screen(image).kind)
        image[:450] = 0
        self.assertIsNone(find_chest_screen(image))

    def test_native_ore_reward_uses_same_continue_flow_as_gold(self):
        scene = find_chest_screen(fixture("reward_native_ore"))
        self.assertEqual("reward", scene.kind)
        self.assertAlmostEqual(813, scene.point[0], delta=8)
        self.assertAlmostEqual(813, scene.point[1], delta=8)

    def test_native_hammer_progress_and_cached_arrival_cannot_tap_empty_pedestal(self):
        for name, count in (("room_loading_native", 4), ("hit_1_native", 3),
                            ("hit_2_native", 2), ("hit_3_native", 1), ("opening_native", 0)):
            with self.subTest(name=name):
                self.assertEqual(count, find_chest_screen(fixture(name)).remaining)
        self.assertIsNone(find_chest_screen(fixture("room_loading_native"), (814, 455)).point)

    def test_unrelated_game_screens_and_dialogs_are_never_chests(self):
        for name in ("battle_screen.png", "end_battle_confirm.png", "connection_lost.png",
                     "event_reward_panel.png", "event_video_gold_reward.png", "wall_list_closed.png"):
            image = cv2.imread(str(Path(config.BASE_DIR) / "tests/fixtures" / name))
            self.assertIsNone(find_chest_screen(image), name)
        self.assertIsNone(find_chest_screen(home()))
        self.assertIsNone(find_chest_screen(fixture("home")))

    def test_incomplete_or_wrong_resolution_images_are_not_input_authority(self):
        for image in (None, np.zeros((900, 1600), np.uint8), np.zeros((900, 1600, 4), np.uint8),
                      np.zeros((900, 1600, 3), np.float32), np.zeros((900, 1200, 3), np.uint8)):
            self.assertIsNone(find_chest_screen(image))

    def test_cached_lock_is_verified_locally_and_changed_position_is_relocated(self):
        image = fixture("closed", (1050, 591))
        point = find_chest_screen(image).point
        self.assertTrue(find_chest_screen(image, point).cached)
        moved = image.copy()
        moved[200:370, 440:610] = (70, 70, 70)
        moved[200:370, 500:670] = image[200:370, 440:610]
        relocated = find_chest_screen(moved, point)
        self.assertFalse(relocated.cached)
        self.assertAlmostEqual(point[0] + 60, relocated.point[0], delta=1)


class ChestReplay:
    """Advance a recorded scene only after the appropriate simulated click."""

    def __init__(self, start="claim"):
        self.current = fixture(start)
        self.queue = []
        self.hits = 0
        self.inputs = []
        self.now = 0.0
        self.stop = threading.Event()
        self.adb = Mock()
        self.adb.tap.side_effect = self.tap
        self.adb.screenshot.side_effect = self.capture
        matcher = ADBController()
        self.adb.is_visible.side_effect = matcher.is_visible
        self.adb.find_template.side_effect = matcher.find_template
        self.adb._load_template.side_effect = matcher._load_template

    def wait(self, seconds):
        self.now += seconds

    def capture(self, **kwargs):
        if self.queue:
            self.current = self.queue.pop(0)
        return self.current.copy()

    def tap(self, x, y, **kwargs):
        scene = find_chest_screen(self.current)
        self.inputs.append((x, y))
        if scene.kind == "claim":
            if (x, y) != scene.point:
                raise AssertionError("Wrong Claim position")
            self.queue = [fixture("room_loading"), fixture("closed")]
        elif scene.kind == "reward":
            if (x, y) != scene.point:
                raise AssertionError("Wrong Continue position")
            self.queue = [home()]
        else:
            if not (740 <= x <= 850 and 420 <= y <= 530):
                raise AssertionError("Hit outside chest")
            self.hits += 1
            self.queue = {
                1: [fixture("hit_1"), fixture("hit_2")],
                2: [fixture("hit_3")],
                3: [fixture("hit_3_flash")],
                4: [fixture("opening"), fixture("reward_loading"), fixture("reward")],
            }[self.hits]
        return True

    def open(self, opener):
        return opener.open(self.current, capture=self.capture, wait=self.wait,
                           stopping=self.stop.is_set,
                           terminal=lambda image: np.array_equal(image, home()))


class ChestInputTests(unittest.TestCase):
    def test_complete_video_flow_has_claim_four_hits_continue_and_no_home_tap(self):
        replay = ChestReplay()
        opener = EventChestOpener(replay.adb, clock=lambda: replay.now)
        result = replay.open(opener)
        self.assertTrue(result.handled)
        self.assertIsNone(result.error)
        self.assertEqual(4, replay.hits)
        self.assertEqual(6, len(replay.inputs))
        self.assertEqual(1, len(set(replay.inputs[1:5])))
        self.assertEqual(1, opener.opened)
        replay.adb.tap_many.assert_not_called()

    def test_next_chest_reuses_validated_position(self):
        first = ChestReplay()
        opener = EventChestOpener(first.adb, clock=lambda: first.now)
        self.assertIsNone(first.open(opener).error)
        second = ChestReplay()
        opener.adb = second.adb
        opener.clock = lambda: second.now
        self.assertIsNone(second.open(opener).error)
        self.assertEqual(1, opener.cache_hits)
        self.assertEqual(first.inputs[1], second.inputs[1])

    def test_no_chest_is_immediate_and_sends_no_input(self):
        replay = ChestReplay()
        replay.current = home()
        opener = EventChestOpener(replay.adb)
        self.assertFalse(replay.open(opener).handled)
        self.assertEqual([], replay.inputs)
        self.assertEqual(0, replay.now)

    def test_click_animation_never_replays_claim_or_hits_more_than_four(self):
        replay = ChestReplay()
        original = replay.tap

        def slow(x, y, **kw):
            result = original(x, y, **kw)
            replay.queue = [replay.current] * 4 + replay.queue
            return result

        replay.adb.tap.side_effect = slow
        self.assertIsNone(replay.open(EventChestOpener(replay.adb, clock=lambda: replay.now)).error)
        self.assertEqual(6, len(replay.inputs))

    def test_stop_after_claim_sends_no_chest_clicks(self):
        replay = ChestReplay()
        original = replay.wait

        def stop(seconds):
            original(seconds)
            replay.stop.set()

        replay.wait = stop
        replay.open(EventChestOpener(replay.adb, clock=lambda: replay.now))
        self.assertEqual(1, len(replay.inputs))

    def test_failed_adb_input_is_not_replayed(self):
        replay = ChestReplay()
        replay.adb.tap.side_effect = None
        replay.adb.tap.return_value = False
        result = replay.open(EventChestOpener(replay.adb, clock=lambda: replay.now))
        self.assertIsNotNone(result.error)
        self.assertEqual(1, replay.adb.tap.call_count)

    def test_ignored_chest_hit_has_bounded_retries_then_stops(self):
        replay = ChestReplay("closed")
        replay.adb.tap.side_effect = lambda *args, **kwargs: True
        result = replay.open(EventChestOpener(replay.adb, clock=lambda: replay.now))
        self.assertIsNotNone(result.error)
        self.assertEqual(3, replay.adb.tap.call_count)

    def test_unknown_transition_waits_without_blind_taps_and_times_out(self):
        replay = ChestReplay()
        replay.adb.tap.side_effect = lambda *args, **kwargs: replay.queue.append(np.zeros((900,1600,3),np.uint8)) or True
        result = replay.open(EventChestOpener(replay.adb, clock=lambda: replay.now))
        self.assertIsNotNone(result.error)
        self.assertEqual(1, replay.adb.tap.call_count)

    def test_resolution_change_and_reload_clear_position_cache(self):
        replay = ChestReplay()
        opener = EventChestOpener(replay.adb, clock=lambda: replay.now)
        replay.open(opener)
        self.assertIsNotNone(opener.position)
        self.assertFalse(opener._observe(fixture("closed", (1280, 720))).cached)
        self.assertIsNone(opener.position)
        opener.position = (800, 450)
        opener.reset()
        self.assertIsNone(opener.position)

    def test_starting_on_last_hammer_opens_with_only_one_hit(self):
        replay = ChestReplay("hit_3_flash")
        replay.hits = 3
        result = replay.open(EventChestOpener(replay.adb, clock=lambda: replay.now))
        self.assertIsNone(result.error)
        self.assertEqual(4, replay.hits)
        self.assertEqual(2, len(replay.inputs))

    def test_one_ignored_first_hit_is_retried_then_normal_progress_finishes(self):
        replay = ChestReplay("closed")
        original = replay.tap
        ignored = []

        def tap(x, y, **kw):
            if not ignored:
                ignored.append((x, y))
                return True
            return original(x, y, **kw)

        replay.adb.tap.side_effect = tap
        result = replay.open(EventChestOpener(replay.adb, clock=lambda: replay.now))
        self.assertIsNone(result.error)
        self.assertEqual(4, replay.hits)
        self.assertEqual(6, replay.adb.tap.call_count)


class ChestModuleTests(unittest.TestCase):
    def farm(self, replay, state=FarmState.RESULT):
        farm = FarmModule(replay.adb, Mock(), Mock(), {"event_mode": False}, stop_event=replay.stop)
        farm.state = state
        farm._wait = replay.wait
        farm.chests.clock = lambda: replay.now
        return farm

    def test_main_handles_chest_without_event_mode_then_counts_result_once(self):
        replay = ChestReplay()
        farm = self.farm(replay)
        self.assertTrue(farm.tick())
        self.assertEqual(FarmState.COLLECT, farm.state)
        self.assertEqual(1, farm.attack_count)
        self.assertFalse(farm.can_yield)
        self.assertEqual(4, replay.hits)

    def test_recovery_from_native_sour_claim_completes_reward_and_returns_home(self):
        replay = ChestReplay("claim_native_sour")
        farm = self.farm(replay)
        farm.reset_after_reload()
        farm._state_recovering()
        self.assertEqual(FarmState.RESULT, farm.state)
        self.assertTrue(farm.tick())
        self.assertEqual(FarmState.COLLECT, farm.state)
        self.assertEqual(1, farm.attack_count)
        self.assertEqual(4, replay.hits)

    def test_chest_claim_ends_battle_wait_before_timeout_or_hero_inputs(self):
        replay = ChestReplay()
        farm = self.farm(replay, FarmState.BATTLE_WAIT)
        farm.battle_start_ts = 0
        with patch.object(farm, "_force_end_battle") as surrender:
            farm.tick()
        self.assertEqual(FarmState.RESULT, farm.state)
        self.assertEqual([], replay.inputs)
        surrender.assert_not_called()

    def test_chest_during_deployment_discards_pending_battle_inputs(self):
        replay = ChestReplay()
        farm = self.farm(replay, FarmState.ATTACKING)
        farm._selected_battle_card = (200, 840)
        farm._handle_state = lambda: farm._screenshot(use_cache=False)
        farm.tick()
        self.assertEqual(FarmState.RESULT, farm.state)
        self.assertIsNone(farm._selected_battle_card)
        self.assertEqual([], replay.inputs)

    def test_starting_or_recovering_on_chest_routes_to_result(self):
        for name in ("claim", "closed", "reward"):
            replay = ChestReplay(name)
            farm = self.farm(replay)
            farm.reset_after_reload()
            farm._state_recovering()
            self.assertEqual(FarmState.RESULT, farm.state)
            self.assertEqual(ModuleScreen.RESULT, farm.confirmed_screen)
            self.assertFalse(farm.can_yield)

    def test_main_recovery_retains_position_but_home_never_authorizes_chest_input(self):
        replay = ChestReplay()
        farm = self.farm(replay)
        farm.chests.position = (814, 455)
        farm.chests.resolution = (900, 1600)
        farm.reset_after_reload()
        self.assertEqual((814, 455), farm.chests.position)
        replay.current = home()
        farm._state_recovering()
        self.assertEqual([], replay.inputs)

    def test_engine_guard_and_popups_leave_chest_owned_by_main(self):
        replay = ChestReplay()
        farm = self.farm(replay, FarmState.BATTLE_WAIT)
        engine = BotEngine({"run_mode": "main"}, stop_event=replay.stop)
        engine.adb = replay.adb
        engine.farm_mod = farm
        engine.coordinator = SimpleNamespace(active_id="main")
        engine._handle_connection_lost = Mock(return_value=False)
        with patch.object(engine, "_input_failed") as failed:
            for name in ("claim", "closed", "hit_3_flash", "reward"):
                engine._guard_frame(fixture(name))
            failed.assert_not_called()
        self.assertFalse(engine._handle_popups())
        self.assertEqual([], replay.inputs)

    def test_connection_recovery_interrupts_chest_before_next_hit(self):
        replay = ChestReplay()
        farm = self.farm(replay)
        farm._capture = Mock(side_effect=[replay.current, RecoveryInterrupted("connection")])
        self.assertTrue(farm.tick())
        self.assertEqual(1, len(replay.inputs))

    def test_builder_owns_optional_chest_before_postprocess_or_handoff(self):
        replay = ChestReplay()
        reader = BuilderBattleReader(replay.adb)
        module = BuilderFarmModule(replay.adb, {}, reader=reader, stop_event=replay.stop)
        module.wait = replay.wait
        module.chests.clock = lambda: replay.now
        self.assertTrue(module.tick())
        self.assertEqual(BuilderPhase.RESULT, module.phase)
        self.assertFalse(module.can_yield)
        self.assertEqual(4, replay.hits)


if __name__ == "__main__":
    unittest.main()
