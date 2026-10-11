"""Regression tests for screen detection and farm state transitions.

These tests never send ADB input to the emulator.
"""

import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.battle_planner import BattlePlanner
from cocmagic.attack_tactics import AttackTactics
from cocmagic.bot_engine import BotEngine
from cocmagic.modules.hero_module import HeroModule
from cocmagic.modules.farm_module import (
    CardSlot,
    ComboProfile,
    FarmModule,
    FarmState,
    T_CHECK_TROOP,
    T_FIND_MATCH,
    T_FIND_MATCH2,
    T_HOME_ATTACK,
    T_ARMY_ATTACK,
    T_RETURN_HOME_NEW,
    T_SAVE_ARMY,
    T_SURRENDER,
    T_USE,
)
from cocmagic.screen_reader import ScreenReader
from cocmagic.run_coordinator import RunCoordinator
from cocmagic.troop_vision import is_electro_card, is_siege_card, read_card_count


class RegionMatchingTests(unittest.TestCase):
    def test_is_visible_forwards_region_and_preserves_screen_coordinates(self):
        rng = np.random.default_rng(17)
        template = rng.integers(0, 256, (13, 17, 3), dtype=np.uint8)
        screenshot = np.zeros((120, 200, 3), dtype=np.uint8)
        screenshot[72:85, 94:111] = template

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "target.png")
            self.assertTrue(cv2.imwrite(path, template))
            adb = ADBController()

            self.assertTrue(adb.is_visible(path, 0.99, screenshot,
                                           region=(90, 70, 30, 30)))
            self.assertFalse(adb.is_visible(path, 0.99, screenshot,
                                            region=(0, 0, 50, 50)))
            self.assertEqual((102, 78), adb.find_template(path, 0.99, screenshot,
                                                           region=(90, 70, 30, 30)))


class FarmFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.battle_image = cv2.imread(os.path.join(config.BASE_DIR, "tests", "fixtures", "battle_screen.png"))
        if cls.battle_image is None:
            raise RuntimeError("tests/fixtures/battle_screen.png is needed for the saved battle-screen regression")

    def test_battle_image_is_not_misclassified_as_scout(self):
        adb = ADBController()
        adb.screenshot = Mock(return_value=self.battle_image)
        farm = FarmModule(adb, None, None, {})

        self.assertFalse(farm._is_scout_screen(self.battle_image))
        self.assertTrue(farm._is_battle_screen(self.battle_image))
        farm.state = FarmState.FIND_MATCH
        farm._state_find_match()
        self.assertEqual(FarmState.ATTACKING, farm.state)
        self.assertGreater(farm.battle_start_ts, 0)

        farm.state = FarmState.LOOT_CHECK
        farm._state_loot_check()
        self.assertEqual(FarmState.ATTACKING, farm.state)

    def test_star_count_supports_one_two_and_three_star_targets(self):
        farm = FarmModule(ADBController(), None, None, {})
        samples = (
            (1, config.asset("KinhDo/IMG_ClassOf_Clan/Sao/1s-3.png")),
            (2, config.asset("KinhDo/IMG_ClassOf_Clan/Sao/Annotation 2026-05-02 202451.png")),
            (3, config.asset("KinhDo/IMG_ClassOf_Clan/star3_white.png")),
        )
        for expected, path in samples:
            image = np.zeros((900, 1600, 3), np.uint8)
            crop = cv2.imread(path)
            image[630:630 + crop.shape[0], 1400:1400 + crop.shape[1]] = crop
            self.assertEqual(expected, farm._count_stars(image))
        self.assertEqual(0, farm._count_stars(self.battle_image))

    def test_next_button_has_full_template_inside_scout_region(self):
        adb = ADBController()
        scout = np.zeros((900, 1600, 3), dtype=np.uint8)
        next_button = cv2.imread(T_FIND_MATCH)
        scout[590:644, 1351:1576] = next_button
        adb.screenshot = Mock(return_value=scout)
        farm = FarmModule(adb, None, None, {})

        self.assertTrue(farm._is_scout_screen(scout))
        farm.state = FarmState.FIND_MATCH
        farm._state_find_match()
        self.assertEqual(FarmState.LOOT_CHECK, farm.state)

    def test_combo_calibration_separates_troops_spells_and_heroes(self):
        adb = ADBController()
        heroes = HeroModule(adb, {})  # Disabled heroes still reserve their cards.
        detected = heroes.find_ready_heroes(self.battle_image, enabled_only=False)
        self.assertGreaterEqual(len(detected), 3)
        farm = FarmModule(adb, None, heroes, {})
        profile = farm._calibrate_combo(self.battle_image)
        self.assertIsNotNone(profile)
        self.assertEqual(["troop", "troop", "spell", "spell"],
                         [slot.role for slot in profile.cards])
        self.assertTrue(all(abs(slot.x - expected_x) <= 3 for slot, expected_x in
                            zip(profile.cards, (179, 300, 811, 932))))
        self.assertTrue(all(all(abs(slot.x - hero_x) > 50 for _, hero_x, _ in detected)
                            for slot in profile.cards))
        self.assertEqual(["freeze", "lightning"],
                         [slot.name for slot in profile.cards if slot.role == "spell"])
        self.assertFalse(any(is_siege_card(self.battle_image, slot.x, slot.y)
                             for slot in profile.cards))

    def test_video_battle_bar_identifies_siege_between_troops_and_heroes(self):
        bar = cv2.imread(os.path.join(config.BASE_DIR, "tests", "fixtures",
                                      "user_siege_battle_bar.png"))
        self.assertIsNotNone(bar)
        image = np.zeros_like(self.battle_image)
        image[735:900] = bar
        adb = ADBController()
        farm = FarmModule(adb, None, HeroModule(adb, {}), {})

        profile = farm._calibrate_combo(image)

        self.assertIsNotNone(profile)
        self.assertEqual(["troop", "troop", "siege", "spell", "spell", "spell"],
                         [slot.role for slot in profile.cards])
        self.assertEqual(430, next(slot.x for slot in profile.cards
                                   if slot.role == "siege"))
        self.assertEqual(3, len(profile.heroes))

    def test_siege_drops_once_then_four_available_heroes_follow(self):
        adb = Mock()
        adb.tap_many.return_value = True
        adb.screenshot.return_value = self.battle_image
        heroes = Mock()
        heroes.get_enabled_heroes.return_value = [
            "king", "queen", "warden", "royal_champ"]
        farm = FarmModule(adb, None, heroes, {})
        farm._battle_plan = farm.planner.plan(self.battle_image)
        farm._attack_tactics = AttackTactics.from_battle(
            farm._battle_plan, self.battle_image)
        farm._confirmed_main_points = [(322, 580)]
        farm._combo_profile = ComboProfile(
            [CardSlot(179, 840, "troop"), CardSlot(430, 840, "siege")],
            [("king", 555, 840), ("queen", 676, 840),
             ("warden", 797, 840), ("royal_champ", 918, 840)],
            (900, 1600))
        farm._card_depleted = Mock(return_value=False)

        farm._deploy_siege()
        after = self.battle_image.copy()
        for _, x, y in farm._combo_profile.heroes:
            after[y-122:y-108, x-40:x+40] = (30, 30, 30)
            after[y-118:y-111, x-38:x+38] = (40, 220, 60)
        adb.screenshot.side_effect = [self.battle_image, after]
        farm._deploy_cached_heroes()

        calls = [call.args[0] for call in adb.tap_many.call_args_list]
        self.assertEqual([(430, 790), (322, 580)], calls[0])
        self.assertEqual(2, len(calls))
        self.assertTrue(all(point == (322, 580) for point in calls[1][1::2]))
        self.assertEqual(4, len(farm._deployed_hero_slots))
        heroes.activate_ability.assert_not_called()

    def test_heroes_follow_confirmed_main_troop_drops(self):
        adb = Mock()
        adb.tap_many.return_value = True
        ui = {"remaining": 7}

        def frame(**kwargs):
            image = self.battle_image.copy()
            image[0, 0, 0] = ui["remaining"]
            return image

        def drops(points, **kwargs):
            ui["remaining"] = max(0, ui["remaining"] - sum(p[1] < 700 for p in points))
            return True

        adb.screenshot.side_effect = frame
        adb.tap_many.side_effect = drops
        heroes = Mock()
        heroes.get_enabled_heroes.return_value = ["king", "warden"]
        farm = FarmModule(adb, None, heroes, {"attack_around": True})
        farm._battle_plan = farm.planner.plan(self.battle_image)
        farm._combo_profile = ComboProfile(
            [CardSlot(179, 840, "troop")],
            [("king", 555, 840), ("warden", 675, 840)], (900, 1600))

        with patch("cocmagic.modules.farm_module.is_electro_card", return_value=False), \
                patch("cocmagic.modules.farm_module.read_card_count",
                      side_effect=lambda image, x, y: int(image[0, 0, 0])):
            farm._deploy_all_troops(frame())
        troop_call_count = adb.tap_many.call_count
        troop_targets = [p for c in adb.tap_many.call_args_list for p in c.args[0]]
        self.assertGreaterEqual(len(farm._confirmed_main_points), 2)
        self.assertTrue(all(point in troop_targets for point in farm._confirmed_main_points))
        adb.screenshot.side_effect = None
        adb.screenshot.return_value = self.battle_image
        farm._card_depleted = Mock(return_value=False)
        after = self.battle_image.copy()
        for x in [555, 675]:
            after[718:732, x-40:x+40] = (30, 30, 30)
            after[722:729, x-38:x+38] = (40, 220, 60)
        adb.screenshot.side_effect = [self.battle_image, after]
        farm._deploy_cached_heroes()

        hero_calls = adb.tap_many.call_args_list[troop_call_count:]
        self.assertEqual(1, len(hero_calls))
        self.assertTrue(all(point in farm._confirmed_main_points
                            for point in hero_calls[0].args[0][1::2]))
        self.assertTrue(all(point not in farm._attack_tactics.flank_points
                            for point in hero_calls[0].args[0][1::2]))

    def test_spells_have_distinct_targets_for_different_functions(self):
        plan = BattlePlanner().plan(self.battle_image)
        tactics = AttackTactics.from_battle(plan, self.battle_image)

        rage = tactics.spell_target("rage", 0)
        healing = tactics.spell_target("healing", 0)
        freeze = tactics.spell_target("freeze", 0)
        lightning = tactics.spell_target("lightning", 0)
        self.assertEqual(4, len({rage, healing, freeze, lightning}))
        self.assertEqual(lightning, tactics.spell_target("earthquake", 0))
        self.assertEqual(tactics.center, freeze)
        self.assertIn(lightning, tactics.hotspots)
        self.assertIsNone(tactics.spell_target("unknown", 0))

    def test_rage_follows_each_electro_direction_without_stacking(self):
        plan = BattlePlanner().plan(self.battle_image)
        tactics = AttackTactics.from_battle(plan, self.battle_image)
        tactics.rage_entries = plan.troop_points[:3]
        targets = [tactics.spell_target("rage", index) for index in range(6)]

        self.assertEqual(6, len(set(targets)))
        self.assertEqual(tactics.center, tactics.spell_target("freeze", 0))
        for entry, target in zip(tactics.rage_entries, targets[:3]):
            self.assertLess(np.linalg.norm(np.subtract(target, tactics.center)),
                            np.linalg.norm(np.subtract(entry, tactics.center)))

    def test_electro_six_and_nine_use_two_and_three_spaced_directions(self):
        plan = BattlePlanner().plan(self.battle_image)
        for total, directions in ((6, 2), (9, 3)):
            with self.subTest(total=total):
                remaining = {"count": total}
                adb = Mock()
                adb.tap.return_value = True

                def frame(**_kwargs):
                    image = np.zeros((900, 1600, 3), np.uint8)
                    image[0, 0, 0] = remaining["count"]
                    return image

                def deploy(targets, **_kwargs):
                    remaining["count"] = max(0, remaining["count"] - sum(p[1] < 700 for p in targets))
                    return True

                adb.screenshot.side_effect = frame
                adb.tap_many.side_effect = deploy
                farm = FarmModule(adb, None, Mock(), {"electro_per_direction": 3})
                farm._battle_plan = plan
                farm._attack_tactics = AttackTactics.from_battle(plan, self.battle_image)
                farm._card_depleted = Mock(side_effect=lambda image, _slot:
                                           image[0, 0, 0] == 0)
                with patch("cocmagic.modules.farm_module.read_card_count",
                           side_effect=lambda image, _x, _y: int(image[0, 0, 0])):
                    _, points = farm._deploy_electro_card(frame(), CardSlot(179, 840, "troop"))

                self.assertEqual(directions, len(points))
                self.assertEqual(0, remaining["count"])
                self.assertTrue(all(np.linalg.norm(np.subtract(a, b)) >= 220
                                    for i, a in enumerate(points) for b in points[i + 1:]))
                self.assertEqual(points, farm._attack_tactics.rage_entries)
                self.assertEqual(points[0], farm._hero_entry)
                drops = [point for call in adb.tap_many.call_args_list
                         for point in call.args[0] if point[1] < 700]
                self.assertEqual(total, len(drops))
                self.assertEqual(directions, len(set(drops)))
                for anchor in points:
                    self.assertEqual(total // directions, drops.count(anchor))
                self.assertLessEqual(adb.screenshot.call_count, directions + 1)

    def test_hero_abilities_fire_together_at_warden_deadline_or_danger(self):
        adb = Mock()
        adb.tap_many.return_value = True
        heroes = Mock()
        heroes.warden_health_fraction.return_value = .9
        farm = FarmModule(adb, None, heroes, {"warden_ability_delay": 10})
        farm._warden_slot = (670, 840)
        farm._warden_deployed_ts = 100.0
        farm._deployed_hero_slots = {"king": (430, 840), "warden": (670, 840),
                                     "queen": (550, 840)}
        with patch("cocmagic.modules.farm_module.time.time", return_value=109.0):
            farm._maybe_activate_hero_abilities(self.battle_image)
        adb.tap_many.assert_not_called()
        with patch("cocmagic.modules.farm_module.time.time", return_value=110.0):
            farm._maybe_activate_hero_abilities(self.battle_image)
            farm._maybe_activate_hero_abilities(self.battle_image)
        adb.tap_many.assert_called_once_with([(670, 790), (430, 790), (550, 790)], interval=.02)
        heroes.activate_ability.assert_not_called()

        farm._hero_abilities_used = False
        farm._warden_low_health_frames = 0
        heroes.warden_health_fraction.return_value = .2
        adb.tap_many.reset_mock()
        with patch("cocmagic.modules.farm_module.time.time", return_value=103.0):
            farm._maybe_activate_hero_abilities(self.battle_image)
            adb.tap_many.assert_not_called()
            farm._maybe_activate_hero_abilities(self.battle_image)
        adb.tap_many.assert_called_once_with([(670, 790), (430, 790), (550, 790)], interval=.02)

    def test_heroes_without_warden_use_the_group_delay_from_first_deployment(self):
        adb = Mock()
        adb.tap_many.return_value = True
        heroes = Mock()
        farm = FarmModule(adb, None, heroes, {"warden_ability_delay": 10})
        farm._deployed_hero_slots = {"king": (430, 840), "queen": (550, 840)}
        farm._heroes_deployed_ts = 100.0
        with patch("cocmagic.modules.farm_module.time.time", return_value=109.0):
            farm._maybe_activate_hero_abilities(self.battle_image)
        adb.tap_many.assert_not_called()
        with patch("cocmagic.modules.farm_module.time.time", return_value=110.0):
            farm._maybe_activate_hero_abilities(self.battle_image)
        adb.tap_many.assert_called_once_with([(430, 790), (550, 790)], interval=.02)
        heroes.warden_health_fraction.assert_not_called()

    def test_warden_health_strip_from_user_battle_image(self):
        image = cv2.imread(os.path.join(config.BASE_DIR, "tests", "fixtures",
                                        "user_electro_battle.jpg"))
        image = cv2.resize(image, (1600, 900))
        full = HeroModule.warden_health_fraction(image, 664, 840)
        self.assertIsNotNone(full)
        self.assertGreater(full, .8)
        damaged = image.copy()
        damaged[716:731, 648:704] = (30, 30, 30)
        low = HeroModule.warden_health_fraction(damaged, 664, 840)
        self.assertIsNotNone(low)
        self.assertLess(low, .35)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_unknown_spell_is_kept_instead_of_blind_cast(self, _sleep):
        adb = Mock()
        adb.screenshot.return_value = self.battle_image
        farm = FarmModule(adb, None, Mock(), {})
        plan = farm.planner.plan(self.battle_image)
        farm._attack_tactics = AttackTactics.from_battle(plan, self.battle_image)
        farm._combo_profile = ComboProfile([CardSlot(811, 840, "spell", "")], [],
                                           (900, 1600))

        farm._deploy_spells()

        adb.tap.assert_not_called()
        adb.tap_many.assert_not_called()

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_spells_cast_one_at_a_time_and_stop_when_empty(self, _sleep):
        adb = Mock()
        frames = [self.battle_image.copy() for _ in range(3)]
        for count, frame in zip((2, 1, 0), frames):
            frame[0, 0, 0] = count
        adb.screenshot.side_effect = frames
        adb.tap_many.return_value = True
        farm = FarmModule(adb, None, Mock(), {})
        plan = farm.planner.plan(self.battle_image)
        farm._attack_tactics = AttackTactics.from_battle(plan, self.battle_image)
        farm._combo_profile = ComboProfile([CardSlot(811, 840, "spell", "rage")], [],
                                           (900, 1600))
        farm._card_depleted = Mock(side_effect=lambda image, _slot: image[0, 0, 0] == 0)

        with patch("cocmagic.modules.farm_module.read_card_count",
                   side_effect=lambda image, _x, _y: int(image[0, 0, 0])):
            farm._deploy_spells()

        self.assertEqual(2, adb.tap_many.call_count)
        first = adb.tap_many.call_args_list[0].args[0]
        second = adb.tap_many.call_args_list[1].args[0]
        self.assertEqual(2, len(first))
        self.assertEqual(2, len(second))
        self.assertEqual((811, 840), first[0])
        self.assertEqual((811, 840), second[0])
        self.assertNotEqual(first[1], second[1])

    def test_troop_card_detection_accepts_a_shifted_bottom_border(self):
        image = np.zeros((900, 1600, 3), dtype=np.uint8)
        for x in (179, 300, 434, 555, 676, 811, 932):
            image[880, x-50:x+50, 0] = 180
        farm = FarmModule(Mock(), None, None, {})

        self.assertEqual([179, 300, 434, 555, 676, 811, 932],
                         [x for x, _ in farm._detect_troop_cards(image)])

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_quick_train_selects_saved_recipes_and_slot_one_use(self, _sleep):
        adb = Mock()
        adb.screenshot.return_value = self.battle_image
        adb.find_and_tap.side_effect = lambda path, *args, **kwargs: path in (T_CHECK_TROOP, T_USE)
        farm = FarmModule(adb, None, None, {"auto_train": True})
        farm.state = FarmState.TRAIN

        self.assertTrue(farm.tick())
        self.assertEqual(FarmState.COLLECT, farm.state)
        self.assertIsNone(farm.halt_reason)
        self.assertEqual((795, 95), adb.tap.call_args_list[0].args)
        self.assertTrue(any(call.args[0] == T_USE and call.kwargs.get("region")
                            for call in adb.find_and_tap.call_args_list))

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_save_army_does_not_count_as_quick_train(self, _sleep):
        adb = Mock()
        adb.screenshot.return_value = self.battle_image
        adb.find_and_tap.side_effect = lambda path, *args, **kwargs: path == T_CHECK_TROOP
        adb.is_visible.side_effect = lambda path, *args, **kwargs: path == T_SAVE_ARMY
        farm = FarmModule(adb, None, None, {"auto_train": True})
        farm.state = FarmState.TRAIN

        self.assertFalse(farm.tick())
        self.assertIn("Slot 1", farm.halt_reason)
        self.assertEqual(FarmState.TRAIN, farm.state)
        self.assertFalse(any(call.args[0] == T_SAVE_ARMY
                             for call in adb.find_and_tap.call_args_list))
        self.assertTrue(any(call.args[0] == T_USE and call.kwargs.get("region")
                            for call in adb.find_and_tap.call_args_list))

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_surrender_waits_for_a_real_confirmation(self, _sleep):
        adb = Mock()
        adb.screenshot.return_value = self.battle_image
        adb.is_visible.return_value = False
        adb.find_and_tap.side_effect = lambda path, *args, **kwargs: path != T_SURRENDER
        farm = FarmModule(adb, None, None, {})

        self.assertFalse(farm._force_end_battle())
        adb.tap.assert_not_called()

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_result_is_only_counted_after_home_is_visible(self, _sleep):
        adb = Mock()
        adb.screenshot.return_value = self.battle_image
        adb.is_visible.return_value = False
        adb.find_template.return_value = None
        adb.find_and_tap.side_effect = lambda path, *args, **kwargs: path == T_RETURN_HOME_NEW
        farm = FarmModule(adb, None, None, {"auto_train": True})
        farm.state = FarmState.RESULT
        farm._battle_plan = farm.planner.plan(self.battle_image)

        farm._state_result()
        self.assertEqual(0, farm.attack_count)
        self.assertEqual(FarmState.RESULT, farm.state)

        adb.is_visible.side_effect = lambda path, *args, **kwargs: path == T_HOME_ATTACK
        farm._state_result()
        self.assertEqual(1, farm.attack_count)
        self.assertEqual(FarmState.COLLECT, farm.state)
        self.assertIsNone(farm._battle_plan)

    def test_home_uses_learned_button_after_verified_return(self):
        adb = Mock()
        farm = FarmModule(adb, None, None, {"auto_train": True})
        farm._initial_trained = True
        farm._button_cache["home_attack"] = (72, 820)
        farm._home_verified = True

        with patch("cocmagic.modules.farm_module.time.sleep"):
            farm._state_home()

        adb.tap.assert_called_once_with(72, 820, delay=0.05)
        adb.screenshot.assert_not_called()
        self.assertEqual(FarmState.FIND_MATCH, farm.state)

    def test_failed_cached_home_tap_does_not_advance_state(self):
        adb = Mock()
        adb.tap.return_value = False
        farm = FarmModule(adb, None, None, {"auto_train": False})
        farm._button_cache["home_attack"] = (72, 820)
        farm._home_verified = True

        farm._state_home()

        self.assertEqual(FarmState.HOME, farm.state)
        adb.screenshot.assert_not_called()

    def test_match_menu_uses_learned_buttons(self):
        adb = Mock()
        real_adb = ADBController()
        menu = np.zeros((900, 1600, 3), dtype=np.uint8)
        army = np.zeros_like(menu)
        menu_tpl = cv2.imread(T_FIND_MATCH2)
        army_tpl = cv2.imread(T_ARMY_ATTACK)
        menu[584:617, 633:871] = menu_tpl
        army[679:722, 1268:1552] = army_tpl
        adb.screenshot.side_effect = [menu, army]
        adb.is_visible.return_value = False
        adb.find_template.side_effect = real_adb.find_template
        adb._load_template.side_effect = real_adb._load_template
        adb.tap.return_value = True
        farm = FarmModule(adb, None, None, {"auto_train": False})
        farm._button_cache.update({"find_match": (752, 600), "army_attack": (1410, 700)})
        farm._button_templates.update({"find_match": T_FIND_MATCH2,
                                       "army_attack": T_ARMY_ATTACK})

        with patch("cocmagic.modules.farm_module.time.sleep"):
            farm._state_find_match()
            farm._state_find_match()

        self.assertEqual([(752, 600), (1410, 700)],
                         [call.args for call in adb.tap.call_args_list])
        self.assertEqual(2, adb.screenshot.call_count)
        self.assertEqual("scout", farm._find_phase)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_shifted_menu_button_relearns_position(self, _sleep):
        adb = Mock()
        real_adb = ADBController()
        menu = np.zeros((900, 1600, 3), dtype=np.uint8)
        menu[584:617, 721:959] = cv2.imread(T_FIND_MATCH2)
        adb.screenshot.return_value = menu
        adb.is_visible.return_value = False
        adb.find_template.side_effect = real_adb.find_template
        adb._load_template.side_effect = real_adb._load_template
        adb.tap.return_value = True
        farm = FarmModule(adb, None, None, {"auto_train": False})
        farm._button_cache["find_match"] = (752, 600)
        farm._button_templates["find_match"] = T_FIND_MATCH2

        farm._state_find_match()

        self.assertEqual((840, 600), farm._button_cache["find_match"])
        adb.tap.assert_called_once_with(840, 600, delay=0.05)
        self.assertEqual("army", farm._find_phase)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_missed_attack_tap_returns_home_and_recenters_cache(self, _sleep):
        adb = Mock()
        adb.screenshot.return_value = np.zeros((900, 1600, 3), dtype=np.uint8)
        adb.is_visible.side_effect = lambda path, *args, **kwargs: path == T_HOME_ATTACK
        adb.find_template.return_value = (103, 791)
        adb.tap.return_value = True
        farm = FarmModule(adb, None, None, {"auto_train": False})
        farm.state = FarmState.FIND_MATCH
        farm._button_cache["home_attack"] = (72, 820)

        farm._state_find_match()

        self.assertEqual(FarmState.HOME, farm.state)
        self.assertEqual((103, 791), farm._button_cache["home_attack"])
        self.assertTrue(farm._home_verified)
        self.assertEqual(1, farm._home_attack_failures)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_repeated_missed_attack_taps_stop_with_reason(self, _sleep):
        adb = Mock()
        adb.screenshot.return_value = np.zeros((900, 1600, 3), dtype=np.uint8)
        adb.is_visible.side_effect = lambda path, *args, **kwargs: path == T_HOME_ATTACK
        adb.find_template.return_value = (103, 791)
        adb.tap.return_value = True
        farm = FarmModule(adb, None, None, {"auto_train": False})
        farm._home_verified = True
        farm._button_cache["home_attack"] = (103, 791)

        for _ in range(4):
            farm._state_home()
            farm._state_find_match()

        self.assertIn("4 lần thử", farm.halt_reason)

    def test_combo_is_calibrated_once_across_attacks(self):
        adb = Mock()
        adb.screenshot.return_value = self.battle_image
        adb.find_template.return_value = None
        heroes = Mock()
        farm = FarmModule(adb, None, heroes, {})
        profile = ComboProfile([CardSlot(179, 840, "troop")], [], (900, 1600))
        farm._calibrate_combo = Mock(return_value=profile)
        farm._deploy_all_troops = Mock()
        farm._deploy_cached_heroes = Mock()

        with patch("cocmagic.modules.farm_module.time.sleep"):
            for _ in range(2):
                farm._battle_plan = farm.planner.plan(self.battle_image)
                self.assertIsNotNone(farm._battle_plan)
                farm._state_attacking()

        farm._calibrate_combo.assert_called_once()
        self.assertEqual(2, farm._deploy_all_troops.call_count)

    def test_troop_batch_uses_safe_plan_points_and_stops_when_slot_is_empty(self):
        adb = Mock()
        adb.tap_many.return_value = True
        heroes = Mock()
        farm = FarmModule(adb, None, heroes, {})
        farm._battle_plan = farm.planner.plan(self.battle_image)
        self.assertIsNotNone(farm._battle_plan)
        slot = CardSlot(179, 840, "troop")
        farm._combo_profile = ComboProfile([slot], [], (900, 1600))
        depleted = cv2.cvtColor(self.battle_image, cv2.COLOR_BGR2GRAY)
        depleted = cv2.cvtColor(depleted, cv2.COLOR_GRAY2BGR)
        adb.screenshot.return_value = depleted

        with patch("cocmagic.modules.farm_module.is_electro_card", return_value=False), \
                patch("cocmagic.modules.farm_module.read_card_count",
                      side_effect=lambda image, x, y: 0 if image is depleted else 1):
            farm._deploy_all_troops(self.battle_image)

        adb.tap.assert_not_called()
        self.assertEqual(2, adb.tap_many.call_count)
        targets = adb.tap_many.call_args.args[0]
        self.assertEqual(1, len(targets))
        self.assertTrue(all(point in farm._battle_plan.troop_points for point in targets))
        self.assertIsNone(farm.halt_reason)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_transient_gray_troop_bar_waits_for_active_cards(self, _sleep):
        gray = cv2.cvtColor(cv2.cvtColor(self.battle_image, cv2.COLOR_BGR2GRAY),
                            cv2.COLOR_GRAY2BGR)
        adb = Mock()
        adb.screenshot.return_value = self.battle_image
        farm = FarmModule(adb, None, Mock(), {})
        farm._combo_profile = ComboProfile([CardSlot(179, 840, "troop")], [], (900, 1600))

        ready = farm._ensure_deploy_bar_ready(gray)

        self.assertIs(ready, self.battle_image)
        self.assertIsNone(farm.halt_reason)
        adb.screenshot.assert_called_once()

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_stale_combo_positions_recalibrate_after_retry(self, _sleep):
        gray = cv2.cvtColor(cv2.cvtColor(self.battle_image, cv2.COLOR_BGR2GRAY),
                            cv2.COLOR_GRAY2BGR)
        shifted = gray.copy()
        shifted[770:875, 255:345] = self.battle_image[770:875, 255:345]
        adb = Mock()
        adb.screenshot.return_value = shifted
        farm = FarmModule(adb, None, Mock(), {})
        farm._combo_profile = ComboProfile([CardSlot(179, 840, "troop")], [], (900, 1600))
        updated = ComboProfile([CardSlot(300, 840, "troop")], [], (900, 1600))
        farm._calibrate_combo = Mock(return_value=updated)

        ready = farm._ensure_deploy_bar_ready(shifted)

        self.assertIs(ready, shifted)
        self.assertIs(farm._combo_profile, updated)
        farm._calibrate_combo.assert_called_once()

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_all_gray_cards_cannot_silently_enter_battle_wait(self, _sleep):
        gray = cv2.cvtColor(cv2.cvtColor(self.battle_image, cv2.COLOR_BGR2GRAY),
                            cv2.COLOR_GRAY2BGR)
        adb = Mock()
        adb.screenshot.return_value = gray
        farm = FarmModule(adb, None, Mock(), {})
        farm.state = FarmState.ATTACKING
        farm._battle_plan = farm.planner.plan(self.battle_image)
        farm._combo_profile = ComboProfile([CardSlot(179, 840, "troop")], [], (900, 1600))
        farm._calibrate_combo = Mock(return_value=None)

        farm._state_attacking()

        self.assertEqual(FarmState.ATTACKING, farm.state)
        self.assertIn("Không thấy quân", farm.halt_reason)
        adb.tap.assert_not_called()

    def test_skipped_cards_without_deployment_rejects_battle(self):
        gray = cv2.cvtColor(cv2.cvtColor(self.battle_image, cv2.COLOR_BGR2GRAY),
                            cv2.COLOR_GRAY2BGR)
        adb = Mock()
        farm = FarmModule(adb, None, Mock(), {})
        farm._battle_plan = farm.planner.plan(self.battle_image)
        farm._combo_profile = ComboProfile([CardSlot(179, 840, "troop")], [], (900, 1600))

        farm._deploy_all_troops(gray)

        self.assertTrue(farm._deployment_rejected)
        self.assertIsNone(farm.halt_reason)
        adb.tap.assert_not_called()

    def test_adb_batch_failure_stops_deployment(self):
        adb = Mock()
        adb.tap_many.return_value = False
        adb.screenshot.return_value = self.battle_image
        farm = FarmModule(adb, None, Mock(), {})
        farm._battle_plan = farm.planner.plan(self.battle_image)
        farm._combo_profile = ComboProfile([CardSlot(179, 840, "troop")], [], (900, 1600))

        with patch("cocmagic.modules.farm_module.is_electro_card", return_value=False):
            farm._deploy_all_troops(self.battle_image)

        self.assertIn("ADB", farm.halt_reason)
        adb.screenshot.assert_not_called()

    def test_rejected_troop_drops_reject_battle_instead_of_trying_other_cards(self):
        adb = Mock()
        adb.tap_many.return_value = True
        adb.screenshot.return_value = self.battle_image
        farm = FarmModule(adb, None, Mock(), {})
        farm._battle_plan = farm.planner.plan(self.battle_image)
        farm._combo_profile = ComboProfile([CardSlot(179, 840, "troop"),
                                            CardSlot(300, 840, "troop")], [], (900, 1600))

        with patch("cocmagic.modules.farm_module.is_electro_card", return_value=False):
            farm._deploy_all_troops(self.battle_image)

        self.assertTrue(farm._deployment_rejected)
        self.assertIsNone(farm.halt_reason)
        self.assertEqual(1 + len(farm._attack_tactics.main_points + farm._attack_tactics.flank_points),
                         adb.tap_many.call_count)
        adb.tap.assert_not_called()

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_outer_perimeter_probes_until_a_troop_count_falls(self, _sleep):
        image = cv2.imread(os.path.join(config.BASE_DIR, "tests", "fixtures",
                                        "dense_base_no_border.jpg"))
        image = cv2.resize(image, (1600, 900))
        adb = Mock()
        adb.tap.return_value = True
        adb.tap_many.return_value = True
        adb.screenshot.return_value = image
        farm = FarmModule(adb, None, Mock(), {})
        farm._battle_plan = farm.planner.plan(image)
        self.assertEqual("outer_perimeter", farm._battle_plan.source)
        farm._combo_profile = ComboProfile([CardSlot(179, 840, "troop")], [], (900, 1600))
        farm._card_depleted = Mock(return_value=False)
        ui = {"remaining": 4}

        def frame(**kwargs):
            current = image.copy()
            current[0, 0, 0] = ui["remaining"]
            return current

        def drops(points, **kwargs):
            if points[0] == farm._battle_plan.troop_points[1]:
                ui["remaining"] = max(0, ui["remaining"] - len(points))
            return True

        adb.screenshot.side_effect = frame
        adb.tap_many.side_effect = drops
        with patch("cocmagic.modules.farm_module.read_card_count",
                   side_effect=lambda current, x, y: int(current[0, 0, 0])), \
                patch("cocmagic.modules.farm_module.is_electro_card", return_value=False):
            farm._deploy_all_troops(frame())

        calls = adb.tap_many.call_args_list
        self.assertEqual([farm._battle_plan.troop_points[0]], calls[1].args[0])
        self.assertEqual([farm._battle_plan.troop_points[1]], calls[2].args[0])
        self.assertEqual([farm._battle_plan.troop_points[1]], farm._confirmed_main_points)
        self.assertEqual(farm._battle_plan.troop_points[1], farm._attack_tactics.entry)
        self.assertIsNone(farm.halt_reason)
        self.assertFalse(farm._deployment_rejected)

    @patch("cocmagic.modules.farm_module.time.sleep")
    def test_outer_perimeter_all_rejected_surrenders_without_stopping_bot(self, _sleep):
        image = cv2.imread(os.path.join(config.BASE_DIR, "tests", "fixtures",
                                        "dense_base_no_border.jpg"))
        image = cv2.resize(image, (1600, 900))
        adb = Mock()
        adb.tap.return_value = True
        adb.tap_many.return_value = True
        adb.screenshot.return_value = image
        adb.find_template.return_value = None
        farm = FarmModule(adb, None, Mock(), {})
        farm._battle_plan = farm.planner.plan(image)
        farm._combo_profile = ComboProfile([CardSlot(179, 840, "troop")], [], (900, 1600))
        farm._ensure_deploy_bar_ready = Mock(return_value=image)
        farm._card_depleted = Mock(return_value=False)
        farm._count_display_changed = Mock(return_value=False)
        farm._force_end_battle = Mock(return_value=True)
        farm._deploy_cached_heroes = Mock()
        farm._deploy_spells = Mock()

        farm._state_attacking()

        self.assertEqual(FarmState.RESULT, farm.state)
        self.assertTrue(farm._deployment_rejected)
        self.assertIsNone(farm.halt_reason)
        self.assertEqual(1 + len(farm._battle_plan.troop_points), adb.tap_many.call_count)
        farm._force_end_battle.assert_called_once()
        farm._deploy_cached_heroes.assert_not_called()
        farm._deploy_spells.assert_not_called()


class LootThresholdTests(unittest.TestCase):
    def setUp(self):
        self.reader = ScreenReader(ADBController())
        self.settings = {"min_gold": 500_000, "min_elixir": 500_000,
                         "min_dark": 0}

    def test_gold_alone_qualifies(self):
        self.assertTrue(self.reader.loot_meets_threshold(
            {"gold": 600_000, "elixir": 100_000}, self.settings))

    def test_elixir_alone_qualifies(self):
        self.assertTrue(self.reader.loot_meets_threshold(
            {"gold": 100_000, "elixir": 600_000}, self.settings))

    def test_both_below_rejects(self):
        self.assertFalse(self.reader.loot_meets_threshold(
            {"gold": 499_999, "elixir": 499_999}, self.settings))

    def test_dark_remains_a_separate_requirement(self):
        self.settings["min_dark"] = 10_000
        self.assertFalse(self.reader.loot_meets_threshold(
            {"gold": 600_000, "elixir": 0, "dark": 5_000}, self.settings))
        self.assertTrue(self.reader.loot_meets_threshold(
            {"gold": 600_000, "elixir": 0, "dark": 11_000}, self.settings))

    def test_zero_thresholds_do_not_block(self):
        self.settings.update(min_gold=0, min_elixir=0)
        self.assertTrue(self.reader.loot_meets_threshold({}, self.settings))


class TroopVisionTests(unittest.TestCase):
    def test_saved_battle_card_is_electro_and_has_seven_troops(self):
        image = cv2.imread(os.path.join(config.BASE_DIR, "tests", "fixtures", "battle_screen.png"))
        self.assertTrue(is_electro_card(image, 179, 840))
        self.assertEqual(7, read_card_count(image, 179, 840))
        self.assertFalse(is_electro_card(image, 300, 840))

    def test_user_card_badge_reads_six_electro(self):
        card = cv2.imread(os.path.join(config.BASE_DIR, "tests", "fixtures",
                                       "electro_card_x6.png"))
        image = np.zeros((900, 1600, 3), np.uint8)
        image[730:880, 119:239] = cv2.resize(card, (120, 150))
        self.assertTrue(is_electro_card(image, 179, 840))
        self.assertEqual(6, read_card_count(image, 179, 840))


class BattlePlannerTests(unittest.TestCase):
    def test_dense_base_without_border_uses_construction_perimeter(self):
        image = cv2.imread(os.path.join(config.BASE_DIR, "tests", "fixtures",
                                        "dense_base_no_border.jpg"))
        image = cv2.resize(image, (1600, 900))
        plan = BattlePlanner().plan(image)

        self.assertIsNotNone(plan)
        self.assertEqual("outer_perimeter", plan.source)
        self.assertGreaterEqual(len(plan.troop_points), 4)
        self.assertTrue(all(120 <= x < 1500 and 120 <= y < 700
                            for x, y in plan.troop_points))

    def test_points_are_outside_detected_boundary(self):
        image = cv2.imread(os.path.join(config.BASE_DIR, "tests", "fixtures", "battle_screen.png"))
        plan = BattlePlanner().plan(image)
        self.assertIsNotNone(plan)
        self.assertGreaterEqual(len(plan.troop_points), 4)
        for x, y in plan.troop_points:
            self.assertLess(cv2.pointPolygonTest(plan.boundary.astype(np.float32),
                                                 (float(x), float(y)), False), 0)
            self.assertTrue(220 < x < 1400 and 135 < y < 620)

    def test_blank_screen_is_rejected(self):
        self.assertIsNone(BattlePlanner().plan(np.zeros((900, 1600, 3), np.uint8)))

    def test_points_follow_a_shifted_boundary(self):
        def synthetic(center_x):
            image = np.full((900, 1600, 3), (55, 145, 55), dtype=np.uint8)
            outline = np.array([(center_x, 120), (center_x + 450, 410),
                                (center_x, 700), (center_x - 450, 410)], np.int32)
            cv2.polylines(image, [outline], True, (0, 0, 255), 3)
            return image

        left = BattlePlanner().plan(synthetic(720))
        right = BattlePlanner().plan(synthetic(880))
        self.assertIsNotNone(left)
        self.assertIsNotNone(right)
        self.assertGreater(right.spell_center[0], left.spell_center[0] + 100)
        self.assertGreater(np.mean([x for x, _ in right.troop_points]),
                           np.mean([x for x, _ in left.troop_points]) + 50)

    def test_cold_blue_ground_can_be_used_outside_red_border(self):
        image = np.full((900, 1600, 3), (120, 110, 100), dtype=np.uint8)
        outline = np.array([(800, 110), (1360, 400),
                            (800, 690), (240, 400)], np.int32)
        cv2.polylines(image, [outline], True, (0, 0, 255), 3)

        plan = BattlePlanner().plan(image)

        self.assertIsNotNone(plan)
        self.assertGreaterEqual(len(plan.troop_points), 4)
        self.assertTrue(all(cv2.pointPolygonTest(plan.boundary.astype(np.float32),
                                                 (float(x), float(y)), False) < 0
                            for x, y in plan.troop_points))


class AdbBatchTests(unittest.TestCase):
    @patch("cocmagic.process_utils.subprocess.run")
    def test_tap_many_sends_one_clamped_numeric_script(self, run):
        run.return_value.returncode = 0
        adb = ADBController()
        self.assertTrue(adb.tap_many([(100, 200), (-10, 1000)]))
        run.assert_called_once()
        script = run.call_args.kwargs["input"].decode("ascii")
        self.assertIn("input tap 100 200", script)
        self.assertIn("input tap 0 899", script)
        self.assertIn("sleep 0.050", script)

    @patch("cocmagic.process_utils.subprocess.run")
    def test_single_tap_reports_adb_failure(self, run):
        run.return_value.returncode = 1
        run.return_value.stderr = b"device offline"
        adb = ADBController()
        self.assertFalse(adb.tap(100, 200, delay=0))

    def test_engine_stops_when_training_requires_setup(self):
        engine = BotEngine({"upgrade_walls": False})
        engine._handle_popups = Mock(return_value=False)
        engine.farm_mod = Mock()
        engine.farm_mod.halt_reason = None
        def failed_tick(**kwargs):
            engine.farm_mod.halt_reason = "Quick Train Slot 1 unavailable"
            return False
        engine.farm_mod.tick.side_effect = failed_tick
        engine.farm_mod.device_serial = "test"
        engine.coordinator = RunCoordinator("test", {"main": engine.farm_mod}, "main")
        engine.running = True

        engine._main_loop()

        self.assertFalse(engine.running)
        engine.farm_mod.tick.assert_called_once()

    def test_generic_ok_on_normal_screen_does_not_clear_button_cache(self):
        engine = BotEngine({})
        engine.adb = Mock()
        engine.adb.screenshot.return_value = np.full((900, 1600, 3), 150, np.uint8)
        engine.adb.is_visible.side_effect = (
            lambda path, *args, **kwargs: path == config.asset("okay.png")
        )
        engine.farm_mod = Mock()

        engine._handle_popups()

        engine.adb.tap.assert_not_called()
        engine.farm_mod.invalidate_ui_cache.assert_not_called()

    @patch("cocmagic.bot_engine.time.sleep")
    def test_wall_upgrade_does_not_interrupt_home_tap_retry(self, _sleep):
        engine = BotEngine({"upgrade_walls": True})
        engine._handle_popups = Mock(return_value=False)
        engine.wall_mod = Mock()
        adb = Mock(device="test")
        farm = FarmModule(adb, None, None, engine.settings, wall_mod=engine.wall_mod)
        farm._home_attack_failures = 1
        farm._handle_state = Mock()
        farm.tick()
        engine.wall_mod.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
