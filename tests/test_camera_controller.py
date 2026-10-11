"""Camera contracts plus real MuMu Practice pairs (redacted/cropped manifest)."""

from pathlib import Path
import subprocess
import threading
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.attack_tactics import AttackTactics
from cocmagic.battle_planner import BattlePlanner
from cocmagic.camera_backend import SerialGestureBackend, TouchDevice
from cocmagic.camera_controller import (
    CameraController,
    CameraStatus,
    ScreenSpace,
    army_selection,
    measure_motion,
)
from cocmagic.modules.farm_module import (
    FarmModule,
    FarmState,
    CardSlot,
    ComboProfile,
    SpellProgress,
    _BattleInputStopped,
)
from cocmagic.troop_vision import read_card_count


FIXTURES = Path(config.BASE_DIR) / "tests/fixtures/dual_village/camera"


def frame(name):
    suffix = ".jpg" if name.startswith(("pan-", "zoom-")) else ".png"
    image = cv2.imread(str(FIXTURES / f"{name}{suffix}"))
    if image is None:
        raise AssertionError(f"Missing fixture {name}")
    return image


def with_bar(name):
    image = frame("pan-after")
    image[735:] = frame(name)
    return image


class ImageEvidenceTests(unittest.TestCase):
    def test_real_pan_pair_excludes_stationary_hud(self):
        motion = measure_motion(frame("pan-before"), frame("pan-after"))
        self.assertTrue(motion.valid and motion.changed)
        self.assertAlmostEqual(1, motion.scale, delta=0.01)
        self.assertLess(motion.dy, -150)
        self.assertGreater(motion.inliers, 100)

    def test_real_pinch_pair_has_scale_change(self):
        motion = measure_motion(frame("zoom-before"), frame("zoom-after"))
        self.assertTrue(motion.valid and motion.changed)
        self.assertLess(motion.scale, 0.75)

    def test_hud_only_change_is_not_camera_motion(self):
        before = frame("pan-after")
        after = before.copy()
        mask = ScreenSpace.map_mask(before.shape)
        after[mask == 0] = np.random.default_rng(42).integers(
            0, 256, after[mask == 0].shape, np.uint8
        )
        motion = measure_motion(before, after)
        self.assertTrue(motion.valid)
        self.assertFalse(motion.changed)

    def test_blank_and_new_resolution_are_not_success(self):
        self.assertFalse(
            measure_motion(
                np.zeros((900, 1600, 3), np.uint8), np.zeros((900, 1600, 3), np.uint8)
            ).valid
        )
        self.assertIsNone(ScreenSpace.map_mask((720, 1280)))
        self.assertIsNone(
            BattlePlanner().plan(np.zeros((720, 1280, 3), np.uint8), camera_revision=1)
        )

    def test_real_selected_frame_is_detected_and_count_survived_drag(self):
        self.assertTrue(army_selection(with_bar("selected-before")))
        self.assertTrue(army_selection(with_bar("selected-after")))
        self.assertFalse(army_selection(frame("pan-after")))
        self.assertEqual(5, read_card_count(with_bar("selected-before"), 74, 840))
        self.assertEqual(5, read_card_count(with_bar("selected-after"), 74, 840))

    def test_real_lower_edge_probe_preceded_two_unit_batch(self):
        self.assertEqual(
            [10, 9, 7],
            [
                read_card_count(with_bar(name), 170, 840)
                for name in ("drop-before", "drop-after", "drop-bulk-after")
            ],
        )
        self.assertTrue(ScreenSpace.map_point((952, 644)))
        self.assertFalse(ScreenSpace.map_point((952, 744)))

    def test_tracked_plan_rebuilds_visible_lower_candidates(self):
        plan = BattlePlanner().plan(frame("pan-after"), camera_revision=7)
        self.assertIsNotNone(plan)
        self.assertEqual(7, plan.camera_revision)
        self.assertTrue(plan.lower_edge_points)
        self.assertTrue(all(ScreenSpace.map_point(p) for p in plan.troop_points))
        self.assertTrue(
            all(
                cv2.pointPolygonTest(
                    plan.boundary.astype(np.float32), tuple(map(float, p)), False
                )
                < 0
                for p in plan.troop_points
            )
        )
        with self.assertRaises(ValueError):
            AttackTactics.from_battle(plan, frame("pan-after"), camera_revision=8)

    def test_fixed_diamond_is_not_authorized_by_revision_or_resolution(self):
        image = cv2.imread(
            str(Path(config.BASE_DIR) / "tests/fixtures/user_decorated_scenery.png")
        )
        self.assertIsNotNone(BattlePlanner().plan(image))  # disabled-camera baseline
        self.assertIsNone(BattlePlanner().plan(image, camera_revision=1))
        self.assertIsNone(
            BattlePlanner().plan(image, camera_revision=2, standard_view=(image, 1))
        )
        self.assertIsNone(
            BattlePlanner().plan(image, camera_revision=1, standard_view=(image, 1))
        )
        self.assertIsNone(BattlePlanner().confirm_standard_view(image, 1))

    def test_outward_offset_cannot_move_tracked_drop_onto_hud(self):
        image = np.full((900, 1600, 3), 35, np.uint8)
        outline = np.array([(800, 120), (1400, 460), (800, 780), (80, 460)], np.int32)
        cv2.polylines(image, [outline], True, (0, 0, 255), 3)
        plan = BattlePlanner().plan(image, camera_revision=7)
        self.assertIsNotNone(plan)
        self.assertTrue(all(ScreenSpace.map_point(p) for p in plan.troop_points))
        self.assertNotIn((1299, 542), plan.troop_points)  # inside Next / damage HUD

    def test_spell_and_map_points_never_enter_hud(self):
        plan = BattlePlanner().plan(frame("pan-after"), camera_revision=1)
        tactics = AttackTactics.from_battle(plan, frame("pan-after"), camera_revision=1)
        tactics.center = (1400, 650)
        self.assertIsNone(tactics.spell_target("freeze", 0))
        for point in ((75, 840), (130, 660), (1400, 630), (100, 150), (800, 710)):
            self.assertFalse(ScreenSpace.map_point(point))
        self.assertFalse(ScreenSpace.safe_path((800, 550), (800, 800), "battle"))


