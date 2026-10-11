"""Live probes must share the GUI/CLI VM lease, including ADB aliases."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from cocmagic import config
from cocmagic.device_manager import DeviceOwnership
from tools.live_probe_support import owned_input


class LiveProbeSafetyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.config_patch = patch.object(config, "DATA_DIR", self.folder.name)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.ownership = DeviceOwnership(
            "boot:probe-vm", "127.0.0.1:16416", ("127.0.0.1:16416", "emulator-5556")
        )
        self.resolver = patch(
            "tools.live_probe_support.resolve_device_ownership",
            return_value=self.ownership,
        )
        self.resolver.start()
        self.addCleanup(self.resolver.stop)

    @staticmethod
    def adb(serial="127.0.0.1:16416"):
        return Mock(adb="adb.exe", device=serial)

    def test_alias_probe_is_rejected_without_releasing_the_owner(self):
        first, second = self.adb(), self.adb("emulator-5556")
        with owned_input(first):
            with self.assertRaises(RuntimeError):
                with owned_input(second):
                    self.fail("Alias acquired input already owned by another probe")
            second.release_touch.assert_not_called()
            first.release_touch.assert_not_called()
        first.release_touch.assert_called_once_with()
        # A probe lease alone never writes the user's scheduler runtime.
        self.assertFalse(list(Path(self.folder.name).rglob("*.json")))
        with owned_input(second):
            pass
        second.release_touch.assert_called_once_with()

    def test_exception_releases_gestures_and_vm_lock_for_the_next_probe(self):
        first, second = self.adb(), self.adb()
        with self.assertRaisesRegex(ValueError, "probe interrupted"):
            with owned_input(first):
                raise ValueError("probe interrupted")
        first.release_touch.assert_called_once_with()
        with owned_input(second):
            pass
        second.release_touch.assert_called_once_with()

    def test_release_failure_still_closes_vm_lock(self):
        first, second = self.adb(), self.adb()
        first.release_touch.side_effect = OSError("transport disconnected")
        with self.assertRaises(OSError):
            with owned_input(first):
                pass
        with owned_input(second):
            pass
        second.release_touch.assert_called_once_with()
