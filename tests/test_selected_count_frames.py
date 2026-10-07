"""Real ADB crops: selected card corners must not become partial count digits."""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cocmagic import config
from cocmagic.modules.farm_module import CardSlot, ComboProfile, FarmModule
from cocmagic.troop_vision import read_card_count, count_badge_changed


FIXTURES = Path(__file__).parent / "fixtures"
SLOT = CardSlot(939, 840, "spell", "rage")


def native_frame(name):
    # Failure diagnostics retain this exact ROI from the 1600x900 ADB frame.
    crop = cv2.imread(str(FIXTURES / name))
    image = np.zeros((900, 1600, 3), np.uint8)
    image[715:890, 874:1019] = crop
    return image


class SelectedCountFrameTests(unittest.TestCase):
    def synthetic_bordered_count(self, count):
        image = np.zeros((900, 1600, 3), np.uint8)
        canvas = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        font = ImageFont.truetype(config.asset("Supercell-Magic.otf"), 22)
        ImageDraw.Draw(canvas).text((929, 745), f"x{count}", font=font, fill="white")
        image = cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)
        image[735:785, 997:1000] = 255
        return image

    def test_vertical_frame_does_not_allow_a_damaged_leading_one_to_be_dropped(self):
        image = self.synthetic_bordered_count(10)
        self.assertEqual(10, read_card_count(image, SLOT.x, SLOT.y))
        image[735:785, 948:954] = 0
        self.assertIsNone(read_card_count(image, SLOT.x, SLOT.y))

    def test_small_top_fragment_without_adjacent_frame_still_invalidates_the_count(self):
        image = self.synthetic_bordered_count(3)
        self.assertEqual(3, read_card_count(image, SLOT.x, SLOT.y))
        image[750:767, 975] = 255
        image[750:752, 976:980] = 255
        self.assertIsNone(read_card_count(image, SLOT.x, SLOT.y))

    def test_native_selected_and_unselected_counts_are_complete(self):
        samples = [("rage_native_x5_unselected.png", 5),
                   ("rage_native_x4_before.png", 4),
                   ("rage_native_x4_unselected.png", 4),
                   ("rage_native_x4_selected.png", 4),
                   ("rage_native_x3_unselected.png", 3),
                   ("rage_native_x3_selected.png", 3),
                   ("rage_native_x2_selected.png", 2)]
        for name, expected in samples:
            with self.subTest(name=name):
                self.assertEqual(expected, read_card_count(native_frame(name), SLOT.x, SLOT.y))

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_native_decreases_are_confirmed_without_recovery_captures(self, _sleep):
        for count in (5, 4, 3):
            with self.subTest(count=count):
                before = native_frame(f"rage_native_x{count}_unselected.png")
                after = native_frame(f"rage_native_x{count - 1}_selected.png")
                farm = FarmModule(Mock(), None, None, {})
                farm.adb.screenshot.return_value = after

                _, accepted = farm._verify_card_use(before, SLOT)

                self.assertTrue(accepted)
                self.assertEqual(1, farm.adb.screenshot.call_count)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_same_count_selection_changes_never_confirm_a_cast(self, _sleep):
        for count in (4, 3):
            with self.subTest(count=count):
                before = native_frame(f"rage_native_x{count}_unselected.png")
                after = native_frame(f"rage_native_x{count}_selected.png")
                farm = FarmModule(Mock(), None, None, {})
                farm.adb.screenshot.return_value = after
                self.assertFalse(count_badge_changed(before, after, SLOT.x, SLOT.y))
                _, accepted = farm._verify_card_use(before, SLOT)
                self.assertFalse(accepted)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_real_selected_count_sequence_uses_all_three_remaining_rages(self, _sleep):
        frames = [native_frame(f"rage_native_x{count}_selected.png") for count in (3, 2)]
        # Retain the native card frame, using the bundled font for x1/x0.
        for count in (1, 0):
            image = frames[0].copy()
            image[735:768, 945:991] = (105, 57, 104)
            canvas = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            font = ImageFont.truetype(config.asset("Supercell-Magic.otf"), 22)
            x = 961 if count == 1 else 950
            ImageDraw.Draw(canvas).text((x, 735), f"x{count}", font=font, fill="white")
            frames.append(cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR))
        self.assertEqual([3, 2, 1, 0], [read_card_count(f, SLOT.x, SLOT.y) for f in frames])
        farm = FarmModule(Mock(), None, None, {})
        farm.adb.screenshot.side_effect = frames
        farm.adb.tap_many.return_value = True
        farm._combo_profile = ComboProfile([SLOT], [], (900, 1600))
        farm._attack_tactics = Mock()
        farm._attack_tactics.spell_target.side_effect = lambda name, index: (700 + index * 40, 400)

        farm._deploy_spells()

        self.assertEqual(3, farm.adb.tap_many.call_count)
        self.assertEqual({}, farm._pending_spells)
        self.assertIsNone(farm.halt_reason)


if __name__ == "__main__":
    unittest.main()