class ControllerTests(unittest.TestCase):
    def make_controller(self):
        adb = ADBController(
            serial="test-serial", settings={}, stop_event=threading.Event()
        )
        backend = Mock(
            touch=TouchDevice("/dev/input/event4", 900, 1600, 1, (1600, 900))
        )
        backend.pan.return_value = backend.zoom.return_value = (
            backend.release.return_value
        ) = True
        camera = CameraController(adb, backend, stop_event=adb.stop_event)
        camera.wait_stable = Mock(return_value=frame("pan-after"))
        return camera, adb, backend

    def test_unchanged_zoom_suppresses_further_input_until_new_view(self):
        c, a, backend = self.make_controller()
        self.assertEqual(
            CameraStatus.UNCHANGED, c.zoom(0.6, troop_selected=False).status
        )
        self.assertEqual(
            CameraStatus.UNCHANGED, c.zoom(0.6, troop_selected=False).status
        )
        backend.zoom.assert_called_once()
        self.assertEqual(1, a.camera_revision)
        c.reset_view()
        c.zoom(0.6, troop_selected=False)
        self.assertEqual(2, backend.zoom.call_count)

    def test_measured_pan_success(self):
        c, a, backend = self.make_controller()
        c.wait_stable.side_effect = [frame("pan-before"), frame("pan-after")]
        self.assertEqual(
            CameraStatus.SUCCESS,
            c.pan((800, 510), (800, 365), troop_selected=False).status,
        )
        backend.release.assert_called_once()
        self.assertEqual(1, a.camera_revision)

    def test_failed_and_throwing_gestures_release_and_invalidate(self):
        for fails in (False, RuntimeError("injected")):
            c, a, backend = self.make_controller()
            a._cached_screenshot = frame("pan-after")
            a._frame_matches["old"] = (10, 20)
            if isinstance(fails, Exception):
                backend.pan.side_effect = fails
            else:
                backend.pan.return_value = fails
            self.assertEqual(
                CameraStatus.ERROR,
                c.pan((800, 510), (800, 365), troop_selected=False).status,
            )
            self.assertIsNone(a._cached_screenshot)
            self.assertFalse(a._frame_matches)
            self.assertEqual(1, a.camera_revision)
            backend.release.assert_called_once()

    def test_unstable_after_and_failed_cleanup_are_not_success(self):
        c, a, backend = self.make_controller()
        c.wait_stable.side_effect = [frame("pan-before"), None]
        self.assertEqual(
            CameraStatus.ERROR,
            c.pan((800, 510), (800, 365), troop_selected=False).status,
        )
        c, a, backend = self.make_controller()
        backend.release.side_effect = RuntimeError("cleanup failed")
        self.assertEqual(
            CameraStatus.ERROR,
            c.pan((800, 510), (800, 365), troop_selected=False).status,
        )

    def test_stop_before_and_during_gesture(self):
        c, a, backend = self.make_controller()
        a.stop_event.set()
        self.assertEqual(
            CameraStatus.STOPPED,
            c.pan((800, 510), (800, 365), troop_selected=False).status,
        )
        backend.pan.assert_not_called()
        c, a, backend = self.make_controller()
        backend.pan.side_effect = lambda *args: a.stop_event.set() or False
        self.assertEqual(
            CameraStatus.STOPPED,
            c.pan((800, 510), (800, 365), troop_selected=False).status,
        )
        backend.release.assert_called_once()

    def test_selected_unknown_or_hud_path_never_submits_gesture(self):
        for selected in (True, None):
            c, a, backend = self.make_controller()
            self.assertEqual(
                CameraStatus.UNSUPPORTED,
                c.pan((800, 510), (800, 365), troop_selected=selected).status,
            )
            backend.pan.assert_not_called()
        c, a, backend = self.make_controller()
        c.wait_stable.return_value = with_bar("selected-before")
        self.assertEqual(
            CameraStatus.UNSUPPORTED,
            c.pan((800, 510), (800, 365), context="scout", troop_selected=False).status,
        )
        backend.pan.assert_not_called()
        c.pan((800, 510), (800, 800), troop_selected=False)
        backend.pan.assert_not_called()

    def test_no_backend_and_stop_aware_stability_budget(self):
        c, a, backend = self.make_controller()
        backend.touch = None
        backend.probe.return_value = False
        self.assertEqual(
            CameraStatus.UNSUPPORTED, c.zoom(0.6, troop_selected=False).status
        )
        backend.zoom.assert_not_called()
        c = CameraController(a, backend, max_frames=4)
        a.screenshot = Mock(return_value=np.zeros((900, 1600, 3), np.uint8))
        with patch.object(c, "_wait"):
            self.assertIsNone(c.wait_stable("home"))
        self.assertEqual(4, a.screenshot.call_count)

    def test_normalize_has_attempt_limit(self):
        c, a, backend = self.make_controller()
        c.zoom = Mock(
            return_value=Mock(status=CameraStatus.SUCCESS, after=frame("pan-after"))
        )
        self.assertEqual(
            CameraStatus.ERROR, c.normalize(troop_selected=False, max_attempts=3).status
        )
        self.assertEqual(3, c.zoom.call_count)

    def test_native_modal_blocks_camera_over_stationary_map(self):
        c, a, backend = self.make_controller()
        image = frame("pan-after")
        image[280:580, 330:1230] = frame("connection-modal-crop")
        c.wait_stable.return_value = image
        self.assertFalse(c.frame_clear(image))
        self.assertEqual(
            CameraStatus.ERROR,
            c.pan((800, 510), (800, 365), troop_selected=False).status,
        )
        backend.pan.assert_not_called()
        self.assertEqual(0, a.camera_revision)


