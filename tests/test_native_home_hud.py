"""Main farming must use the same native Home proof as village navigation."""

from pathlib import Path
import unittest
from unittest.mock import Mock

import cv2

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.modules.farm_module import FarmModule, FarmState, T_HOME_ATTACK_LABEL
from cocmagic.village_module import ModuleScreen
from cocmagic.builder_vision import BuilderBattleReader, SlotState, AbilityState


class NativeMainHomeTests(unittest.TestCase):
    def setUp(self):
        self.adb = ADBController(serial="offline-native-home")
        self.farm = FarmModule(
            self.adb, Mock(), Mock(), {"auto_train": False, "upgrade_walls": False}
        )
        self.root = Path(config.BASE_DIR) / "tests/fixtures/dual_village/acceptance"
        self.image = cv2.imread(str(self.root / "main-home-attack-stars.png"))
        self.assertIsNotNone(self.image)
        self.adb.screenshot = Mock(side_effect=lambda **kwargs: self.image.copy())
        self.adb.tap = Mock(return_value=True)
        self.farm._wait = Mock()

    def test_changed_main_home_artwork_opens_attack_with_a_verified_label(self):
        self.assertTrue(self.farm._is_home_screen(self.image))
        self.farm._state_home()
        self.assertEqual(FarmState.FIND_MATCH, self.farm.state)
        self.assertEqual(
            T_HOME_ATTACK_LABEL, self.farm._button_templates["home_attack"]
        )
        self.assertEqual(1, self.adb.tap.call_count)
        point = self.farm._native_main_home(self.image).points["attack"]
        self.assertEqual(point, self.adb.tap.call_args.args)

    def test_recovery_yields_home_to_hybrid_before_any_attack(self):
        self.farm._begin_recovery(FarmState.HOME)
        for _ in range(3):
            self.assertTrue(self.farm.tick(yield_requested=lambda: True))
            if self.farm.can_yield:
                break
        self.assertEqual(ModuleScreen.HOME, self.farm.confirmed_screen)
        self.assertTrue(self.farm.can_yield)
        self.adb.tap.assert_not_called()

    def test_label_fallback_refuses_builder_and_blocking_modal(self):
        builder = cv2.imread(str(self.root / "builder-home-bonus-zero-native.png"))
        modal = self.image.copy()
        modal[180:625, 350:1250] = 170
        for image in (builder, modal):
            with self.subTest():
                self.assertIsNone(self.farm._native_main_home(image))
        self.adb.tap.assert_not_called()


class NativeBuilderHeroTests(unittest.TestCase):
    def test_short_health_border_keeps_charging_hero_deployed(self):
        path = (
            Path(config.BASE_DIR)
            / "tests/fixtures/dual_village/acceptance/builder-hero-charging-short-border.png"
        )
        image = cv2.imread(str(path))
        reader = BuilderBattleReader()
        bar = reader.read_bar(image)
        self.assertTrue(bar.valid)
        hero = next(s for s in bar.slots if s.kind == "battle_machine")
        self.assertEqual(
            (SlotState.DEPLOYED, AbilityState.CHARGING), (hero.state, hero.ability)
        )
        troops = [s for s in bar.slots if s.role == "troop"]
        self.assertEqual(5, len(troops))
        self.assertTrue(all(s.state == SlotState.UNDEPLOYED for s in troops))

    def test_selected_baby_dragon_is_undeployed_and_other_camps_are_unselected(self):
        path = (
            Path(config.BASE_DIR)
            / "tests/fixtures/dual_village/acceptance/builder-hero-charging-short-border.png"
        )
        bar = BuilderBattleReader().read_bar(cv2.imread(str(path)))
        self.assertTrue(bar.valid)
        troops = [s for s in bar.slots if s.role == "troop"]
        self.assertTrue(troops[0].selected)
        self.assertEqual(SlotState.UNDEPLOYED, troops[0].state)
        self.assertFalse(any(s.selected for s in troops[1:]))

    def test_later_selected_camp_does_not_require_a_cyan_header(self):
        path = (
            Path(config.BASE_DIR)
            / "tests/fixtures/dual_village/acceptance/builder-selected-camp5.png"
        )
        bar = BuilderBattleReader().read_bar(cv2.imread(str(path)))
        self.assertTrue(bar.valid)
        selected = [s for s in bar.slots if s.selected]
        self.assertEqual(["camp:5"], [s.key for s in selected])
        self.assertEqual(SlotState.UNDEPLOYED, selected[0].state)
