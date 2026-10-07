"""Regressions from bandicam 2026-10-04 16-58-59-503.mp4."""

import unittest
from unittest.mock import Mock, patch

import cv2

from cocmagic.adb_controller import ADBController
from cocmagic.attack_tactics import AttackTactics
from cocmagic.event_rewards import find_reward_panel
from cocmagic.modules.farm_module import CardSlot, ComboProfile, FarmModule, FarmState
from cocmagic.modules.hero_module import HeroModule
from test_battle_input_review import button_screen, fixture, with_count
from cocmagic.modules.farm_module import T_RETURN_HOME_NEW, RETURN_HOME_REGION


def deployed(image, x, y=840):
    image = image.copy()
    image[y - 122:y - 108, x - 40:x + 40] = (30, 30, 30)
    image[y - 118:y - 111, x - 38:x + 38] = (40, 220, 60)
    return image


class VideoVisionTests(unittest.TestCase):
    def test_gold_rarity_frame_does_not_hide_dark_elixir(self):
        image = fixture("event_video_gold_reward.png")
        panel = find_reward_panel(image)
        self.assertEqual(["dark"], [c.resource for c in panel.choices])
        self.assertGreater(panel.preferred("elixir").point[0], 1000)
        for size in [(1050, 591), (1280, 720), (1600, 900)]:
            self.assertEqual("dark", find_reward_panel(cv2.resize(image, size)).preferred().resource)

    def test_video_warden_has_no_health_strip_despite_logged_deployment(self):
        image = fixture("event_video_warden_undeployed.png")
        self.assertTrue(HeroModule.has_deployed_health(image, 562, 840))
        self.assertTrue(HeroModule.has_deployed_health(image, 683, 840))
        self.assertFalse(HeroModule.has_deployed_health(image, 804, 840))
        self.assertFalse(HeroModule.has_deployed_health(image, 925, 840))
        self.assertEqual((804, 790), HeroModule.portrait_point(804, 840))

    def test_grass_above_idle_hero_is_not_deployment_confirmation(self):
        image = fixture("event_video_army.png")
        for x in [562, 683, 804, 925]:
            self.assertFalse(HeroModule.has_deployed_health(image, x, 840))
            self.assertTrue(HeroModule.has_deployed_health(deployed(image, x), x, 840))

    def test_warden_mode_menu_is_not_a_resource_reward(self):
        self.assertIsNone(find_reward_panel(fixture("event_video_warden_mode_menu.png")))


