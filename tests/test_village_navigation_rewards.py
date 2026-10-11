import threading
import unittest
from pathlib import Path
import cv2
from unittest.mock import Mock
from types import SimpleNamespace

from cocmagic.builder_screen_reader import (
    BuilderScreenReader,
    Capture,
    StarBonusState,
    Village,
)
from cocmagic.builder_rewards import BuilderRewards
from cocmagic.camera_controller import CameraStatus
from cocmagic.village_navigator import VillageNavigator
from test_builder_screen_reader import frame


class Device:
    """Deterministic screenshots and observable input, not a runtime module."""

    def __init__(self, scene):
        self.device = "fixture-serial"
        self.scene = scene
        self.input_lock = threading.RLock()
        self.camera_revision = 0
        self.stop_event = threading.Event()
        self.inputs = []
        self.accept = True
        self.transition = None
        self.home_after_close = True
        self.frames = {}

    def screenshot(self, use_cache=True):
        if use_cache:
            raise AssertionError("Transaction reused cached screenshot")
        if self.scene not in self.frames:
            self.frames[self.scene] = frame(self.scene)
        return self.frames[self.scene].copy()

    def tap(self, x, y, **kwargs):
        self.inputs.append((self.scene, x, y))
        if not self.accept:
            return False
        if self.transition:
            self.transition(self, x, y)
        return True


class Reader(BuilderScreenReader):
    def __init__(self, adb):
        super().__init__(adb)
        self.i = 0

    def capture(self):
        self.i += 1
        return Capture(
            self.adb.screenshot(use_cache=False),
            self.i,
            self.i * 0.3,
            self.adb.camera_revision,
        )


class Camera:
    def __init__(self, adb):
        self.adb = adb
        self.operations = 0
        self.frame_clear = lambda image: True
        self.destination = None

    def reset_view(self):
        self.adb.camera_revision += 1

    def pan(self, *args, **kwargs):
        self.operations += 1
        if not self.frame_clear(self.adb.screenshot(use_cache=False)):
            return SimpleNamespace(status=CameraStatus.ERROR)
        if self.destination:
            self.adb.scene = self.destination
        self.adb.camera_revision += 1
        return SimpleNamespace(status=CameraStatus.SUCCESS)

    zoom = pan


class NavigationTests(unittest.TestCase):
    def test_released_camera_settle_timeout_requires_new_home_before_target(self):
        device, reader, camera, nav = self.setup_navigation("builder-offset")
        fresh = reader.capture()
        nav.confirmed_home = Mock(
            return_value=(fresh, SimpleNamespace(village=Village.BUILDER))
        )
        reader.map_target = Mock(side_effect=[None, (900, 400)])
        camera.pan = Mock(
            return_value=SimpleNamespace(
                status=CameraStatus.ERROR,
                reason="Ảnh sau chưa ổn định hoặc không xác nhận được camera",
            )
        )
        found, operations = nav.locate(
            "cart_object", Village.BUILDER, __import__("time").monotonic() + 30
        )
        self.assertIsNotNone(found)
        self.assertEqual(1, operations)
        self.assertEqual(2, nav.confirmed_home.call_count)
        self.assertFalse(device.inputs)

    def setup_navigation(self, scene):
        device = Device(scene)
        reader = Reader(device)
        camera = Camera(device)
        nav = VillageNavigator(
            device, reader, camera, timeout=30, max_camera_operations=2
        )
        nav.wait = lambda seconds=0.25: None
        return device, reader, camera, nav

    def test_actual_anchor_navigation_from_camera_offset(self):
        device, reader, camera, nav = self.setup_navigation("main-offset")
        camera.destination = "main-pan"
        device.transition = lambda d, x, y: setattr(d, "scene", "builder-home-a")
        result = nav.navigate("builder", source="main")
        self.assertTrue(result.success, result.reason)
        self.assertEqual(1, len(device.inputs))
        self.assertGreaterEqual(result.camera_operations, 1)
        self.assertGreater(device.camera_revision, 0)

    def test_actual_builder_boat_anchor_and_reverse_destination(self):
        device, reader, camera, nav = self.setup_navigation("builder-offset")
        device.transition = lambda d, x, y: setattr(d, "scene", "main-home")
        result = nav.navigate("main", source="builder")
        self.assertTrue(result.success, result.reason)
        self.assertEqual(Village.MAIN, result.village)
        self.assertEqual(1, len(device.inputs))

    def test_modal_battle_menu_result_loading_refuse_boat_and_camera(self):
        for scene in (
            "cart-empty-a",
            "reward",
            "battle",
            "result",
            "builder-menu",
            "loading",
            "button-covered",
        ):
            with self.subTest(scene=scene):
                device, reader, camera, nav = self.setup_navigation(scene)
                self.assertFalse(nav.navigate("main").success)
                self.assertFalse(device.inputs)
                self.assertEqual(0, camera.operations)

    def test_boat_tap_failure_does_not_confirm_target(self):
        device, reader, camera, nav = self.setup_navigation("builder-offset")
        device.accept = False
        result = nav.navigate("main")
        self.assertFalse(result.success)
        self.assertEqual(1, len(device.inputs))

    def test_accepted_tap_with_no_transition_is_bounded(self):
        device, reader, camera, nav = self.setup_navigation("builder-offset")
        result = nav.navigate("main")
        self.assertFalse(result.success)
        # The global deadline can expire before the retry count. Both limits
        # must bound the transaction, regardless of matcher/CPU throughput.
        self.assertGreaterEqual(len(device.inputs), 1)
        self.assertLessEqual(len(device.inputs), nav.max_boat_taps)

    def test_modal_appearing_immediately_before_tap_blocks_input(self):
        device, reader, camera, nav = self.setup_navigation("builder-offset")
        original = reader.capture

        def capture():
            if reader.i == 4:
                device.scene = "cart-empty-a"
            return original()

        reader.capture = capture
        self.assertFalse(nav.navigate("main").success)
        self.assertFalse(device.inputs)

    def test_stop_or_source_mismatch_cannot_send_input(self):
        device, reader, camera, nav = self.setup_navigation("builder-offset")
        self.assertFalse(nav.navigate("main", source="main").success)
        self.assertFalse(device.inputs)
        device.stop_event.set()
        self.assertFalse(nav.navigate("main").success)
        self.assertFalse(device.inputs)


