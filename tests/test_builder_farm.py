"""Builder GĐ5 lifecycle/receipts; fake input is explicitly offline evidence."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import threading
import hashlib
import json
import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np

from cocmagic import config
from cocmagic.builder_vision import (
    BuilderBattleReader,
    BuilderSlot,
    ArmyObservation,
    BattleObservation,
    SlotState,
    AbilityState,
)
from cocmagic.builder_tactics import BuilderTactics
from cocmagic.builder_screen_reader import (
    Capture,
    ScreenObservation,
    ScreenKind,
    Village,
    StarBonusObservation,
    StarBonusState,
)
from cocmagic.modules.builder_farm_module import BuilderFarmModule, BuilderPhase
from cocmagic.village_module import ModuleScreen
from cocmagic.battle_planner import BattlePlan
from cocmagic.camera_controller import CameraStatus

FIXTURES = Path(config.BASE_DIR) / "tests/fixtures/dual_village/builder"


def fixture(name):
    image = cv2.imread(str(FIXTURES / (name + ".png")))
    if image is None:
        raise AssertionError(name)
    return image


def slot(
    key="camp:1",
    state=SlotState.UNDEPLOYED,
    ability=AbilityState.READY,
    role="troop",
    kind="baby_dragon",
    x=300,
):
    return BuilderSlot(
        key, kind, role, (x, 810), (x - 55, 700, 110, 190), state, ability
    )


class NativeReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = BuilderBattleReader()

    def test_evidence_bundle_hashes_match_saved_assets_and_fixtures(self):
        art = Path(config.asset("dual_village/builder"))
        manifests = [
            (
                art,
                json.loads((art / "manifest.json").read_text(encoding="utf-8"))[
                    "assets"
                ].values(),
            ),
            (
                FIXTURES,
                json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))[
                    "fixtures"
                ],
            ),
        ]
        for directory, rows in manifests:
            for row in rows:
                with self.subTest(path=row["path"]):
                    path = directory / row["path"]
                    self.assertEqual(
                        row["sha256"], hashlib.sha256(path.read_bytes()).hexdigest()
                    )
                    self.assertIsNotNone(cv2.imread(str(path)))

    def test_native_home_shadow_does_not_hide_clear_no_star_button(self):
        from cocmagic.builder_screen_reader import StarBonusReader

        reader = StarBonusReader(self.reader)
        image = fixture("home-shadow")
        first = reader.observe(Capture(image, 1, 1.0, 0))
        second = reader.observe(Capture(image.copy(), 2, 1.5, 0))
        self.assertEqual(StarBonusState.UNKNOWN, first.state)
        self.assertEqual(StarBonusState.COMPLETE, second.state)
        image[690:715, 20:195] = 0
        self.assertEqual(
            StarBonusState.UNKNOWN, reader.observe(Capture(image, 3, 2.0, 0)).state
        )

    def test_native_scout_has_six_camps_and_machine(self):
        observation = self.reader.read_bar(fixture("scout"))
        self.assertTrue(observation.valid, observation.reason)
        self.assertEqual(
            ["battle_machine"] + [f"camp:{i}" for i in range(1, 7)],
            [s.key for s in observation.slots],
        )
        self.assertTrue(all(s.state == SlotState.UNDEPLOYED for s in observation.slots))

    def test_native_deployment_receipt_and_hero_state(self):
        observation = self.reader.read_bar(fixture("deployed"))
        self.assertTrue(observation.valid)
        bykey = {s.key: s for s in observation.slots}
        self.assertEqual(SlotState.DEPLOYED, bykey["camp:1"].state)
        self.assertEqual(AbilityState.READY, bykey["camp:1"].ability)
        self.assertEqual(SlotState.DEPLOYED, bykey["battle_machine"].state)

    def test_native_stage2_survivor_dead_reinforcement_and_used_skill(self):
        observation = self.reader.read_bar(fixture("stage2-used"))
        self.assertTrue(observation.valid, observation)
        bykey = {s.key: s for s in observation.slots}
        self.assertEqual(SlotState.DEAD, bykey["camp:1"].state)
        self.assertEqual(AbilityState.USED, bykey["camp:2"].ability)
        self.assertEqual(SlotState.DEPLOYED, bykey["camp:2"].state)
        self.assertEqual(SlotState.UNDEPLOYED, bykey["camp:7"].state)
        self.assertEqual("battle_copter", bykey["battle_copter"].kind)
        self.assertEqual(
            ScreenKind.BATTLE, self.reader.classify(fixture("stage2-used")).kind
        )

    def test_no_hero_and_changed_slot_positions_do_not_shift_camp_ids(self):
        image = fixture("scout")
        image[690:900, 90:235] = image[690:900, 1200:1345]
        observation = self.reader.read_bar(image)
        self.assertTrue(observation.valid)
        self.assertEqual(
            [f"camp:{i}" for i in range(1, 7)], [s.key for s in observation.slots]
        )
        shifted = image.copy()
        shifted[700:900, 100:875] = image[700:900, 243:1018]
        shifted[700:900, 875:1018] = image[700:900, 1200:1343]
        self.assertEqual("camp:1", self.reader.read_bar(shifted).slots[0].key)

    def test_locked_placeholder_never_becomes_troop(self):
        observation = self.reader.read_army(fixture("army"))
        self.assertTrue(observation.valid)
        self.assertTrue(observation.complete)
        self.assertEqual(6, len([s for s in observation.slots if s.role == "primary"]))
        self.assertEqual(
            1, len([s for s in observation.slots if s.role == "reinforcement"])
        )
        self.assertIsNone(observation.choice)
        empty = self.reader.read_army(fixture("army-empty"))
        self.assertIsNotNone(empty.choice)
        self.assertFalse(empty.complete)

    def test_native_wrong_reinforcement_is_distinguished_from_correct_primary_camps(
        self,
    ):
        observation = self.reader.read_army(fixture("army-wrong-reinforcement"))
        self.assertTrue(observation.valid)
        self.assertTrue(
            all(
                s.kind == "baby_dragon"
                for s in observation.slots
                if s.role == "primary"
            )
        )
        reinforcement = next(s for s in observation.slots if s.role == "reinforcement")
        self.assertEqual("bomber", reinforcement.kind)
        self.assertIsNotNone(reinforcement.remove)

    def test_main_battle_and_blank_are_not_builder_battle(self):
        image = cv2.imread(
            str(
                Path(config.BASE_DIR)
                / "tests/fixtures/dual_village/navigation/battle.jpg"
            )
        )
        self.assertFalse(self.reader.battle(image).valid)
        self.assertFalse(self.reader.read_bar(np.zeros((900, 1600, 3), np.uint8)).valid)

    def test_native_builder_result_requires_return_and_total_damage(self):
        result = self.reader.classify(fixture("result"))
        self.assertEqual(ScreenKind.RESULT, result.kind)
        self.assertEqual(Village.BUILDER, result.village)
        self.assertTrue(result.points.get("return"))
        without_button = fixture("result")
        without_button[700:815, 650:950] = 0
        self.assertNotEqual(
            ScreenKind.RESULT, self.reader.classify(without_button).kind
        )

    def test_cart_remains_identifiable_when_resource_icon_partly_covers_it(self):
        image = fixture("cart-covered")
        point = self.reader.map_target(image, "cart_object")
        self.assertIsNotNone(point)
        self.assertEqual(ScreenKind.BUILDER_HOME, self.reader.classify(image).kind)

    def test_native_hero_charge_and_white_cooldown_are_separate_states(self):
        ready = self.reader.read_bar(fixture("hero-ready"))
        cooldown = self.reader.read_bar(fixture("hero-cooldown"))
        self.assertTrue(ready.valid)
        self.assertTrue(cooldown.valid)
        hero = next(s for s in ready.slots if s.role == "hero")
        after = next(s for s in cooldown.slots if s.role == "hero")
        self.assertEqual(AbilityState.READY, hero.ability)
        self.assertEqual(SlotState.DEPLOYED, after.state)
        self.assertEqual(AbilityState.CHARGING, after.ability)

    def test_unavailable_gray_hero_does_not_block_other_camps(self):
        image = fixture("scout")
        gray = cv2.cvtColor(image[730:895, 100:225], cv2.COLOR_BGR2GRAY)
        image[730:895, 100:225] = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        observation = self.reader.read_bar(image)
        self.assertTrue(observation.valid)
        hero = next(s for s in observation.slots if s.role == "hero")
        self.assertEqual(SlotState.UNAVAILABLE, hero.state)

    def test_green_map_behind_undeployed_hero_is_not_health_receipt(self):
        image = fixture("scout")
        image[100:730] = (30, 170, 30)
        observation = self.reader.read_bar(image)
        self.assertTrue(observation.valid)
        hero = next(s for s in observation.slots if s.role == "hero")
        self.assertEqual(SlotState.UNDEPLOYED, hero.state)

    def test_native_cart_defending_is_identified_without_waiting_for_battle(self):
        screen = self.reader.classify(fixture("cart-defending"))
        self.assertEqual("cart", screen.panel)
        self.assertTrue(screen.points.get("cart_defending"))
        self.assertTrue(screen.points.get("cart_disabled"))
        self.assertFalse(screen.points.get("cart_collect"))

    def test_native_disabled_cart_with_money_does_not_become_empty(self):
        screen = self.reader.classify(fixture("cart-disabled-balance"))
        self.assertEqual("cart", screen.panel)
        self.assertTrue(screen.points.get("cart_disabled"))
        self.assertFalse(
            screen.points.get("cart_empty") or screen.points.get("cart_defending")
        )

    def test_native_menu_revalidates_primary_lineup_and_visible_x1_counts(self):
        observation = self.reader.read_menu_army(fixture("menu"))
        self.assertTrue(observation.valid)
        troops = [s for s in observation.slots if s.role != "hero"]
        self.assertEqual(6, len(troops))
        self.assertTrue(all(s.kind == "baby_dragon" and s.count == 1 for s in troops))

    def test_selected_survivor_and_reinforcement_are_fresh_undeployed_slots(self):
        observation = self.reader.read_bar(fixture("survivor-selected"))
        self.assertTrue(observation.valid)
        bykey = {s.key: s for s in observation.slots}
        self.assertEqual(SlotState.UNDEPLOYED, bykey["camp:5"].state)
        self.assertEqual("baby_dragon", bykey["camp:5"].kind)
        self.assertEqual("reinforcement", bykey["camp:7"].role)
        self.assertEqual(SlotState.UNDEPLOYED, bykey["camp:7"].state)

    def test_camp_label_survives_frame_left_edge_offset(self):
        observation = self.reader.read_bar(fixture("camp4-offset"))
        self.assertTrue(observation.valid)
        self.assertEqual(
            ["battle_machine"] + [f"camp:{i}" for i in range(1, 7)],
            [s.key for s in observation.slots],
        )


class TacticsTests(unittest.TestCase):
    def plan(self, tactics):
        tactics.plan = BattlePlan(
            [(400, 330), (1150, 300), (500, 590), (1200, 520)],
            (800, 440),
            1.0,
            np.zeros((4, 2)),
            camera_revision=2,
        )

    def test_two_strategies_have_different_distribution(self):
        for mode in ("around", "single_point"):
            tactics = BuilderTactics(mode)
            self.plan(tactics)
            points = []
            for i in range(4):
                s = slot(f"camp:{i + 1}")
                p = tactics.point(s, 2)
                points.append(p)
                tactics.receipt(s, p, True, i)
            self.assertEqual(4 if mode == "around" else 1, len(set(points)))

    def test_rejected_single_point_is_replaced_only_after_receipt(self):
        tactics = BuilderTactics("single_point")
        self.plan(tactics)
        s = slot()
        first = tactics.point(s, 2)
        tactics.receipt(s, first, False, 1.0)
        self.assertNotEqual(first, tactics.point(s, 2))
        self.assertIsNone(tactics.point(s, 3))

    def test_around_rejects_one_candidate_but_uses_other_edges(self):
        tactics = BuilderTactics("around")
        self.plan(tactics)
        first = tactics.point(slot(), 2)
        tactics.receipt(slot(), first, False, 0.0)
        second = tactics.point(slot(), 2)
        self.assertNotEqual(first, second)
        tactics.receipt(slot(), second, True, 1.0)
        self.assertNotIn(first, tactics.accepted)

    def test_stage_change_preserves_used_or_unconfirmed_one_shot(self):
        tactics = BuilderTactics()
        tactics.used_abilities.add("camp:1")
        tactics.attempted_abilities.add("camp:2")
        tactics.reset_stage()
        tactics.deployed_at = {"camp:1": 0.0, "camp:2": 0.0, "camp:7": 0.0}
        self.assertFalse(
            tactics.skill_due(slot("camp:1", SlotState.DEPLOYED), 10.0, 1.0)
        )
        self.assertFalse(
            tactics.skill_due(slot("camp:2", SlotState.DEPLOYED), 10.0, 1.0)
        )
        self.assertTrue(
            tactics.skill_due(slot("camp:7", SlotState.DEPLOYED), 10.0, 1.0)
        )

    def test_unraised_header_is_not_a_consumed_skill_receipt(self):
        tactics = BuilderTactics()
        tactics.observe((slot(ability=AbilityState.USED),))
        self.assertFalse(tactics.used_abilities)
        tactics.observe((slot(state=SlotState.DEPLOYED, ability=AbilityState.USED),))
        self.assertIn("camp:1", tactics.used_abilities)

    def test_skill_delay_is_per_camp_and_requires_actual_ready(self):
        tactics = BuilderTactics()
        tactics.deployed_at = {"camp:1": 5.0}
        self.assertFalse(tactics.skill_due(slot(state=SlotState.DEPLOYED), 5.5, 1.0))
        self.assertTrue(tactics.skill_due(slot(state=SlotState.DEPLOYED), 6.5, 1.0))
        self.assertFalse(
            tactics.skill_due(
                slot(state=SlotState.DEPLOYED, ability=AbilityState.USED), 10.0, 1.0
            )
        )

    def test_stage_two_visible_footprint_is_from_image_and_probed(self):
        tactics = BuilderTactics()
        image = fixture("stage2-prep")
        plan = tactics.build(image, 7)
        self.assertIsNotNone(plan)
        self.assertEqual("builder_visual_footprint", plan.source)
        self.assertEqual(7, plan.camera_revision)
        self.assertGreaterEqual(len(plan.troop_points), 4)
        self.assertIsNone(BuilderTactics._visible_footprint(np.zeros_like(image), 7))

    def test_dark_stepped_builder_boundary_provides_current_outer_probes(self):
        plan = BuilderTactics().build(fixture("stepped-boundary"), 4)
        self.assertIsNotNone(plan)
        self.assertEqual("builder_red_segments", plan.source)
        self.assertTrue(plan.requires_probe)
        self.assertEqual(4, plan.camera_revision)
        self.assertIsNone(
            BuilderTactics._builder_boundary(np.zeros((900, 1600, 3), np.uint8), 4)
        )


class ModuleTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.stop = threading.Event()
        self.adb = Mock(device="fake-builder", camera_revision=0, stop_event=self.stop)
        self.adb.tap.return_value = True
        self.image = np.zeros((900, 1600, 3), np.uint8)
        self.reader = Mock()
        self.reader.capture.return_value = Capture(self.image, 1, 100.0, 0)
        self.reader.classify.return_value = ScreenObservation(
            ScreenKind.BUILDER_HOME,
            "home",
            Village.BUILDER,
            points={"attack": (100, 800)},
        )
        self.reader.read_bar.return_value = ArmyObservation((slot(),), True)
        self.reader.battle.return_value = BattleObservation(True, True)
        self.nav = Mock()
        self.nav.confirmed_home.return_value = (
            self.reader.capture.return_value,
            self.reader.classify.return_value,
        )
        self.rewards = Mock()
        self.rewards.claim_star_bonus.return_value = SimpleNamespace(
            success=True,
            claims=0,
            bonus=StarBonusObservation(StarBonusState.COMPLETE, 100.0, "complete"),
        )
        self.camera = Mock()
        self.module = BuilderFarmModule(
            self.adb,
            {
                "run_mode": "builder",
                "builder_collect_cart": False,
                "builder_auto_setup_baby_dragons": False,
            },
            reader=self.reader,
            navigator=self.nav,
            rewards=self.rewards,
            camera=self.camera,
            stop_event=self.stop,
            clock=lambda: self.now,
        )
        self.module.wait = lambda *_: None

    def battle_screen(self, preparing=True):
        self.reader.classify.return_value = ScreenObservation(
            ScreenKind.BATTLE, "builder", Village.BUILDER
        )
        self.reader.battle.return_value = BattleObservation(True, preparing)

    def test_complete_bonus_does_not_stop_builder_only(self):
        self.assertTrue(self.module.tick())
        self.adb.tap.assert_called_once_with(100, 800, jitter=0, delay=0.1)
        self.assertIsNone(self.module.halt_reason)
        self.assertEqual(BuilderPhase.SEARCH, self.module.phase)

    def test_unsettled_camera_waits_for_new_geometry_with_a_bounded_retry(self):
        self.battle_screen()
        self.module.settings["camera_auto_adjust"] = True
        self.module.tactics.build = Mock(return_value=None)
        self.camera.zoom.return_value = SimpleNamespace(
            status=CameraStatus.ERROR,
            reason="Ảnh sau chưa ổn định hoặc không xác nhận được camera",
        )
        self.assertTrue(self.module._deploy(self.reader.capture.return_value, slot()))
        self.assertIsNone(self.module.halt_reason)
        self.assertIsNotNone(self.module.geometry_unclear_since)
        self.adb.tap.assert_not_called()
        self.now += self.module.settings["builder_transition_timeout"] + 1
        self.assertFalse(self.module._deploy(self.reader.capture.return_value, slot()))
        self.adb.tap.assert_not_called()

    def test_camera_input_release_failure_still_halts_with_the_actual_reason(self):
        self.battle_screen()
        self.module.settings["camera_auto_adjust"] = True
        self.module.tactics.build = Mock(return_value=None)
        self.camera.zoom.return_value = SimpleNamespace(
            status=CameraStatus.ERROR,
            reason="Input/release thất bại; bỏ tọa độ cũ",
        )
        self.assertFalse(self.module._deploy(self.reader.capture.return_value, slot()))
        self.assertIn("Input/release thất bại", self.module.halt_reason)
        self.adb.tap.assert_not_called()

    def test_stop_during_camera_does_not_report_a_builder_failure(self):
        self.battle_screen()
        self.module.settings["camera_auto_adjust"] = True
        self.module.tactics.build = Mock(return_value=None)
        self.camera.zoom.return_value = SimpleNamespace(status=CameraStatus.STOPPED)
        self.assertTrue(self.module._deploy(self.reader.capture.return_value, slot()))
        self.assertIsNone(self.module.halt_reason)
        self.adb.tap.assert_not_called()

    def test_yield_only_after_postprocessing_and_home_proof(self):
        self.assertTrue(self.module.tick(yield_requested=lambda: True))
        self.assertTrue(self.module.can_yield)
        self.adb.tap.assert_not_called()
        self.rewards.claim_star_bonus.assert_called_once()
        self.now += 3
        self.assertFalse(self.module.can_yield)

    def test_unsettled_home_cannot_yield(self):
        self.nav.confirmed_home.return_value = None
        self.module.tick(yield_requested=lambda: True)
        self.assertFalse(self.module.can_yield)
        self.adb.tap.assert_not_called()

    def test_stop_before_tick_and_between_selection_and_map_tap(self):
        self.stop.set()
        self.module.tick()
        self.adb.tap.assert_not_called()
        self.stop.clear()
        self.battle_screen()
        self.module.stage = 1
        self.module.tactics.plan = BattlePlan(
            [(400, 330)], (800, 440), 1.0, np.zeros((4, 2))
        )
        self.adb.tap.side_effect = lambda *_a, **_k: self.stop.set() or True
        with patch(
            "cocmagic.modules.builder_farm_module.measure_motion",
            return_value=SimpleNamespace(valid=True, changed=False),
        ):
            self.assertTrue(
                self.module._deploy(self.reader.capture.return_value, slot())
            )
        self.assertEqual(1, self.adb.tap.call_count)

    def test_selected_undeployed_camp_retry_does_not_toggle_selection_off(self):
        self.battle_screen()
        self.module.tactics.plan = BattlePlan(
            [(400, 330)], (800, 440), 1.0, np.zeros((4, 2))
        )
        selected = replace(slot(), selected=True)
        self.reader.read_bar.side_effect = [
            ArmyObservation((selected,), True),
            ArmyObservation((replace(selected, state=SlotState.DEPLOYED),), True),
        ]
        with patch(
            "cocmagic.modules.builder_farm_module.measure_motion",
            return_value=SimpleNamespace(valid=True, changed=False),
        ):
            self.assertTrue(
                self.module._deploy(self.reader.capture.return_value, selected)
            )
        self.adb.tap.assert_called_once_with(400, 330, jitter=0, delay=0.1)
        self.assertEqual(1, self.module.metrics["deployed"])

    def test_structure_probes_are_rebuilt_from_the_selected_camp_frame(self):
        self.battle_screen()
        before = self.image.copy()
        fresh = self.image.copy()
        fresh[400, 400] = 255
        self.reader.capture.side_effect = [
            Capture(before, 1, 100.0, 0),
            Capture(fresh, 2, 101.0, 0),
            Capture(fresh.copy(), 3, 102.0, 0),
        ]
        self.reader.read_bar.side_effect = [
            ArmyObservation((slot(),), True),
            ArmyObservation((slot(state=SlotState.DEPLOYED),), True),
        ]
        old = BattlePlan(
            [(600, 330)], (800, 440), 0.5, np.zeros((4, 2)), "builder_visual_footprint"
        )
        new = BattlePlan(
            [(400, 330)], (800, 440), 0.8, np.zeros((4, 2)), "builder_red_segments"
        )
        self.module.tactics.plan = old

        def build(image, revision):
            self.assertIs(fresh, image)
            self.assertEqual(0, revision)
            self.module.tactics.plan = new
            return new

        self.module.tactics.build = Mock(side_effect=build)
        with patch(
            "cocmagic.modules.builder_farm_module.measure_motion",
            return_value=SimpleNamespace(valid=True, changed=False),
        ):
            self.assertTrue(self.module._deploy(Capture(before, 0, 99.0, 0), slot()))
        self.assertEqual(
            [(300, 810), (400, 330)],
            [call.args for call in self.adb.tap.call_args_list],
        )
        self.module.tactics.build.assert_called_once()

    def test_reload_discards_old_inputs_abilities_points_and_setup(self):
        self.module.setup_verified = True
        self.module.tactics.used_abilities.add("camp:1")
        self.module.tactics.confirmed_point = (400, 330)
        self.module.battle_at = 90.0
        self.module.reset_after_reload()
        self.assertFalse(self.module.setup_verified)
        self.assertFalse(self.module.tactics.used_abilities)
        self.assertIsNone(self.module.tactics.confirmed_point)
        self.assertIsNone(self.module.battle_at)
        self.assertEqual(ModuleScreen.UNKNOWN, self.module.confirmed_screen)
        self.adb.tap.assert_not_called()

    def test_popup_invalidation_preserves_consumption_but_invalidates_map(self):
        self.module.tactics.used_abilities.add("camp:1")
        self.module.tactics.confirmed_point = (400, 330)
        self.module.invalidate_after_popup()
        self.assertIn("camp:1", self.module.tactics.used_abilities)
        self.assertIsNone(self.module.tactics.confirmed_point)

    def test_two_stage_transition_needs_new_preparation_not_100_percent(self):
        self.battle_screen(False)
        self.reader.read_bar.return_value = ArmyObservation(
            (slot(state=SlotState.DEAD, ability=AbilityState.USED),), True
        )
        self.module.tick()
        self.assertEqual(1, self.module.stage)
        self.module.tick()
        self.assertEqual(1, self.module.stage)
        self.module.tactics.used_abilities.add("camp:1")
        self.battle_screen(True)
        self.module.tick()
        self.assertEqual(1, self.module.stage)
        self.module.tick()
        self.assertEqual(2, self.module.stage)
        self.assertIn("camp:1", self.module.tactics.used_abilities)

    def test_result_at_either_stage_returns_home_and_counts_once(self):
        for stage in (1, 2):
            with self.subTest(stage=stage):
                self.module.stage = stage
                self.reader.classify.return_value = ScreenObservation(
                    ScreenKind.RESULT, "result", Village.BUILDER
                )
                self.reader.match.return_value = (800, 740)
                self.module.tick()
                self.module.tick()
                self.assertEqual(1, self.module.metrics["battle_count"])

    def test_unexpected_home_is_postprocessed_without_fake_result(self):
        self.module.phase = BuilderPhase.FIGHT
        self.module.battle_at = 80.0
        self.module.tick(yield_requested=lambda: True)
        self.assertTrue(self.module.can_yield)
        self.assertEqual(0, self.module.metrics["battle_count"])

    def test_foreign_result_can_return_but_never_counts_as_builder_battle(self):
        self.reader.classify.return_value = ScreenObservation(
            ScreenKind.RESULT, "main", Village.MAIN
        )
        self.reader.match.return_value = (800, 740)
        self.module.tick()
        self.assertEqual(0, self.module.metrics["battle_count"])
        self.assertEqual(BuilderPhase.POST, self.module.phase)

    def test_timeout_budgets_are_independent_of_main(self):
        self.battle_screen(False)
        self.module.battle_at = self.now - 550
        self.assertFalse(self.module.tick())
        self.assertIn("Timeout trận builder", self.module.halt_reason)
        self.adb.tap.assert_not_called()

    def test_unknown_transition_and_prepare_have_finite_limits(self):
        self.reader.classify.return_value = ScreenObservation(
            ScreenKind.UNKNOWN, "unknown"
        )
        self.module.battle_at = 90.0
        self.module.tick()
        self.now += 36
        self.assertFalse(self.module.tick())
        self.module.reset_after_reload()
        self.now += 76
        self.assertFalse(self.module.tick())

    def test_transient_unknown_bar_budget_starts_at_first_bad_observation(self):
        self.battle_screen(False)
        self.module.last_progress = self.now - 100
        self.reader.read_bar.return_value = ArmyObservation(reason="occluded")
        self.assertTrue(self.module.tick())
        self.assertIsNone(self.module.halt_reason)
        self.now += 36
        self.assertFalse(self.module.tick())

    def test_dead_no_hero_does_not_block_training(self):
        self.battle_screen(False)
        self.reader.read_bar.return_value = ArmyObservation(
            (slot(state=SlotState.DEAD, ability=AbilityState.USED),), True
        )
        self.assertTrue(self.module.tick())
        self.assertEqual(BuilderPhase.FIGHT, self.module.phase)
        self.adb.tap.assert_not_called()

    def test_native_timer_progress_prevents_false_watchdog_with_dead_army(self):
        self.battle_screen(False)
        self.reader.read_bar.return_value = ArmyObservation(
            (slot(state=SlotState.DEAD, ability=AbilityState.USED),), True
        )
        for name, elapsed in [("timer-waiting", 0), ("timer-ending", 91)]:
            self.image[49:91, 735:865] = fixture(name)
            self.now = 100.0 + elapsed
            self.assertTrue(self.module.tick(), self.module.halt_reason)
        self.assertEqual(BuilderPhase.FIGHT, self.module.phase)
        self.adb.tap.assert_not_called()

    def test_frozen_timer_and_army_still_trip_bounded_watchdog(self):
        self.battle_screen(False)
        self.reader.read_bar.return_value = ArmyObservation(
            (slot(state=SlotState.DEAD, ability=AbilityState.USED),), True
        )
        self.image[49:91, 735:865] = fixture("timer-waiting")
        self.assertTrue(self.module.tick())
        self.now += 91
        self.assertFalse(self.module.tick())
        self.assertIn("Watchdog builder", self.module.halt_reason)
        self.adb.tap.assert_not_called()

    def test_ability_receipt_required_and_failed_one_shot_never_replayed(self):
        s = slot(state=SlotState.DEPLOYED)
        self.reader.read_bar.return_value = ArmyObservation((s,), True)
        self.assertFalse(self.module._ability(s))
        self.assertEqual(1, self.adb.tap.call_count)
        self.assertIn(s.key, self.module.tactics.attempted_abilities)
        self.assertEqual(0, self.module.metrics["troop_abilities"])

    def test_used_skill_receipt_counts_once(self):
        s = slot(state=SlotState.DEPLOYED)
        self.reader.read_bar.side_effect = [
            ArmyObservation((s,), True),
            ArmyObservation((replace(s, ability=AbilityState.USED),), True),
        ]
        self.assertTrue(self.module._ability(s))
        self.assertEqual(1, self.module.metrics["troop_abilities"])
        self.assertIn(s.key, self.module.tactics.used_abilities)

    def test_death_after_skill_is_reported_uncertain_and_never_replayed(self):
        s = slot(state=SlotState.DEPLOYED)
        dead = replace(s, state=SlotState.DEAD, ability=AbilityState.USED)
        self.reader.read_bar.side_effect = [
            ArmyObservation((s,), True),
            ArmyObservation((dead,), True),
        ]
        self.assertTrue(self.module._ability(s))
        self.assertEqual(0, self.module.metrics["troop_abilities"])
        self.assertEqual(1, self.module.metrics["unconfirmed_abilities"])
        self.assertIn(s.key, self.module.tactics.attempted_abilities)
        self.assertIsNone(self.module.halt_reason)

    def test_rejected_points_have_finite_retry_budget(self):
        self.module.tactics.attempts["camp:1"] = 4
        self.assertFalse(self.module._deploy(self.reader.capture.return_value, slot()))
        self.adb.tap.assert_not_called()

    def test_cart_failure_blocks_yield(self):
        self.module.settings["builder_collect_cart"] = True
        self.rewards.collect_cart.return_value = SimpleNamespace(
            success=False, collected=False, returned_home=False, reason="unknown"
        )
        self.assertFalse(self.module.tick(yield_requested=lambda: True))
        self.assertFalse(self.module.can_yield)

    def test_reload_between_select_and_drop_cancels_old_map_input(self):
        self.battle_screen()
        self.module.tactics.plan = BattlePlan(
            [(400, 330)], (800, 440), 1.0, np.zeros((4, 2))
        )
        self.adb.tap.side_effect = lambda *_a, **_k: (
            self.module.reset_after_reload() or True
        )
        with patch(
            "cocmagic.modules.builder_farm_module.measure_motion",
            return_value=SimpleNamespace(valid=True, changed=False),
        ):
            self.assertTrue(
                self.module._deploy(self.reader.capture.return_value, slot())
            )
        self.assertEqual(1, self.adb.tap.call_count)
        self.assertIsNone(self.module.halt_reason)
        self.assertIsNone(self.module.tactics.plan)

    def test_verified_setup_is_reused_until_reload(self):
        self.module.settings["builder_auto_setup_baby_dragons"] = True
        self.module.setup_verified = True
        self.module.tick()
        self.reader.locate_ui.assert_not_called()
        self.adb.tap.assert_called_once_with(100, 800, jitter=0, delay=0.1)
        self.module.reset_after_reload()
        self.assertFalse(self.module.setup_verified)

    def test_changed_lineup_at_menu_returns_for_setup_before_find(self):
        self.module.settings["builder_auto_setup_baby_dragons"] = True
        self.module.setup_verified = True
        self.reader.classify.return_value = ScreenObservation(
            ScreenKind.ATTACK_MENU, "builder", Village.BUILDER
        )
        self.reader.read_menu_army.return_value = ArmyObservation(
            (slot(kind="bomber"),), True
        )
        self.reader.locate_ui.return_value = (1360, 165)
        self.assertTrue(self.module.tick())
        self.assertFalse(self.module.setup_verified)
        self.assertEqual(BuilderPhase.HOME, self.module.phase)
        self.reader.match.assert_not_called()
        self.assertEqual(0, self.module.metrics["attack_count"])

    def test_setup_only_removes_wrong_camp_and_requires_removal_receipt(self):
        self.module.phase = BuilderPhase.SETUP
        wrong = replace(
            slot("reinforcement:1200"),
            role="reinforcement",
            kind="bomber",
            remove=(1240, 380),
        )
        correct = slot()
        self.reader.read_army.side_effect = [
            ArmyObservation((correct, wrong), True),
            ArmyObservation((correct,), True),
        ]
        self.assertTrue(
            self.module._setup(
                self.reader.capture.return_value, SimpleNamespace(points={})
            )
        )
        self.adb.tap.assert_called_once_with(1240, 380, jitter=0, delay=0.1)
        self.assertFalse(self.module.setup_verified)

    def test_setup_adds_dragon_then_rechecks_before_other_input(self):
        self.module.phase = BuilderPhase.SETUP
        self.reader.read_army.side_effect = [
            ArmyObservation((slot(),), True, choice=(600, 730)),
            ArmyObservation(
                (slot(), replace(slot("camp:7", x=1200), role="reinforcement")),
                True,
                complete=True,
            ),
        ]
        self.assertTrue(
            self.module._setup(
                self.reader.capture.return_value, SimpleNamespace(points={})
            )
        )
        self.assertEqual(1, self.adb.tap.call_count)
        self.assertFalse(self.module.setup_verified)

    def test_unopened_dragon_and_failed_setup_receipt_are_finite(self):
        self.module.phase = BuilderPhase.SETUP
        self.reader.read_army.return_value = ArmyObservation(
            (slot(),), True, complete=False
        )
        self.assertFalse(
            self.module._setup(
                self.reader.capture.return_value, SimpleNamespace(points={})
            )
        )
        self.adb.tap.assert_not_called()

    def test_unavailable_dragon_after_one_removal_never_removes_another_camp(self):
        self.module.phase = BuilderPhase.SETUP
        self.module.setup_pending_empty = True
        wrong = replace(slot(kind="bomber"), remove=(400, 380))
        self.reader.read_army.return_value = ArmyObservation((wrong,), True)
        self.assertFalse(
            self.module._setup(
                self.reader.capture.return_value, SimpleNamespace(points={})
            )
        )
        self.adb.tap.assert_not_called()

    def test_full_replacement_budget_allows_verified_eight_camp_completion(self):
        self.module.phase = BuilderPhase.SETUP
        self.module.setup_edits = 16  # Eight removals + eight verified additions.
        camps = tuple(slot(f"camp:{i + 1}", x=300 + i * 120) for i in range(8))
        self.reader.read_army.return_value = ArmyObservation(camps, True, complete=True)
        self.assertTrue(
            self.module._setup(
                self.reader.capture.return_value,
                SimpleNamespace(points={"close": (1400, 130)}),
            )
        )
        self.assertTrue(self.module.setup_verified)
        self.assertEqual(2, self.adb.tap.call_count)  # close, then verified Home Attack

    def test_hero_skill_interleaves_deployment_only_when_actually_ready(self):
        self.battle_screen(False)
        hero = slot(
            "battle_machine", SlotState.DEPLOYED, role="hero", kind="battle_machine"
        )
        self.reader.read_bar.return_value = ArmyObservation((hero, slot()), True)
        with patch.object(self.module, "_ability", return_value=True) as ability:
            self.module.tick()
        ability.assert_called_once_with(hero)

    def test_hero_requires_charging_receipt_then_new_ready_before_reuse(self):
        hero = slot(
            "battle_machine", SlotState.DEPLOYED, role="hero", kind="battle_machine"
        )
        charging = replace(hero, ability=AbilityState.CHARGING)
        self.reader.read_bar.side_effect = [
            ArmyObservation((hero,), True),
            ArmyObservation((charging,), True),
        ]
        self.assertTrue(self.module._ability(hero))
        self.assertEqual(1, self.module.metrics["hero_abilities"])
        self.assertNotIn(hero.key, self.module.tactics.hero_waiting)
        self.module.tactics.observe((charging,))
        self.assertNotIn(hero.key, self.module.tactics.hero_waiting)

    def test_return_home_is_not_replayed_if_result_remains(self):
        self.reader.classify.return_value = ScreenObservation(
            ScreenKind.RESULT,
            "result",
            Village.BUILDER,
            "builder_result",
            {"return": (800, 760)},
        )
        self.module.tick()
        self.module.tick()
        self.assertEqual(1, self.adb.tap.call_count)
        self.now += 36
        self.assertFalse(self.module.tick())
        self.assertEqual(1, self.adb.tap.call_count)

    def test_find_now_is_not_replayed_without_scene_receipt(self):
        self.reader.classify.return_value = ScreenObservation(
            ScreenKind.ATTACK_MENU, "menu", Village.BUILDER
        )
        self.reader.match.return_value = (1180, 590)
        self.module.tick()
        self.module.tick()
        self.assertEqual(1, self.adb.tap.call_count)
        self.assertEqual(1, self.module.metrics["attack_count"])
        self.now += 76
        self.assertFalse(self.module.tick())
        self.assertEqual(1, self.adb.tap.call_count)

    def test_startup_cart_is_resumed_before_bonus_and_never_reopened(self):
        self.module.settings["builder_collect_cart"] = True
        self.reader.classify.return_value = ScreenObservation(
            ScreenKind.MODAL, "cart", Village.BUILDER, "cart"
        )
        self.rewards.collect_cart.return_value = SimpleNamespace(
            success=True, collected=True, returned_home=True
        )
        self.assertTrue(self.module.tick())
        self.rewards.collect_cart.assert_called_once_with(resume=True)
        self.rewards.claim_star_bonus.assert_called_once()
        self.assertEqual(BuilderPhase.HOME, self.module.phase)
        self.assertFalse(self.module.can_yield)  # needs independent fresh Home proof


class EngineBuilderTests(unittest.TestCase):
    def test_engine_registers_real_builder_module_without_main_modules(self):
        from cocmagic.bot_engine import BotEngine

        engine = BotEngine(config.migrate_settings({"run_mode": "builder"}))
        engine.adb = Mock(
            device="builder-only",
            camera_revision=0,
            stop_event=threading.Event(),
            input_lock=threading.RLock(),
        )
        engine._init_modules()
        self.assertIsInstance(engine.builder_mod, BuilderFarmModule)
        self.assertEqual("builder", engine.coordinator.active_id)
        self.assertIsNone(engine.farm_mod)
        self.assertIsNone(engine.hero_mod)
        self.assertIsNone(engine.wall_mod)
        self.assertEqual("unknown", engine.coordinator.status()["confirmed_screen"])

    def test_builder_banner_and_start_do_not_parse_unfinished_main_settings(self):
        from cocmagic.bot_engine import BotEngine

        engine = BotEngine(
            {"run_mode": "builder", "min_gold": "draft", "wall_resource": "draft"}
        )
        engine._connect_adb = Mock(return_value=False)
        with patch.object(
            config, "AVAILABLE_RUN_MODES", frozenset({"main", "builder"})
        ):
            self.assertFalse(engine.start())
        engine._connect_adb.assert_called_once()

    def test_builder_ctrl_c_without_supplied_event_cancels_module_inputs(self):
        from cocmagic.bot_engine import BotEngine

        engine = BotEngine({"run_mode": "builder"})
        self.assertIsNotNone(engine.stop_event)
        engine._signal_handler(None, None)
        self.assertTrue(engine.stop_event.is_set())

    def test_builder_timeouts_are_validated_instead_of_main_draft(self):
        for key, value in (
            ("builder_battle_timeout", 85),
            ("builder_baby_ability_delay", float("nan")),
            ("builder_point_retries", 2.5),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                config.validate_settings(
                    {"run_mode": "builder", key: value, "min_gold": "draft"}
                )


if __name__ == "__main__":
    unittest.main()
