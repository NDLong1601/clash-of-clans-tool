"""Regression coverage for the two confirmation dialogs reported by users."""

from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from cocmagic.adb_controller import ADBController
from cocmagic.modules.farm_module import FarmModule, FarmState, T_END_BATTLE_BUTTON, T_SURRENDER
from cocmagic.modules.wall_module import WallModule
from cocmagic.ui_dialogs import BUTTON_REGION, find_confirmation_button


FIXTURES = Path(__file__).parent / "fixtures"


def centered_dialog(name):
    crop = cv2.imread(str(FIXTURES / name))
    if crop is None:
        raise RuntimeError(f"Missing dialog regression fixture: {name}")
    screen = np.zeros((900, 1600, 3), np.uint8)
    y, x = (900 - crop.shape[0]) // 2, (1600 - crop.shape[1]) // 2
    screen[y:y + crop.shape[0], x:x + crop.shape[1]] = crop
    return screen


class ConfirmationDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.battle_dialog = centered_dialog("end_battle_confirm.png")
        cls.wall_dialog = centered_dialog("upgrade_walls_confirm.png")
        cls.blank = np.zeros((900, 1600, 3), np.uint8)

    def test_only_centered_cancel_and_okay_dialog_is_accepted(self):
        adb = ADBController()
        self.assertEqual((940, 553), find_confirmation_button(adb, self.battle_dialog))
        self.assertEqual((932, 551), find_confirmation_button(adb, self.wall_dialog))
        self.assertIsNone(find_confirmation_button(adb, self.blank))
        without_cancel = self.wall_dialog.copy()
        without_cancel[490:610, 520:805] = 0
        self.assertIsNone(find_confirmation_button(adb, without_cancel))

    def test_wall_confirmation_cache_rechecks_the_whole_dialog(self):
        wall = WallModule(ADBController(), Mock(), {})
        self.assertEqual((932, 551), wall._confirmation_button(self.wall_dialog))
        self.assertEqual((932, 551), wall._position_cache["confirm"])
        with patch.object(wall.adb, "find_template",
                          wraps=wall.adb.find_template) as detect:
            self.assertEqual((932, 551),
                             wall._confirmation_button(self.wall_dialog))
        self.assertNotEqual(BUTTON_REGION, detect.call_args.kwargs["region"])

        without_cancel = self.wall_dialog.copy()
        without_cancel[490:610, 520:805] = 0
        self.assertIsNone(wall._confirmation_button(without_cancel))
        self.assertEqual((932, 551), wall._position_cache["confirm"])
        self.assertIsNone(wall._confirmation_button(self.blank))
        self.assertEqual((932, 551), wall._position_cache["confirm"])
        self.assertEqual((932, 551), wall._confirmation_button(self.wall_dialog))

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_end_battle_clicks_okay_before_accepting_result(self, _sleep):
        adb = ADBController()
        battle = self.blank.copy()
        result = self.blank.copy()
        result[0, 0] = (1, 2, 3)
        adb.screenshot = Mock(side_effect=[battle, self.battle_dialog, result])
        adb.find_and_tap = Mock(side_effect=lambda path, *a, **kw: path == T_END_BATTLE_BUTTON)
        adb.tap = Mock(return_value=True)
        farm = FarmModule(adb, None, None, {})
        farm._is_result_screen = Mock(side_effect=lambda image: image is result)
        farm._is_home_screen = Mock(return_value=False)

        self.assertTrue(farm._force_end_battle())
        adb.tap.assert_called_once_with(940, 553, jitter=0, delay=0.1)
        self.assertEqual([T_SURRENDER, T_END_BATTLE_BUTTON],
                         [c.args[0] for c in adb.find_and_tap.call_args_list])

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_wait_state_resolves_delayed_end_battle_dialog(self, _sleep):
        adb = ADBController()
        result = self.blank.copy()
        adb.screenshot = Mock(side_effect=[self.battle_dialog, result])
        adb.tap = Mock(return_value=True)
        farm = FarmModule(adb, None, None, {"farm_battle_timeout": 85})
        farm.state = FarmState.BATTLE_WAIT
        farm.battle_start_ts = 0
        farm._is_home_screen = Mock(return_value=False)
        farm._is_result_screen = Mock(side_effect=lambda image: image is result)

        farm._state_battle_wait()

        self.assertEqual(FarmState.RESULT, farm.state)
        adb.tap.assert_called_once_with(940, 553, jitter=0, delay=0.1)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_result_state_does_not_search_return_home_behind_dialog(self, _sleep):
        adb = ADBController()
        result = self.blank.copy()
        adb.screenshot = Mock(side_effect=[self.battle_dialog, result])
        adb.tap = Mock(return_value=True)
        adb.find_and_tap = Mock(return_value=False)
        farm = FarmModule(adb, None, None, {})
        farm.state = FarmState.RESULT
        farm._is_home_screen = Mock(return_value=False)
        farm._is_result_screen = Mock(side_effect=lambda image: image is result)

        farm._state_result()

        adb.tap.assert_called_once_with(940, 553, jitter=0, delay=0.1)
        adb.find_and_tap.assert_not_called()
        self.assertEqual(FarmState.RESULT, farm.state)

    @patch("cocmagic.modules.wall_module.time.sleep")
    def test_wall_upgrade_clicks_okay_and_checks_resource_debit(self, _sleep):
        adb = ADBController()
        adb.tap = Mock(return_value=True)
        adb.screenshot = Mock(return_value=self.blank)
        reader = Mock()
        reader.read_home_resources.side_effect = [
            {"elixir": 8_000_000}, {"elixir": 6_500_000}]
        wall = WallModule(adb, reader, {})

        self.assertTrue(wall._confirm_upgrade(
            self.wall_dialog, "elixir", 8_000_000, 1_500_000))
        adb.tap.assert_called_once_with(932, 551, jitter=0, delay=0.2)

    @patch("cocmagic.modules.wall_module.time.sleep")
    def test_green_village_background_does_not_cancel_wall_confirmation(self, _sleep):
        # A second green region beside Okay used to resemble two gem offers.
        dialog = self.wall_dialog.copy()
        dialog[500:600, 1210:1360] = (40, 220, 40)
        adb = ADBController()
        adb.tap = Mock(return_value=True)
        adb.screenshot = Mock(return_value=self.blank)
        reader = Mock()
        reader.read_home_resources.return_value = {"gold": 7_500_000}
        wall = WallModule(adb, reader, {})

        self.assertFalse(wall._is_gem_dialog(dialog))
        self.assertTrue(wall._confirm_upgrade(
            dialog, "gold", 9_000_000, 1_500_000))
        adb.tap.assert_called_once_with(932, 551, jitter=0, delay=0.2)
        self.assertTrue(wall.last_upgrade_verified)

    @patch("cocmagic.modules.wall_module.time.sleep")
    def test_wall_upgrade_does_not_report_success_without_debit(self, _sleep):
        adb = ADBController()
        adb.tap = Mock(return_value=True)
        adb.screenshot = Mock(return_value=self.blank)
        reader = Mock()
        reader.read_home_resources.return_value = {"elixir": 8_000_000}
        wall = WallModule(adb, reader, {})

        self.assertFalse(wall._confirm_upgrade(
            self.wall_dialog, "elixir", 8_000_000, 1_500_000))
        adb.tap.assert_called_once()

    @patch("cocmagic.modules.wall_module.time.sleep")
    def test_wall_home_return_counts_as_confirmed_when_hud_ocr_lags(self, _sleep):
        adb = ADBController()
        adb.tap = Mock(return_value=True)
        home = self.blank.copy()
        icon = cv2.imread(str(FIXTURES / "builder_available_region.png"))
        home[0:110, 690:800] = icon
        adb.screenshot = Mock(return_value=home)
        reader = Mock()
        reader.read_home_resources.return_value = {"elixir": 8_000_000}
        wall = WallModule(adb, reader, {})

        self.assertTrue(wall._confirm_upgrade(
            self.wall_dialog, "elixir", 8_000_000, 1_500_000))
        self.assertFalse(wall.last_upgrade_verified)
        adb.tap.assert_called_once_with(932, 551, jitter=0, delay=0.2)

    @patch("cocmagic.modules.wall_module.time.sleep")
    def test_gem_offer_is_never_confirmed_as_wall_upgrade(self, _sleep):
        adb = ADBController()
        adb.tap = Mock(return_value=True)
        wall = WallModule(adb, Mock(), {})
        gem = self.blank.copy()
        gem[240:530, 660:1320] = 240
        gem[500:580, 840:1060] = (40, 220, 40)
        gem[500:580, 1120:1340] = (40, 220, 40)

        self.assertFalse(wall._confirm_upgrade(gem, "gold", 9_000_000, 1_500_000))
        adb.tap.assert_not_called()

    def test_unresolved_wall_dialog_is_cancelled_without_map_tap(self):
        adb = ADBController()
        adb.screenshot = Mock(return_value=self.wall_dialog)
        adb.back = Mock()
        adb.tap = Mock()
        wall = WallModule(adb, Mock(), {})

        wall._close_panels()

        adb.back.assert_called_once()
        adb.tap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