class RewardTransactionsTests(unittest.TestCase):
    def setUp(self):
        self.device = Device("reward")
        self.reader = Reader(self.device)
        self.camera = Camera(self.device)
        self.nav = VillageNavigator(self.device, self.reader, self.camera, timeout=30)
        self.nav.wait = lambda seconds=0.25: None
        self.rewards = BuilderRewards(self.device, self.reader, self.nav, timeout=30)

    def test_claim_returns_remaining_task_after_panel_closes(self):
        self.device.transition = lambda d, x, y: setattr(d, "scene", "bonus-available")
        result = self.rewards.claim_star_bonus()
        self.assertTrue(result.success, result.reason)
        self.assertEqual(StarBonusState.AVAILABLE, result.bonus.state)
        self.assertEqual(1, result.claims)
        self.assertEqual(1, len(self.device.inputs))

    def test_claim_complete_only_after_fresh_home_pair(self):
        self.device.transition = lambda d, x, y: setattr(d, "scene", "builder-home-a")
        result = self.rewards.claim_star_bonus()
        self.assertTrue(result.success, result.reason)
        self.assertEqual(StarBonusState.COMPLETE, result.bonus.state)
        self.assertEqual(2, len(result.bonus.captures))

    def test_panel_stays_open_never_replays_claim(self):
        result = self.rewards.claim_star_bonus()
        self.assertFalse(result.success)
        self.assertEqual(StarBonusState.UNKNOWN, result.bonus.state)
        self.assertEqual(1, len(self.device.inputs))

    def test_tap_failure_returns_unknown(self):
        self.device.accept = False
        result = self.rewards.claim_star_bonus()
        self.assertFalse(result.success)
        self.assertEqual(StarBonusState.UNKNOWN, result.bonus.state)
        self.assertEqual(1, len(self.device.inputs))

    def test_loading_or_covered_button_after_claim_never_complete(self):
        for name in ("loading", "button-covered"):
            with self.subTest(name=name):
                self.device.scene = "reward"
                self.device.inputs = []
                self.device.transition = lambda d, x, y: setattr(d, "scene", name)
                result = self.rewards.claim_star_bonus()
                self.assertFalse(result.success)
                self.assertEqual(StarBonusState.UNKNOWN, result.bonus.state)
                self.assertEqual(1, len(self.device.inputs))

    def test_new_reward_panels_need_a_proven_home_between_claims(self):
        # Each home return is visible once before the next panel. A continuous
        # panel, even with changed artwork, is not a verified second reward.
        self.rewards.max_claims = 2
        home_frames = [0]
        original = self.reader.capture

        def capture():
            if self.device.scene == "builder-home-a":
                home_frames[0] += 1
                if home_frames[0] % 2 == 0:
                    self.device.scene = "reward"
            return original()

        self.reader.capture = capture
        self.device.transition = lambda d, x, y: setattr(d, "scene", "builder-home-a")
        result = self.rewards.claim_star_bonus()
        self.assertFalse(result.success)
        self.assertEqual(StarBonusState.CLAIMABLE, result.bonus.state)
        self.assertEqual(2, len(self.device.inputs))


