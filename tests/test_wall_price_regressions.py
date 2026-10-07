"""Replay wall price and changing button layouts without game inputs."""

from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.modules.wall_module import (
    ELIXIR_COST_REGION, GOLD_COST_REGION, WallModule,
)
from cocmagic.screen_reader import ScreenReader


FIXTURES = Path(__file__).parent / "fixtures"


def fixture_screen(name, region):
    image = np.zeros((900, 1600, 3), np.uint8)
    crop = cv2.imread(str(FIXTURES / name))
    x, y, w, h = region
    if crop is None or crop.shape[:2] != (h, w):
        raise AssertionError(f"Invalid fixture: {name}")
    image[y:y + h, x:x + w] = crop
    return image


def render_number(image, region, value, font_size=12, background=(225, 225, 215)):
    x, y, w, h = region
    crop = Image.new("RGB", (w, h), background)
    draw = ImageDraw.Draw(crop)
    font = ImageFont.truetype(config.asset("Supercell-Magic.otf"), font_size)
    draw.text((3, 3), f"{value:,}".replace(",", " "), font=font,
              fill="white", stroke_width=2, stroke_fill="#333333")
    image[y:y + h, x:x + w] = cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2BGR)


class WallPriceRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = ScreenReader(ADBController())
        cls.group = fixture_screen("wall_upgrade_group_controls.png",
                                    (250, 565, 1090, 230))
        cls.single = fixture_screen("wall_upgrade_single_controls.png",
                                     (250, 565, 1090, 230))
        cls.compact = fixture_screen("wall_upgrade_no_add10_controls.png",
                                      (250, 565, 1090, 230))
        cls.seven = fixture_screen("wall_list_seven_remaining.png",
                                    (480, 120, 680, 580))

    def make_wall(self, adb=None, stop_event=None):
        return WallModule(adb or ADBController(), self.reader,
                          {"wall_type": "gold", "wall_resource": 31_000_000},
                          stop_event=stop_event)

    def test_real_video_price_is_ten_million_for_both_resources(self):
        # The old HUD segmentation returned zero on both bright price buttons.
        for region in (GOLD_COST_REGION, ELIXIR_COST_REGION):
            self.assertEqual(0, self.reader.read_ui_number(self.group, region,
                                                         min_digits=4))
        self.assertEqual({"gold": 10_000_000, "elixir": 10_000_000},
                         self.make_wall()._read_costs(self.group))

    def test_small_and_larger_grouped_prices_are_read_completely(self):
        for size in (12, 13, 14):
            for value in (1_500_000, 10_000_000, 20_000_000, 30_000_000):
                with self.subTest(size=size, value=value):
                    image = self.group.copy()
                    render_number(image, GOLD_COST_REGION, value, size)
                    self.assertEqual(value, self.reader.read_ui_number(
                        image, GOLD_COST_REGION, min_digits=4, small_text=True))

    def test_missing_zero_cannot_lower_ten_million_quote_to_one_million(self):
        image = self.group.copy()
        image[639:658, 834:848] = 225  # Missing zero in the first "10" group.
        self.assertEqual(0, self.reader.read_ui_number(
            image, GOLD_COST_REGION, min_digits=4, small_text=True))

    def test_plain_bright_button_is_not_a_price(self):
        image = np.full((900, 1600, 3), 225, np.uint8)
        self.assertIsNone(self.make_wall()._read_costs(image))

    def test_no_add10_layout_from_video_has_valid_add_remove_and_gold_quote(self):
        wall = self.make_wall()
        _, plus, minus = wall._wait_for_group_controls(self.compact)
        self.assertEqual((622, 747), plus)
        self.assertEqual((447, 748), minus)
        self.assertEqual((863, 694), wall._upgrade_button("gold", self.compact))
        self.assertEqual({"gold": 10_000_000, "elixir": 0},
                         wall._read_costs(self.compact))

    def test_cached_controls_and_price_follow_both_layouts(self):
        wall = self.make_wall()
        for image, plus, gold in ((self.group, (711, 747), (950, 694)),
                                  (self.compact, (622, 747), (863, 694)),
                                  (self.group, (711, 747), (950, 694))):
            self.assertEqual(plus, wall._add_wall_button(image))
            self.assertEqual(gold, wall._upgrade_button("gold", image))
            self.assertEqual(10_000_000, wall._read_costs(image)["gold"])
            self.assertEqual(plus, wall._position_cache["add_wall"])

    def test_missing_gold_icon_cannot_reuse_old_button_or_wall_ring(self):
        wall = self.make_wall()
        self.assertIsNotNone(wall._add_wall_button(self.compact))
        missing = self.compact.copy()
        missing[626:763, 853:873] = 0
        self.assertIsNone(wall._upgrade_button("gold", missing))
        self.assertIsNone(wall._add_wall_button(missing))
        self.assertIsNone(wall._read_costs(missing))

    def test_listed_wall_count_is_read_and_unknown_count_is_not_guessed(self):
        wall = self.make_wall()
        row = wall._find_wall_row(self.seven)
        self.assertEqual((573, 656), row)
        self.assertEqual(7, wall._listed_wall_count(self.seven, row))
        unreadable = self.seven.copy()
        unreadable[642:670, 570:618] = 225
        self.assertIsNone(wall._listed_wall_count(unreadable, row))

    @patch("cocmagic.modules.wall_module.time.sleep")
    def test_gold_mode_waits_for_gold_quote_even_when_elixir_is_already_readable(self, _sleep):
        wall = self.make_wall()
        wall.adb.screenshot = Mock(return_value=self.group)
        image, prices = wall._wait_for_costs(self.single)
        self.assertIs(image, self.group)
        self.assertEqual(10_000_000, prices["gold"])
        wall.adb.screenshot.assert_called_once_with(use_cache=False)

    @patch("cocmagic.modules.wall_module.time.sleep")
    def test_add_wall_waits_for_fresh_updated_total(self, _sleep):
        wall = self.make_wall()
        updated = self.group.copy()
        x, y, _, h = GOLD_COST_REGION
        render_number(updated, (x, y, 125, h), 20_000_000)
        wall.adb.screenshot = Mock(side_effect=[self.group, updated])
        image, prices = wall._wait_for_costs(self.group, "gold", 20_000_000)
        self.assertIs(image, updated)
        self.assertEqual(20_000_000, prices["gold"])
        self.assertEqual(2, wall.adb.screenshot.call_count)
        self.assertTrue(all(call.kwargs == {"use_cache": False}
                            for call in wall.adb.screenshot.call_args_list))

    @patch("cocmagic.modules.wall_module.time.sleep")
    def test_unchanged_or_wrong_total_is_rejected_after_bounded_wait(self, _sleep):
        wall = self.make_wall()
        wall.adb.screenshot = Mock(return_value=self.group)
        _, prices = wall._wait_for_costs(self.group, "gold", 20_000_000)
        self.assertIsNone(prices)
        self.assertEqual(3, wall.adb.screenshot.call_count)

    def test_stop_interrupts_pending_price_update(self):
        stop = Mock()
        stop.is_set.return_value = False
        stop.wait.return_value = True
        wall = self.make_wall(stop_event=stop)
        wall.adb.screenshot = Mock()
        _, prices = wall._wait_for_costs(self.group, "gold", 20_000_000)
        self.assertIsNone(prices)
        stop.wait.assert_called_once_with(.15)
        wall.adb.screenshot.assert_not_called()

    @patch("cocmagic.modules.wall_module.time.sleep")
    def test_full_three_wall_batch_selects_adds_confirms_and_verifies_debit(self, _sleep):
        self._replay_wall_batch()

    @patch("cocmagic.modules.wall_module.time.sleep")
    def test_seven_remaining_walls_use_moved_buttons_and_upgrade_three(self, _sleep):
        self._replay_wall_batch(compact=True, listed_count=7)

    @patch("cocmagic.modules.wall_module.time.sleep")
    def test_batch_is_limited_to_two_remaining_walls(self, _sleep):
        self._replay_wall_batch(compact=True, listed_count=2)

    @patch("cocmagic.modules.wall_module.time.sleep")
    def test_last_wall_is_upgraded_without_add_or_upgrade_more(self, _sleep):
        self._replay_wall_batch(compact=True, listed_count=1)

    def _replay_wall_batch(self, compact=False, listed_count=None):
        batch_count = min(3, listed_count) if listed_count is not None else 3
        controls = self.compact if compact else self.group
        add_point = (622, 707) if compact else (711, 707)
        upgrade_point = (798, 704) if compact else (885, 704)
        row_point = (573, 656) if compact else (573, 653)
        home = fixture_screen("wall_upgrade_resource_bars.png", (1330, 0, 270, 260))
        builder = cv2.imread(str(FIXTURES / "builder_available_region.png"))
        home[0:110, 690:800] = builder
        after = home.copy()
        remaining = 31_000_000 - batch_count * 10_000_000
        render_number(after, (1330, 25, 205, 45), remaining, 22, (0, 0, 0))
        self.assertEqual(31_000_000, self.reader.read_home_resources(home)["gold"])
        self.assertEqual(remaining, self.reader.read_home_resources(after)["gold"])
        wall_list = (self.seven.copy() if compact else fixture_screen(
            "wall_list_left_visible.png", (480, 120, 680, 580)))
        if listed_count is not None and listed_count != 7:
            render_number(wall_list, (570, 642, 48, 28), listed_count, 17,
                          (30, 40, 35))
        confirm = cv2.imread(str(FIXTURES / "upgrade_walls_confirm.png"))
        dialog = np.zeros_like(home)
        h, w = confirm.shape[:2]
        x, y = (1600 - w) // 2, (900 - h) // 2
        dialog[y:y + h, x:x + w] = confirm
        group = home.copy()
        group[565:795, 250:1340] = controls[565:795, 250:1340]
        groups = {1: group}
        for count in range(2, batch_count + 1):
            groups[count] = group.copy()
            # Preserve the resource-icon templates to the right of the text.
            price_regions = ((723, 632, 125, 35),) if compact else (
                GOLD_COST_REGION, ELIXIR_COST_REGION)
            for rx, ry, _, rh in price_regions:
                render_number(groups[count], (rx, ry, 125, rh), 10_000_000 * count)

        state = {"phase": "home", "count": 1, "lag": 0}
        adb = ADBController()

        def screenshot(**kwargs):
            phase = state["phase"]
            if phase == "group":
                if state["lag"]:
                    state["lag"] -= 1
                    return self.single if state["count"] == 1 else groups[state["count"] - 1]
                return groups[state["count"]]
            single = group if listed_count == 1 else self.single
            return {"home": home, "list": wall_list, "single": single,
                    "confirm": dialog, "after": after}[phase]

        def tap(x, y, **kwargs):
            phase = state["phase"]
            if phase == "home":
                self.assertEqual((810, 52), (x, y))
                state["phase"] = "list"
            elif phase == "list":
                self.assertEqual(row_point, (x, y))
                state["phase"] = "single"
            elif phase == "single" and listed_count == 1:
                self.assertEqual(upgrade_point, (x, y))
                state["phase"] = "confirm"
            elif phase == "single":
                self.assertEqual((708, 748), (x, y))
                state.update(phase="group", lag=1)
            elif phase == "group" and (x, y) == add_point:
                state["count"] += 1
                state["lag"] = 1
            elif phase == "group":
                self.assertEqual(batch_count, state["count"])
                self.assertEqual(upgrade_point, (x, y))
                state["phase"] = "confirm"
            elif phase == "confirm":
                self.assertEqual((932, 551), (x, y))
                state["phase"] = "after"
            else:
                self.fail(f"Unexpected tap at {phase}: {(x, y)}")
            return True

        adb.screenshot = Mock(side_effect=screenshot)
        adb.tap = Mock(side_effect=tap)
        adb.swipe = Mock()
        adb.back = Mock()
        wall = self.make_wall(adb)
        if compact:
            wall.settings["wall_type"] = "both"

        self.assertTrue(wall.run())
        self.assertEqual("after", state["phase"])
        self.assertEqual(batch_count, wall.walls_upgraded)
        self.assertEqual(4 if listed_count == 1 else batch_count + 4,
                         adb.tap.call_count)
        adb.swipe.assert_not_called()
        adb.back.assert_not_called()


if __name__ == "__main__":
    unittest.main()
