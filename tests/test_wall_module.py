"""Wall upgrade regression tests; all device operations are mocked."""

import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

import cv2
import numpy as np

from cocmagic.adb_controller import ADBController
from cocmagic.modules.wall_module import (
    ADD_REGION, T_ADD_WALL, T_ELIXIR_UPGRADE, T_GOLD_UPGRADE,
    T_REMOVE_WALL, T_UPMORE, WallModule,
)


class WallUpgradeTests(unittest.TestCase):
    def make_wall(self, settings=None):
        adb = Mock()
        reader = Mock()
        return WallModule(adb, reader, settings or {"wall_type": "both"})

    def _mock_wall_buttons(self, wall):
        buttons = {T_UPMORE: (708, 748), T_ADD_WALL: (711, 747),
                   T_REMOVE_WALL: (358, 748), T_GOLD_UPGRADE: (950, 694),
                   T_ELIXIR_UPGRADE: (1128, 697)}
        wall._find = Mock(side_effect=lambda template, *_args: buttons.get(template))

    def test_9250000_gold_buys_six_walls_at_1500000_each(self):
        wall = self.make_wall()
        self.assertEqual(
            ("gold", 6),
            wall._choose_batch({"gold": 9_250_000, "elixir": 8_163_455},
                               {"gold": 1_500_000, "elixir": 1_500_000}),
        )

    def test_exact_9000000_threshold_is_eligible(self):
        wall = self.make_wall({"wall_type": "both", "wall_resource": 9_000_000})
        self.assertEqual(("gold", 6), wall._choose_batch(
            {"gold": 9_000_000, "elixir": 8_999_999},
            {"gold": 1_500_000, "elixir": 1_500_000}))

    def test_either_resource_can_qualify_and_reserve_is_honored(self):
        wall = self.make_wall({"wall_type": "both", "wall_reserve": 1_000_000})
        self.assertEqual(
            ("elixir", 4),
            wall._choose_batch({"gold": 1_000_000, "elixir": 8_000_000},
                               {"gold": 1_500_000, "elixir": 1_500_000}),
        )

    def _builder_screen(self, fixture):
        region = cv2.imread(str(Path(__file__).parent / "fixtures" / fixture))
        self.assertIsNotNone(region)
        image = np.zeros((900, 1600, 3), np.uint8)
        image[0:110, 690:800] = region
        return image

    def _wall_list_screen(self, fixture="wall_list_left_visible.png", dx=0, dy=0):
        region = cv2.imread(str(Path(__file__).parent / "fixtures" / fixture))
        self.assertIsNotNone(region)
        image = self._builder_screen("builder_available_region.png")
        image[120 + dy:700 + dy, 480 + dx:1160 + dx] = region
        return image

    def test_wall_row_from_video_is_found_in_widened_builder_list(self):
        wall = WallModule(ADBController(), Mock(), {})
        image = self._wall_list_screen()
        self.assertEqual((573, 653), wall._find_wall_row(image))

    def test_wall_row_can_move_right_or_to_bottom_of_list(self):
        wall = WallModule(ADBController(), Mock(), {})
        for dx, dy in ((0, 0), (140, 0), (0, 24)):
            with self.subTest(dx=dx, dy=dy):
                self.assertEqual((573 + dx, 653 + dy), wall._find_wall_row(
                    self._wall_list_screen(dx=dx, dy=dy)))

    def test_closed_builder_list_does_not_reuse_visible_wall_position(self):
        wall = WallModule(ADBController(), Mock(), {})
        self.assertIsNotNone(wall._find_wall_row(self._wall_list_screen()))
        self.assertIsNone(wall._find_wall_row(self._wall_list_screen(
            "wall_list_closed.png")))

    def test_visible_wall_is_selected_before_another_scroll(self):
        adb = ADBController()
        adb.screenshot = Mock(return_value=self._wall_list_screen())
        adb.tap = Mock(return_value=True)
        adb.swipe = Mock()
        reader = Mock()
        reader.read_home_resources.return_value = {"gold": 31_000_000,
                                                   "elixir": 19_290_421}
        wall = WallModule(adb, reader, {"wall_type": "gold",
                                        "wall_resource": 9_000_000})
        wall._close_panels = Mock()

        # The replay stops at selection; the clip has no Upgrade More screen.
        wall._upgrade_one_batch()

        self.assertEqual([
            call(810, 52, jitter=0, delay=0.15),
            call(573, 653, jitter=0, delay=0.2),
        ], adb.tap.call_args_list)
        adb.swipe.assert_not_called()
        self.assertTrue(wall.last_interacted)

    def test_available_portrait_allows_one_builder_even_with_legacy_setting(self):
        adb = ADBController()
        adb.screenshot = Mock(return_value=self._builder_screen(
            "builder_available_region.png"))
        adb.tap = Mock(return_value=False)
        reader = Mock()
        reader.read_home_resources.return_value = {"gold": 9_000_000,
                                                   "elixir": 8_000_000}
        wall = WallModule(adb, reader, {"upgrade_walls": True,
                                        "wall_type": "both",
                                        "wall_resource": 9_000_000,
                                        "wall_special_builder_slots": 1})
        wall._close_panels = Mock()

        self.assertFalse(wall.run())  # Stops at mocked ADB tap, after builder gate.
        adb.tap.assert_called_once_with(810, 52, jitter=0, delay=0.15)
        self.assertEqual((748, 55), wall._position_cache["builder"])
        reader.read_ui_number.assert_not_called()

    def test_cached_builder_position_requires_a_current_match(self):
        wall = WallModule(ADBController(), Mock(), {})
        available = self._builder_screen("builder_available_region.png")
        unavailable = self._builder_screen("builder_unavailable_region.png")

        self.assertTrue(wall._builder_available(available))
        self.assertEqual((748, 55), wall._position_cache["builder"])
        self.assertFalse(wall._builder_available(unavailable))
        self.assertEqual((748, 55), wall._position_cache["builder"])

    def test_add_wall_cache_recovers_after_button_moves(self):
        wall = WallModule(ADBController(), Mock(), {})
        template = cv2.imread(T_ADD_WALL)
        self.assertIsNotNone(template)
        height, width = template.shape[:2]

        def screen(left, top):
            image = np.zeros((900, 1600, 3), np.uint8)
            image[top:top + height, left:left + width] = template
            return image

        first_screen = screen(642, 690)
        first = wall._find_cached("add_wall", T_ADD_WALL,
                                  first_screen, ADD_REGION, .84,
                                  (width, height))
        self.assertEqual((642 + width // 2, 690 + height // 2), first)
        self.assertEqual(first, wall._position_cache["add_wall"])
        with patch.object(wall.adb, "find_template",
                          wraps=wall.adb.find_template) as detect:
            self.assertEqual(first, wall._find_cached(
                "add_wall", T_ADD_WALL, first_screen, ADD_REGION, .84,
                (width, height)))
        self.assertNotEqual(ADD_REGION, detect.call_args.kwargs["region"])
        self.assertIsNone(wall._find_cached(
            "add_wall", T_ADD_WALL, np.zeros((900, 1600, 3), np.uint8),
            ADD_REGION, .84, (width, height)))
        self.assertEqual(first, wall._position_cache["add_wall"])

        moved = wall._find_cached("add_wall", T_ADD_WALL,
                                  screen(652, 730), ADD_REGION, .84,
                                  (width, height))
        self.assertEqual((652 + width // 2, 730 + height // 2), moved)
        self.assertEqual(moved, wall._position_cache["add_wall"])

    def test_hireable_goblin_icon_does_not_authorize_upgrade(self):
        adb = ADBController()
        adb.screenshot = Mock(return_value=self._builder_screen(
            "builder_unavailable_region.png"))
        adb.tap = Mock()
        reader = Mock()
        reader.read_home_resources.return_value = {"gold": 9_250_000,
                                                   "elixir": 8_000_000}
        wall = WallModule(adb, reader, {"upgrade_walls": True,
                                        "wall_type": "both"})

        self.assertFalse(wall.run())
        self.assertFalse(wall.last_interacted)
        adb.tap.assert_not_called()

    def test_successful_six_wall_batch_increments_session_counter(self):
        wall = self.make_wall({"upgrade_walls": True, "wall_type": "gold",
                               "wall_resource": 9_000_000})
        wall.adb.screenshot.return_value = np.zeros((900, 1600, 3), np.uint8)
        wall.adb.tap.return_value = True
        wall.reader.read_home_resources.return_value = {"gold": 9_000_000,
                                                        "elixir": 0}
        wall._builder_available = Mock(return_value=True)
        wall._position_cache["builder"] = (748, 55)
        wall._find_wall_row = Mock(return_value=(700, 300))
        self._mock_wall_buttons(wall)
        wall._read_costs = Mock(side_effect=[
            {"gold": 1_500_000, "elixir": 0},
            *({"gold": 1_500_000 * count, "elixir": 0}
              for count in range(2, 7)),
            {"gold": 9_000_000, "elixir": 0},
        ])
        wall._confirm_upgrade = Mock(return_value=True)
        wall._close_panels = Mock()

        self.assertTrue(wall.run())
        self.assertEqual(6, wall.walls_upgraded)
        self.assertEqual(2, wall.reader.read_home_resources.call_count)

    def test_gold_and_elixir_are_upgraded_before_returning_to_farm(self):
        wall = self.make_wall({"upgrade_walls": True, "wall_type": "both",
                               "wall_resource": 9_000_000})
        wall.adb.screenshot.return_value = np.zeros((900, 1600, 3), np.uint8)
        wall.adb.tap.return_value = True
        initial = {"gold": 9_250_000, "elixir": 9_500_000}
        after_gold = {"gold": 250_000, "elixir": 9_500_000}
        after_both = {"gold": 250_000, "elixir": 500_000}
        wall.reader.read_home_resources.side_effect = [
            initial, initial, after_gold, after_gold, after_both]
        wall._builder_available = Mock(return_value=True)
        wall._position_cache["builder"] = (748, 55)
        wall._find_wall_row = Mock(return_value=(700, 300))
        self._mock_wall_buttons(wall)
        batch_costs = [
            {"gold": 1_500_000, "elixir": 1_500_000},
            *({"gold": 1_500_000 * count,
               "elixir": 1_500_000 * count} for count in range(2, 7)),
            {"gold": 9_000_000, "elixir": 9_000_000},
        ]
        wall._read_costs = Mock(side_effect=batch_costs * 2)

        def confirm(*_args):
            wall.last_upgrade_verified = True
            return True

        wall._confirm_upgrade = Mock(side_effect=confirm)
        wall._close_panels = Mock()

        self.assertTrue(wall.run())
        self.assertEqual(["gold", "elixir"],
                         [call.args[1] for call in wall._confirm_upgrade.call_args_list])
        self.assertEqual(12, wall.walls_upgraded)
        self.assertEqual(5, wall.reader.read_home_resources.call_count)
        self.assertEqual(2, wall._close_panels.call_count)

    def test_wall_upgrade_can_be_disabled_for_event_training(self):
        wall = self.make_wall({"upgrade_walls": False})
        self.assertFalse(wall.run())
        wall.adb.screenshot.assert_not_called()

    def test_gem_modal_is_detected_before_any_confirmation(self):
        wall = self.make_wall()
        image = np.zeros((900, 1600, 3), np.uint8)
        image[240:530, 660:1320] = 240
        image[500:580, 840:1060] = (40, 220, 40)
        image[500:580, 1120:1340] = (40, 220, 40)
        self.assertTrue(wall._is_gem_dialog(image))
        self.assertFalse(wall._is_gem_dialog(np.zeros_like(image)))
        image[500:580, 1120:1340] = 240
        self.assertFalse(wall._is_gem_dialog(image))


if __name__ == "__main__":
    unittest.main()
