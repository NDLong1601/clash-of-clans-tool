"""Bounded live hybrid startup/daily cycle using the production engine/modules.

By default stops at main handoff. --main-cycles continues through real farming
results and stops at confirmed Home, using production frame/input guards.
The optional daily pass advances only the probe's wall clock, never Windows.
"""

import argparse
from dataclasses import asdict
from datetime import timedelta
import hashlib
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
from cocmagic.recovery import RecoveryInterrupted
from cocmagic.village_module import ModuleScreen
from tools.live_probe_support import owned_input


class ProbeClock(HybridClock):
    def __init__(self):
        super().__init__()
        self.offset = timedelta()

    def now(self):
        return super().now() + self.offset


def source_hashes():
    root = Path(__file__).resolve().parents[1]
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for directory in ("cocmagic", "tools", "tests", "assets")
            for path in sorted((root / directory).rglob("*"))
            if path.is_file() and path.suffix in (".py", ".png", ".json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--daily-pass", action="store_true")
    parser.add_argument("--main-cycles", type=int, default=0)
    parser.add_argument("--instance-settings", action="store_true")
    parser.add_argument("--stop-file")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.main_cycles < 0 or args.seconds <= 0:
        parser.error("--main-cycles >= 0 và --seconds > 0")
    if args.main_cycles and args.daily_pass:
        parser.error("Không ghép soak main với giờ daily giả lập")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    settings = {}
    if args.instance_settings:
        data = json.loads((Path(config.DATA_DIR) / "instances.json").read_text(encoding="utf-8"))
        instance = next((item for item in data["instances"] if item["serial"] == args.serial), None)
        if instance is None:
            parser.error("Không tìm được cấu hình serial trong instances.json")
        settings.update(instance["settings"])
    settings.update(run_mode="hybrid", upgrade_walls=False, event_mode=False)
    if not args.main_cycles:
        settings["auto_train"] = False
    settings = config.validate_settings(settings)
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
    before_hashes = source_hashes()
    inputs, events, timings = [], [], []
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
    recoveries = []
    try:
        engine._init_modules()
        coordinator = engine.coordinator
        coordinator.clock = clock
        # Match BotEngine.start(), including the guard that can invalidate a
        # main battle frame. A handoff-only probe previously missed this path.
        engine.adb.frame_guard = engine._guard_frame
        real_input_failed = engine._input_failed

        def input_failed(*values, **kwargs):
            recoveries.append({"at": time.monotonic(), "active": coordinator.active_id,
                               "reason": values[0] if values else "Input ADB thất bại"})
            return real_input_failed(*values, **kwargs)

        engine._input_failed = input_failed
        engine.adb.input_failure_handler = input_failed
        real_main_tick = engine.farm_mod.tick

        def main_tick(**kwargs):
            main_ticks[0] += 1
            return real_main_tick(**kwargs)

        engine.farm_mod.tick = main_tick
        last_popup_check = started - 5
        while not stop.is_set() and time.monotonic() - started < args.seconds:
            if args.stop_file and Path(args.stop_file).exists():
                stop.set()
                break
            before = coordinator.active_id
            tick_started = time.monotonic()
            try:
                with engine.adb.input_lock:
                    if tick_started - last_popup_check >= 5:
                        handled = coordinator.exclusive(engine._handle_popups)
                        last_popup_check = tick_started
                        if handled:
                            continue
                    okay = coordinator.tick()
            except RecoveryInterrupted:
                if coordinator.halt_reason:
                    break
                stop.wait(0.5)
                continue
            status = coordinator.status()
            timings.append({"at": tick_started, "seconds": time.monotonic() - tick_started,
                            "active": before, "status": status["status"]})
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
                if not args.main_cycles and (not args.daily_pass or passes == 2):
                    completed = not coordinator.runtime.builder_incomplete
                    break
                # Mark the next current day's scheduled check due, no replay.
                if args.daily_pass:
                    current = clock.now()
                    next_due = (current + timedelta(days=1)).replace(
                        hour=15, minute=31, second=0, microsecond=0
                    )
                    clock.offset += next_due - current
                    print(
                        "[Probe] Advancing probe wall clock to next day 15:31; production schedule unchanged.",
                        flush=True,
                    )
            if (args.main_cycles and passes and coordinator.active_id == "main"
                    and engine.farm_mod.attack_count >= args.main_cycles
                    and engine.farm_mod.state.name == "HOME"
                    and engine.farm_mod.confirmed_screen == ModuleScreen.HOME):
                completed = (passes == 1 and not coordinator.runtime.builder_incomplete
                             and not coordinator.runtime.pending_builder_check
                             and coordinator.pending is None)
                break
            stop.wait(0.25)
    finally:
        stopped_by_user = stop.is_set()
        stop.set()
        engine.adb.frame_guard = None
        engine.adb.input_failure_handler = None
        image = engine.adb.screenshot(use_cache=False)
        if image is not None:
            cv2.imwrite(str(output / "final.png"), image)
        coordinator = engine.coordinator
        after_hashes = source_hashes()
        changed_source = sorted(name for name in before_hashes.keys() | after_hashes.keys()
                                if before_hashes.get(name) != after_hashes.get(name))
        elapsed = time.monotonic() - started
        budget_exhausted = not completed and not stopped_by_user and elapsed >= args.seconds
        failure_reason = None if completed else (
            coordinator.halt_reason or
            ("Lặp kiểm tra làng đêm trong soak main" if args.main_cycles and passes > 1 else
             "Hết ngân sách probe" if budget_exhausted else
             "Đã dừng probe" if stopped_by_user else "Chưa đạt điều kiện hoàn thành")
        )
        receipt = {
            "serial": args.serial,
            "elapsed": elapsed,
            "completed": completed,
            "cancelled": stopped_by_user,
            "passes": passes,
            "budget_exhausted": budget_exhausted,
            "failure_reason": failure_reason,
            "source_hashes": before_hashes,
            "source_changed_during_probe": changed_source,
            "status": coordinator.status(),
            "builder_metrics": engine.builder_mod.metrics,
            "bonus": asdict(engine.builder_mod.last_bonus)
            if engine.builder_mod.last_bonus
            else None,
            "cart": asdict(engine.builder_mod.last_cart)
            if engine.builder_mod.last_cart
            else None,
            "events": events,
            "timings": timings,
            "recoveries": recoveries,
            "inputs": inputs,
            "main_ticks": main_ticks[0],
            "main_metrics": engine.farm_mod.metrics,
            "requested_main_cycles": args.main_cycles,
            "production_guards": True,
            "probe_settings": {
                "auto_train": engine.settings["auto_train"],
                "camera_auto_adjust": engine.settings["camera_auto_adjust"],
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
