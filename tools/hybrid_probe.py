"""Bounded live hybrid startup/daily cycle using the production engine/modules.

Stops after the coordinator has confirmed main, before any main farming tick.
The optional daily pass advances only the probe's wall clock, never Windows.
"""

import argparse
from dataclasses import asdict
from datetime import timedelta
import json
from pathlib import Path
import sys
import threading
import time

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.bot_engine import BotEngine
from cocmagic.hybrid_coordinator import HybridClock
from tools.live_probe_support import owned_input


class ProbeClock(HybridClock):
    def __init__(self):
        super().__init__()
        self.offset = timedelta()

    def now(self):
        return super().now() + self.offset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--daily-pass", action="store_true")
    parser.add_argument("--stop-file")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    settings = config.validate_settings(
        {
            "run_mode": "hybrid",
            "auto_train": False,
            "upgrade_walls": False,
            "event_mode": False,
        }
    )
    engine = BotEngine(settings, device_serial=args.serial, stop_event=stop)
    engine.adb = ADBController(serial=args.serial, settings=settings, stop_event=stop)
    if not engine.adb.connect():
        return 1
    image = engine.adb.screenshot(use_cache=False)
    if image is None or image.shape[:2] != (900, 1600):
        return 1
    cv2.imwrite(str(output / "initial.png"), image)
    # Keep the production lease even though probe runtime is isolated.
    with owned_input(engine.adb):
        return run_probe(args, output, stop, engine)


def run_probe(args, output, stop, engine):
    # Only the probe process sees this path; user settings/runtime are intact.
    config.DATA_DIR = str(output / "runtime-data")
    inputs, events = [], []
    real_tap = engine.adb.tap

    def tap(x, y, **kwargs):
        result = real_tap(x, y, **kwargs)
        inputs.append(
            {
                "at": time.monotonic(),
                "point": [x, y],
                "success": result,
                "active": engine.coordinator.active_id,
            }
        )
        return result

    engine.adb.tap = tap
    started = time.monotonic()
    passes = 0
    completed = False
    clock = ProbeClock()
    last = None
    main_ticks = [0]
    try:
        engine._init_modules()
        coordinator = engine.coordinator
        coordinator.clock = clock
        real_main_tick = engine.farm_mod.tick

        def main_tick(**kwargs):
            main_ticks[0] += 1
            return real_main_tick(**kwargs)

        engine.farm_mod.tick = main_tick
        while not stop.is_set() and time.monotonic() - started < args.seconds:
            if args.stop_file and Path(args.stop_file).exists():
                stop.set()
                break
            before = coordinator.active_id
            with engine.adb.input_lock:
                okay = coordinator.tick()
            status = coordinator.status()
            signature = (
                status["status"],
                status["active_module"],
                status["last_bonus_state"],
                status["last_error"],
            )
            if signature != last:
                events.append({"at": time.monotonic(), **status})
                print(json.dumps(events[-1], ensure_ascii=False), flush=True)
                last = signature
            if not okay:
                break
            if coordinator.active_id == "main" and before == "builder":
                passes += 1
                cv2.imwrite(
                    str(output / f"main-pass-{passes}.png"),
                    engine.adb.screenshot(use_cache=False),
                )
                if not args.daily_pass or passes == 2:
                    completed = not coordinator.runtime.builder_incomplete
                    break
                # Mark the next current day's scheduled check due, no replay.
                current = clock.now()
                next_due = (current + timedelta(days=1)).replace(
                    hour=15, minute=31, second=0, microsecond=0
                )
                clock.offset += next_due - current
                print(
                    "[Probe] Advancing probe wall clock to next day 15:31; production schedule unchanged.",
                    flush=True,
                )
            stop.wait(0.25)
    finally:
        stopped_by_user = stop.is_set()
        stop.set()
        image = engine.adb.screenshot(use_cache=False)
        if image is not None:
            cv2.imwrite(str(output / "final.png"), image)
        coordinator = engine.coordinator
        receipt = {
            "serial": args.serial,
            "elapsed": time.monotonic() - started,
            "completed": completed,
            "cancelled": stopped_by_user,
            "passes": passes,
            "budget_exhausted": not completed
            and not stopped_by_user
            and not coordinator.halt_reason,
            "status": coordinator.status(),
            "builder_metrics": engine.builder_mod.metrics,
            "bonus": asdict(engine.builder_mod.last_bonus)
            if engine.builder_mod.last_bonus
            else None,
            "cart": asdict(engine.builder_mod.last_cart)
            if engine.builder_mod.last_cart
            else None,
            "events": events,
            "inputs": inputs,
            "main_ticks": main_ticks[0],
            "probe_settings": {
                "auto_train": False,
                "upgrade_walls": False,
                "event_mode": False,
            },
            "probe_wall_clock_advanced": args.daily_pass,
        }
        (output / "receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if engine.runtime_store:
            engine.runtime_store.close()
    return 0 if completed else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
