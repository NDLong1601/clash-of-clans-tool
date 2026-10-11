"""GĐ7 failure injection. Real guards/modules, simulated transport, no device input."""

from pathlib import Path
from types import SimpleNamespace
import queue
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.bot_engine import BotEngine
from cocmagic.builder_screen_reader import ScreenKind, ScreenObservation, Village
from cocmagic.builder_vision import BuilderBattleReader, SlotState, AbilityState
from cocmagic.camera_backend import SerialGestureBackend, TouchDevice
from cocmagic.hybrid_runtime import HybridRuntimeStore, HybridRuntime
from cocmagic.modules.builder_farm_module import BuilderFarmModule, BuilderPhase
from cocmagic.modules.farm_module import FarmModule, FarmState, CardSlot, SpellProgress
from cocmagic.modules.wall_module import WallModule
from cocmagic.recovery import RecoveryInterrupted, RuntimeWriteError
from cocmagic.run_coordinator import RunCoordinator
from cocmagic.session_manager import BotSession
from cocmagic.ui_dialogs import find_inactivity_reload
from cocmagic.village_module import ModuleScreen


ROOT = Path(config.BASE_DIR)


def picture(path):
    image = cv2.imread(str(ROOT / "tests/fixtures" / path))
    if image is None:
        raise AssertionError(path)
    return image


def engine(serial="offline-A", active="builder", stop_event=None):
    bot = BotEngine(
        {"run_mode": active, "auto_train": False},
        device_serial=serial,
        stop_event=stop_event,
    )
    bot.adb = ADBController(serial=serial, settings={}, stop_event=bot.stop_event)
    bot._wait = Mock()
    bot.adb.tap = Mock(return_value=True)
    bot.farm_mod = FarmModule(
        bot.adb, Mock(), Mock(), bot.settings, stop_event=bot.stop_event
    )
    bot.builder_mod = BuilderFarmModule(
        bot.adb, bot.settings, stop_event=bot.stop_event
    )
    bot.coordinator = RunCoordinator(
        serial,
        {"main": bot.farm_mod, "builder": bot.builder_mod},
        active,
        stop_event=bot.stop_event,
    )
    bot.adb.frame_guard = bot._guard_frame
    bot.adb.input_failure_handler = bot._input_failed
    return bot


def mixed_mode_worker(serial, settings, events, stop_event):
    """Two spawned workers, real modules/transport guard, simulated device IO."""
    bot = engine(serial, settings["run_mode"], stop_event)
    bot.settings["min_gold"] = settings["min_gold"]
    bot.adb.tap = ADBController.tap.__get__(bot.adb)
    store = HybridRuntimeStore(settings["runtime_dir"], serial).acquire()
    try:

        def transport(command, **_kwargs):
            events.put(
                {
                    "kind": "log",
                    "serial": serial,
                    "text": f"input:{command[2]}:{settings['run_mode']}:{settings['min_gold']}",
                }
            )
            return SimpleNamespace(returncode=0, stderr=b"")

        with patch("cocmagic.adb_controller.run_hidden", side_effect=transport):
            bot.adb.tap(300, 400, delay=0)
        store.save(
            HybridRuntime(
                last_bonus_state="available"
                if settings["run_mode"] == "builder"
                else "complete"
            )
        )
        events.put({"kind": "status", **bot.coordinator.status()})
        if settings["run_mode"] == "builder":
            bot.adb._capture_screenshot = Mock(return_value=None)
            for _ in range(6):
                try:
                    bot.adb.screenshot(use_cache=False)
                except RecoveryInterrupted:
                    pass
            events.put({"kind": "status", **bot.coordinator.status()})
        else:
            stop_event.wait(15)
        events.put(
            {
                "kind": "done",
                "serial": serial,
                "ok": not bool(bot.coordinator.halt_reason),
                "stopped": stop_event.is_set(),
            }
        )
    finally:
        store.close()


