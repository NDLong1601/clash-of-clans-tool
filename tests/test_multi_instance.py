"""Isolation, persistence, and discovery for concurrent emulator sessions."""

import multiprocessing
import os
import queue
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.bot_engine import BotEngine
from cocmagic.bot_worker import run_instance
from cocmagic.device_manager import DeviceInfo, deduplicate_devices, normalize_serial, parse_devices
from cocmagic.gui import BotPanel
from cocmagic.instance_store import InstanceStore
from cocmagic.session_manager import BotSession


def fake_session_worker(serial, settings, events, stop_event):
    events.put({"kind": "log", "text": f"{serial}:{settings['min_gold']}"})
    stop_event.wait(10)
    events.put({"kind": "done", "stopped": stop_event.is_set(), "ok": True})


class DiscoveryTests(unittest.TestCase):
    def test_parser_keeps_only_ready_local_emulators(self):
        output = ("List of devices attached\n"
                  "127.0.0.1:16384 device model:MuMu\n"
                  "127.0.0.1:16416 offline\n"
                  "emulator-5554 device model:Android\n"
                  "usb123 device model:Phone\n")
        self.assertEqual(["127.0.0.1:16384", "emulator-5554"],
                         [item.serial for item in parse_devices(output)])

    def test_serial_validation_rejects_remote_targets(self):
        self.assertEqual("127.0.0.1:16416", normalize_serial("16416"))
        with self.assertRaises(ValueError):
            normalize_serial("192.168.1.8:5555")
        with self.assertRaises(ValueError):
            normalize_serial("70000")

    def test_multiple_adb_aliases_of_one_vm_produce_one_tab(self):
        devices = [DeviceInfo(serial, "device", "boot:same") for serial in
                   ("emulator-5554", "127.0.0.1:5555", "127.0.0.1:16384")]
        devices.append(DeviceInfo("127.0.0.1:16416", "device", "boot:other"))
        self.assertEqual(["127.0.0.1:16384", "127.0.0.1:16416"],
                         [item.serial for item in deduplicate_devices(devices)])
        self.assertEqual("127.0.0.1:5555",
                         deduplicate_devices(devices, ("127.0.0.1:5555",))[0].serial)


class StoreTests(unittest.TestCase):
    def test_profiles_save_independently_and_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "instances.json")
            store = InstanceStore(path, {"min_gold": 500_000, "auto_train": True})
            first = store.add("16384")
            second = store.add("16416")
            changed = first["settings"].copy()
            changed["min_gold"] = 900_000
            store.update_settings(first["serial"], changed)
            self.assertEqual(500_000, second["settings"]["min_gold"])
            loaded = InstanceStore(path, {"min_gold": 1}).load()
            self.assertEqual(900_000, loaded["127.0.0.1:16384"]["settings"]["min_gold"])
            self.assertEqual(500_000, loaded["127.0.0.1:16416"]["settings"]["min_gold"])

    def test_invalid_store_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "instances.json")
            with open(path, "w", encoding="utf-8") as target:
                target.write("{broken")
            with self.assertRaises(ValueError):
                InstanceStore(path, {}).load()
            with open(path, "r", encoding="utf-8") as source:
                self.assertEqual("{broken", source.read())

    def test_duplicate_port_is_not_added_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            store = InstanceStore(os.path.join(folder, "instances.json"), {})
            store.add("16384")
            store.add("127.0.0.1:16384")
            self.assertEqual(1, len(store.instances))


