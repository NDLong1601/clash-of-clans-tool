"""Checks for license parsing, local secret storage and worker gating."""

import io
import json
import os
from pathlib import Path
import queue
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from cocmagic.bot_worker import run_instance
from cocmagic.license_client import (
    LicenseClient, LicenseError, LicensePolicy, load_policy, normalize_key,
)


TEST_KEY = "CM-" + "A" * 48


class LicenseClientTests(unittest.TestCase):
    def test_policy_is_disabled_without_config(self):
        missing = Path(tempfile.gettempdir()) / f"cocmagic-missing-{uuid.uuid4().hex}.json"
        self.assertFalse(missing.exists())
        self.assertFalse(load_policy(missing).enabled)

    def test_key_normalization_rejects_short_keys(self):
        self.assertEqual("CM" + "A" * 48, normalize_key(TEST_KEY.lower()))
        with self.assertRaises(LicenseError):
            normalize_key("CM-1234")

    @unittest.skipUnless(os.name == "nt", "DPAPI requires Windows")
    def test_saved_key_round_trips_through_windows_dpapi(self):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as temporary:
            path = Path(temporary.name)
        try:
            client = LicenseClient(LicensePolicy(True, "http://127.0.0.1:8787"),
                                   key_file=path, device_id="a" * 64)
            client.save_key(TEST_KEY)
            self.assertNotEqual(normalize_key(TEST_KEY).encode("ascii"), path.read_bytes())
            self.assertEqual(normalize_key(TEST_KEY), client.read_key())
        finally:
            path.unlink(missing_ok=True)

    def test_http_rejection_preserves_server_reason(self):
        client = LicenseClient(LicensePolicy(True, "http://127.0.0.1:8787"),
                               device_id="a" * 64)
        error_body = io.BytesIO(json.dumps({"ok": False, "code": "another_machine"}).encode())
        error = HTTPError("http://127.0.0.1:8787", 403, "Forbidden", {}, error_body)
        with patch("cocmagic.license_client.urlopen", side_effect=error):
            with self.assertRaises(LicenseError) as raised:
                client.check(TEST_KEY)
        self.assertEqual("another_machine", raised.exception.code)
        self.assertFalse(raised.exception.temporary)

    def test_worker_does_not_start_engine_when_license_is_rejected(self):
        client = Mock()
        client.policy.enabled = True
        client.check.side_effect = LicenseError("revoked")
        events = queue.SimpleQueue()
        stop = Mock()
        stop.is_set.return_value = False
        with patch("cocmagic.license_client.LicenseClient.from_config", return_value=client), \
             patch("cocmagic.bot_engine.BotEngine") as engine:
            run_instance("127.0.0.1:16416", {}, events, stop)
        engine.assert_not_called()
        output = []
        while not events.empty():
            output.append(events.get_nowait())
        self.assertEqual("done", output[-1]["kind"])
        self.assertFalse(output[-1]["ok"])


if __name__ == "__main__":
    unittest.main()