class RecoveryTests(unittest.TestCase):
    def test_valid_resolution_loading_during_main_deployment_cancels_old_targets(self):
        bot = engine(active="main")
        bot.farm_mod.state = FarmState.ATTACKING
        bot.farm_mod._confirmed_main_points = [(400, 330)]
        bot.adb._capture_screenshot = Mock(
            return_value=np.zeros((900, 1600, 3), np.uint8)
        )
        with self.assertRaises(RecoveryInterrupted):
            bot.adb.screenshot(use_cache=False)
        self.assertEqual(FarmState.RECOVERING, bot.farm_mod.state)
        self.assertFalse(bot.farm_mod._confirmed_main_points)
        bot.adb.tap.assert_not_called()

    def test_cart_panel_lost_before_collect_never_reuses_old_button(self):
        bot = engine()
        rewards = bot.builder_mod.rewards
        frame = SimpleNamespace(image=np.zeros((900, 1600, 3), np.uint8))
        panel = ScreenObservation(
            ScreenKind.MODAL,
            "cart",
            Village.BUILDER,
            "cart",
            {"cart_collect": (800, 770), "close": (1400, 50)},
        )
        rewards._wait_cart = Mock(side_effect=[(frame, panel), (None, None)])
        rewards._close_cart = Mock(return_value=False)
        result = rewards.collect_cart(resume=True)
        self.assertFalse(result.success)
        self.assertFalse(result.collected)
        bot.adb.tap.assert_not_called()

    def test_title_only_connection_modal_blocks_without_blind_retry(self):
        bot = engine(active="main")
        image = picture("connection_lost.png")
        image[505:570, 400:650] = image[350, 800]
        bot.adb._capture_screenshot = Mock(return_value=image)
        with self.assertRaises(RecoveryInterrupted):
            bot.adb.screenshot(use_cache=False)
        bot.adb.tap.assert_not_called()
        self.assertEqual(FarmState.RECOVERING, bot.farm_mod.state)

    def test_connection_interrupts_every_nested_transaction_before_next_input(self):
        actions = {
            "main": lambda b: b.farm_mod._capture(use_cache=False),
            "builder": lambda b: b.builder_mod.tick(),
            "stage": lambda b: b.builder_mod.tick(),
            "reward": lambda b: b.builder_mod.rewards.claim_star_bonus(),
            "cart": lambda b: b.builder_mod.rewards.collect_cart(resume=True),
            "village": lambda b: b.builder_mod.navigator.navigate(Village.MAIN),
        }
        for name, action in actions.items():
            with self.subTest(transaction=name):
                bot = engine(active="main" if name == "main" else "builder")
                bot.adb._capture_screenshot = Mock(
                    return_value=picture("connection_lost.png")
                )
                bot.farm_mod._initial_trained = True
                bot.farm_mod._pending_spells[CardSlot(800, 840, "spell")] = (
                    SpellProgress(cast_index=1)
                )
                bot.builder_mod.phase = (
                    BuilderPhase.TRANSITION if name == "stage" else BuilderPhase.FIGHT
                )
                bot.builder_mod.tactics.used_abilities.add("camp:1")
                with self.assertRaises(RecoveryInterrupted):
                    action(bot)
                self.assertEqual(1, bot.adb.tap.call_count)  # only verified Try Again
                self.assertEqual(FarmState.RECOVERING, bot.farm_mod.state)
                self.assertEqual(BuilderPhase.CLASSIFY, bot.builder_mod.phase)
                self.assertFalse(bot.builder_mod.tactics.used_abilities)
                self.assertFalse(bot.farm_mod._pending_spells)
                self.assertTrue(bot.farm_mod._initial_trained)
                self.assertEqual("unknown", bot.coordinator.status()["actual_village"])

    def test_lost_adb_resets_once_then_halts_only_bad_instance(self):
        one, two = engine(), engine("offline-B", "main")
        two.farm_mod.state = FarmState.BATTLE_WAIT
        two.farm_mod._button_cache["next"] = (1200, 600)
        one.adb._capture_screenshot = Mock(return_value=None)
        for _ in range(6):
            with self.assertRaises(RecoveryInterrupted):
                one.adb.screenshot(use_cache=False)
        self.assertIn("6 lần", one.coordinator.halt_reason)
        self.assertEqual(1, one.builder_mod.metrics["recoveries"])
        self.assertEqual(FarmState.BATTLE_WAIT, two.farm_mod.state)
        self.assertEqual({"next": (1200, 600)}, two.farm_mod._button_cache)
        self.assertIsNone(two.coordinator.halt_reason)
        one.adb.tap.assert_not_called()
        two.adb.tap.assert_not_called()

    def test_failed_retry_still_invalidates_battle_and_repeated_reload_is_bounded(self):
        bot = engine()
        bot.adb.tap.return_value = False
        bot.adb._capture_screenshot = Mock(return_value=picture("connection_lost.png"))
        for _ in range(4):
            with self.assertRaises(RecoveryInterrupted):
                bot.adb.screenshot(use_cache=False)
        self.assertEqual(3, bot.adb.tap.call_count)
        self.assertIsNotNone(bot.coordinator.halt_reason)
        self.assertEqual(BuilderPhase.CLASSIFY, bot.builder_mod.phase)

    def test_reload_during_handoff_unsuspends_source_and_cancels_old_request(self):
        bot = engine(active="main")
        main = bot.farm_mod
        main.tick = Mock(return_value=True)
        main._handoff_ready = True
        main._confirmed_screen = ModuleScreen.HOME
        main.state = FarmState.HOME

        def navigate(*_):
            self.assertTrue(main._suspended)
            bot.coordinator.reset_after_reload()
            raise RecoveryInterrupted("reload during boat")

        bot.coordinator.switch_village = navigate
        bot.coordinator.request_switch("builder", "daily")
        with self.assertRaises(RecoveryInterrupted):
            bot.coordinator.tick()
        self.assertFalse(main._suspended)
        self.assertIsNone(bot.coordinator.pending)
        self.assertIsNone(bot.coordinator._transition_target)
        self.assertIsNone(bot.coordinator.halt_reason)

    def test_main_mode_navigates_only_from_classified_builder_home(self):
        bot = engine(active="main")
        bot.village_reader = Mock()
        bot.village_reader.classify.return_value = ScreenObservation(
            ScreenKind.BUILDER_HOME, "home", Village.BUILDER
        )
        bot.navigator = Mock()
        bot.navigator.navigate.return_value = SimpleNamespace(success=True)
        bot.adb._capture_screenshot = Mock(
            return_value=picture("dual_village/builder/home-shadow.png")
        )
        with self.assertRaises(RecoveryInterrupted):
            bot.adb.screenshot(use_cache=False)
        bot.navigator.navigate.assert_called_once_with(
            Village.MAIN, source=Village.BUILDER
        )
        self.assertEqual(FarmState.RECOVERING, bot.farm_mod.state)
        bot.adb.tap.assert_not_called()

    def test_wall_reload_unwinds_without_cleanup_inputs(self):
        bot = engine(active="main")
        wall = WallModule(bot.adb, Mock(), {}, stop_event=bot.stop_event)
        wall.reader.read_home_resources.return_value = {"gold": 999999999}
        wall._builder_available = Mock(return_value=True)
        wall._position_cache["builder"] = (800, 50)
        wall._close_panels = Mock()
        bot.adb.screenshot = Mock(
            side_effect=[
                np.zeros((900, 1600, 3), np.uint8),
                RecoveryInterrupted("reload"),
            ]
        )
        with self.assertRaises(RecoveryInterrupted):
            wall._upgrade_one_batch()
        wall._close_panels.assert_not_called()
        self.assertEqual(1, bot.adb.tap.call_count)

    def test_callback_failure_does_not_reset_or_crash_other_instance(self):
        bot = engine()
        bot.status_callback = Mock(side_effect=RuntimeError("UI callback failed"))
        with patch("builtins.print") as log:
            bot._emit_status(bot.coordinator.status())
            bot._emit_status(bot.coordinator.status())
        self.assertEqual(1, log.call_count)
        self.assertIsNone(bot.coordinator.halt_reason)
        self.assertEqual(0, bot.builder_mod.metrics["recoveries"])

    def test_failed_camera_listener_does_not_skip_other_invalidations(self):
        adb = ADBController(serial="A", settings={})
        failed = Mock(side_effect=RuntimeError("cache failure"))
        second = Mock()
        adb.add_camera_listener(failed)
        adb.add_camera_listener(second)
        with self.assertRaisesRegex(RuntimeError, "cache failure"):
            adb.mark_camera_input()
        second.assert_called_once_with(1)


