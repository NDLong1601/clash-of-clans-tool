"""Exercise real bar recognition and stateful deployment without emulator input."""

import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.attack_tactics import AttackTactics
from cocmagic.modules.hero_module import HeroModule
from cocmagic.modules.farm_module import (
    CardSlot, ComboProfile, FarmModule, FarmState, T_RETURN_HOME_NEW,
    T_HOME_ATTACK, RETURN_HOME_REGION, HOME_ATTACK_REGION,
)
from cocmagic.event_rewards import find_reward_panel
from cocmagic.troop_vision import detect_bar_cards, read_card_count, is_siege_card


def fixture(name):
    image = cv2.imread(config.BASE_DIR + "/tests/fixtures/" + name)
    return cv2.resize(image, (1600, 900))


def with_count(image, count, x=179):
    """Draw real count glyphs; the actual artwork and battlefield remain visible."""
    image = image.copy()
    badge = Image.new("RGB", (75, 50), (15, 15, 15))
    font = ImageFont.truetype(config.asset("Supercell-Magic.otf"), 22)
    ImageDraw.Draw(badge).text((0, 10), f"x{count}", font=font, fill="white")
    image[735:785, x - 10:x + 65] = cv2.cvtColor(np.asarray(badge), cv2.COLOR_RGB2BGR)
    return image


def button_screen(path, region):
    image = np.zeros((900, 1600, 3), np.uint8)
    template = cv2.imread(path)
    x, y, _, _ = region
    h, w = template.shape[:2]
    image[y:y + h, x:x + w] = template
    return image


class RealArmyBarTests(unittest.TestCase):
    def test_decorated_scenery_full_profile_uses_actual_frames_and_artwork(self):
        image = fixture("user_decorated_scenery.png")
        adb = ADBController()
        farm = FarmModule(adb, None, HeroModule(adb, {}), {})
        self.assertEqual([179, 295, 439, 566, 692, 809, 931, 1066, 1188],
                         [x for x, _ in detect_bar_cards(image)])
        profile = farm._calibrate_combo(image)
        self.assertEqual([("troop", 179, ""), ("troop", 295, ""),
                          ("siege", 439, ""), ("spell", 1066, "rage"),
                          ("spell", 1188, "totem")],
                         [(s.role, s.x, s.name) for s in profile.cards])
        self.assertEqual({"king", "queen", "warden", "prince"},
                         {name for name, _, _ in profile.heroes})
        self.assertTrue(all(y == 840 for _, _, y in profile.heroes))

    def test_different_prince_portrait_reserves_hero_slot(self):
        image = fixture("user_electro_battle.jpg")
        adb = ADBController()
        profile = FarmModule(adb, None, HeroModule(adb, {}), {})._calibrate_combo(image)
        self.assertEqual({"prince", "king", "warden"},
                         {name for name, _, _ in profile.heroes})
        self.assertEqual(["troop", "troop", "spell", "spell"],
                         [s.role for s in profile.cards])

    def test_disabled_gray_heroes_still_reserve_slots(self):
        image = fixture("user_decorated_scenery.png")
        adb = ADBController()
        heroes = HeroModule(adb, {})
        self.assertEqual([], heroes.find_ready_heroes(image))
        self.assertEqual(4, len(heroes.find_ready_heroes(image, enabled_only=False)))

    def test_two_digit_counts_and_single_spell_counts_from_real_images(self):
        image = fixture("user_decorated_scenery.png")
        self.assertEqual(10, read_card_count(image, 179, 840))
        self.assertEqual(3, read_card_count(image, 1066, 840))
        self.assertEqual(1, read_card_count(image, 1188, 840))
        self.assertEqual(10, read_card_count(fixture("battle_screen.png"), 932, 840))

    def test_siege_portrait_is_identified_without_confusing_troops_and_heroes(self):
        image = fixture("user_decorated_scenery.png")
        for x in [179, 295, 439, 566, 692, 809, 931, 1066, 1188]:
            with self.subTest(x=x):
                self.assertEqual(x == 439, is_siege_card(image, x, 840))

    def test_count_rendering_supports_full_armies_and_zero(self):
        image = fixture("user_decorated_scenery.png")
        for count in [0, 1, 7, 10, 30, 65, 100]:
            with self.subTest(count=count):
                self.assertEqual(count, read_card_count(with_count(image, count), 179, 840))

    def test_partial_leading_one_is_uncertain_and_cannot_be_read_as_zero(self):
        image = with_count(fixture("user_decorated_scenery.png"), 10)
        image[735:785, 189:195] = (15, 15, 15)
        self.assertIsNone(read_card_count(image, 179, 840))