class BackendTests(unittest.TestCase):
    def test_swipe_failure_and_stop_release_bypasses_stop(self):
        a = ADBController(serial="device-A", settings={}, stop_event=threading.Event())
        with (
            patch.object(a, "_shell", return_value=False),
            patch("cocmagic.adb_controller.run_hidden") as run,
        ):
            run.return_value.returncode = 0
            self.assertFalse(a.swipe(800, 500, 800, 300))
            self.assertIn("CANCEL", run.call_args.args[0][-1])
            self.assertEqual([a.adb, "-s", "device-A"], run.call_args.args[0][:3])
        a.stop_event.set()
        with patch.object(a, "_shell") as shell:
            self.assertFalse(a.swipe(800, 500, 800, 300))
            shell.assert_not_called()

    def test_pinch_shared_sync_and_timeout_cleanup(self):
        a = ADBController(serial="device-B", settings={})
        backend = SerialGestureBackend(a)
        backend.touch = TouchDevice("/dev/input/event4", 900, 1600, 1, (1600, 900))
        backend.probe = Mock(return_value=True)
        with patch(
            "cocmagic.camera_backend.run_hidden",
            side_effect=[subprocess.TimeoutExpired("adb", 5), Mock(returncode=0)],
        ) as run:
            self.assertFalse(backend.zoom((800, 410), 0.6))
            script = run.call_args_list[0].kwargs["input"].decode()
            self.assertIn("trap", script)
            self.assertIn("3 47 0", script)
            self.assertIn("3 47 1", script)
            self.assertNotIn("input swipe", script)
            first_sync = script.index(
                "sendevent /dev/input/event4 0 0 0", script.index("set -e")
            )
            self.assertLess(script.index("3 57 32000"), first_sync)
            self.assertLess(script.index("3 57 32001"), first_sync)
            cleanup = run.call_args_list[1].args[0][-1]
            self.assertIn("3 57 -1", cleanup)
            self.assertIn("kill", cleanup)
            self.assertTrue(
                all(
                    call.args[0][1:3] == ["-s", "device-B"]
                    for call in run.call_args_list
                )
            )

    def test_unsupported_or_active_touch_never_enables_pinch(self):
        a = ADBController(serial="device-C", settings={})
        backend = SerialGestureBackend(a)
        backend._read = Mock(return_value="no multi touch")
        self.assertFalse(backend.probe())
        self.assertIsNone(backend.touch)
        self.assertFalse(backend.zoom((800, 410), 0.6))
        with self.assertRaises(ValueError):
            TouchDevice("/dev/input/event4", 900, 1600, 0, (1600, 900)).raw_point(
                (800, 410)
            )

    def test_stop_after_probe_submits_no_pinch(self):
        stop = threading.Event()
        a = ADBController(serial="device-D", settings={}, stop_event=stop)
        backend = SerialGestureBackend(a)
        backend.touch = TouchDevice("/dev/input/event4", 900, 1600, 1, (1600, 900))
        backend.probe = Mock(side_effect=lambda *args: stop.set() or True)
        with patch("cocmagic.camera_backend.run_hidden") as run:
            self.assertFalse(backend.zoom((800, 410), 0.6))
            run.assert_not_called()