class ModalTests(unittest.TestCase):
    def test_native_dark_home_battle_reward_cart_never_trigger_inactivity(self):
        for path in (
            "dual_village/builder/home-shadow.png",
            "dual_village/builder/stage2-used.png",
            "dual_village/navigation/reward.png",
            "dual_village/builder/cart-covered.png",
        ):
            with self.subTest(path=path):
                self.assertIsNone(find_inactivity_reload(picture(path)))
        # Specifically defeated old darkness+bright-text heuristic.
        image = np.zeros((900, 1600, 3), np.uint8)
        image[340:360, 380:600] = 180
        self.assertFalse(BotEngine({})._detect_inactivity_popup(image))

    def test_both_exact_inactivity_anchors_are_required_even_over_builder_battle(self):
        reader = BuilderBattleReader()
        image = picture("dual_village/builder/stage2-used.png")
        title = reader.art["inactivity_title"]
        reload = reader.art["inactivity_reload"]
        image[335 : 335 + title.shape[0], 380 : 380 + title.shape[1]] = title
        self.assertIsNone(find_inactivity_reload(image))
        image[485 : 485 + reload.shape[0], 380 : 380 + reload.shape[1]] = reload
        self.assertIsNotNone(find_inactivity_reload(image))
        screen = reader.classify(image)
        self.assertEqual("inactivity", screen.panel)
        self.assertIsNone(screen.village)