@patch("cocmagic.modules.farm_module.time.sleep")
class BurstInputTests(unittest.TestCase):
    def make_farm(self):
        image = fixture("event_video_army.png")
        adb = Mock()
        adb.tap.return_value = adb.tap_many.return_value = True
        matcher = ADBController()
        adb.is_visible.side_effect = matcher.is_visible
        heroes = HeroModule(adb, {"use_king": True, "use_queen": True,
                                  "use_warden": True, "use_royal_champ": True})
        farm = FarmModule(adb, None, heroes, {"event_mode": True, "warden_ability_delay": 0})
        farm.state = FarmState.ATTACKING
        farm._battle_plan = farm.planner.plan(image)
        farm._attack_tactics = AttackTactics.from_battle(farm._battle_plan, image)
        farm._confirmed_main_points = [(1160, 180)]
        farm._hero_entry = (1160, 180)
        return farm, image

    def test_large_army_probes_once_then_sends_remaining_twenty_nine_as_one_burst(self, _sleep):
        farm, image = self.make_farm()
        slot = CardSlot(292, 840, "troop")
        ui = {"remaining": 30}

        def frame(**kw):
            return with_count(image, ui["remaining"], slot.x)

        def inputs(points, **kw):
            ui["remaining"] -= sum(p == (1160, 180) for p in points)
            return True

        farm.adb.screenshot.side_effect = frame
        farm.adb.tap_many.side_effect = inputs
        _, points = farm._deploy_regular_card(frame(), slot, [(1160, 180)])
        self.assertEqual(0, ui["remaining"])
        self.assertEqual([(1160, 180)], points)
        self.assertEqual([1, 1, 29], [len(c.args[0]) for c in farm.adb.tap_many.call_args_list])
        self.assertLessEqual(farm.adb.screenshot.call_count, 2)
        farm.adb.tap.assert_not_called()

    def test_next_card_reuses_verified_point_without_another_probe_or_selection_capture(self, _sleep):
        farm, image = self.make_farm()
        slot = CardSlot(292, 840, "troop")
        ui = {"remaining": 30}
        farm._verified_battle_points.add((1160, 180))
        farm.adb.screenshot.side_effect = lambda **kw: with_count(image, ui["remaining"], slot.x)

        def inputs(points, **kw):
            ui["remaining"] -= sum(p == (1160, 180) for p in points)
            return True

        farm.adb.tap_many.side_effect = inputs
        farm._deploy_regular_card(with_count(image, 30, slot.x), slot, [(1160, 180)])
        self.assertEqual([1, 30], [len(c.args[0]) for c in farm.adb.tap_many.call_args_list])
        self.assertEqual(1, farm.adb.screenshot.call_count)

    def test_bonus_mid_troop_burst_resumes_only_unconsumed_units(self, _sleep):
        farm, image = self.make_farm()
        panel = fixture("event_video_gold_reward.png")
        reward = find_reward_panel(panel).preferred().point
        slot = CardSlot(292, 840, "troop")
        farm._verified_battle_points.add((1160, 180))
        ui = {"remaining": 30, "modal": False, "rewarded": False, "drops": 0}

        def frame(**kw):
            return panel if ui["modal"] else with_count(image, ui["remaining"], slot.x)

        def tap(x, y, **kw):
            self.assertEqual(reward, (x, y)) if ui["modal"] else None
            if ui["modal"]:
                ui.update(modal=False, rewarded=True)
            return True

        def inputs(points, **kw):
            for point in points:
                self.assertTrue(farm._reward_safe_point(point))
                if ui["modal"]:
                    continue  # Real modal swallows commands outside its cards.
                if point == (1160, 180):
                    self.assertGreater(ui["remaining"], 0)
                    ui["remaining"] -= 1
                    ui["drops"] += 1
                    if ui["drops"] == 4 and not ui["rewarded"]:
                        ui["modal"] = True
            return True

        farm.adb.screenshot.side_effect = frame
        farm.adb.tap.side_effect = tap
        farm.adb.tap_many.side_effect = inputs
        farm._deploy_regular_card(frame(), slot, [(1160, 180)])
        self.assertEqual(30, ui["drops"])
        self.assertEqual(0, ui["remaining"])
        self.assertEqual([1, 30, 26], [len(c.args[0]) for c in farm.adb.tap_many.call_args_list])
        self.assertEqual(1, farm._reward_generation)
        self.assertIsNone(farm.halt_reason)

    def test_hero_pairs_are_one_group_and_warden_never_hits_mode_switch(self, _sleep):
        farm, image = self.make_farm()
        hero_slots = [("king", 562, 840), ("queen", 683, 840),
                      ("warden", 804, 840), ("royal_champ", 925, 840)]
        farm._combo_profile = ComboProfile([], hero_slots, (900, 1600))
        after = image
        for _, x, y in hero_slots:
            after = deployed(after, x, y)
        farm.adb.screenshot.side_effect = [image, after]
        farm._deploy_cached_heroes()
        expected = [point for _, x, y in hero_slots for point in ((x, 790), (1160, 180))]
        farm.adb.tap_many.assert_called_once_with(expected, interval=.03)
        farm.adb.tap.assert_not_called()
        self.assertEqual(4, len(farm._deployed_hero_slots))
        self.assertEqual((804, 840), farm._warden_slot)
        self.assertIsNone(farm.halt_reason)

    def test_late_warden_health_redraw_does_not_send_an_accidental_second_portrait_click(self, _sleep):
        farm, image = self.make_farm()
        farm._combo_profile = ComboProfile([], [("warden", 804, 840)], (900, 1600))
        farm.adb.screenshot.side_effect = [image, image, deployed(image, 804)]
        farm._deploy_cached_heroes()
        farm.adb.tap_many.assert_called_once_with([(804, 790), (1160, 180)], interval=.03)
        self.assertEqual((804, 840), farm._warden_slot)
        self.assertFalse(farm._hero_abilities_used)
        self.assertIsNone(farm.halt_reason)

    def test_bonus_mid_hero_group_retries_only_heroes_not_yet_deployed(self, _sleep):
        farm, image = self.make_farm()
        hero_slots = [("king", 562, 840), ("queen", 683, 840),
                      ("warden", 804, 840), ("royal_champ", 925, 840)]
        farm._combo_profile = ComboProfile([], hero_slots, (900, 1600))
        panel = fixture("event_video_gold_reward.png")
        reward = find_reward_panel(panel).preferred().point
        ui = {"modal": False, "selected": None, "deployed": [], "rewarded": False}
        icons = {(x, 790): name for name, x, _ in hero_slots}

        def frame(**kw):
            if ui["modal"]:
                return panel
            result = image
            for name, x, y in hero_slots:
                if name in ui["deployed"]:
                    result = deployed(result, x, y)
            return result

        def inputs(points, **kw):
            for p in points:
                if ui["modal"]:
                    continue
                if p in icons:
                    self.assertNotIn(icons[p], ui["deployed"], "Deployed hero was clicked as a new hero")
                    ui["selected"] = icons[p]
                else:
                    ui["deployed"].append(ui["selected"])
                    ui["selected"] = None
                    if len(ui["deployed"]) == 2 and not ui["rewarded"]:
                        ui["modal"] = True
            return True

        def tap(x, y, **kw):
            self.assertEqual(reward, (x, y))
            ui.update(modal=False, rewarded=True)
            return True

        farm.adb.screenshot.side_effect = frame
        farm.adb.tap_many.side_effect = inputs
        farm.adb.tap.side_effect = tap
        farm._deploy_cached_heroes()
        self.assertEqual(["king", "queen", "warden", "royal_champ"], ui["deployed"])
        self.assertEqual([8, 4], [len(c.args[0]) for c in farm.adb.tap_many.call_args_list])
        self.assertIsNone(farm.halt_reason)

    def test_bonus_mid_abilities_completes_suffix_and_keeps_no_pending_group(self, _sleep):
        farm, image = self.make_farm()
        farm.state = FarmState.BATTLE_WAIT
        farm._deployed_hero_slots = {"king": (562, 840), "queen": (683, 840),
                                     "warden": (804, 840), "royal_champ": (925, 840)}
        farm._heroes_deployed_ts = farm._warden_deployed_ts = 1
        farm._warden_slot = (804, 840)
        panel = fixture("event_video_gold_reward.png")
        reward = find_reward_panel(panel).preferred().point
        ui = {"modal": False, "rewarded": False, "used": []}
        names = {(x, y - 50): name for name, (x, y) in farm._deployed_hero_slots.items()}

        def inputs(points, **kw):
            for p in points:
                if ui["modal"]:
                    continue
                name = names[p]
                if name not in ui["used"]:
                    ui["used"].append(name)
                if len(ui["used"]) == 1 and not ui["rewarded"]:
                    ui["modal"] = True
            return True

        def tap(x, y, **kw):
            self.assertEqual(reward, (x, y))
            ui.update(modal=False, rewarded=True)
            return True

        farm.adb.screenshot.side_effect = lambda **kw: panel if ui["modal"] else image
        farm.adb.tap_many.side_effect = inputs
        farm.adb.tap.side_effect = tap
        farm._maybe_activate_hero_abilities(image)
        self.assertEqual(["warden", "king", "queen", "royal_champ"], ui["used"])
        self.assertTrue(farm._hero_abilities_used)
        self.assertEqual([], farm._pending_ability_names)
        self.assertEqual(2, farm.adb.tap_many.call_count)
        self.assertIsNone(farm.halt_reason)

    def test_ocr_cache_reuses_one_frame_but_never_a_changed_count(self, _sleep):
        farm, image = self.make_farm()
        first, second = with_count(image, 30, 292), with_count(image, 29, 292)
        slot = CardSlot(292, 840, "troop")
        from cocmagic.troop_vision import read_card_count
        with patch("cocmagic.modules.farm_module.read_card_count", wraps=read_card_count) as read:
            for _ in range(5):
                self.assertEqual(30, farm._read_card_count(first, 292, 840))
                self.assertFalse(farm._card_depleted(first, slot))
            self.assertEqual(1, read.call_count)
            self.assertEqual(29, farm._read_card_count(second, 292, 840))
            self.assertEqual(2, read.call_count)
        farm.reset_after_reload()
        self.assertEqual(set(), farm._verified_battle_points)
        self.assertEqual([], farm._pending_ability_names)
        self.assertEqual({}, farm._count_cache)

    def test_result_after_ability_burst_cancels_pending_actions_in_battle_wait(self, _sleep):
        farm, image = self.make_farm()
        farm.state = FarmState.BATTLE_WAIT
        farm._deployed_hero_slots = {"warden": (804, 840), "king": (562, 840)}
        farm._warden_deployed_ts = 1
        farm._warden_slot = (804, 840)
        farm.adb.screenshot.return_value = button_screen(T_RETURN_HOME_NEW, RETURN_HOME_REGION)
        farm._handle_state = lambda: farm._maybe_activate_hero_abilities(image)
        self.assertTrue(farm.tick())
        self.assertEqual(FarmState.RESULT, farm.state)
        self.assertEqual(1, farm.adb.tap_many.call_count)
        farm.adb.tap.assert_not_called()

    def test_one_calibration_shares_bar_coordinates_with_hero_vision(self, _sleep):
        farm, image = self.make_farm()
        matcher = ADBController()
        farm.adb.find_template.side_effect = matcher.find_template
        farm.adb._load_template.side_effect = matcher._load_template
        with patch("cocmagic.modules.hero_module.detect_bar_cards") as second_scan:
            profile = farm._calibrate_combo(image)
        second_scan.assert_not_called()
        self.assertEqual(["troop", "troop", "siege", "spell", "spell"],
                         [s.role for s in profile.cards])
        self.assertEqual(4, len(profile.heroes))


if __name__ == "__main__":
    unittest.main()
