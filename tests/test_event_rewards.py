"""Event rewards must interrupt battle inputs without choosing troops."""

import os
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cocmagic import config
from cocmagic.bot_engine import BotEngine
from cocmagic.event_rewards import find_reward_panel
from cocmagic.modules.farm_module import CardSlot, ComboProfile, FarmModule, FarmState, SpellProgress


class RewardVisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = cv2.imread(config.BASE_DIR + "/tests/fixtures/event_reward_panel.png")

    def with_labels(self, names):
        image = self.panel.copy()
        font = ImageFont.truetype(config.asset("Supercell-Magic.otf"), 18)
        for (x, w), name in zip(((229, 174), (437, 184), (653, 174)), names):
            canvas = Image.new("RGB", (w - 20, 42), (25, 25, 25))
            draw = ImageDraw.Draw(canvas)
            box = draw.textbbox((0, 0), name, font=font)
            draw.text(((w - 20 - box[2] + box[0]) // 2, 8), name, font=font,
                      fill=(255, 255, 225))
            image[350:392, x + 10:x + w - 10] = cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)
        return image

    def test_user_image_selects_dark_instead_of_either_troop(self):
        for size in ((1050, 591), (1600, 900), (1280, 720)):
            with self.subTest(size=size):
                panel = find_reward_panel(cv2.resize(self.panel, size))
                self.assertEqual(["dark"], [choice.resource for choice in panel.choices])
                choice = panel.preferred("gold")
                self.assertAlmostEqual(.705, choice.point[0] / size[0], delta=.003)

    def test_resources_are_recognized_in_every_column_and_priority_is_applied(self):
        for names in (("Gold", "Elixir", "Dark Elixir"), ("Dark Elixir", "Gold", "Elixir")):
            image = cv2.resize(self.with_labels(names), (1600, 900))
            panel = find_reward_panel(image)
            self.assertEqual({"dark", "gold", "elixir"}, {c.resource for c in panel.choices})
            for resource in ("gold", "elixir", "dark"):
                self.assertEqual(resource, panel.preferred(resource).resource)

    def test_troops_and_unknown_labels_are_never_resource_fallbacks(self):
        panel = find_reward_panel(self.with_labels(("Giant Skeleton", "Totem Thrower", "Mystery")))
        self.assertIsNotNone(panel)
        self.assertIsNone(panel.preferred())

    def test_missing_title_or_missing_card_prevents_selection(self):
        image = self.panel.copy()
        image[55:150, 230:820] = 0
        self.assertEqual((), find_reward_panel(image).choices)
        image = self.panel.copy()
        image[170:450, 650:835] = 0
        self.assertEqual((), find_reward_panel(image).choices)

    def test_ordinary_battle_and_other_dialogs_are_not_reward_panels(self):
        for name in ("battle_screen.png", "end_battle_confirm.png", "connection_lost.png"):
            image = cv2.imread(os.path.join(config.BASE_DIR, "tests", "fixtures", name))
            self.assertIsNone(find_reward_panel(image))


class RewardInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = cv2.resize(cv2.imread(config.BASE_DIR + "/tests/fixtures/event_reward_panel.png"),
                               (1600, 900))
        cls.battle = cv2.imread(config.BASE_DIR + "/tests/fixtures/battle_screen.png")
        cls.reward = find_reward_panel(cls.panel).preferred().point

    def make_farm(self, state=FarmState.ATTACKING):
        adb = Mock()
        adb.tap.return_value = True
        farm = FarmModule(adb, None, Mock(), {"event_mode": True})
        farm.state = state
        return farm

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_popup_mid_batch_is_resolved_then_original_card_is_selected_again(self, _sleep):
        farm = self.make_farm()
        card, first, second = (179, 840), (250, 650), (350, 650)
        ui = {"modal": False, "selected": None, "drops": []}

        def tap(x, y, **kwargs):
            point = (x, y)
            if ui["modal"]:
                self.assertEqual(self.reward, point)
                ui.update(modal=False, selected=None)
            elif point == card:
                ui["selected"] = card
            else:
                self.assertEqual(card, ui["selected"])
                ui["drops"].append(point)
                if point == first:
                    ui["modal"] = True
            return True

        farm.adb.tap.side_effect = tap
        farm.adb.screenshot.side_effect = lambda **kw: self.panel if ui["modal"] else self.battle
        farm._handle_state = lambda: farm._battle_tap_many([card, first, second],
                                                          interval=.04, select_first=True)
        profile = ComboProfile([CardSlot(*card, "troop")], [], (900, 1600))
        farm._combo_profile = profile
        self.assertTrue(farm.tick())
        self.assertEqual([first, second], ui["drops"])
        self.assertEqual([card, first, self.reward, card, second],
                         [call.args[:2] for call in farm.adb.tap.call_args_list])
        self.assertIs(profile, farm._combo_profile)
        farm.adb.tap_many.assert_not_called()

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_all_three_threshold_panels_are_handled_while_waiting_and_at_result(self, _sleep):
        farm = self.make_farm(FarmState.BATTLE_WAIT)
        farm.adb.screenshot.side_effect = [self.panel, self.battle, self.battle] * 3
        farm._selected_battle_card = (179, 840)
        for state in (FarmState.BATTLE_WAIT, FarmState.BATTLE_WAIT, FarmState.RESULT):
            farm.state = state
            self.assertIs(self.battle, farm._screenshot())
        self.assertEqual(3, farm.adb.tap.call_count)
        self.assertTrue(all(call.args == self.reward for call in farm.adb.tap.call_args_list))

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_reward_mid_spell_sequence_preserves_count_verification_and_remaining_cast(self, _sleep):
        farm = self.make_farm()
        spell = (811, 840)
        ui = {"remaining": 2, "modal": False, "selected": None, "casts": []}

        def frame(**kwargs):
            if ui["modal"]:
                return self.panel
            image = self.battle.copy()
            image[0, 0, 0] = ui["remaining"]
            return image

        def tap(x, y, **kwargs):
            point = (x, y)
            if ui["modal"]:
                self.assertEqual(self.reward, point)
                ui.update(modal=False, selected=None)
            elif point == spell:
                ui["selected"] = spell
            else:
                self.assertEqual(spell, ui["selected"])
                ui["casts"].append(point)
                ui["remaining"] -= 1
                ui["modal"] = ui["remaining"] == 1
            return True

        farm.adb.tap.side_effect = tap
        farm.adb.screenshot.side_effect = frame
        farm._combo_profile = ComboProfile([CardSlot(*spell, "spell", "rage")], [], (900, 1600))
        farm._attack_tactics = Mock()
        farm._attack_tactics.spell_target.side_effect = lambda name, index: (700 + index * 40, 400)
        farm._card_depleted = lambda image, slot: image[0, 0, 0] == 0
        with patch("cocmagic.modules.farm_module.read_card_count",
                   side_effect=lambda image, x, y: int(image[0, 0, 0])):
            farm._deploy_spells()
        self.assertEqual([(700, 400), (740, 400)], ui["casts"])
        self.assertEqual(0, ui["remaining"])
        self.assertIsNone(farm.halt_reason)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_bonus_during_battle_wait_spell_recovery_restores_selection_and_finishes_rage(self, _sleep):
        farm = self.make_farm(state=FarmState.BATTLE_WAIT)
        slot = CardSlot(811, 840, "spell", "rage")
        ui = {"remaining": 2, "modal": False, "selected": None, "casts": []}

        def frame(**kwargs):
            if ui["modal"]:
                return self.panel
            image = self.battle.copy()
            image[0, 0, 0] = ui["remaining"]
            return image

        def tap(x, y, **kwargs):
            point = (x, y)
            if ui["modal"]:
                self.assertEqual(self.reward, point)
                ui.update(modal=False, selected=None)
            elif point == (slot.x, slot.y):
                ui["selected"] = point
            else:
                self.assertEqual((slot.x, slot.y), ui["selected"])
                ui["casts"].append(point)
                ui["remaining"] -= 1
                ui["modal"] = ui["remaining"] == 1
            return True

        farm.adb.tap.side_effect = tap
        farm.adb.screenshot.side_effect = frame
        farm._combo_profile = ComboProfile([slot], [], (900, 1600))
        farm._attack_tactics = Mock()
        farm._attack_tactics.spell_target.side_effect = lambda name, index: (700 + index * 40, 400)
        farm._card_depleted = lambda image, card: image[0, 0, 0] == 0
        farm._pending_spells[slot] = SpellProgress(cast_index=2)
        with patch("cocmagic.modules.farm_module.read_card_count",
                   side_effect=lambda image, x, y: int(image[0, 0, 0])):
            farm._resume_pending_spells(frame())

        self.assertEqual([(780, 400), (820, 400)], ui["casts"])
        self.assertEqual(0, ui["remaining"])
        self.assertEqual(FarmState.BATTLE_WAIT, farm.state)
        self.assertEqual({}, farm._pending_spells)
        self.assertEqual(1, farm._reward_generation)
        self.assertIsNone(farm.halt_reason)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_unknown_bonus_stops_tick_without_dropping_troops_or_going_home(self, _sleep):
        farm = self.make_farm()
        unknown = self.panel.copy()
        unknown[530:600, 1010:1245] = 0
        self.assertIsNone(find_reward_panel(unknown).preferred())
        farm.adb.screenshot.return_value = unknown
        farm._go_home_safe = Mock()
        farm._handle_state = lambda: farm._battle_tap_many([(250, 650)], interval=.04)
        self.assertFalse(farm.tick())
        self.assertIn("tránh chọn lính", farm.halt_reason)
        farm.adb.tap.assert_not_called()
        farm.adb.tap_many.assert_not_called()
        farm._go_home_safe.assert_not_called()

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_undismissed_panel_does_not_receive_deployment_taps(self, _sleep):
        farm = self.make_farm()
        farm.adb.screenshot.return_value = self.panel
        farm._handle_state = lambda: farm._battle_tap(250, 650)
        self.assertFalse(farm.tick())
        farm.adb.tap.assert_called_once_with(*self.reward, jitter=0, delay=.15)
        self.assertIn("chưa đóng", farm.halt_reason)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_network_recovery_interrupts_reward_confirmation(self, _sleep):
        farm = self.make_farm()
        dialog = cv2.imread(config.BASE_DIR + "/tests/fixtures/connection_lost.png")
        farm.adb.screenshot.side_effect = [self.panel, dialog]
        farm.recovery_handler = lambda image: image is dialog
        farm._selected_battle_card = (179, 840)
        farm._handle_state = lambda: farm._battle_tap(250, 650)
        self.assertTrue(farm.tick())
        farm.adb.tap.assert_called_once_with(*self.reward, jitter=0, delay=.15)

    def test_default_mode_preserves_batching_and_does_not_scan_rewards(self):
        farm = self.make_farm()
        farm.settings["event_mode"] = False
        farm.adb.screenshot.return_value = self.panel
        with patch("cocmagic.modules.farm_module.find_reward_panel") as finder:
            self.assertIs(self.panel, farm._screenshot())
            farm._battle_tap_many([(179, 840), (250, 650)], interval=.04)
        finder.assert_not_called()
        farm.adb.tap.assert_not_called()
        farm.adb.tap_many.assert_called_once_with([(179, 840), (250, 650)], interval=.04)

    def test_engine_does_not_treat_reward_panel_as_inactivity(self):
        engine = BotEngine({"event_mode": True})
        engine.adb = Mock()
        engine.adb.screenshot.return_value = self.panel
        engine._handle_connection_lost = Mock(return_value=False)
        engine._detect_inactivity_popup = Mock(return_value=True)
        self.assertFalse(engine._handle_popups())
        engine._detect_inactivity_popup.assert_not_called()
        engine.adb.tap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