class WorkerTests(unittest.TestCase):
    def test_adb_commands_target_the_selected_serial_and_respect_stop(self):
        with patch.object(ADBController, "_run", return_value="device\n") as run:
            controller = ADBController(serial="emulator-5554", settings={})
            self.assertTrue(controller.connect())
            run.assert_called_once_with(["-s", "emulator-5554", "get-state"])
        stop = Mock()
        stop.is_set.return_value = True
        controller = ADBController(serial="127.0.0.1:16384", settings={},
                                   stop_event=stop)
        with patch.object(controller, "_shell") as shell:
            self.assertFalse(controller.tap(100, 100))
            self.assertIsNone(controller.screenshot())
            shell.assert_not_called()

    def test_engine_binds_explicit_serial(self):
        with patch("os.path.exists", return_value=True), patch(
                "cocmagic.bot_engine.ADBController") as controller:
            controller.return_value.connect.return_value = True
            engine = BotEngine({"verbose": True}, device_serial="127.0.0.1:16416")
            self.assertTrue(engine._connect_adb())
            self.assertEqual("127.0.0.1:16416", controller.call_args.kwargs["serial"])
            self.assertEqual({"verbose": True}, controller.call_args.kwargs["settings"])

    def test_worker_sends_log_status_and_completion(self):
        messages = queue.SimpleQueue()
        stop = Mock()
        stop.is_set.return_value = False
        with patch("cocmagic.bot_engine.BotEngine") as engine:
            def start():
                print("worker A")
                engine.call_args.kwargs["status_callback"](
                    {"status": "TRAIN", "wall_count": 2})
                return True
            engine.return_value.start.side_effect = start
            run_instance("127.0.0.1:16384", {"min_gold": 1}, messages, stop)
        items = []
        while True:
            try:
                items.append(messages.get_nowait())
            except queue.Empty:
                break
        self.assertTrue(any(item.get("kind") == "log" and "worker A" in item["text"]
                            for item in items))
        self.assertIn({"kind": "status", "status": "TRAIN", "wall_count": 2,
                       "serial": "127.0.0.1:16384"}, items)
        self.assertEqual("done", items[-1]["kind"])

    def test_two_processes_route_logs_and_stop_independently(self):
        context = multiprocessing.get_context("spawn")
        first = BotSession("127.0.0.1:16384", fake_session_worker, context)
        second = BotSession("127.0.0.1:16416", fake_session_worker, context)
        try:
            first.start({"min_gold": 1})
            second.start({"min_gold": 2})
            deadline = time.monotonic() + 12
            logs = [[], []]
            while time.monotonic() < deadline and not all(logs):
                for index, session in enumerate((first, second)):
                    logs[index].extend(item["text"] for item in session.poll()
                                       if item["kind"] == "log")
                time.sleep(0.05)
            self.assertEqual(["127.0.0.1:16384:1"], logs[0])
            self.assertEqual(["127.0.0.1:16416:2"], logs[1])
            first.stop()
            deadline = time.monotonic() + 5
            while first.is_alive() and time.monotonic() < deadline:
                first.poll()
                time.sleep(0.05)
            self.assertFalse(first.is_alive())
            self.assertTrue(second.is_alive())
        finally:
            first.stop()
            second.stop()
            for session in (first, second):
                deadline = time.monotonic() + 5
                while session.is_alive() and time.monotonic() < deadline:
                    session.poll()
                    time.sleep(0.05)
                session.terminate()


class GuiTests(unittest.TestCase):
    def test_two_tabs_have_independent_form_values(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk unavailable: {exc}")
        root.withdraw()
        previous = config.SETTINGS_FILE
        try:
            with tempfile.TemporaryDirectory() as folder:
                config.SETTINGS_FILE = os.path.join(folder, "settings.json")
                with patch.object(BotPanel, "_refresh"):
                    panel = BotPanel(root, initial_port=16384)
                second = panel._add_tab(panel.store.add("16416"))
                first = panel.tabs["127.0.0.1:16384"]
                first.vars["min_gold"].set("900000")
                first._mode_changed("event")
                first.event_resource_display.set("Vàng (Gold)")
                self.assertTrue(first._save())
                self.assertTrue(first.settings["event_mode"])
                self.assertEqual("gold", first.settings["event_resource_priority"])
                self.assertFalse(second.event_mode.get())
                self.assertEqual("disabled", str(second.event_resource.cget("state")))
                loaded = InstanceStore(panel.store.path, config.DEFAULT_SETTINGS).load()
                self.assertEqual("gold", loaded[first.serial]["settings"]["event_resource_priority"])
                self.assertFalse(loaded[second.serial]["settings"]["event_mode"])
                self.assertEqual("500,000", second.vars["min_gold"].get())
                self.assertEqual(2, len(panel.notebook.tabs()))
        finally:
            config.SETTINGS_FILE = previous
            root.destroy()


if __name__ == "__main__":
    unittest.main()
