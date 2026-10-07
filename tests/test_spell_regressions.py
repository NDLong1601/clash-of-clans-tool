"""Spell selection must survive hero abilities and delayed counter redraws."""

import os
import struct
import time
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.modules.farm_module import CardSlot, ComboProfile, FarmModule, FarmState
from cocmagic.troop_vision import read_card_count


class SpellRegressionTests(unittest.TestCase):
    def make_recovery_farm(self):
        slot = CardSlot(939, 840, "spell", "rage")
        ui = {"remaining": 5, "casts": [], "attempts": [], "unreadable": False,
              "unreadable_frames": 0, "on_input": lambda: None}

        def frame(**kwargs):
            image = np.zeros((900, 1600, 3), np.uint8)
            readable = not ui["unreadable"] and ui["unreadable_frames"] == 0
            image[0, 0] = (ui["remaining"], int(readable), 0)
            ui["unreadable_frames"] = max(0, ui["unreadable_frames"] - 1)
            return image

        def inputs(points, **kwargs):
            self.assertEqual((slot.x, slot.y), points[0])
            ui["attempts"].append(points[1])
            ui["on_input"]()
            return True

        def consume():
            ui["remaining"] -= 1
            ui["casts"].append(ui["attempts"][-1])

        ui["on_input"] = consume
        adb = Mock()
        adb.screenshot.side_effect = frame
        adb.is_visible.return_value = False
        adb.find_template.return_value = None
        farm = FarmModule(adb, None, None, {})
        farm.state = FarmState.ATTACKING
        farm.battle_start_ts = time.time()
        farm._combo_profile = ComboProfile([slot], [], (900, 1600))
        farm._attack_tactics = Mock()
        farm._attack_tactics.spell_target.side_effect = lambda name, index: (700 + index * 40, 400)
        farm._read_card_count = lambda image, x, y: int(image[0, 0, 0]) if image[0, 0, 1] else None
        farm._card_depleted = lambda image, card: image[0, 0, 0] == 0
        farm._count_display_changed = lambda a, b, card: bool(
            a[0, 0, 1] and b[0, 0, 1] and a[0, 0, 0] != b[0, 0, 0])
        farm._battle_tap_many = Mock(side_effect=inputs)
        farm._maybe_activate_hero_abilities = Mock()
        farm._guard_battle_frame = Mock()
        farm._is_home_screen = Mock(return_value=False)
        farm._is_result_screen = Mock(return_value=False)
        farm._log_spell_verification_failure = Mock()
        return farm, slot, ui, consume, frame

    def video_frame(self, name):
        image = np.zeros((900, 1600, 3), np.uint8)
        image[720:900] = cv2.imread(os.path.join(config.BASE_DIR, "tests", "fixtures", name))
        return image

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_video_selection_redraw_with_four_rages_is_not_spell_consumption(self, _sleep):
        selected = self.video_frame("rage_after_cast_bar.png")
        unselected = self.video_frame("rage_after_abilities_bar.png")
        self.assertEqual(4, read_card_count(selected, 1060, 840))
        self.assertEqual(4, read_card_count(unselected, 1060, 840))
        adb = Mock()
        adb.screenshot.return_value = unselected
        farm = FarmModule(adb, None, None, {})

        _, accepted = farm._verify_card_use(selected, CardSlot(1060, 840, "spell", "rage"))

        self.assertFalse(accepted)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_video_first_rage_cast_is_confirmed_when_numeric_ocr_is_uncertain(self, _sleep):
        before = self.video_frame("rage_before_cast_bar.png")
        after = self.video_frame("rage_after_cast_bar.png")
        adb = Mock()
        adb.screenshot.return_value = after
        farm = FarmModule(adb, None, None, {})

        self.assertEqual(5, read_card_count(before, 1060, 840))
        with patch("cocmagic.modules.farm_module.read_card_count", return_value=None):
            _, accepted = farm._verify_card_use(before, CardSlot(1060, 840, "spell", "rage"))

        self.assertTrue(accepted)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_uncertain_ocr_does_not_accept_same_count_after_selection_redraw(self, _sleep):
        selected = self.video_frame("rage_after_cast_bar.png")
        unselected = self.video_frame("rage_after_abilities_bar.png")
        adb = Mock()
        adb.screenshot.return_value = unselected
        farm = FarmModule(adb, None, None, {})
        with patch("cocmagic.modules.farm_module.read_card_count", return_value=None):
            _, accepted = farm._verify_card_use(selected, CardSlot(1060, 840, "spell", "rage"))
        self.assertFalse(accepted)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_all_five_rages_are_used_when_hero_abilities_switch_the_selected_card(self, _sleep):
        for readable in (True, False):
            with self.subTest(readable=readable):
                spell = (1060, 840)
                hero_slots = {"king": (550, 840), "queen": (670, 840),
                              "warden": (790, 840), "royal_champ": (910, 840)}
                ability_points = {(x, y - 50) for x, y in hero_slots.values()}
                ui = {"remaining": 5, "selected": "hero", "casts": [], "ability_batches": 0}

                def frame(**kwargs):
                    image = np.zeros((900, 1600, 3), np.uint8)
                    image[0, 0, 0] = ui["remaining"]
                    return image

                def inputs(points, **kwargs):
                    if len(points) == len(hero_slots) and set(points) == ability_points:
                        ui["ability_batches"] += 1
                    for point in points:
                        if point == spell:
                            ui["selected"] = "rage"
                        elif point in ability_points:
                            ui["selected"] = "hero"
                        elif ui["selected"] == "rage" and ui["remaining"]:
                            ui["remaining"] -= 1
                            ui["casts"].append(point)
                    return True

                adb = Mock()
                adb.screenshot.side_effect = frame
                adb.tap.side_effect = lambda x, y, **kw: inputs([(x, y)])
                adb.tap_many.side_effect = inputs
                heroes = Mock()
                heroes.warden_health_fraction.return_value = .2
                farm = FarmModule(adb, None, heroes, {"warden_ability_delay": 10})
                farm._combo_profile = ComboProfile([CardSlot(*spell, "spell", "rage")], [], (900, 1600))
                farm._attack_tactics = Mock()
                farm._attack_tactics.spell_target.side_effect = lambda _name, index: (700 + index * 40, 400)
                farm._deployed_hero_slots = hero_slots.copy()
                farm._warden_slot = hero_slots["warden"]
                farm._warden_deployed_ts = 100.0
                farm._card_depleted = lambda image, _slot: image[0, 0, 0] == 0
                farm._count_display_changed = lambda before, after, _slot: before[0, 0, 0] != after[0, 0, 0]
                count = lambda image, _x, _y: int(image[0, 0, 0]) if readable else None

                with patch("cocmagic.modules.farm_module.read_card_count", side_effect=count), \
                        patch("cocmagic.modules.farm_module.time.time", return_value=103.0):
                    farm._deploy_spells()

                self.assertEqual(0, ui["remaining"])
                self.assertEqual(5, len(ui["casts"]))
                self.assertEqual(5, len(set(ui["casts"])))
                self.assertEqual(1, ui["ability_batches"])
                self.assertIsNone(farm.halt_reason)

    @patch("cocmagic.modules.farm_module.time.sleep")
    @patch("cocmagic.adb_controller.run_hidden")
    def test_delayed_count_change_is_read_from_a_new_frame_even_inside_cache_ttl(self, run, _sleep):
        def raw(count):
            pixels = np.full((4, 5, 4), count, np.uint8)
            return struct.pack("<4I", 5, 4, 1, 1) + pixels.tobytes()

        run.side_effect = [Mock(returncode=0, stdout=raw(5)),
                           Mock(returncode=0, stdout=raw(5)), Mock(returncode=0, stdout=raw(4))]
        adb = ADBController(settings={})
        before = adb.screenshot()
        farm = FarmModule(adb, None, None, {})
        farm._card_depleted = Mock(return_value=False)
        with patch("cocmagic.modules.farm_module.read_card_count",
                   side_effect=lambda image, _x, _y: int(image[0, 0, 0])):
            after, accepted = farm._verify_card_use(before, CardSlot(1060, 840, "spell", "rage"))

        self.assertTrue(accepted)
        self.assertEqual(4, int(after[0, 0, 0]))

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_second_rage_with_three_unreadable_checks_is_reconciled_without_an_extra_cast(self, _sleep):
        farm, slot, ui, consume, _ = self.make_recovery_farm()

        def inputs():
            consume()
            if ui["remaining"] == 3:
                ui["unreadable_frames"] = 3

        ui["on_input"] = inputs
        farm._deploy_spells()

        self.assertEqual(0, ui["remaining"])
        self.assertEqual([(700 + index * 40, 400) for index in range(5)], ui["attempts"])
        self.assertEqual(ui["casts"], ui["attempts"])
        self.assertEqual({}, farm._pending_spells)
        farm._log_spell_verification_failure.assert_called_once()

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_rejected_second_rage_retries_the_same_target_after_confirming_unchanged_count(self, _sleep):
        farm, slot, ui, consume, _ = self.make_recovery_farm()
        ui["on_input"] = lambda: None if len(ui["attempts"]) == 2 else consume()

        farm._deploy_spells()

        self.assertEqual(0, ui["remaining"])
        self.assertEqual([(700, 400), (740, 400), (740, 400), (780, 400),
                          (820, 400), (860, 400)], ui["attempts"])
        self.assertEqual(5, len(ui["casts"]))

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_three_remaining_rages_resume_in_battle_wait_after_ocr_recovers(self, _sleep):
        farm, slot, ui, consume, _ = self.make_recovery_farm()

        def inputs():
            consume()
            if ui["remaining"] == 3:
                ui["unreadable"] = True

        ui["on_input"] = inputs
        farm._deploy_spells()
        self.assertEqual(3, ui["remaining"])
        self.assertEqual(2, len(ui["attempts"]))
        self.assertIsNotNone(farm._pending_spells[slot].unconfirmed_before)

        # The cooldown must not start another batch or surrender early.
        farm.state = FarmState.BATTLE_WAIT
        farm._pending_spells[slot].retry_at = float("inf")
        farm._state_battle_wait()
        self.assertEqual(2, len(ui["attempts"]))
        ui["unreadable"] = False
        farm._pending_spells[slot].retry_at = 0
        farm._state_battle_wait()

        self.assertEqual(0, ui["remaining"])
        self.assertEqual([(700 + index * 40, 400) for index in range(5)], ui["attempts"])
        self.assertEqual(FarmState.BATTLE_WAIT, farm.state)
        self.assertEqual({}, farm._pending_spells)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_deferred_rage_survives_freeze_cast_and_resumes_from_the_correct_index(self, _sleep):
        farm, slot, ui, consume, frame = self.make_recovery_farm()
        freeze = CardSlot(1061, 840, "spell", "freeze")
        farm._combo_profile.cards.append(freeze)
        ui["freeze"] = 1

        def multi_frame(**kwargs):
            image = frame(**kwargs)
            image[0, 1, 0] = ui["freeze"]
            return image

        def inputs(points, **kwargs):
            if points[0] == (freeze.x, freeze.y):
                ui["freeze"] -= 1
            else:
                ui["attempts"].append(points[1])
                consume()
                if ui["remaining"] == 3:
                    ui["unreadable"] = True
            return True

        farm.adb.screenshot.side_effect = multi_frame
        farm._battle_tap_many.side_effect = inputs
        farm._read_card_count = lambda image, x, y: (
            int(image[0, 1, 0]) if x == freeze.x else
            int(image[0, 0, 0]) if image[0, 0, 1] else None)
        farm._card_depleted = lambda image, card: image[0, int(card == freeze), 0] == 0

        farm._deploy_spells()
        self.assertEqual(3, ui["remaining"])
        self.assertEqual(0, ui["freeze"])
        self.assertEqual([slot], list(farm._pending_spells))

        ui["unreadable"] = False
        farm.state = FarmState.BATTLE_WAIT
        farm._pending_spells[slot].retry_at = 0
        farm._state_battle_wait()

        self.assertEqual(0, ui["remaining"])
        self.assertEqual([(700 + index * 40, 400) for index in range(5)], ui["attempts"])
        self.assertEqual({}, farm._pending_spells)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_permanently_unreadable_count_never_causes_blind_repeat_casts(self, _sleep):
        farm, slot, ui, consume, _ = self.make_recovery_farm()

        def inputs():
            consume()
            ui["unreadable"] = True

        ui["on_input"] = inputs
        farm._deploy_spells()
        farm.state = FarmState.BATTLE_WAIT
        for _ in range(3):
            farm._pending_spells[slot].retry_at = 0
            farm._state_battle_wait()

        self.assertEqual(1, len(ui["attempts"]))
        self.assertEqual(4, ui["remaining"])
        self.assertEqual({}, farm._pending_spells)
        self.assertIsNone(farm.halt_reason)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_successful_progress_resets_the_recovery_limit_for_later_rages(self, _sleep):
        farm, slot, ui, consume, _ = self.make_recovery_farm()

        def inputs():
            consume()
            ui["unreadable"] = True

        ui["on_input"] = inputs
        farm._deploy_spells()
        farm.state = FarmState.BATTLE_WAIT
        for _ in range(5):
            if not farm._pending_spells:
                break
            ui["unreadable"] = False
            farm._pending_spells[slot].retry_at = 0
            farm._state_battle_wait()

        self.assertEqual(0, ui["remaining"])
        self.assertEqual([(700 + index * 40, 400) for index in range(5)], ui["attempts"])
        self.assertEqual({}, farm._pending_spells)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_rejected_casts_and_battle_wait_recovery_are_bounded(self, _sleep):
        farm, slot, ui, consume, _ = self.make_recovery_farm()
        ui["on_input"] = lambda: None
        farm._deploy_spells()
        self.assertEqual(3, len(ui["attempts"]))
        farm.state = FarmState.BATTLE_WAIT
        for _ in range(3):
            farm._pending_spells[slot].retry_at = 0
            farm._state_battle_wait()
        farm._state_battle_wait()

        self.assertEqual(12, len(ui["attempts"]))
        self.assertEqual(5, ui["remaining"])
        self.assertEqual({}, farm._pending_spells)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_result_during_deferred_reconciliation_clears_pending_spells_without_inputs(self, _sleep):
        farm, slot, ui, consume, frame = self.make_recovery_farm()

        def inputs():
            consume()
            ui["unreadable"] = True

        ui["on_input"] = inputs
        farm._deploy_spells()
        ui["unreadable"] = False
        battle = frame()
        result = battle.copy()
        result[0, 0, 0] = 255
        farm.adb.screenshot.side_effect = [battle, result]
        farm._is_result_screen = lambda image: image[0, 0, 0] == 255
        farm._guard_battle_frame = FarmModule._guard_battle_frame.__get__(farm)
        farm.state = FarmState.BATTLE_WAIT
        farm._pending_spells[slot].retry_at = 0

        self.assertTrue(farm.tick())

        self.assertEqual(FarmState.RESULT, farm.state)
        self.assertEqual({}, farm._pending_spells)
        self.assertEqual(1, len(ui["attempts"]))

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_hard_battle_timeout_takes_priority_over_pending_spell_recovery(self, _sleep):
        farm, slot, ui, consume, _ = self.make_recovery_farm()
        ui["on_input"] = lambda: None
        farm._deploy_spells()
        farm.state = FarmState.BATTLE_WAIT
        farm.battle_start_ts = time.time() - 90
        farm._pending_spells[slot].retry_at = 0
        farm._force_end_battle = Mock(return_value=True)

        farm._state_battle_wait()

        farm._force_end_battle.assert_called_once()
        self.assertEqual(FarmState.RESULT, farm.state)
        self.assertEqual(3, len(ui["attempts"]))

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_smart_surrender_waits_for_pending_spell_cooldown(self, _sleep):
        farm, slot, ui, consume, _ = self.make_recovery_farm()
        ui["on_input"] = lambda: None
        farm._deploy_spells()
        farm.state = FarmState.BATTLE_WAIT
        farm.battle_start_ts = time.time() - 50
        farm._pending_spells[slot].retry_at = float("inf")
        farm._count_stars = Mock(return_value=1)
        farm._force_end_battle = Mock(return_value=True)

        farm._state_battle_wait()

        farm._force_end_battle.assert_not_called()
        self.assertEqual(FarmState.BATTLE_WAIT, farm.state)
        self.assertEqual(3, len(ui["attempts"]))

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_increasing_count_is_deferred_without_a_repeat_cast(self, _sleep):
        farm, slot, ui, consume, _ = self.make_recovery_farm()
        ui["on_input"] = lambda: ui.update(remaining=6)

        farm._deploy_spells()

        self.assertEqual(1, len(ui["attempts"]))
        self.assertIsNotNone(farm._pending_spells[slot].unconfirmed_before)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_confirmation_count_flicker_is_deferred_until_a_stable_reading(self, _sleep):
        farm, slot, ui, consume, frame = self.make_recovery_farm()
        before = frame()
        counts = [4, 5, 4]

        def flicker(**kwargs):
            ui["remaining"] = counts.pop(0)
            return frame()

        farm.adb.screenshot.side_effect = flicker
        _, status = farm._reconcile_spell_use(before, slot)
        self.assertEqual("uncertain", status)
        self.assertEqual([], ui["attempts"])

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_20261007_video_counts_reconcile_four_to_three_from_fresh_stable_frames(self, _sleep):
        frames = [self.video_frame(f"rage_20261007_x{count}_bar.png") for count in (5, 4, 3)]
        self.assertEqual([5, 4, 3], [read_card_count(frame, 939, 840) for frame in frames])
        farm = FarmModule(Mock(), None, None, {})
        farm.adb.screenshot.return_value = frames[-1]

        after, status = farm._reconcile_spell_use(frames[1], CardSlot(939, 840, "spell", "rage"))

        self.assertIs(frames[-1], after)
        self.assertEqual("used", status)
        self.assertEqual(2, farm.adb.screenshot.call_count)
        self.assertTrue(all(c.kwargs == {"use_cache": False}
                            for c in farm.adb.screenshot.call_args_list))


if __name__ == "__main__":
    unittest.main()
