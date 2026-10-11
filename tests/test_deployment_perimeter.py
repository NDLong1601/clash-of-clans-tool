"""Scenery and decorations must not veto the known construction perimeter."""

import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from cocmagic import config
from cocmagic.battle_planner import BattlePlanner
from cocmagic.modules.farm_module import CardSlot, ComboProfile, FarmModule, FarmState


class PerimeterVisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = cv2.imread(config.BASE_DIR + "/tests/fixtures/user_decorated_scenery.png")

    def test_user_scenery_has_candidates_on_every_visible_side(self):
        plan = BattlePlanner().plan(self.image)
        self.assertIsNotNone(plan)
        self.assertEqual("outer_perimeter", plan.source)
        self.assertTrue(plan.requires_probe)
        self.assertGreaterEqual(len(plan.troop_points), 16)
        sectors = {(x >= 800, y >= 440) for x, y in plan.troop_points}
        self.assertEqual(4, len(sectors))
        for x, y in plan.troop_points:
            self.assertTrue(BattlePlanner.perimeter_point_visible((x, y)))
            self.assertLess(cv2.pointPolygonTest(plan.boundary.astype(np.float32),
                                                 (float(x), float(y)), False), 0)

    def test_no_grass_snow_dark_and_purple_scenery_keep_the_same_candidates(self):
        expected = BattlePlanner().plan(self.image).troop_points
        hsv = cv2.cvtColor(self.image, cv2.COLOR_BGR2HSV)
        for hue, saturation in ((145, 160), (20, 160), (100, 0)):
            with self.subTest(hue=hue, saturation=saturation):
                changed = hsv.copy()
                changed[:, :, 0] = hue
                changed[:, :, 1] = saturation
                plan = BattlePlanner().plan(cv2.cvtColor(changed, cv2.COLOR_HSV2BGR))
                self.assertIsNotNone(plan)
                self.assertEqual(expected, plan.troop_points)

    def test_dense_decorations_over_every_drop_point_do_not_remove_candidates(self):
        expected = BattlePlanner().plan(self.image).troop_points
        image = self.image.copy()
        # A textured purple ornament/tree canopy covers every candidate patch.
        yy, xx = np.indices((41, 41))
        patch = np.where(((xx // 3 + yy // 3) % 2)[..., None],
                         (180, 35, 115), (40, 20, 45)).astype(np.uint8)
        for x, y in expected:
            image[y - 20:y + 21, x - 20:x + 21] = patch
        plan = BattlePlanner().plan(image)
        self.assertIsNotNone(plan)
        self.assertEqual(expected, plan.troop_points)

    def test_supported_red_border_allows_non_green_and_dark_exterior(self):
        outline = np.array([(800, 110), (1360, 400), (800, 690), (240, 400)], np.int32)
        for background in ((0, 180, 220), (10, 10, 10), (160, 30, 120)):
            with self.subTest(background=background):
                image = np.full((900, 1600, 3), background, dtype=np.uint8)
                cv2.polylines(image, [outline], True, (0, 0, 255), 3)
                plan = BattlePlanner().plan(image)
                self.assertIsNotNone(plan)
                self.assertEqual("red_boundary", plan.source)
                self.assertFalse(plan.requires_probe)
                self.assertGreaterEqual(len(plan.troop_points), 4)

    def test_alternative_offsets_are_available_when_a_large_base_rejects_inner_edge(self):
        plan = BattlePlanner().plan(self.image)
        distances = [abs(cv2.pointPolygonTest(plan.boundary.astype(np.float32),
                                             (float(x), float(y)), True))
                     for x, y in plan.troop_points]
        self.assertLess(min(distances), 30)
        self.assertGreater(max(distances), 130)

    def test_loading_and_isolated_text_do_not_produce_a_geometric_plan(self):
        for value in (0, 128, 255):
            self.assertIsNone(BattlePlanner().plan(np.full((900, 1600, 3), value, np.uint8)))
        image = np.zeros((900, 1600, 3), np.uint8)
        cv2.putText(image, "Loading", (650, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        self.assertIsNone(BattlePlanner().plan(image))

    def test_hough_lines_2d_shape_unpacks_safely(self):
        with patch("cv2.HoughLinesP") as mock_hough:
            mock_hough.return_value = np.array([
                [800, 110, 1360, 400],
                [1360, 400, 800, 690],
                [800, 690, 240, 400],
                [240, 400, 800, 110]
            ], dtype=np.int32)
            plan = BattlePlanner().plan(self.image)
            self.assertIsNotNone(plan)


class PerimeterDeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = cv2.imread(config.BASE_DIR + "/tests/fixtures/user_decorated_scenery.png")

    def make_farm(self):
        adb = Mock()
        adb.tap.return_value = True
        adb.tap_many.return_value = True
        farm = FarmModule(adb, Mock(), Mock(), {})
        farm._battle_plan = farm.planner.plan(self.image)
        farm._combo_profile = ComboProfile([CardSlot(179, 840, "troop")], [], (900, 1600))
        farm._card_depleted = Mock(return_value=False)
        return farm

    def test_rich_opponent_with_unfamiliar_ground_enters_attack_instead_of_next(self):
        image = cv2.cvtColor(self.image, cv2.COLOR_BGR2HSV)
        image[:, :, 0] = 145
        image = cv2.cvtColor(image, cv2.COLOR_HSV2BGR)
        farm = self.make_farm()
        farm.state = FarmState.LOOT_CHECK
        farm.adb.screenshot.return_value = image
        farm._is_scout_screen = Mock(return_value=True)
        farm.reader.read_loot.return_value = {"gold": 1_137_591, "elixir": 951_335, "dark": 10_569}
        farm.reader.loot_meets_threshold.return_value = True
        farm._skip_scout = Mock()
        farm._state_loot_check()
        self.assertEqual(FarmState.ATTACKING, farm.state)
        self.assertTrue(farm._battle_plan.requires_probe)
        farm._skip_scout.assert_not_called()

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_rejected_edges_are_probed_then_decorated_edge_is_confirmed_before_bulk_drop(self, _sleep):
        farm = self.make_farm()
        accepted_point = farm._battle_plan.troop_points[3]
        ui = {"remaining": 8, "drops": 0}

        def frame(**kwargs):
            image = self.image.copy()
            image[0, 0, 0] = ui["remaining"]
            return image

        def drops(points, **kwargs):
            for point in points:
                if point == accepted_point and ui["remaining"] > 0:
                    ui["remaining"] -= 1
                    ui["drops"] += 1
            return True

        farm.adb.screenshot.side_effect = frame
        farm.adb.tap_many.side_effect = drops
        with patch("cocmagic.modules.farm_module.read_card_count",
                   side_effect=lambda image, x, y: int(image[0, 0, 0])), \
                patch("cocmagic.modules.farm_module.is_electro_card", return_value=False):
            farm._deploy_all_troops(frame())
        calls = farm.adb.tap_many.call_args_list
        self.assertEqual([[point] for point in farm._battle_plan.troop_points[:4]],
                         [call.args[0] for call in calls[1:5]])
        self.assertEqual([accepted_point] * 7, calls[5].args[0])
        self.assertEqual(8, ui["drops"])
        self.assertEqual([accepted_point], farm._confirmed_main_points)
        self.assertEqual(accepted_point, farm._attack_tactics.entry)
        self.assertFalse(farm._deployment_rejected)
        self.assertIsNone(farm.halt_reason)
        self.assertTrue(all(call.kwargs.get("use_cache") is False
                            for call in farm.adb.screenshot.call_args_list[1:]))

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_count_increase_or_selection_redraw_is_not_a_confirmed_drop(self, _sleep):
        for after_count in (8, 9):
            with self.subTest(after_count=after_count):
                farm = self.make_farm()
                before = self.image.copy()
                before[0, 0, 0] = 8
                after = self.image.copy()
                after[0, 0, 0] = after_count
                farm.adb.screenshot.return_value = after
                farm._card_depleted.return_value = True
                farm._count_display_changed = Mock(return_value=True)
                with patch("cocmagic.modules.farm_module.read_card_count",
                           side_effect=lambda image, x, y: int(image[0, 0, 0])):
                    _, accepted = farm._verify_card_use(before, farm._combo_profile.cards[0])
                self.assertFalse(accepted)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_lagging_counter_is_confirmed_from_fresh_frames_before_next_point(self, _sleep):
        farm = self.make_farm()
        before = self.image.copy()
        before[0, 0, 0] = 8
        after = before.copy()
        after[0, 0, 0] = 7
        farm.adb.screenshot.side_effect = [before, before, after]
        with patch("cocmagic.modules.farm_module.read_card_count",
                   side_effect=lambda image, x, y: int(image[0, 0, 0])):
            image, accepted = farm._verify_card_use(before, farm._combo_profile.cards[0])
        self.assertTrue(accepted)
        self.assertIs(after, image)
        self.assertEqual(3, farm.adb.screenshot.call_count)


if __name__ == "__main__":
    unittest.main()
