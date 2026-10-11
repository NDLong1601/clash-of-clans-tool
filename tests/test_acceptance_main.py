"""Native main pre-deployment Surrender must survive the strict frame guard."""

from pathlib import Path
import unittest
from unittest.mock import Mock

import cv2
import numpy as np

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.bot_engine import BotEngine
from cocmagic.modules.farm_module import FarmModule, FarmState
from cocmagic.run_coordinator import RunCoordinator
from cocmagic.village_module import ModuleScreen


class MainSurrenderTests(unittest.TestCase):
    def setUp(self):
        self.engine = BotEngine({"auto_train": False}, "offline-main")
        self.engine.adb = ADBController(serial="offline-main", settings={})
        self.farm = FarmModule(self.engine.adb, Mock(), Mock(), self.engine.settings)
        self.engine.farm_mod = self.farm
        self.engine.coordinator = RunCoordinator(
            "offline-main", {"main": self.farm}, "main"
        )
        self.farm.state = FarmState.ATTACKING
        self.image = cv2.imread(
            str(
                Path(config.BASE_DIR)
                / "tests/fixtures/dual_village/acceptance/main-surrender.png"
            )
        )
        self.assertIsNotNone(self.image)

    def test_surrender_with_native_main_timer_keeps_deployment_and_cached_points(self):
        self.farm._confirmed_main_points = [(1255, 646)]
        self.assertEqual(ModuleScreen.BATTLE, self.farm._classify_screen(self.image))
        self.engine._guard_frame(self.image)
        self.assertEqual(FarmState.ATTACKING, self.farm.state)
        self.assertEqual([(1255, 646)], self.farm._confirmed_main_points)

    def test_surrender_button_alone_and_builder_battle_cannot_prove_main_battle(self):
        no_timer = self.image.copy()
        no_timer[0:110, 650:970] = 0
        root = Path(config.BASE_DIR) / "tests/fixtures/dual_village/builder"
        for image in (
            no_timer,
            np.zeros_like(self.image),
            cv2.imread(str(root / "scout.png")),
            cv2.imread(str(root / "stage2-prep.png")),
        ):
            with self.subTest():
                self.assertFalse(self.farm._is_battle_screen(image))

    def test_timer_survives_a_different_map_and_warning_red_text(self):
        path = (
            Path(config.BASE_DIR)
            / "tests/fixtures/dual_village/acceptance/main-surrender-map-variant.png"
        )
        image = cv2.imread(str(path))
        self.assertTrue(self.farm._is_battle_screen(image))
        # Explicit transformed test, not a claim of native red-timer coverage.
        white = np.all(image[0:110, 650:970] > 220, axis=2)
        region = image[0:110, 650:970]
        region[white] = (0, 0, 255)
        self.assertTrue(self.farm._is_battle_screen(image))
