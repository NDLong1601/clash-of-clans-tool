"""Run the real BuilderFarmModule for a bounded live verification session."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import threading
import time
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cocmagic.adb_controller import ADBController
from cocmagic.modules.builder_farm_module import BuilderFarmModule
from tools.live_probe_support import owned_input


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--serial", required=True)
    p.add_argument("--mode", choices=("around", "single_point"), default="around")
    p.add_argument("--seconds", type=int, default=480)
    p.add_argument("--battles", type=int, default=1)
    p.add_argument(
        "--new-battles",
        type=int,
        help="Require N results after this probe has searched a new battle",
    )
    p.add_argument("--no-hero", action="store_true")
    p.add_argument("--camera", action="store_true")
    p.add_argument("--no-cart", action="store_true")
    p.add_argument("--no-setup", action="store_true")
    p.add_argument(
        "--stop-after-inputs",
        type=int,
        default=0,
        help="Live cancellation check: set Stop immediately after N taps",
    )
    p.add_argument("--stop-file", help="Set Stop when this file appears")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    stop = threading.Event()
    adb = ADBController(serial=args.serial, stop_event=stop)
    with owned_input(adb):
        return run_probe(args, adb, stop)


def run_probe(args, adb, stop):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    module = BuilderFarmModule(
        adb,
        {
            "run_mode": "builder",
            "builder_deploy_mode": args.mode,
            "builder_use_available_hero": not args.no_hero,
            "camera_auto_adjust": args.camera,
            "builder_collect_cart": not args.no_cart,
            "builder_auto_setup_baby_dragons": not args.no_setup,
        },
        stop_event=stop,
    )
    captures = []
    inputs = []
    gestures = []
    for name in ("pan", "zoom"):
        real = getattr(module.camera, name)

        def gesture(*args, _name=name, _real=real, **kwargs):
            result = _real(*args, **kwargs)
            gestures.append(
                {"kind": _name, "status": result.status.value, "reason": result.reason}
            )
            print(gestures[-1], flush=True)
            return result

        setattr(module.camera, name, gesture)
    real_capture = module.reader.capture

    def capture():
        if args.stop_file and Path(args.stop_file).exists():
            stop.set()
        frame = real_capture()
        if frame.image is not None:
            name = f"frame-{frame.sequence:04}.png"
            cv2.imwrite(str(output / name), frame.image)
            captures.append(
                {
                    "sequence": frame.sequence,
                    "monotonic": frame.captured_at,
                    "revision": frame.revision,
                    "path": name,
                    "screen": asdict(module.reader.classify(frame.image)),
                }
            )
        return frame

    module.reader.capture = capture
    real_tap = adb.tap

    def tap(x, y, **kwargs):
        result = real_tap(x, y, **kwargs)
        inputs.append(
            {
                "at": time.monotonic(),
                "point": [x, y],
                "phase": module.phase.value,
                "stage": module.stage,
                "success": result,
            }
        )
        if args.stop_after_inputs > 0 and len(inputs) >= args.stop_after_inputs:
            stop.set()
        return result

    adb.tap = tap
    start = time.monotonic()
    events = []
    last = None
    new_finished = 0
    last_completed = 0

    def goal_met():
        return (
            new_finished >= args.new_battles
            if args.new_battles is not None
            else module.metrics["battle_count"] >= args.battles
        )

    try:
        while time.monotonic() - start < args.seconds and not stop.is_set():
            with adb.input_lock:
                okay = module.tick(yield_requested=goal_met)
            count = module.metrics["battle_count"]
            if module.metrics["attack_count"] > 0:
                new_finished += max(0, count - last_completed)
            last_completed = count
            status = module.status_line
            if status != last:
                print(status, flush=True)
                events.append(
                    {
                        "at": time.monotonic(),
                        "status": status,
                        "metrics": module.metrics,
                    }
                )
                last = status
            if not okay or module.can_yield and goal_met():
                break
            stop.wait(0.25)
    finally:
        completed = module.can_yield and goal_met()
        cancelled = stop.is_set()
        stop.set()
        receipt = {
            "serial": args.serial,
            "mode": args.mode,
            "elapsed": time.monotonic() - start,
            "metrics": module.metrics,
            "halt_reason": module.halt_reason,
            "status": module.status_line,
            "bonus": asdict(module.last_bonus) if module.last_bonus else None,
            "cart": asdict(module.last_cart) if module.last_cart else None,
            "events": events,
            "inputs": inputs,
            "gestures": gestures,
            "captures": captures,
            "safe_home": module._home_proof and module.phase.value == "home",
            "new_battles_finished": new_finished,
            "completed": completed,
            "cancelled": cancelled,
            "budget_exhausted": not completed
            and not cancelled
            and not module.halt_reason,
        }
        (output / "receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 1 if module.halt_reason else 0 if completed or cancelled else 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