class FarmRevisionTests(unittest.TestCase):
    def make_farm(self, enabled=True):
        a = ADBController(serial="farm-serial", settings={})
        farm = FarmModule(a, Mock(), Mock(), {"camera_auto_adjust": enabled})
        farm._battle_plan = BattlePlanner().plan(frame("pan-after"), camera_revision=0)
        farm._attack_tactics = AttackTactics.from_battle(
            farm._battle_plan, frame("pan-after")
        )
        farm._combo_profile = ComboProfile(
            [CardSlot(170, 840, "troop")], [], (900, 1600)
        )
        farm._confirmed_main_points = [(952, 644)]
        farm._electro_drop_points = [(952, 644)]
        farm._hero_entry = (952, 644)
        farm._verified_battle_points.add((952, 644))
        farm._button_cache["next"] = (1450, 600)
        farm._deployed_hero_slots["king"] = (1191, 840)
        return farm, a

    def test_map_invalidation_preserves_hud_and_consumption(self):
        f, a = self.make_farm()
        combo = f._combo_profile
        slot = CardSlot(1500, 840, "spell", "rage")
        f._pending_spells[slot] = SpellProgress(cast_index=2)
        a._cached_screenshot = frame("pan-after")
        a.mark_camera_input()
        self.assertIsNone(f._battle_plan)
        self.assertIsNone(f._attack_tactics)
        self.assertIsNone(f._hero_entry)
        self.assertFalse(
            f._confirmed_main_points
            or f._electro_drop_points
            or f._verified_battle_points
        )
        self.assertIs(combo, f._combo_profile)
        self.assertEqual({"next": (1450, 600)}, f._button_cache)
        self.assertEqual((1191, 840), f._deployed_hero_slots["king"])
        self.assertEqual(2, f._pending_spells[slot].cast_index)
        self.assertIsNone(a._cached_screenshot)

    def test_stale_geometry_blocks_drop_even_when_auto_adjust_is_off(self):
        f, a = self.make_farm(False)
        a.camera_revision = 1  # simulate a missed callback
        with patch.object(a, "tap_many") as tap:
            with self.assertRaises(_BattleInputStopped):
                f._battle_tap_many([(952, 644)], interval=0.02)
            tap.assert_not_called()

    def test_observed_external_pan_blocks_cached_batch(self):
        f, a = self.make_farm()
        f._map_reference_frame = frame("pan-before")
        with patch.object(a, "tap_many") as tap:
            with self.assertRaises(_BattleInputStopped):
                f._battle_tap_many(
                    [(952, 644)], interval=0.02, screenshot=frame("pan-after")
                )
            tap.assert_not_called()
        self.assertEqual(1, a.camera_revision)

    def test_hud_abilities_do_not_apply_map_motion_guard_or_drop_geometry(self):
        f, a = self.make_farm()
        plan, tactics = f._battle_plan, f._attack_tactics
        f._map_reference_frame = frame("pan-before")
        with patch.object(a, "tap_many", return_value=True) as tap:
            self.assertTrue(
                f._battle_tap_many(
                    [(1191, 790)], interval=0.02, screenshot=frame("pan-after")
                )
            )
        tap.assert_called_once()
        self.assertEqual(0, a.camera_revision)
        self.assertIs(plan, f._battle_plan)
        self.assertIs(tactics, f._attack_tactics)

    def test_event_hud_batch_keeps_geometry_for_fast_and_guarded_input(self):
        for fast in (False, True):
            with self.subTest(fast=fast):
                f, a = self.make_farm()
                f.settings["event_mode"] = True
                f._map_reference_frame = frame("pan-before")
                image = frame("pan-after")
                f._screenshot = Mock(return_value=image)
                f._handle_event_rewards = Mock(return_value=image)
                f._guard_battle_frame = Mock()
                with (
                    patch.object(a, "tap_many", return_value=True),
                    patch.object(a, "tap", return_value=True),
                ):
                    self.assertTrue(
                        f._battle_tap_many(
                            [(1191, 790)], interval=0.02, fast=fast, screenshot=image
                        )
                    )
                self.assertEqual(0, a.camera_revision)
                self.assertIsNotNone(f._attack_tactics)

    def test_accepted_spell_receipt_survives_geometry_invalidated_after_input(self):
        f, a = self.make_farm()
        slot = CardSlot(1500, 840, "spell", "freeze")
        progress = SpellProgress(cast_index=2)
        before, after = frame("pan-before"), frame("pan-after")
        f._read_card_count = Mock(side_effect=[1, 0])
        a.mark_camera_input()
        f._record_spell_use(before, after, slot, progress, target=(952, 644))
        self.assertEqual(3, progress.cast_index)
        self.assertIsNone(f._attack_tactics)
        with patch.object(a, "tap_many") as tap:
            with self.assertRaises(_BattleInputStopped):
                f._battle_tap_many([(952, 644)], interval=0.02)
        tap.assert_not_called()

    def test_camera_change_with_unresolved_cast_halts_without_replay(self):
        f, a = self.make_farm()
        slot = CardSlot(1500, 840, "spell", "rage")
        f._pending_spells[slot] = SpellProgress(
            cast_index=2, unconfirmed_before=frame("pan-after")
        )
        a.mark_camera_input()
        self.assertIsNotNone(f.halt_reason)
        self.assertEqual(2, f._pending_spells[slot].cast_index)

    def test_disabled_camera_never_probes_or_adjusts(self):
        f, a = self.make_farm(False)
        f.camera.backend = Mock()
        self.assertIsNotNone(f._prepare_camera(frame("pan-after")))
        self.assertFalse(f._camera_prepared)
        f.camera.backend.assert_not_called()
        self.assertEqual(0, a.camera_revision)
        self.assertIs(config.DEFAULT_SETTINGS["camera_auto_adjust"], False)

    def test_adjustment_is_after_loot_acceptance_before_any_card(self):
        f, a = self.make_farm()
        f.state = FarmState.LOOT_CHECK
        f._screenshot = Mock(return_value=frame("pan-after"))
        f._is_scout_screen = Mock(return_value=True)
        f.reader.loot_meets_threshold.return_value = False
        f._prepare_camera = Mock(return_value=frame("pan-after"))
        f._skip_scout = Mock()
        f._state_loot_check()
        f._prepare_camera.assert_not_called()
        f.reader.loot_meets_threshold.return_value = True
        f._state_loot_check()
        f._prepare_camera.assert_called_once()
        self.assertEqual(FarmState.ATTACKING, f.state)

    def test_pan_limit_keeps_only_new_supported_lower_points_and_stops_retry(self):
        f, a = self.make_farm()
        f._is_scout_screen = Mock(return_value=True)
        f.camera.pan = Mock(
            return_value=Mock(
                status=CameraStatus.UNCHANGED,
                after=frame("pan-after"),
                reason="limit",
                revision=0,
            )
        )
        result = f._prepare_camera(frame("pan-after"))
        self.assertIsNotNone(result)
        self.assertTrue(f._battle_plan.lower_edge_points)
        self.assertEqual(1, f.camera.pan.call_count)


if __name__ == "__main__":
    unittest.main()
