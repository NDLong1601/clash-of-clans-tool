"""Offline probe control tests; these are not live battle evidence."""

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import numpy as np

from cocmagic import config
from cocmagic.village_module import ModuleScreen
from tools.hybrid_probe import run_probe


class HybridProbeTests(unittest.TestCase):
    def run_steps(self, steps):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            stop = threading.Event()
            stop.wait = Mock(return_value=False)
            farm = SimpleNamespace(tick=Mock(), attack_count=0,
                                   state=SimpleNamespace(name="RECOVERING"),
                                   confirmed_screen=ModuleScreen.UNKNOWN, metrics={})
            coordinator = SimpleNamespace(
                active_id="builder", halt_reason=None, pending=None,
                runtime=SimpleNamespace(builder_incomplete=False, pending_builder_check=False),
            )
            engine = SimpleNamespace(
                adb=SimpleNamespace(tap=Mock(return_value=True), input_lock=threading.RLock(),
                                    screenshot=Mock(return_value=np.zeros((900, 1600, 3), np.uint8))),
                coordinator=coordinator, farm_mod=farm, runtime_store=None,
                builder_mod=SimpleNamespace(metrics={}, last_bonus=None, last_cart=None),
                settings={"auto_train": True, "camera_auto_adjust": True},
                _init_modules=Mock(), _input_failed=Mock(), _guard_frame=Mock(),
                _handle_popups=Mock(return_value=False),
            )
            remaining = iter(steps)

            def tick():
                self.assertIs(engine.adb.frame_guard, engine._guard_frame)
                self.assertIs(engine.adb.input_failure_handler, engine._input_failed)
                if coordinator.active_id == "main":
                    farm.tick()
                active, attacks, phase = next(remaining)
                coordinator.active_id = active
                farm.attack_count = attacks
                farm.state.name = phase
                farm.confirmed_screen = ModuleScreen.HOME if phase == "HOME" else ModuleScreen.UNKNOWN
                farm.metrics = {"attack_count": attacks}
                return True

            coordinator.tick = tick
            coordinator.exclusive = lambda action: action()
            coordinator.status = lambda: {
                "status": farm.state.name, "active_module": coordinator.active_id,
                "last_bonus_state": "complete", "last_error": None,
            }
            args = SimpleNamespace(serial="offline", stop_file=None, seconds=30,
                                   main_cycles=2, daily_pass=False)
            with patch.object(config, "DATA_DIR", folder), patch(
                "tools.hybrid_probe.source_hashes", return_value={"probe": "unchanged"}
            ):
                code = run_probe(args, output, stop, engine)
            return code, json.loads((output / "receipt.json").read_text(encoding="utf-8"))

    def test_soak_keeps_running_after_handoff_and_first_home(self):
        code, receipt = self.run_steps([
            ("main", 0, "RECOVERING"), ("main", 1, "RESULT"),
            ("main", 1, "HOME"), ("main", 2, "RESULT"), ("main", 2, "HOME"),
        ])
        self.assertEqual(0, code)
        self.assertTrue(receipt["completed"])
        self.assertEqual(4, receipt["main_ticks"])
        self.assertEqual(2, receipt["main_metrics"]["attack_count"])
        self.assertEqual(1, receipt["passes"])
        self.assertTrue(receipt["production_guards"])
        self.assertFalse(receipt["budget_exhausted"])

    def test_repeated_builder_visit_cannot_be_reported_as_success(self):
        code, receipt = self.run_steps([
            ("main", 0, "RECOVERING"), ("main", 1, "RESULT"),
            ("builder", 1, "HOME"), ("main", 1, "RECOVERING"),
            ("main", 2, "RESULT"), ("main", 2, "HOME"),
        ])
        self.assertEqual(1, code)
        self.assertFalse(receipt["completed"])
        self.assertEqual(2, receipt["passes"])
        self.assertIn("Lặp", receipt["failure_reason"])
        self.assertFalse(receipt["budget_exhausted"])


if __name__ == "__main__":
    unittest.main()