class CartTransactionsTests(unittest.TestCase):
    def setup_cart(
        self, panel="cart-empty-a", after="cart-empty-b", tap_ok=True, close_ok=True
    ):
        device = Device("builder-offset")
        reader = Reader(device)
        camera = Camera(device)
        nav = VillageNavigator(device, reader, camera, timeout=30)
        nav.wait = lambda seconds=0.25: None
        device.accept = tap_ok

        def transition(d, x, y):
            if d.scene == "builder-offset":
                d.scene = panel
            elif x > 1300:
                if close_ok:
                    d.scene = "builder-offset"
            else:
                d.scene = after

        device.transition = transition
        return device, BuilderRewards(device, reader, nav, timeout=30)

    def test_empty_cart_opens_and_closes_without_collecting(self):
        device, rewards = self.setup_cart()
        result = rewards.collect_cart()
        self.assertTrue(result.success, result.reason)
        self.assertTrue(result.returned_home)
        self.assertFalse(result.collected)
        self.assertEqual(2, len(device.inputs))

    def test_resume_open_cart_never_reopens_map_object(self):
        device, rewards = self.setup_cart("cart-empty-a")
        device.scene = "cart-empty-a"
        result = rewards.collect_cart(resume=True)
        self.assertTrue(result.success, result.reason)
        self.assertTrue(result.returned_home)
        self.assertEqual(1, len(device.inputs))
        self.assertEqual("cart-empty-a", device.inputs[0][0])

    def test_disabled_collect_with_balance_is_unavailable_not_fake_empty_or_collected(
        self,
    ):
        device, rewards = self.setup_cart("cart-disabled-balance")
        # The older GĐ4 collectable composite retains the native empty-cart
        # message. Use the new native balance/disabled receipt for this branch.
        path = (
            Path(__file__).parent
            / "fixtures/dual_village/builder/cart-disabled-balance.png"
        )
        image = cv2.imread(str(path))
        self.assertIsNotNone(image)
        self.assertNotIn("cart_empty", rewards.reader.classify(image).points)
        device.frames["cart-disabled-balance"] = image
        device.scene = "cart-disabled-balance"
        result = rewards.collect_cart(resume=True)
        self.assertTrue(result.success, result.reason)
        self.assertTrue(result.unavailable and result.returned_home)
        self.assertFalse(result.collected or result.defending)
        self.assertIn("chưa xác định nguyên nhân", result.reason)
        self.assertEqual(1, len(device.inputs))

    def test_defense_in_progress_finishes_without_waiting_for_battle(self):
        device, rewards = self.setup_cart("cart-defending")
        result = rewards.collect_cart()
        self.assertTrue(result.success, result.reason)
        self.assertTrue(result.defending)
        self.assertEqual(2, len(device.inputs))

    def test_collect_requires_changed_counter_and_disabled_button_then_home(self):
        device, rewards = self.setup_cart("cart-collectable")
        result = rewards.collect_cart()
        self.assertTrue(result.success, result.reason)
        self.assertTrue(result.collected and result.returned_home)
        self.assertEqual(3, len(device.inputs))

    def test_accepted_collect_with_no_change_is_not_replayed_and_cart_closes(self):
        device, rewards = self.setup_cart("cart-collectable", "cart-collectable")
        result = rewards.collect_cart()
        self.assertFalse(result.success)
        self.assertFalse(result.collected)
        self.assertTrue(result.returned_home)
        self.assertEqual(3, len(device.inputs))

    def test_wrong_panel_never_collects_or_closes_unknown_modal(self):
        device, rewards = self.setup_cart("reward")
        result = rewards.collect_cart()
        self.assertFalse(result.success)
        self.assertEqual(1, len(device.inputs))

    def test_failed_open_or_close_reports_screen_not_restored(self):
        for tap_ok, close_ok in ((False, True), (True, False)):
            with self.subTest(tap_ok=tap_ok):
                device, rewards = self.setup_cart(tap_ok=tap_ok, close_ok=close_ok)
                result = rewards.collect_cart()
                self.assertFalse(result.success)
                self.assertFalse(result.returned_home)
                self.assertLessEqual(len(device.inputs), 2)


if __name__ == "__main__":
    unittest.main()