@patch("cocmagic.modules.farm_module.time.sleep")
class VerifiedDeploymentTests(unittest.TestCase):
    def run_army(self, count, perimeter, accepted_index=0):
        image = fixture("user_decorated_scenery.png" if perimeter else "battle_screen.png")
        adb = Mock()
        adb.tap.return_value = True
        farm = FarmModule(adb, None, Mock(), {"attack_around": False})
        farm._battle_plan = farm.planner.plan(image)
        farm._attack_tactics = AttackTactics.from_battle(farm._battle_plan, image)
        farm._combo_profile = ComboProfile([CardSlot(179, 840, "troop")], [], (900, 1600))
        candidates = (farm._battle_plan.troop_points if perimeter else
                      farm._attack_tactics.main_points)
        accepted = candidates[accepted_index]
        ui = {"remaining": count, "drops": [], "probes": []}

        def frame(**kwargs):
            return with_count(image, ui["remaining"])

        def taps(points, **kwargs):
            ui["probes"].append(points)
            for p in points:
                if p == accepted and ui["remaining"]:
                    ui["remaining"] -= 1
                    ui["drops"].append(p)
            return True

        adb.screenshot.side_effect = frame
        adb.tap_many.side_effect = taps
        with patch("cocmagic.modules.farm_module.is_electro_card", return_value=False):
            farm._deploy_all_troops(frame())
        return farm, ui, accepted

    def test_standard_attack_drops_more_than_twenty_and_confirms_each_new_point(self, _sleep):
        farm, ui, accepted = self.run_army(30, False)
        self.assertEqual(0, ui["remaining"])
        self.assertEqual(30, len(ui["drops"]))
        self.assertEqual([accepted], farm._confirmed_main_points)
        self.assertFalse(farm._deployment_rejected)
        self.assertIsNone(farm.halt_reason)
        self.assertTrue(all(len(points) == 1 or set(points) == {accepted}
                            for points in ui["probes"]))

    def test_large_perimeter_army_survives_rejected_edges_and_drops_all_sixty_five(self, _sleep):
        farm, ui, accepted = self.run_army(65, True, 3)
        self.assertEqual(0, ui["remaining"])
        self.assertEqual(65, len(ui["drops"]))
        self.assertEqual([accepted], farm._confirmed_main_points)
        self.assertEqual(accepted, farm._attack_tactics.entry)
        self.assertIsNone(farm.halt_reason)

    def test_selection_redraw_or_gray_art_with_unchanged_count_is_not_a_drop(self, _sleep):
        image = fixture("user_decorated_scenery.png")
        before = with_count(image, 10)
        gray = cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        for count in [10, 11]:
            with self.subTest(count=count):
                adb = Mock()
                adb.screenshot.return_value = with_count(gray, count)
                farm = FarmModule(adb, None, None, {})
                _, accepted = farm._verify_card_use(before, CardSlot(179, 840, "troop"))
                self.assertFalse(accepted)

    def test_lagging_counter_reads_fresh_frames_and_accepts_only_decrease(self, _sleep):
        image = fixture("user_decorated_scenery.png")
        before, after = with_count(image, 10), with_count(image, 9)
        adb = Mock()
        adb.screenshot.side_effect = [before, before, after]
        farm = FarmModule(adb, None, None, {})
        result, accepted = farm._verify_card_use(before, CardSlot(179, 840, "troop"))
        self.assertTrue(accepted)
        self.assertIs(after, result)
        self.assertTrue(all(c.kwargs == {"use_cache": False}
                            for c in adb.screenshot.call_args_list))

    def test_colored_empty_spell_is_not_selected_or_cast_during_gray_animation(self, _sleep):
        image = with_count(fixture("battle_screen.png"), 0, 811)
        adb = Mock()
        adb.screenshot.return_value = image
        farm = FarmModule(adb, None, Mock(), {})
        farm._combo_profile = ComboProfile([CardSlot(811, 840, "spell", "freeze")], [], (900, 1600))
        farm._attack_tactics = AttackTactics.from_battle(farm.planner.plan(image), image)
        farm._deploy_spells()
        adb.tap.assert_not_called()
        adb.tap_many.assert_not_called()


