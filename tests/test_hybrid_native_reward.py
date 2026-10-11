"""Native Star Bonus overlay must be handled before cart/boat navigation."""

from pathlib import Path
import time
import unittest

import cv2

from cocmagic import config
from cocmagic.builder_rewards import BuilderRewards
from cocmagic.builder_screen_reader import (
    BuilderScreenReader,
    Capture,
    ScreenKind,
    StarBonusReader,
    StarBonusState,
    Village,
)
from cocmagic.village_navigator import VillageNavigator
from test_village_navigation_rewards import Camera, Device, Reader


class NativeRewardTests(unittest.TestCase):
    def setUp(self):
        self.image = cv2.imread(
            str(
                Path(config.BASE_DIR)
                / "tests/fixtures/dual_village/acceptance/builder-star-reward-native.png"
            )
        )
        self.reader = BuilderScreenReader()

    def test_native_overlay_is_claimable_and_blocks_home(self):
        screen = self.reader.classify(self.image)
        self.assertEqual(
            (ScreenKind.MODAL, "star_reward", Village.BUILDER),
            (screen.kind, screen.panel, screen.village),
        )
        self.assertEqual((800, 701), screen.points["claim"])
        self.assertFalse(self.reader.home_is_clear(self.image, Village.BUILDER))
        bonus = StarBonusReader(self.reader).observe(Capture(self.image, 1, 10.0, 0))
        self.assertEqual(StarBonusState.CLAIMABLE, bonus.state)

    def test_unrecognized_blue_overlay_never_becomes_home_or_complete(self):
        for name in (
            "reward_title_native",
            "reward_star_native",
            "reward_button_native",
        ):
            self.reader.spec["anchors"].pop(name)
        screen = self.reader.classify(self.image)
        self.assertEqual(ScreenKind.MODAL, screen.kind)
        self.assertNotIn("claim", screen.points)
        observer = StarBonusReader(self.reader)
        for sequence in (1, 2):
            bonus = observer.observe(Capture(self.image.copy(), sequence, sequence, 0))
            self.assertEqual(StarBonusState.UNKNOWN, bonus.state)

    def test_obscured_okay_cannot_authorize_a_claim(self):
        self.image[645:755, 675:930] = 0
        screen = self.reader.classify(self.image)
        self.assertEqual("star_reward", screen.panel)
        self.assertNotIn("claim", screen.points)
        bonus = StarBonusReader(self.reader).observe(Capture(self.image, 1, 10.0, 0))
        self.assertEqual(StarBonusState.UNKNOWN, bonus.state)

    def test_missing_builder_portrait_cannot_authorize_a_claim(self):
        self.image[:120, 775:1090] = 0
        screen = self.reader.classify(self.image)
        self.assertEqual(ScreenKind.MODAL, screen.kind)
        self.assertNotIn("claim", screen.points)

    def test_native_reward_closes_once_and_reads_new_home_before_complete(self):
        device = Device("reward-native")
        device.frames[device.scene] = self.image
        device.transition = lambda d, x, y: setattr(d, "scene", "builder-home-a")
        reader = Reader(device)
        nav = VillageNavigator(device, reader, Camera(device), timeout=30)
        nav.wait = lambda *_: None
        result = BuilderRewards(device, reader, nav, timeout=30).claim_star_bonus()
        self.assertTrue(result.success, result.reason)
        self.assertEqual(StarBonusState.COMPLETE, result.bonus.state)
        self.assertEqual(1, result.claims)
        self.assertEqual([("reward-native", 800, 701)], device.inputs)
        self.assertEqual(2, len(result.bonus.captures))

    def test_reward_panel_refuses_cart_and_boat_navigation_without_input(self):
        device = Device("reward-native")
        device.frames[device.scene] = self.image
        nav = VillageNavigator(device, Reader(device), Camera(device), timeout=10)
        nav.wait = lambda *_: None
        self.assertFalse(nav.navigate(Village.MAIN).success)
        found, _ = nav.locate("cart_object", Village.BUILDER, time.monotonic() + 10)
        self.assertIsNone(found)
        self.assertFalse(device.inputs)
        self.assertEqual(0, nav.camera.operations)
