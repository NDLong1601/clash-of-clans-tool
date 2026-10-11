"""CLI must expose engine failures in every available mode/license path."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from cocmagic import config
from cocmagic.main import main, parse_args


class AcceptanceCliTests(unittest.TestCase):
    def test_engine_failure_exits_nonzero_with_and_without_license_watchdog(self):
        for mode in ("main", "builder", "hybrid"):
            for enabled in (False, True):
                with self.subTest(mode=mode, license=enabled):
                    client = Mock()
                    client.policy.enabled = enabled
                    client.policy.check_interval_seconds = 600
                    client.check.return_value.expires_at = None
                    engine = Mock()
                    engine.start.return_value = False
                    with (
                        patch.object(sys, "argv", ["main.py", "--run-mode", mode]),
                        patch(
                            "cocmagic.main.LicenseClient.from_config",
                            return_value=client,
                        ),
                        patch("cocmagic.main.BotEngine", return_value=engine),
                        patch(
                            "cocmagic.main.config.load_settings",
                            return_value=config.migrate_settings({}),
                        ),
                        patch("cocmagic.main.os.path.exists", return_value=True),
                        redirect_stdout(io.StringIO()),
                    ):
                        with self.assertRaises(SystemExit) as error:
                            main()
                    self.assertEqual(1, error.exception.code)
                    engine.start.assert_called_once()
                    self.assertEqual(enabled, client.check.called)

    def test_successful_engine_keeps_cli_success(self):
        client = Mock()
        client.policy.enabled = False
        with (
            patch.object(sys, "argv", ["main.py"]),
            patch("cocmagic.main.LicenseClient.from_config", return_value=client),
            patch("cocmagic.main.BotEngine") as engine,
            patch(
                "cocmagic.main.config.load_settings",
                return_value=config.migrate_settings({}),
            ),
            patch("cocmagic.main.os.path.exists", return_value=True),
        ):
            engine.return_value.start.return_value = True
            self.assertIsNone(main())

    def test_help_lists_current_modes_without_obsolete_availability_message(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["main.py", "--help"]), redirect_stdout(output):
            with self.assertRaises(SystemExit) as error:
                parse_args()
        self.assertEqual(0, error.exception.code)
        for mode in config.AVAILABLE_RUN_MODES:
            self.assertIn(mode, output.getvalue())
        self.assertNotIn("chờ GĐ6", output.getvalue())