@patch("cocmagic.modules.farm_module.time.sleep")
class BattleInterruptionTests(unittest.TestCase):
    def make_farm(self, event=True):
        adb = Mock()
        adb.tap.return_value = adb.tap_many.return_value = True
        matcher = ADBController()
        adb.is_visible.side_effect = matcher.is_visible
        farm = FarmModule(adb, None, Mock(), {"event_mode": event})
        farm.state = FarmState.ATTACKING
        return farm

    def test_result_after_hundred_percent_bonus_cancels_card_restore_and_map_tap(self, _sleep):
        farm = self.make_farm()
        panel = fixture("event_reward_panel.png")
        result = button_screen(T_RETURN_HOME_NEW, RETURN_HOME_REGION)
        farm.adb.screenshot.side_effect = [panel, result]
        farm._selected_battle_card = (179, 840)
        farm._handle_state = lambda: farm._battle_tap(250, 650)
        self.assertTrue(farm.tick())
        self.assertEqual(FarmState.RESULT, farm.state)
        self.assertIsNone(farm.halt_reason)
        self.assertEqual([find_reward_panel(panel).preferred().point],
                         [c.args[:2] for c in farm.adb.tap.call_args_list])
        farm.adb.tap_many.assert_not_called()

    def test_result_mid_event_batch_cancels_every_remaining_target(self, _sleep):
        farm = self.make_farm()
        battle = fixture("battle_screen.png")
        result = button_screen(T_RETURN_HOME_NEW, RETURN_HOME_REGION)
        farm.adb.screenshot.side_effect = [battle, result]
        farm._handle_state = lambda: farm._battle_tap_many(
            [(250, 650), (350, 650), (450, 650)], interval=.04)
        self.assertTrue(farm.tick())
        self.assertEqual([(250, 650)], [c.args[:2] for c in farm.adb.tap.call_args_list])
        self.assertEqual(FarmState.RESULT, farm.state)

    def test_home_during_deployment_does_not_receive_more_inputs(self, _sleep):
        farm = self.make_farm()
        farm.adb.screenshot.return_value = button_screen(T_HOME_ATTACK, HOME_ATTACK_REGION)
        farm._handle_state = lambda: farm._battle_tap(250, 650)
        self.assertTrue(farm.tick())
        self.assertEqual(FarmState.RESULT, farm.state)
        farm.adb.tap.assert_not_called()

    def test_default_attack_cancels_next_group_after_result_appears(self, _sleep):
        farm = self.make_farm(False)
        battle = fixture("battle_screen.png")
        farm._battle_plan = farm.planner.plan(battle)
        farm._attack_tactics = AttackTactics.from_battle(farm._battle_plan, battle)
        farm._confirmed_main_points = [(300, 600)]
        farm._combo_profile = ComboProfile([], [("king", 555, 840), ("warden", 676, 840)], (900, 1600))
        farm.hero_mod.get_enabled_heroes.return_value = ["king", "warden"]
        farm._card_depleted = Mock(return_value=False)
        farm.adb.screenshot.side_effect = [battle, button_screen(T_RETURN_HOME_NEW, RETURN_HOME_REGION)]
        farm._handle_state = farm._deploy_cached_heroes
        self.assertTrue(farm.tick())
        farm.adb.tap_many.assert_called_once_with(
            [(555, 790), (300, 600), (676, 790), (300, 600)], interval=.03)
        self.assertEqual(FarmState.RESULT, farm.state)

    def test_bonus_title_flicker_waits_for_two_clear_frames_before_reselection(self, _sleep):
        farm = self.make_farm()
        panel = fixture("event_reward_panel.png")
        battle = fixture("battle_screen.png")
        farm._selected_battle_card = (179, 840)
        farm.adb.screenshot.side_effect = [panel, battle, panel, battle, battle, battle]
        farm._handle_state = lambda: farm._screenshot()
        self.assertTrue(farm.tick())
        self.assertEqual([find_reward_panel(panel).preferred().point, (179, 840)],
                         [c.args[:2] for c in farm.adb.tap.call_args_list])
        self.assertEqual(6, farm.adb.screenshot.call_count)

    def test_result_mid_ability_group_in_battle_wait_cancels_remaining_abilities(self, _sleep):
        farm = self.make_farm()
        farm.state = FarmState.BATTLE_WAIT
        farm.adb.screenshot.side_effect = [fixture("battle_screen.png"),
                                           button_screen(T_RETURN_HOME_NEW, RETURN_HOME_REGION)]
        farm._handle_state = lambda: farm._battle_tap_many(
            [(555, 840), (676, 840), (434, 840)], interval=.04)
        self.assertTrue(farm.tick())
        self.assertEqual(FarmState.RESULT, farm.state)
        self.assertEqual([(555, 840)], [c.args[:2] for c in farm.adb.tap.call_args_list])

    def test_animating_bonus_without_title_blocks_map_input_until_resource_is_visible(self, _sleep):
        farm = self.make_farm()
        panel = fixture("event_reward_panel.png")
        partial = panel.copy()
        partial[84:228, 350:1250] = 0
        self.assertEqual((), find_reward_panel(partial).choices)
        battle = fixture("battle_screen.png")
        farm._selected_battle_card = (179, 840)
        farm.adb.screenshot.side_effect = [partial, panel, battle, battle, battle]
        farm._handle_state = lambda: farm._battle_tap(250, 650)
        self.assertTrue(farm.tick())
        self.assertIsNone(farm.halt_reason)
        self.assertEqual([find_reward_panel(panel).preferred().point, (179, 840), (250, 650)],
                         [c.args[:2] for c in farm.adb.tap.call_args_list])

    def test_unknown_exception_cancels_transaction_without_blind_home_inputs(self, _sleep):
        farm = self.make_farm(False)
        farm.adb.screenshot.return_value = button_screen(T_RETURN_HOME_NEW, RETURN_HOME_REGION)
        farm._handle_state = Mock(side_effect=RuntimeError("Interrupted operation"))
        with patch("traceback.print_exc"):
            self.assertFalse(farm.tick())
        self.assertEqual(FarmState.RECOVERING, farm.state)
        self.assertIn('Interrupted operation', farm.halt_reason)
        farm.adb.tap.assert_not_called()
        farm.adb.tap_many.assert_not_called()


