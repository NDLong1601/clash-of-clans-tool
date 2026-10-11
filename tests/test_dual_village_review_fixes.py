"""Regression scenarios from the GĐ0–GĐ8 review; all game input is offline."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.bot_engine import BotEngine
from cocmagic.builder_screen_reader import (
    Capture,
    ScreenKind,
    ScreenObservation,
    Village,
)
from cocmagic.builder_vision import (
    BuilderSlot,
    SlotState,
    AbilityState,
    ArmyObservation,
    BattleObservation,
)
from cocmagic.battle_planner import BattlePlan
from cocmagic.device_manager import DeviceOwnership, resolve_device_ownership
from cocmagic.hybrid_runtime import HybridRuntime, HybridRuntimeStore
from cocmagic.modules.builder_farm_module import BuilderFarmModule
from cocmagic.modules.farm_module import FarmModule, FarmState, _BattleInputStopped
from cocmagic.run_coordinator import RunCoordinator
from cocmagic.village_module import ModuleScreen


class MainHandoffTests(unittest.TestCase):
    def setUp(self):
        self.adb = ADBController(serial="offline-review", settings={})
        self.farm = FarmModule(self.adb, Mock(), Mock(), {"camera_auto_adjust": False})
        self.image = cv2.imread(
            str(Path(config.BASE_DIR) / "tests/fixtures/user_decorated_scenery.png")
        )
        self.assertIsNotNone(self.image)

    def test_builder_to_main_recovery_keeps_disabled_camera_probe_and_current_revision(
        self,
    ):
        builder = Mock(
            device_serial=self.adb.device,
            can_yield=True,
            halt_reason=None,
            confirmed_screen=ModuleScreen.HOME,
            confirmed_village=Village.BUILDER,
        )
        builder.tick.return_value = True

        def navigate(source, target):
            self.assertEqual(("builder", "main"), (source, target))
            self.farm.camera.reset_view()
            return True

        coordinator = RunCoordinator(
            self.adb.device,
            {"builder": builder, "main": self.farm},
            "builder",
            switch_village=navigate,
        )
        coordinator.request_switch("main", "bonus complete")
        self.assertTrue(coordinator.tick())
        self.assertEqual("main", coordinator.active_id)
        self.assertEqual(FarmState.RECOVERING, self.farm.state)
        self.assertGreater(self.adb.camera_revision, 0)
        self.farm._capture = Mock(return_value=self.image)
        self.farm._classify_screen = Mock(return_value=ModuleScreen.HOME)
        self.farm._state_recovering()
        self.farm.state = FarmState.LOOT_CHECK
        self.farm._screenshot = Mock(return_value=self.image)
        self.farm._is_scout_screen = Mock(return_value=True)
        self.farm.reader.loot_meets_threshold.return_value = True
        self.farm._skip_scout = Mock()
        self.farm._state_loot_check()
        self.farm._skip_scout.assert_not_called()
        self.assertEqual(FarmState.ATTACKING, self.farm.state)
        self.assertEqual("outer_perimeter", self.farm._battle_plan.source)
        self.assertTrue(self.farm._battle_plan.requires_probe)
        self.assertEqual(26, len(self.farm._battle_plan.troop_points))
        self.assertEqual(
            self.adb.camera_revision, self.farm._battle_plan.camera_revision
        )
        self.farm._assert_camera_targets(self.farm._battle_plan.troop_points)

    def test_camera_move_during_battle_still_rejects_fixed_fallback_and_old_input(self):
        self.farm._battle_plan = self.farm._make_battle_plan(self.image)
        self.assertIsNotNone(self.farm._battle_plan)
        self.adb.mark_camera_input()
        self.assertIsNone(self.farm._make_battle_plan(self.image))
        with patch.object(self.adb, "tap_many") as tap:
            with self.assertRaises(_BattleInputStopped):
                self.farm._battle_tap_many([(400, 330)], interval=0.02)
        tap.assert_not_called()

    def test_only_verified_home_reopens_disabled_camera_probes(self):
        self.farm._battle_plan = self.farm._make_battle_plan(self.image)
        self.adb.mark_camera_input()
        self.farm._screenshot = Mock(return_value=self.image)
        self.farm._classify_screen = Mock(return_value=ModuleScreen.UNKNOWN)
        self.farm._finish_home_work()
        self.assertIsNone(self.farm._make_battle_plan(self.image))
        self.farm._classify_screen.return_value = ModuleScreen.HOME
        self.farm._finish_home_work()
        self.assertIsNotNone(self.farm._make_battle_plan(self.image))
        self.farm.settings["camera_auto_adjust"] = True
        self.assertIsNone(self.farm._make_battle_plan(self.image))


class IdentityDiscoveryTests(unittest.TestCase):
    boot = "12345678-1234-4234-9234-123456789abc"
    other_boot = "12345678-1234-4234-9234-123456789def"

    def test_aliases_get_one_input_identity_and_canonical_mumu_runtime(self):
        listing = (
            "List of devices attached\n"
            "emulator-5556 device\n127.0.0.1:16416 device\n127.0.0.1:16384 device\n"
        )

        def execute(args, **kwargs):
            if args[1:] == ["devices", "-l"]:
                return SimpleNamespace(returncode=0, stdout=listing)
            self.assertEqual(
                ["shell", "cat", "/proc/sys/kernel/random/boot_id"], args[3:]
            )
            boot = self.other_boot if args[2] == "127.0.0.1:16384" else self.boot
            return SimpleNamespace(returncode=0, stdout=boot + "\n")

        with patch("cocmagic.device_manager.run_hidden", side_effect=execute):
            a = resolve_device_ownership("adb", "emulator-5556")
            b = resolve_device_ownership("adb", "127.0.0.1:16416")
        self.assertEqual(a, b)
        self.assertEqual("boot:" + self.boot, a.identity)
        self.assertEqual("127.0.0.1:16416", a.runtime_serial)
        self.assertEqual(("127.0.0.1:16416", "emulator-5556"), a.aliases)

    def test_unknown_identity_is_rejected_instead_of_using_serial_as_identity(self):
        for output in ("", "permission denied", "00000000-0000-0000-0000-000000000000"):
            with (
                self.subTest(output=output),
                patch(
                    "cocmagic.device_manager.run_hidden",
                    return_value=SimpleNamespace(returncode=0, stdout=output),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "chưa cấp quyền input"):
                    resolve_device_ownership("adb", "emulator-5556")

    def test_boot_change_during_discovery_is_rejected(self):
        responses = [
            SimpleNamespace(returncode=0, stdout=self.boot),
            SimpleNamespace(returncode=0, stdout="List of devices attached\n"),
            SimpleNamespace(returncode=0, stdout=self.other_boot),
        ]
        with patch("cocmagic.device_manager.run_hidden", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "đổi phiên boot"):
                resolve_device_ownership("adb", "emulator-5556")

    def test_unavailable_alias_listing_does_not_weaken_input_identity(self):
        responses = [
            SimpleNamespace(returncode=0, stdout=self.boot),
            SimpleNamespace(returncode=1, stdout=""),
            SimpleNamespace(returncode=0, stdout=self.boot),
        ]
        with patch("cocmagic.device_manager.run_hidden", side_effect=responses):
            owner = resolve_device_ownership("adb", "emulator-5556")
        self.assertEqual("boot:" + self.boot, owner.identity)
        self.assertEqual("emulator-5556", owner.runtime_serial)


class AliasLeaseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def store(self, serial, identity="boot:same", **kwargs):
        store = HybridRuntimeStore(
            self.folder.name,
            serial,
            device_identity=identity,
            log=lambda _: None,
            **kwargs,
        )
        self.addCleanup(store.close)
        return store

    def test_second_alias_process_is_rejected_without_releasing_the_first(self):
        first = self.store("emulator-5556").acquire()
        code = (
            "from cocmagic.hybrid_runtime import HybridRuntimeStore\n"
            f'HybridRuntimeStore({self.folder.name!r}, "127.0.0.1:16416", '
            'device_identity="boot:same").acquire()'
        )
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("writer", result.stderr)
        rejected = self.store("127.0.0.1:16416")
        with self.assertRaises(RuntimeError):
            rejected.acquire()
        rejected.close()
        with self.assertRaises(RuntimeError):
            self.store("localhost:16416").acquire()
        first.close()
        rejected.acquire()

    def test_distinct_vms_have_independent_input_and_stop(self):
        first = self.store("A", "boot:A").acquire()
        second = self.store("B", "boot:B").acquire()
        second.save(HybridRuntime(last_bonus_state="available"))
        first.close()
        self.store("A-alias", "boot:A").acquire()
        with self.assertRaises(RuntimeError):
            self.store("B-alias", "boot:B").acquire()
        self.assertEqual("available", second.load().last_bonus_state)

    def test_aliases_share_runtime_and_keep_it_across_boot(self):
        first = self.store("emulator-5556", runtime_serial="127.0.0.1:16416").acquire()
        first.save(
            HybridRuntime(
                last_daily_check_date="2026-10-11", last_bonus_state="available"
            )
        )
        first.close()
        next_boot = self.store(
            "127.0.0.1:16416", "boot:next", runtime_serial="127.0.0.1:16416"
        ).acquire()
        self.assertEqual(first.path, next_boot.path)
        self.assertEqual("2026-10-11", next_boot.load().last_daily_check_date)

    def test_old_alias_runtime_is_read_without_deleting_or_overwriting_it(self):
        old = HybridRuntimeStore(
            self.folder.name, "emulator-5556", log=lambda _: None
        ).acquire()
        old.save(
            HybridRuntime(
                last_bonus_state="available", last_daily_check_date="2026-10-11"
            )
        )
        original = old.path.read_bytes()
        old.close()
        shared = self.store(
            "127.0.0.1:16416",
            runtime_serial="127.0.0.1:16416",
            legacy_serials=("emulator-5556",),
        ).acquire()
        runtime = shared.load()
        self.assertEqual("available", runtime.last_bonus_state)
        shared.save(runtime)
        self.assertEqual(original, old.path.read_bytes())
        self.assertEqual(
            "127.0.0.1:16416",
            json.loads(shared.path.read_text(encoding="utf-8"))["serial"],
        )

    def test_runtime_lock_failure_rolls_back_identity_lease(self):
        legacy = HybridRuntimeStore(
            self.folder.name, "canonical", log=lambda _: None
        ).acquire()
        self.addCleanup(legacy.close)
        rejected = self.store("alias", runtime_serial="canonical")
        with self.assertRaises(RuntimeError):
            rejected.acquire()
        self.assertIsNone(rejected._identity_lock_file)
        self.store("different-runtime").acquire()

    def test_old_serial_owner_blocks_a_new_canonical_alias_after_reboot(self):
        old = HybridRuntimeStore(
            self.folder.name, "emulator-5556", log=lambda _: None
        ).acquire()
        self.addCleanup(old.close)
        new = self.store(
            "127.0.0.1:16416",
            "boot:new",
            runtime_serial="127.0.0.1:16416",
            legacy_serials=("emulator-5556", "127.0.0.1:16416"),
        )
        with self.assertRaises(RuntimeError):
            new.acquire()
        self.assertIsNone(new._identity_lock_file)
        old.close()
        new.acquire()
        with self.assertRaises(RuntimeError):
            HybridRuntimeStore(
                self.folder.name, "emulator-5556", log=lambda _: None
            ).acquire()

    def test_engine_acquires_identity_and_alias_locks_before_input(self):
        bot = BotEngine(config.migrate_settings({}), "emulator-5556")
        bot.adb = ADBController(serial="emulator-5556", settings={})
        owner = DeviceOwnership(
            "boot:same", "127.0.0.1:16416", ("emulator-5556", "127.0.0.1:16416")
        )
        with (
            patch("cocmagic.bot_engine.resolve_device_ownership", return_value=owner),
            patch("cocmagic.bot_engine.HybridRuntimeStore") as store,
        ):
            self.assertTrue(bot._acquire_input_runtime())
        self.assertEqual(owner.identity, store.call_args.kwargs["device_identity"])
        self.assertEqual(owner.runtime_serial, store.call_args.kwargs["runtime_serial"])
        self.assertEqual(owner.aliases, store.call_args.kwargs["legacy_serials"])
        store.return_value.acquire.assert_called_once()
        self.assertTrue(bot._owns_input)

    def test_engine_never_sends_or_releases_input_when_identity_is_unknown(self):
        for mode in ("main", "builder", "hybrid"):
            with self.subTest(mode=mode):
                bot = BotEngine(
                    config.migrate_settings({"run_mode": mode}), "emulator-5556"
                )
                bot.adb = ADBController(serial="emulator-5556", settings={})
                bot._connect_adb = Mock(return_value=True)
                bot._print_banner = Mock()
                bot._init_modules = Mock()
                bot.adb.screenshot = Mock(
                    return_value=np.zeros((900, 1600, 3), np.uint8)
                )
                with (
                    patch(
                        "cocmagic.bot_engine.resolve_device_ownership",
                        side_effect=RuntimeError("identity unavailable"),
                    ),
                    patch("cocmagic.bot_engine.signal.signal"),
                    patch.object(bot.adb, "tap") as tap,
                    patch.object(bot.adb, "release_touch") as release,
                ):
                    with self.assertRaisesRegex(RuntimeError, "identity unavailable"):
                        bot.start()
                bot._init_modules.assert_not_called()
                tap.assert_not_called()
                release.assert_not_called()
                self.assertFalse(bot._owns_input)


class BuilderProgressTests(unittest.TestCase):
    def test_slow_hero_recharge_cycles_deploy_all_camps_in_both_modes(self):
        for mode in ("around", "single_point"):
            with self.subTest(mode=mode):
                now = [100.0]
                next_hero_ready = [0.0]
                selected = [None]
                image = np.zeros((900, 1600, 3), np.uint8)
                stop = threading.Event()
                adb = Mock(device="offline-review", camera_revision=0, stop_event=stop)
                hero = BuilderSlot(
                    "battle_machine",
                    "battle_machine",
                    "hero",
                    (160, 810),
                    (105, 700, 110, 190),
                    SlotState.DEPLOYED,
                    AbilityState.READY,
                )
                camps = {
                    f"camp:{i}": BuilderSlot(
                        f"camp:{i}",
                        "baby_dragon",
                        "troop",
                        (200 + 120 * i, 810),
                        (145 + 120 * i, 700, 110, 190),
                        SlotState.UNDEPLOYED,
                        AbilityState.READY,
                    )
                    for i in range(1, 7)
                }
                deployed = []

                def tap(x, y, **kwargs):
                    if (x, y) == hero.point:
                        next_hero_ready[0] = now[0] + 30.0
                    elif y == 810:
                        selected[0] = next(
                            s.key for s in camps.values() if s.point == (x, y)
                        )
                    else:
                        key = selected[0]
                        self.assertEqual(SlotState.UNDEPLOYED, camps[key].state)
                        camps[key] = replace(
                            camps[key],
                            state=SlotState.DEPLOYED,
                            ability=AbilityState.USED,
                        )
                        deployed.append((key, (x, y)))
                    return True

                adb.tap.side_effect = tap
                reader = Mock()
                reader.capture.side_effect = lambda: Capture(image, 1, now[0], 0)
                reader.classify.return_value = ScreenObservation(
                    ScreenKind.BATTLE, "offline", Village.BUILDER
                )
                reader.battle.return_value = BattleObservation(True, False)
                reader.read_bar.side_effect = lambda _: ArmyObservation(
                    (
                        replace(
                            hero,
                            ability=AbilityState.READY
                            if now[0] >= next_hero_ready[0]
                            else AbilityState.CHARGING,
                        ),
                        *camps.values(),
                    ),
                    True,
                )
                module = BuilderFarmModule(
                    adb,
                    {"run_mode": "builder", "builder_deploy_mode": mode},
                    reader=reader,
                    navigator=Mock(),
                    rewards=Mock(),
                    camera=Mock(),
                    stop_event=stop,
                    clock=lambda: now[0],
                )
                module.stage = 1
                module.tactics.plan = BattlePlan(
                    [(400, 330), (1200, 330)], (800, 440), 1.0, np.zeros((4, 2))
                )
                with patch(
                    "cocmagic.modules.builder_farm_module.measure_motion",
                    return_value=SimpleNamespace(valid=True, changed=False),
                ):
                    for _ in range(12):
                        self.assertTrue(module.tick())
                        now[0] += 35.0
                self.assertIsNone(module.halt_reason)
                self.assertEqual(6, module.metrics["deployed"])
                self.assertEqual(6, module.metrics["hero_abilities"])
                self.assertEqual(list(camps), [key for key, _ in deployed])
                if mode == "single_point":
                    self.assertEqual(1, len({point for _, point in deployed}))

    def test_camera_discards_pixel_history_but_keeps_skills_and_retry_budget(self):
        adb = ADBController(serial="offline-review", settings={})
        module = BuilderFarmModule(
            adb,
            {"run_mode": "builder"},
            reader=Mock(),
            navigator=Mock(),
            rewards=Mock(),
        )
        tactics = module.tactics
        tactics.accepted = [(410, 330)]
        tactics.rejected = {(400, 330), (1200, 330)}
        tactics.attempts = {"camp:1": 3}
        tactics.used_abilities = {"camp:1"}
        tactics.attempted_abilities = {"camp:2"}
        tactics.deployed_at = {"camp:1": 20.0}
        tactics.hero_attempted = {"battle_machine": 22.0}
        tactics.hero_waiting = {"battle_machine"}
        module.camera.reset_view()
        self.assertEqual([], tactics.accepted)
        self.assertEqual(set(), tactics.rejected)
        tactics.plan = BattlePlan(
            [(400, 330), (1200, 330)],
            (800, 440),
            1.0,
            np.zeros((4, 2)),
            camera_revision=adb.camera_revision,
        )
        self.assertEqual((400, 330), tactics.point(None, adb.camera_revision))
        self.assertEqual({"camp:1": 3}, tactics.attempts)
        self.assertEqual({"camp:1"}, tactics.used_abilities)
        self.assertEqual({"camp:2"}, tactics.attempted_abilities)
        self.assertEqual({"camp:1": 20.0}, tactics.deployed_at)
        self.assertEqual({"battle_machine": 22.0}, tactics.hero_attempted)
        self.assertEqual({"battle_machine"}, tactics.hero_waiting)


if __name__ == "__main__":
    unittest.main()
