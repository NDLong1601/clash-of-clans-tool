"""GĐ1 compatibility, scoped validation, UI lifecycle and profile isolation."""

import io
import json
import os
import tempfile
import tkinter as tk
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from unittest.mock import Mock, patch

from cocmagic import config
from cocmagic.bot_engine import BotEngine
from cocmagic.gui import BotPanel
from cocmagic.instance_store import InstanceStore
from cocmagic.license_client import LicenseError
from cocmagic.main import main


class MigrationTests(unittest.TestCase):
    def test_legacy_migration_is_lossless_idempotent_and_owns_extension_data(self):
        legacy = {
            "min_gold": 812345,
            "upgrade_walls": False,
            "event_mode": False,
            "use_queen": False,
            "extension": {"slots": [1, 2]},
        }
        original = deepcopy(legacy)
        migrated = config.migrate_settings(legacy)
        self.assertEqual("main", migrated["run_mode"])
        self.assertEqual(2, migrated["settings_schema_version"])
        self.assertEqual(migrated, config.migrate_settings(migrated))
        self.assertEqual(legacy, {key: migrated[key] for key in legacy})
        migrated["extension"]["slots"].append(3)
        self.assertEqual(original, legacy)

    def test_saved_new_values_and_future_extensions_are_preserved(self):
        saved = {
            "settings_schema_version": 3,
            "run_mode": "hybrid",
            "builder_deploy_mode": "single_point",
            "camera_auto_adjust": True,
            "hybrid_check_time": "16:45",
            "future_option": ["x"],
        }
        migrated = config.migrate_settings(saved)
        self.assertEqual(saved, {key: migrated[key] for key in saved})

    def test_loading_both_legacy_files_does_not_write_them(self):
        with tempfile.TemporaryDirectory() as folder:
            settings_path = os.path.join(folder, "settings.json")
            store_path = os.path.join(folder, "instances.json")
            legacy = {"min_gold": 123456, "unknown": {"tags": ["keep"]}}
            payload = {
                "version": 1,
                "instances": [{"serial": "16384", "name": "First", "settings": legacy}],
            }
            for path, value in ((settings_path, legacy), (store_path, payload)):
                with open(path, "w", encoding="utf-8") as target:
                    json.dump(value, target)
            before = {path: open_bytes(path) for path in (settings_path, store_path)}
            with patch.object(config, "SETTINGS_FILE", settings_path):
                loaded = config.load_settings()
                self.assertEqual("main", loaded["run_mode"])
            store = InstanceStore(store_path, {"run_mode": "builder"})
            profiles = store.load()
            self.assertEqual(
                "main", profiles["127.0.0.1:16384"]["settings"]["run_mode"]
            )
            self.assertEqual(before, {path: open_bytes(path) for path in before})
            store.save()
            with open(store_path, encoding="utf-8") as source:
                self.assertEqual(1, json.load(source)["version"])
            again = InstanceStore(store_path, {}).load()
            self.assertEqual(profiles, again)

    def test_cli_settings_save_reload_preserves_options(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(
                config, "SETTINGS_FILE", os.path.join(folder, "settings.json")
            ),
        ):
            saved = config.migrate_settings(
                {
                    "run_mode": "builder",
                    "min_gold": 765432,
                    "extension": {"slots": [1]},
                    "builder_deploy_mode": "single_point",
                }
            )
            config.save_settings(saved)
            self.assertEqual(saved, config.load_settings())

    def test_partial_save_keeps_other_tabs_and_instances_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            template = {"min_gold": 500000, "extension": {"slots": [1]}}
            store = InstanceStore(os.path.join(folder, "instances.json"), template)
            first = store.add("16384")
            second = store.add("16416")
            first["settings"]["extension"]["slots"].append(2)
            store.update_settings(
                first["serial"], {"builder_deploy_mode": "single_point"}
            )
            store.update_settings(
                first["serial"], {"min_gold": 900000, "run_mode": "hybrid"}
            )
            self.assertEqual([1], second["settings"]["extension"]["slots"])
            self.assertEqual([1], template["extension"]["slots"])
            loaded = InstanceStore(store.path, {}).load()
            one, two = (
                loaded[key]["settings"] for key in (first["serial"], second["serial"])
            )
            self.assertEqual(
                (900000, "single_point", "hybrid"),
                (one["min_gold"], one["builder_deploy_mode"], one["run_mode"]),
            )
            self.assertEqual(
                (500000, "around", "main"),
                (two["min_gold"], two["builder_deploy_mode"], two["run_mode"]),
            )
            self.assertEqual([1, 2], one["extension"]["slots"])