@patch("cocmagic.modules.farm_module.time.sleep")
class CompleteAttackTests(unittest.TestCase):
    def test_recognize_select_deploy_heroes_cast_and_handle_three_bonuses(self, _sleep):
        """Use the real image pipeline, only simulating the game's input response."""
        for event in (False, True):
            with self.subTest(event=event):
                battle = fixture("battle_screen.png")
                panel = fixture("event_reward_panel.png")
                result = button_screen(T_RETURN_HOME_NEW, RETURN_HOME_REGION)
                adb = ADBController()
                settings = {"event_mode": event, "use_king": True, "use_prince": True,
                            "use_warden": True, "warden_ability_delay": 0}
                heroes = HeroModule(adb, settings)
                farm = FarmModule(adb, None, heroes, settings)
                farm.state = FarmState.ATTACKING
                profile = farm._calibrate_combo(battle)
                farm._combo_profile = profile
                cards = {(s.x, s.y): s for s in profile.cards}
                hero_points = {(x, y - 50): name for name, x, y in profile.heroes}
                ui = {"remaining": {s.x: read_card_count(battle, s.x, s.y) for s in profile.cards},
                      "selected": None, "deployed": [], "abilities": [],
                      "modal": False, "reward_count": 0, "drops": 0, "result": False}

                def frame(**kwargs):
                    if ui["modal"]:
                        return panel
                    if ui["result"]:
                        return result
                    image = battle.copy()
                    for s in profile.cards:
                        if ui["remaining"][s.x] == 0:
                            art = image[770:875, s.x - 45:s.x + 45]
                            art[:] = cv2.cvtColor(cv2.cvtColor(art, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                        image = with_count(image, ui["remaining"][s.x], s.x)
                    for p in ui["deployed"]:
                        x, _ = p
                        art = image[770:875, x - 45:x + 45]
                        art[:] = cv2.cvtColor(cv2.cvtColor(art, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                    return image

                def tap(x, y, **kwargs):
                    p = (x, y)
                    self.assertFalse(ui["result"], "Deployment input reached the result screen")
                    if ui["modal"]:
                        if p == find_reward_panel(panel).preferred().point:
                            ui["modal"] = False
                            ui["selected"] = None
                            ui["reward_count"] += 1
                        else:
                            self.assertTrue(farm._reward_safe_point(p),
                                            "Queued troop/hero input could choose a reward")
                    elif p in cards:
                        ui["selected"] = p
                    elif p in hero_points:
                        if p in ui["deployed"]:
                            ui["abilities"].append(p)
                        ui["selected"] = p
                    else:
                        selected = ui["selected"]
                        self.assertIsNotNone(selected, "Map tap had no selected card")
                        if selected in hero_points:
                            self.assertNotIn(selected, ui["deployed"])
                            ui["deployed"].append(selected)
                        else:
                            slot = cards[selected]
                            self.assertGreater(ui["remaining"][slot.x], 0)
                            ui["remaining"][slot.x] -= 1
                            ui["drops"] += 1
                            if event and ui["drops"] in (5, 15, 25):
                                ui["modal"] = True
                    return True

                def many(points, **kwargs):
                    return all(tap(*p) for p in points)

                adb.screenshot = Mock(side_effect=frame)
                adb.tap = Mock(side_effect=tap)
                adb.tap_many = Mock(side_effect=many)
                farm._handle_state = farm._state_attacking
                self.assertTrue(farm.tick())
                self.assertIsNone(farm.halt_reason)
                self.assertEqual(FarmState.BATTLE_WAIT, farm.state)
                self.assertTrue(all(count == 0 for count in ui["remaining"].values()))
                self.assertEqual(set(hero_points), set(ui["deployed"]))
                self.assertEqual(3, len(ui["deployed"]))
                self.assertEqual(set(hero_points), set(ui["abilities"]))
                self.assertEqual(3, len(ui["abilities"]))
                self.assertEqual(3 if event else 0, ui["reward_count"])


if __name__ == "__main__":
    unittest.main()
