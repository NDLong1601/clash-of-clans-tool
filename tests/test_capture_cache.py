"""Capture format, stale-frame prevention, and relocated template detection."""

import os
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from cocmagic.adb_controller import ADBController


def raw_frame(bgr, modern=True):
    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA)
    header = struct.pack("<3I", bgr.shape[1], bgr.shape[0], 1)
    return header + (struct.pack("<I", 1) if modern else b"") + rgba.tobytes()


class CaptureCacheTests(unittest.TestCase):
    def test_raw_capture_preserves_colors_with_both_header_versions(self):
        image = np.array([[[10, 20, 30], [100, 80, 45]],
                          [[220, 50, 80], [0, 255, 190]]], np.uint8)
        for modern in (True, False):
            with self.subTest(modern=modern):
                np.testing.assert_array_equal(image, ADBController._decode_raw_screenshot(
                    raw_frame(image, modern)))

    def test_truncated_and_unsupported_raw_formats_are_rejected(self):
        self.assertIsNone(ADBController._decode_raw_screenshot(b""))
        self.assertIsNone(ADBController._decode_raw_screenshot(struct.pack("<3I", 1600, 900, 1)))
        self.assertIsNone(ADBController._decode_raw_screenshot(struct.pack("<3I", 2, 2, 4) + b"x" * 16))

    @patch("cocmagic.adb_controller.run_hidden")
    def test_input_invalidates_a_cached_frame_before_the_next_capture(self, run):
        captures = []

        def execute(command, **kwargs):
            if "screencap" in command:
                captures.append(len(captures) + 1)
                return Mock(returncode=0, stdout=raw_frame(np.full((4, 5, 3), captures[-1], np.uint8)))
            return Mock(returncode=0, stdout=b"", stderr=b"")

        run.side_effect = execute
        adb = ADBController(settings={})
        first = adb.screenshot()
        self.assertIs(first, adb.screenshot())
        self.assertTrue(adb.tap(5, 5, delay=0))
        second = adb.screenshot()
        self.assertEqual(2, int(second[0, 0, 0]))
        self.assertTrue(adb.tap_many([(5, 5)], interval=0))
        third = adb.screenshot()
        self.assertEqual(3, int(third[0, 0, 0]))
        self.assertEqual(3, len(captures))

    @patch("cocmagic.adb_controller.run_hidden")
    def test_unsupported_raw_capture_falls_back_to_png(self, run):
        image = np.full((4, 5, 3), (20, 100, 230), np.uint8)
        png = cv2.imencode(".png", image)[1].tobytes()
        run.side_effect = [Mock(returncode=0, stdout=b"unsupported"),
                           Mock(returncode=0, stdout=png), Mock(returncode=0, stdout=png)]
        adb = ADBController(settings={})
        np.testing.assert_array_equal(image, adb.screenshot())
        np.testing.assert_array_equal(image, adb.screenshot(use_cache=False))
        self.assertEqual(3, run.call_count)

    def test_learned_template_position_is_relocated_on_a_changed_screen(self):
        rng = np.random.default_rng(42)
        template = rng.integers(0, 255, (15, 20, 3), np.uint8)
        first = np.zeros((120, 200, 3), np.uint8)
        second = first.copy()
        first[20:35, 30:50] = template
        second[70:85, 140:160] = template
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "button.png")
            cv2.imwrite(path, template)
            adb = ADBController(settings={})
            self.assertEqual((40, 27), adb.find_template(path, .99, first))
            self.assertEqual((150, 77), adb.find_template(path, .99, second))


if __name__ == "__main__":
    unittest.main()