def open_bytes(path):
    with open(path, "rb") as source:
        return source.read()


class ValidationTests(unittest.TestCase):
    def test_only_active_villages_are_validated(self):
        invalid_main = {
            "run_mode": "builder",
            "min_gold": "draft",
            "star_target": 99,
            "wall_type": "unknown",
        }
        self.assertEqual("builder", config.validate_settings(invalid_main)["run_mode"])
        with self.assertRaises(ValueError):
            config.validate_settings({**invalid_main, "run_mode": "hybrid"})
        invalid_builder = {"builder_deploy_mode": "unknown"}
        config.validate_settings(invalid_builder)
        with self.assertRaises(ValueError):
            config.validate_settings({**invalid_builder, "run_mode": "hybrid"})

    def test_enums_boolean_types_and_hybrid_schedule_are_checked(self):
        for changes in (
            {"run_mode": "night"},
            {"run_mode": []},
            {"run_mode": "builder", "builder_deploy_mode": "random"},
            {"run_mode": "builder", "builder_collect_cart": "false"},
            {"run_mode": "hybrid", "builder_use_available_hero": 1},
            {"run_mode": "hybrid", "builder_auto_setup_baby_dragons": None},
            {"run_mode": "hybrid", "hybrid_check_time": "24:00"},
            {"run_mode": "hybrid", "hybrid_check_time": "15:60"},
            {"run_mode": "hybrid", "hybrid_timezone": "UTC"},
            {"camera_auto_adjust": "true"},
            {"settings_schema_version": "2"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                config.validate_settings(changes)
        for time in ("00:00", "15:30", "23:59"):
            config.validate_settings({"run_mode": "hybrid", "hybrid_check_time": time})

    def test_builder_save_retains_main_draft_without_enabling_event_rewards(self):
        updated = config.build_settings(
            {"event_mode": False},
            {
                "run_mode": "builder",
                "min_gold": "unfinished",
                "min_farm": "90",
                "farm_battle_timeout": "10",
                "builder_deploy_mode": "single_point",
            },
            False,
        )
        self.assertEqual("unfinished", updated["min_gold"])
        self.assertFalse(updated["event_mode"])
        self.assertFalse(updated["upgrade_walls"])
        self.assertEqual("single_point", updated["builder_deploy_mode"])
        with self.assertRaises(ValueError):
            config.build_settings(updated, {"run_mode": "hybrid"}, False)

    def test_explicit_main_toggles_survive_save(self):
        updated = config.build_settings({}, {"event_mode": False}, False)
        self.assertFalse(updated["event_mode"])
        self.assertFalse(updated["upgrade_walls"])

    def test_engine_refuses_invalid_modes_before_adb(self):
        for mode in ("invalid", "night"):
            engine = BotEngine({"run_mode": mode})
            engine._connect_adb = Mock()
            output = io.StringIO()
            with self.subTest(mode=mode), redirect_stdout(output):
                self.assertFalse(engine.start())
            engine._connect_adb.assert_not_called()
            self.assertIn(mode, output.getvalue())
            self.assertFalse(engine.running)

    def test_cli_accepts_saved_and_override_hybrid_without_writing_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "settings.json")
            for saved_mode, arguments in (
                ("hybrid", []),
                ("main", ["--run-mode", "hybrid"]),
            ):
                with open(path, "w", encoding="utf-8") as target:
                    json.dump({"run_mode": saved_mode}, target)
                before = open_bytes(path)
                client = Mock()
                client.policy.enabled = False
                output = io.StringIO()
                with (
                    self.subTest(saved_mode=saved_mode),
                    patch("sys.argv", ["main.py", "--settings", path, *arguments]),
                    patch(
                        "cocmagic.main.LicenseClient.from_config", return_value=client
                    ),
                    patch("cocmagic.main.BotEngine") as engine,
                    patch.object(config, "SETTINGS_FILE", path),
                    redirect_stdout(output),
                ):
                    main()
                    engine.return_value.start.assert_called_once()
                    self.assertEqual("hybrid", engine.call_args.args[0]["run_mode"])
                self.assertEqual(before, open_bytes(path))

    def test_cli_accepts_saved_and_override_builder_without_rewriting_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "settings.json")
            for saved_mode, arguments in (
                ("builder", []),
                ("main", ["--run-mode", "builder"]),
            ):
                with open(path, "w", encoding="utf-8") as target:
                    json.dump({"run_mode": saved_mode}, target)
                before = open_bytes(path)
                client = Mock()
                client.policy.enabled = False
                with (
                    self.subTest(saved_mode=saved_mode),
                    patch("sys.argv", ["main.py", "--settings", path, *arguments]),
                    patch(
                        "cocmagic.main.LicenseClient.from_config", return_value=client
                    ),
                    patch("cocmagic.main.BotEngine") as engine,
                    patch.object(config, "SETTINGS_FILE", path),
                ):
                    main()
                    engine.return_value.start.assert_called_once()
                    self.assertEqual("builder", engine.call_args.args[0]["run_mode"])
                self.assertEqual(before, open_bytes(path))


class VillageGuiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk unavailable: {error}")
        self.root.withdraw()
        self.folder = tempfile.TemporaryDirectory()
        self.settings_patch = patch.object(
            config, "SETTINGS_FILE", os.path.join(self.folder.name, "settings.json")
        )
        self.settings_patch.start()
        client = Mock()
        client.policy.enabled = False
        client.policy.check_interval_seconds = 600
        with (
            patch.object(BotPanel, "_refresh"),
            patch("cocmagic.gui.LicenseClient.from_config", return_value=client),
        ):
            self.panel = BotPanel(self.root, initial_port=16384)
        self.first = self.panel.tabs["127.0.0.1:16384"]
        self.second = self.panel._add_tab(self.panel.store.add("16416"))

    def tearDown(self):
        for job in self.root.tk.call("after", "info"):
            self.root.after_cancel(job)
        self.root.destroy()
        self.settings_patch.stop()
        self.folder.cleanup()

    def test_cross_tab_save_reload_and_two_profiles(self):
        one, two = self.first, self.second
        one.vars["min_gold"].set("950k")
        one.vars["builder_deploy_mode"].set("single_point")
        one.vars["builder_collect_cart"].set(False)
        one.run_mode.set("hybrid")
        one.notebook.select(1)
        one.save_button.invoke()
        loaded = InstanceStore(self.panel.store.path, {}).load()
        saved = loaded[one.serial]["settings"]
        self.assertEqual(
            (950000, "single_point", False, "hybrid"),
            (
                saved["min_gold"],
                saved["builder_deploy_mode"],
                saved["builder_collect_cart"],
                saved["run_mode"],
            ),
        )
        self.assertEqual("500,000", two.vars["min_gold"].get())
        self.assertEqual("around", two.vars["builder_deploy_mode"].get())
        self.assertEqual("main", loaded[two.serial]["settings"]["run_mode"])
        self.assertEqual("hybrid", one.run_mode.get())

    def test_builder_can_save_with_unfinished_main_and_start_its_own_module(self):
        tab = self.first
        tab.set_online(True)
        tab.mode_buttons["builder"].invoke()
        tab.vars["min_gold"].set("unfinished")
        self.assertTrue(tab._save())
        self.assertEqual("normal", str(tab.start_button.cget("state")))
        with patch.object(tab.session, "start") as start:
            tab._start()
            start.assert_called_once()
            self.assertEqual("builder", start.call_args.args[0]["run_mode"])
        self.assertFalse(tab.settings["event_mode"])

    def test_main_run_locks_configuration_but_keeps_tabs_viewable(self):
        tab = self.first
        tab.set_online(True)
        with (
            patch.object(tab.session, "start") as start,
            patch.object(tab.session, "is_alive", return_value=False),
        ):
            tab.notebook.select(2)
            tab.start_button.invoke()
            start.assert_called_once()
            self.assertEqual("main", start.call_args.args[0]["run_mode"])
            self.assertTrue(
                all(str(widget.cget("state")) == "disabled" for widget in tab.inputs)
            )
            self.assertEqual("normal", str(tab.stop_button.cget("state")))
            for index in range(3):
                tab.notebook.select(index)
                self.assertEqual(index, tab.notebook.index("current"))
            with patch.object(tab.session, "stop") as stop:
                tab.stop_button.invoke()
                stop.assert_called_once()
            tab.last_result = None
            with patch.object(
                tab.session,
                "poll",
                return_value=[
                    {"kind": "done", "stopped": True, "ok": True},
                    {"kind": "exited", "code": 0},
                ],
            ):
                tab.poll()
            self.assertEqual("Đã dừng", tab.status.get())
            self.assertEqual("normal", str(tab.start_button.cget("state")))
            self.assertEqual("readonly", str(tab.wall_type.cget("state")))

    def test_license_refresh_enables_available_hybrid_mode(self):
        tab = self.first
        tab.set_online(True)
        tab.run_mode.set("hybrid")
        result = Mock(expires_at=None)
        result.label.return_value = "License OK"
        self.panel.license_status = tk.StringVar(master=self.root)
        self.panel._license_result(result, None, False)
        self.assertEqual("normal", str(tab.start_button.cget("state")))
        tab.run_mode.set("main")
        self.assertEqual("normal", str(tab.start_button.cget("state")))

    def test_main_off_toggles_and_unknown_keys_survive_gui_save(self):
        tab = self.first
        tab.settings["opaque_extension"] = {"a": [1, 2]}
        tab.wall_mode.set(False)
        tab.event_mode.set(False)
        tab._sync_main_inputs()
        self.assertTrue(tab._save())
        self.assertFalse(tab.settings["upgrade_walls"])
        self.assertFalse(tab.settings["event_mode"])
        loaded = InstanceStore(self.panel.store.path, {}).load()
        self.assertEqual(
            {"a": [1, 2]}, loaded[tab.serial]["settings"]["opaque_extension"]
        )

    def test_notebook_focus_does_not_scroll_page_but_input_focus_is_visible(self):
        tab = self.first
        self.root.geometry("880x680")
        self.root.deiconify()
        self.root.update()
        tab.notebook.select(2)
        tab.notebook.focus_force()
        self.root.update()
        self.assertEqual(0.0, tab.canvases["run"].yview()[0])
        tab.notebook.select(0)
        self.root.update()
        target = next(
            widget
            for widget in tab.inputs
            if widget.winfo_class() == "TEntry"
            and str(widget.cget("textvariable"))
            == str(tab.vars["warden_ability_delay"])
        )
        target.focus_force()
        self.root.update()
        canvas = tab.canvases["main"]
        top = target.winfo_rooty() - canvas.winfo_rooty()
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(top + target.winfo_height(), canvas.winfo_height())

    def test_running_profile_cannot_be_saved_and_other_profile_remains_editable(self):
        with patch.object(self.first.session, "is_alive", return_value=True):
            self.first._set_running(True)
            with patch.object(self.panel.store, "update_settings") as save:
                self.assertFalse(self.first._save())
                save.assert_not_called()
            self.second.vars["min_gold"].set("600k")
            self.assertTrue(self.second._save())
            self.assertEqual(600000, self.second.settings["min_gold"])

    def test_save_reports_dirty_success_and_specific_disk_failure(self):
        tab = self.first
        tab.vars["min_gold"].set("600k")
        self.assertIn("chưa lưu", tab.save_state.get())
        self.assertTrue(tab._save())
        self.assertIn("Đã lưu", tab.save_state.get())
        before = tab.settings.copy()
        tab.vars["min_gold"].set("700k")
        with (
            patch.object(self.panel.store, "save", side_effect=OSError("disk full")),
            patch("cocmagic.gui.messagebox.showerror") as error,
        ):
            self.assertFalse(tab._save())
            self.assertIn("disk full", tab.save_state.get())
            error.assert_called_once()
        self.assertEqual(before, tab.settings)
        self.assertEqual(before, self.panel.store.instances[tab.serial]["settings"])

    def test_foreign_status_is_ignored_and_duplicate_log_fragments_are_coalesced(self):
        tab = self.first
        previous = tab.status.get()
        with (
            patch.object(
                tab.session,
                "poll",
                return_value=[
                    {
                        "kind": "status",
                        "serial": self.second.serial,
                        "status": "wrong",
                        "wall_count": 999,
                    }
                ],
            ),
            patch.object(tab.session, "is_alive", return_value=True),
        ):
            tab.poll()
        self.assertEqual(previous, tab.status.get())
        self.assertEqual("0 viên", tab.wall_count.get())
        tab._clear_log()
        for value in ("same", " message\n", "same message", "\n", "new\n"):
            tab._append_log(value)
        self.assertEqual("same message\nnew\n", tab.log.get("1.0", "end-1c"))

    def test_host_scan_failure_keeps_running_sessions_and_new_scan_adds_instance(self):
        self.first.online = self.second.online = True
        with (
            patch.object(self.first.session, "is_alive", return_value=True),
            patch.object(self.second.session, "is_alive", return_value=True),
            patch.object(self.first.session, "stop") as a,
            patch.object(self.second.session, "stop") as b,
        ):
            self.panel.discovery_events.put(("error", "host scan failed"))
            self.panel._poll()
            a.assert_not_called()
            b.assert_not_called()
            self.assertTrue(self.first.online and self.second.online)
        from cocmagic.device_manager import DeviceInfo

        self.panel.discovery_events.put(
            (
                "devices",
                [
                    DeviceInfo(s, "device")
                    for s in (self.first.serial, self.second.serial, "127.0.0.1:16448")
                ],
            )
        )
        self.panel._poll()
        self.assertEqual(3, len(self.panel.tabs))
        self.assertIs(self.first, self.panel.tabs[self.first.serial])

    def test_start_all_respects_each_mode_and_stop_all_reaches_running_session(self):
        self.first.set_online(True)
        self.second.set_online(True)
        self.second.run_mode.set("builder")
        with (
            patch.object(self.first.session, "start") as first_start,
            patch.object(self.second.session, "start") as second_start,
        ):
            self.panel._start_all()
            first_start.assert_called_once()
            second_start.assert_called_once()
            self.assertEqual("builder", second_start.call_args.args[0]["run_mode"])
            self.assertEqual("builder", self.second.run_mode.get())
        self.second.run_mode.set("hybrid")
        with (
            patch.object(self.first.session, "start") as first_start,
            patch.object(self.second.session, "start") as second_start,
        ):
            self.panel._start_all()
            first_start.assert_called_once()
            second_start.assert_called_once()
            self.assertEqual("hybrid", second_start.call_args.args[0]["run_mode"])
        with (
            patch.object(self.first.session, "is_alive", return_value=True),
            patch.object(self.first.session, "stop") as stop,
        ):
            self.panel._stop_all()
            stop.assert_called_once()

    def test_license_watchdog_keeps_grace_then_stops_both_modes_on_expiry(self):
        self.first.run_mode.set("main")
        self.second.run_mode.set("hybrid")
        # This fixture disables the license card; supply its status observer.
        self.panel.license_status = tk.StringVar(master=self.root)
        self.panel.license_valid = True
        self.panel.license_last_ok = 90
        self.panel.license_expiry_deadline = 200
        self.panel.license_client.policy.offline_grace_seconds = 60
        with (
            patch("cocmagic.gui.time.monotonic", return_value=100),
            patch.object(self.first.session, "is_alive", return_value=True),
            patch.object(self.second.session, "is_alive", return_value=True),
            patch.object(self.first.session, "stop") as first_stop,
            patch.object(self.second.session, "stop") as second_stop,
        ):
            self.panel._license_result(
                None, LicenseError("network", temporary=True), False
            )
            first_stop.assert_not_called()
            second_stop.assert_not_called()
            self.assertTrue(self.panel.license_valid)
            self.panel._license_result(None, LicenseError("expired"), False)
            first_stop.assert_called_once()
            second_stop.assert_called_once()
        self.assertFalse(self.panel.license_valid)
        self.assertEqual(
            ("main", "hybrid"), (self.first.run_mode.get(), self.second.run_mode.get())
        )

    def test_close_waits_for_cooperative_stop_of_both_workers(self):
        with (
            patch.object(
                self.first.session, "is_alive", return_value=True
            ) as first_alive,
            patch.object(
                self.second.session, "is_alive", return_value=True
            ) as second_alive,
            patch.object(self.first.session, "stop") as first_stop,
            patch.object(self.second.session, "stop") as second_stop,
            patch.object(self.first.session, "poll", return_value=[]),
            patch.object(self.second.session, "poll", return_value=[]),
            patch.object(self.first.session, "terminate") as terminate,
            patch.object(self.root, "destroy") as destroy,
        ):
            self.panel._on_close()
            first_stop.assert_called_once()
            second_stop.assert_called_once()
            self.panel._poll()
            destroy.assert_not_called()
            terminate.assert_not_called()
            first_alive.return_value = second_alive.return_value = False
            self.panel._poll()
            destroy.assert_called_once()

    def test_valid_scan_stops_only_missing_serial(self):
        self.first.set_online(True)
        self.second.set_online(True)
        self.panel.discovery_events.put(("devices", [Mock(serial=self.second.serial)]))
        with (
            patch.object(self.first.session, "is_alive", return_value=True),
            patch.object(self.second.session, "is_alive", return_value=True),
            patch.object(self.first.session, "stop") as first_stop,
            patch.object(self.second.session, "stop") as second_stop,
            patch.object(self.first.session, "poll", return_value=[]),
            patch.object(self.second.session, "poll", return_value=[]),
        ):
            self.panel._poll()
            first_stop.assert_called_once()
            second_stop.assert_not_called()
        self.assertFalse(self.first.online)
        self.assertTrue(self.second.online)


if __name__ == "__main__":
    unittest.main()