class StopAndTransportTests(unittest.TestCase):
    def test_rejected_second_worker_never_cancels_the_first_workers_touch(self):
        bot = engine(active="main")
        bot._connect_adb = Mock(return_value=True)
        bot._print_banner = Mock()
        bot.adb.screenshot = Mock(return_value=np.zeros((900, 1600, 3), np.uint8))
        bot.adb.release_touch = Mock()
        with (
            patch("cocmagic.bot_engine.HybridRuntimeStore") as store,
            patch(
                "cocmagic.bot_engine.resolve_device_ownership",
                return_value=SimpleNamespace(
                    identity="boot:test",
                    runtime_serial=bot.adb.device,
                    aliases=(bot.adb.device,),
                ),
            ),
            patch("cocmagic.bot_engine.signal.signal"),
        ):
            store.return_value.acquire.side_effect = RuntimeError("existing writer")
            with self.assertRaisesRegex(RuntimeError, "existing writer"):
                bot.start()
        bot.adb.release_touch.assert_not_called()
        bot.adb.tap.assert_not_called()

    def test_repeated_input_errors_halt_after_three_without_resetting_the_other_instance(
        self,
    ):
        bot = engine()
        bot.adb.tap = ADBController.tap.__get__(bot.adb)
        with patch(
            "cocmagic.adb_controller.run_hidden",
            return_value=SimpleNamespace(returncode=1, stderr=b"input failed"),
        ):
            for _ in range(3):
                with self.assertRaises(RecoveryInterrupted):
                    bot.adb.tap(400, 400, delay=0)
        self.assertIn("3 lần", bot.coordinator.halt_reason)

    def test_stop_during_builder_ability_has_no_followup_tap_or_fake_receipt(self):
        bot = engine()
        bot.adb.frame_guard = None
        bot.adb._capture_screenshot = Mock(
            return_value=picture("dual_village/builder/deployed.png")
        )
        module = bot.builder_mod
        troop = next(
            s
            for s in module.reader.read_bar(bot.adb.screenshot()).slots
            if s.state == SlotState.DEPLOYED
            and s.ability == AbilityState.READY
            and s.role != "hero"
        )
        bot.adb.tap.side_effect = lambda *_a, **_k: bot.stop_event.set() or True
        self.assertTrue(module._ability(troop))
        self.assertEqual(1, bot.adb.tap.call_count)
        self.assertEqual(0, module.metrics["troop_abilities"])

    def test_stop_in_reward_cart_and_boat_wait_does_not_submit_any_input(self):
        for name in ("reward", "cart", "boat"):
            with self.subTest(transaction=name):
                bot = engine()
                bot.adb.frame_guard = None
                bot.adb._capture_screenshot = Mock(
                    return_value=np.zeros((900, 1600, 3), np.uint8)
                )
                # Stop arrives at the transaction's first wait.
                bot.builder_mod.navigator.wait = Mock(
                    side_effect=lambda *_: bot.stop_event.set()
                )
                if name == "reward":
                    result = bot.builder_mod.rewards.claim_star_bonus()
                    self.assertFalse(result.success)
                    self.assertNotEqual("complete", result.bonus.state.value)
                elif name == "cart":
                    self.assertFalse(
                        bot.builder_mod.rewards.collect_cart(resume=True).success
                    )
                else:
                    self.assertFalse(
                        bot.builder_mod.navigator.navigate(Village.MAIN).success
                    )
                bot.adb.tap.assert_not_called()

    def test_two_processes_different_modes_and_configs_keep_input_runtime_status_and_failure_isolated(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            a = BotSession("offline-A", mixed_mode_worker)
            b = BotSession("offline-B", mixed_mode_worker)
            sessions = (a, b)
            try:
                for session, mode, amount in ((a, "builder", 123), (b, "main", 456)):
                    session.start(
                        {"run_mode": mode, "min_gold": amount, "runtime_dir": directory}
                    )
                messages = [[], []]
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    for i, s in enumerate(sessions):
                        messages[i].extend(s.poll())
                    if not a.is_alive() and all(
                        any(e["kind"] == "status" for e in row) for row in messages
                    ):
                        break
                    time.sleep(0.05)
                self.assertFalse(a.is_alive())
                self.assertTrue(b.is_alive())
                self.assertTrue(
                    any(
                        "offline-A:builder:123" in e.get("text", "")
                        for e in messages[0]
                    )
                )
                self.assertTrue(
                    any("offline-B:main:456" in e.get("text", "") for e in messages[1])
                )
                self.assertTrue(any(e.get("halt_reason") for e in messages[0]))
                self.assertFalse(any(e.get("halt_reason") for e in messages[1]))
                for i, session in enumerate(sessions):
                    self.assertTrue(
                        all(
                            e.get("serial", session.serial) == session.serial
                            for e in messages[i]
                        )
                    )
                first = HybridRuntimeStore(directory, "offline-A").acquire()
                try:
                    self.assertEqual("available", first.load().last_bonus_state)
                finally:
                    first.close()
            finally:
                for s in sessions:
                    s.stop()
                for s in sessions:
                    if s.process:
                        s.process.join(timeout=5)
                    s.terminate()
            second = HybridRuntimeStore(directory, "offline-B").acquire()
            try:
                self.assertEqual("complete", second.load().last_bonus_state)
            finally:
                second.close()

    def test_stop_during_batch_kills_only_its_remote_job_and_sends_no_next_batch(self):
        stop = threading.Event()
        adb = ADBController(serial="A", settings={}, stop_event=stop)

        def execute(*_a, **_k):
            stop.set()
            return SimpleNamespace(returncode=0, stderr=b"")

        with patch("cocmagic.adb_controller.run_hidden", side_effect=execute) as run:
            self.assertFalse(adb.tap_many([(300, 400)] * 16, 0.02))
            self.assertFalse(adb.tap_many([(500, 500)], 0.02))
        self.assertEqual(3, run.call_count)  # batch, kill, CANCEL only
        self.assertEqual(15, run.call_args_list[0].kwargs["timeout"])
        self.assertIn("kill", run.call_args_list[1].args[0][-1])
        self.assertIn("CANCEL", run.call_args_list[2].args[0][-1])
        self.assertTrue(
            all(c.args[0][:3] == [adb.adb, "-s", "A"] for c in run.call_args_list)
        )

    def test_input_failure_unwinds_and_timeout_cleans_remote_batch_before_recovery(
        self,
    ):
        adb = ADBController(serial="A", settings={})
        adb.input_failure_handler = Mock()
        with patch(
            "cocmagic.adb_controller.run_hidden",
            side_effect=[
                subprocess.TimeoutExpired("adb", 15),
                SimpleNamespace(returncode=0),
                SimpleNamespace(returncode=0),
            ],
        ):
            with self.assertRaises(RecoveryInterrupted):
                adb.tap_many([(300, 400)])
        adb.input_failure_handler.assert_called_once_with()

    def test_unconfirmed_batch_cleanup_is_fatal_not_permission_to_resume(self):
        adb = ADBController(serial="A", settings={})
        adb.input_failure_handler = Mock()
        with patch(
            "cocmagic.adb_controller.run_hidden",
            side_effect=[
                subprocess.TimeoutExpired("adb", 15),
                subprocess.TimeoutExpired("adb", 3),
                SimpleNamespace(returncode=0),
            ],
        ):
            with self.assertRaises(RecoveryInterrupted):
                adb.tap_many([(300, 400)])
        self.assertTrue(adb.input_failure_handler.call_args.kwargs["fatal"])

    def test_oversized_batch_never_submits_and_stopped_capture_has_no_png_fallback(
        self,
    ):
        stop = threading.Event()
        adb = ADBController(serial="A", settings={}, stop_event=stop)
        with patch("cocmagic.adb_controller.run_hidden") as run:
            with self.assertRaises(ValueError):
                adb.tap_many([(300, 400)] * 17)
            run.assert_not_called()

            def raw(*_a, **_k):
                stop.set()
                return SimpleNamespace(returncode=1, stdout=b"")

            run.side_effect = raw
            self.assertIsNone(adb.screenshot())
            self.assertEqual(1, run.call_count)

    def test_stop_in_pinch_releases_slots_and_submits_no_second_gesture(self):
        stop = threading.Event()
        adb = ADBController(serial="B", settings={}, stop_event=stop)
        backend = SerialGestureBackend(adb)
        backend.touch = TouchDevice("/dev/input/event4", 900, 1600, 1, (1600, 900))
        backend.probe = Mock(return_value=True)

        def execute(*_a, **_k):
            stop.set()
            return SimpleNamespace(returncode=0)

        with patch("cocmagic.camera_backend.run_hidden", side_effect=execute) as run:
            self.assertFalse(backend.zoom((800, 410), 0.6))
            self.assertFalse(backend.zoom((800, 410), 0.6))
        self.assertEqual(2, run.call_count)
        self.assertIn("3 57 -1", run.call_args_list[1].args[0][-1])

    def test_raw_pinch_cleanup_failure_is_not_reported_as_released_by_cancel(self):
        adb = ADBController(serial="B", settings={})
        backend = SerialGestureBackend(adb)
        backend.touch = TouchDevice("/dev/input/event4", 900, 1600, 1, (1600, 900))
        backend.probe = Mock(return_value=True)
        adb.release_touch = Mock(return_value=True)
        with patch(
            "cocmagic.camera_backend.run_hidden",
            side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=1)],
        ):
            self.assertFalse(backend.zoom((800, 410), 0.6))
        self.assertFalse(backend.release())

    def test_status_queue_rejects_foreign_serial_and_copies_nested_settings(self):
        context = Mock()
        context.Queue.return_value = queue.Queue()
        context.Process.return_value.is_alive.return_value = True
        session = BotSession("A", context=context)
        original = {"run_mode": "builder", "extension": {"values": [1]}}
        session.start(original)
        original["extension"]["values"].append(2)
        self.assertEqual(
            [1], context.Process.call_args.kwargs["args"][1]["extension"]["values"]
        )
        session.events.put({"kind": "status", "serial": "B", "status": "wrong"})
        session.events.put({"kind": "status", "serial": "A", "status": "right"})
        self.assertEqual(["right"], [e["status"] for e in session.poll()])

    def test_atomic_runtime_failure_leaves_both_serial_documents_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            a = HybridRuntimeStore(directory, "A").acquire()
            b = HybridRuntimeStore(directory, "B").acquire()
            try:
                a.save(HybridRuntime(last_bonus_state="available"))
                b.save(HybridRuntime(last_bonus_state="complete"))
                before = a.path.read_bytes(), b.path.read_bytes()
                with patch(
                    "cocmagic.hybrid_runtime.os.replace",
                    side_effect=OSError("disk full"),
                ):
                    with self.assertRaises(RuntimeWriteError):
                        a.save(HybridRuntime(last_bonus_state="unknown"))
                self.assertEqual(before, (a.path.read_bytes(), b.path.read_bytes()))
                self.assertFalse(list(Path(directory).glob("*.tmp")))
            finally:
                a.close()
                b.close()
