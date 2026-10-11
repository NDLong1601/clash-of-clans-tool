import json
from pathlib import Path
import unittest

import cv2
import numpy as np

from cocmagic import config
from cocmagic.builder_screen_reader import (
    BonusProgressOCR,
    BuilderScreenReader,
    Capture,
    ScreenKind,
    StarBonusReader,
    StarBonusState,
    Village,
)


FIXTURES = Path(config.BASE_DIR) / "tests/fixtures/dual_village/navigation"


def frame(name):
    path = FIXTURES / (name + ".jpg")
    if not path.exists():
        path = FIXTURES / (name + ".png")
    image = cv2.imread(str(path))
    if image is None:
        raise AssertionError(str(path))
    return image


class ScreenEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = BuilderScreenReader()

    def test_all_declared_image_states(self):
        manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["fixtures"]:
            with self.subTest(entry=entry["id"]):
                result = self.reader.classify(frame(entry["id"]))
                expected = entry["expected"]
                if expected == "available":
                    self.assertEqual(ScreenKind.BUILDER_HOME, result.kind)
                elif expected == "claimable":
                    self.assertEqual(
                        (ScreenKind.MODAL, "star_reward", Village.BUILDER),
                        (result.kind, result.panel, result.village),
                    )
                    self.assertIn("claim", result.points)
                else:
                    self.assertEqual(expected.split("/")[0], result.kind.value)
                    if "/" in expected:
                        self.assertEqual(expected.split("/")[1], result.panel)

    def test_missing_or_uncalibrated_or_blank_images(self):
        for image in (
            None,
            np.zeros((900, 1600, 3), np.uint8),
            frame("builder-home-b")[::2, ::2],
        ):
            self.assertEqual(ScreenKind.UNKNOWN, self.reader.classify(image).kind)

    def test_dark_background_and_shared_buttons_do_not_establish_builder(self):
        image = frame("main-home")
        image[115:700, 190:1400] //= 3
        self.assertNotEqual(ScreenKind.BUILDER_HOME, self.reader.classify(image).kind)
        image = frame("builder-home-b")
        image[:110, 780:1010] = 0  # Builder-specific portrait absent.
        self.assertEqual(ScreenKind.UNKNOWN, self.reader.classify(image).kind)

    def test_unknown_modal_blocks_home_without_authorizing_any_tap(self):
        image = frame("builder-home-b")
        image[180:625, 350:1250] = 170
        screen = self.reader.classify(image)
        self.assertEqual(ScreenKind.MODAL, screen.kind)
        self.assertFalse(screen.points)

    def test_main_reward_cannot_be_claimable_builder_reward(self):
        image = frame("reward")
        main = frame("main-home")
        image[:115] = (main[:115] * 0.45).astype(np.uint8)
        image[715:880, :200] = (main[715:880, :200] * 0.45).astype(np.uint8)
        observation = StarBonusReader(self.reader).observe(Capture(image, 1, 1.0, 0))
        self.assertEqual(StarBonusState.UNKNOWN, observation.state)

    def test_reward_button_occluded_never_claimable(self):
        image = frame("reward")
        image[620:710, 680:920] = 0
        screen = self.reader.classify(image)
        self.assertEqual("star_reward", screen.panel)
        self.assertNotIn("claim", screen.points)
        self.assertEqual(
            StarBonusState.UNKNOWN,
            StarBonusReader(self.reader).observe(Capture(image, 1, 1.0, 0)).state,
        )

    def test_cart_buttons_require_distinct_color_states(self):
        empty = self.reader.classify(frame("cart-empty-b"))
        enabled = self.reader.classify(frame("cart-collectable"))
        self.assertIn("cart_disabled", empty.points)
        self.assertNotIn("cart_collect", empty.points)
        self.assertIn("cart_collect", enabled.points)
        self.assertNotIn("cart_disabled", enabled.points)

    def test_camera_guard_refuses_every_non_home_fixture(self):
        for name in (
            "builder-menu",
            "main-menu",
            "cart-empty-a",
            "cart-defending",
            "reward",
            "battle",
            "result",
            "loading",
            "button-covered",
        ):
            with self.subTest(name=name):
                self.assertFalse(
                    self.reader.home_is_clear(frame(name), Village.BUILDER)
                )

    def test_main_home_with_changed_attack_artwork_uses_label_and_independent_hud(self):
        path = FIXTURES.parent / "acceptance/main-home-attack-stars.png"
        image = cv2.imread(str(path))
        self.assertIsNotNone(image)
        self.assertIsNone(self.reader.match("main_attack", image))
        self.assertIsNone(self.reader.match("main_attack_current", image))
        result = self.reader.classify(image)
        self.assertEqual(
            (ScreenKind.MAIN_HOME, Village.MAIN), (result.kind, result.village)
        )
        self.assertEqual(
            self.reader.match("home_attack_label", image), result.points["attack"]
        )
        self.assertTrue(self.reader.home_is_clear(image, Village.MAIN))
        self.assertFalse(self.reader.home_is_clear(image, Village.BUILDER))

    def test_main_attack_label_cannot_replace_missing_home_hud(self):
        image = cv2.imread(
            str(FIXTURES.parent / "acceptance/main-home-attack-stars.png")
        )
        for x, y, w, h in (
            (660, 0, 230, 115),
            (0, 300, 140, 190),
            (1440, 585, 160, 150),
            (22, 15, 86, 18),
            (15, 735, 180, 147),
        ):
            with self.subTest(region=(x, y, w, h)):
                hidden = image.copy()
                hidden[y : y + h, x : x + w] = 0
                self.assertEqual(ScreenKind.UNKNOWN, self.reader.classify(hidden).kind)
                self.assertFalse(self.reader.home_is_clear(hidden, Village.MAIN))

    def test_changed_main_attack_artwork_does_not_bypass_modal_or_prove_builder_bonus(
        self,
    ):
        image = cv2.imread(
            str(FIXTURES.parent / "acceptance/main-home-attack-stars.png")
        )
        modal = image.copy()
        modal[180:625, 350:1250] = 170
        self.assertEqual(ScreenKind.MODAL, self.reader.classify(modal).kind)
        self.assertFalse(self.reader.home_is_clear(modal, Village.MAIN))
        bonus = StarBonusReader(self.reader)
        for sequence in (1, 2):
            self.assertEqual(
                StarBonusState.UNKNOWN,
                bonus.observe(Capture(image.copy(), sequence, sequence * 0.3, 0)).state,
            )


class StarBonusEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.reader = BuilderScreenReader()
        self.bonus = StarBonusReader(self.reader)

    def observe_pair(self, names=("builder-home-a", "builder-home-b"), *, ocr=None):
        self.bonus.progress_ocr = ocr
        first = self.bonus.observe(Capture(frame(names[0]), 1, 1.0, 0))
        second = self.bonus.observe(Capture(frame(names[1]), 2, 1.3, 0))
        return first, second

    def test_complete_requires_two_independent_native_captures(self):
        first, second = self.observe_pair()
        self.assertEqual(StarBonusState.UNKNOWN, first.state)
        self.assertEqual(StarBonusState.COMPLETE, second.state)
        self.assertEqual((1, 2), second.captures)

    def test_native_builder_zero_progress_is_available(self):
        image = cv2.imread(
            str(FIXTURES.parent / "acceptance/builder-home-bonus-zero-native.png")
        )
        self.assertEqual(ScreenKind.BUILDER_HOME, self.reader.classify(image).kind)
        self.assertIsNotNone(self.reader.match("bonus_star_native", image))
        self.assertTrue(self.reader.home_is_clear(image, Village.BUILDER))
        self.bonus.observe(Capture(image.copy(), 1, 1.0, 0))
        result = self.bonus.observe(Capture(image.copy(), 2, 1.3, 0))
        self.assertEqual(StarBonusState.AVAILABLE, result.state)
        self.assertIn(result.progress, (None, (0, 8)))

    def test_native_bonus_occlusion_never_becomes_complete(self):
        image = cv2.imread(
            str(FIXTURES.parent / "acceptance/builder-home-bonus-zero-native.png")
        )
        image[690:767, 20:195] = 0
        self.assertEqual(ScreenKind.BUILDER_HOME, self.reader.classify(image).kind)
        for sequence in (1, 2):
            result = self.bonus.observe(
                Capture(image.copy(), sequence, sequence * 0.3, 0)
            )
            self.assertEqual(StarBonusState.UNKNOWN, result.state)

    def test_zero_and_variable_denominator_only_supplement_visible_star(self):
        for text, progress in (
            ("0/7", (0, 7)),
            ("4/8", (4, 8)),
            ("0/13", (0, 13)),
            ("8/8", (8, 8)),
        ):
            with self.subTest(text=text):
                self.bonus.reset()
                _, second = self.observe_pair(
                    ("bonus-available", "bonus-available"), ocr=lambda im: text
                )
                self.assertEqual(StarBonusState.AVAILABLE, second.state)
                self.assertEqual(progress, second.progress)

    def test_ocr_cannot_prove_absence_and_conflicting_progress_is_unknown(self):
        _, second = self.observe_pair(ocr=lambda im: "0/7")
        self.assertEqual(StarBonusState.UNKNOWN, second.state)
        self.bonus.reset()
        _, second = self.observe_pair(
            ("bonus-available", "bonus-available"), ocr=lambda im: "9/8"
        )
        self.assertEqual(StarBonusState.UNKNOWN, second.state)

    def test_failed_optional_ocr_does_not_hide_visible_stars(self):
        def failure(im):
            raise RuntimeError("bad OCR")

        _, second = self.observe_pair(
            ("bonus-available", "bonus-available"), ocr=failure
        )
        self.assertEqual(StarBonusState.AVAILABLE, second.state)
        self.assertIsNone(second.progress)

    def test_repeated_capture_object_sequence_and_too_short_interval_rejected(self):
        for case in ("object", "id", "time", "revision"):
            with self.subTest(case=case):
                self.bonus.reset()
                image = frame("builder-home-b")
                self.bonus.observe(Capture(image, 1, 1.0, 0))
                c = Capture(
                    image if case == "object" else image.copy(),
                    1 if case == "id" else 2,
                    1.05 if case == "time" else 1.3,
                    1 if case == "revision" else 0,
                )
                self.assertEqual(StarBonusState.UNKNOWN, self.bonus.observe(c).state)

    def test_no_result_main_loading_modal_menu_or_cover_can_be_complete(self):
        for name in (
            "result",
            "battle",
            "main-home",
            "loading",
            "builder-menu",
            "cart-empty-a",
            "button-covered",
        ):
            with self.subTest(name=name):
                self.bonus.reset()
                _, second = self.observe_pair((name, name))
                self.assertEqual(StarBonusState.UNKNOWN, second.state)

    def test_missing_frame_interrupts_the_pair(self):
        self.bonus.observe(Capture(frame("builder-home-a"), 1, 1.0, 0))
        self.assertEqual(
            StarBonusState.UNKNOWN, self.bonus.observe(Capture(None, 2, 1.3, 0)).state
        )
        self.assertEqual(
            StarBonusState.UNKNOWN,
            self.bonus.observe(Capture(frame("builder-home-b"), 3, 1.6, 0)).state,
        )

    def test_map_move_and_flying_effects_interrupt_negative_evidence(self):
        _, second = self.observe_pair(("builder-home-b", "builder-offset"))
        self.assertEqual(StarBonusState.UNKNOWN, second.state)
        self.bonus.reset()
        image = frame("builder-home-b")
        image[693:714, 40:130] = 255
        for i in range(2):
            self.assertEqual(
                StarBonusState.UNKNOWN,
                self.bonus.observe(Capture(image.copy(), i + 1, 1 + i * 0.3, 0)).state,
            )

    def test_star_region_covered_with_attack_still_visible_is_unknown(self):
        for color in (0, 80):
            with self.subTest(color=color):
                self.bonus.reset()
                image = frame("builder-home-b")
                image[690:715, 20:195] = color
                self.assertEqual(
                    ScreenKind.BUILDER_HOME, self.reader.classify(image).kind
                )
                for i in range(2):
                    self.assertEqual(
                        StarBonusState.UNKNOWN,
                        self.bonus.observe(
                            Capture(image.copy(), i + 1, 1 + i * 0.3, 0)
                        ).state,
                    )

    def test_star_disappearance_needs_its_own_new_pair(self):
        self.bonus.observe(Capture(frame("bonus-available"), 1, 1.0, 0))
        self.assertEqual(
            StarBonusState.UNKNOWN,
            self.bonus.observe(Capture(frame("builder-home-a"), 2, 1.3, 0)).state,
        )
        self.assertEqual(
            StarBonusState.COMPLETE,
            self.bonus.observe(Capture(frame("builder-home-b"), 3, 1.6, 0)).state,
        )


class SupplementaryOCRTests(unittest.TestCase):
    def test_generated_font_counter_and_uncertain_input(self):
        from PIL import Image, ImageDraw, ImageFont

        ocr = BonusProgressOCR()
        font = ImageFont.truetype(config.asset("Supercell-Magic.otf"), 24)
        for text in ("0/7", "4/8", "0/13"):
            with self.subTest(text=text):
                image = Image.new("RGB", (175, 70), (40, 80, 120))
                ImageDraw.Draw(image).text((45, 0), text, font=font, fill="white")
                self.assertEqual(
                    text, ocr(cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR))
                )
        self.assertIsNone(ocr(np.zeros((70, 175, 3), np.uint8)))
        self.assertIsNone(ocr(None))


if __name__ == "__main__":
    unittest.main()
