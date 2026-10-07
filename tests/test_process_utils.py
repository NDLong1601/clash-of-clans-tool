"""Windows console subprocesses must stay invisible and retain their pipes."""

import os
import sys
import unittest
from pathlib import Path

from cocmagic.process_utils import run_hidden


@unittest.skipUnless(os.name == "nt", "Windows console behavior")
class HiddenProcessTests(unittest.TestCase):
    def test_console_child_has_no_window_and_keeps_standard_streams(self):
        python = str(Path(sys.executable).with_name("python.exe"))
        result = run_hidden(
            [python, "-c", (
                "import ctypes, sys; "
                "print(ctypes.windll.kernel32.GetConsoleWindow()); "
                "print(sys.stdin.read(), end=''); "
                "print('diagnostic', file=sys.stderr)"
            )],
            input="ADB pipe test", capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(0, result.returncode)
        self.assertEqual("0\nADB pipe test", result.stdout)
        self.assertEqual("diagnostic\n", result.stderr)


if __name__ == "__main__":
    unittest.main()
