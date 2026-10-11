"""Standalone GĐ4 probe; explicit serial, no builder farming or mode changes."""

import argparse
from contextlib import nullcontext
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cocmagic.adb_controller import ADBController
from cocmagic.builder_screen_reader import BuilderScreenReader
from cocmagic.builder_rewards import BuilderRewards
from cocmagic.village_navigator import VillageNavigator
from tools.live_probe_support import owned_input


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument(
        "--action",
        choices=("inspect", "navigate", "bonus", "claim", "cart"),
        default="inspect",
    )
    parser.add_argument("--target", choices=("main", "builder"))
    parser.add_argument("--output", help="Optional JSON receipt path")
    args = parser.parse_args()
    if args.action == "navigate" and not args.target:
        parser.error("navigate requires --target")
    adb = ADBController(serial=args.serial)
    lease = nullcontext() if args.action in ("inspect", "bonus") else owned_input(adb)
    with lease:
        return run_probe(args, adb)


def run_probe(args, adb):
    reader = BuilderScreenReader(adb)
    navigator = VillageNavigator(adb, reader)
    rewards = BuilderRewards(adb, reader, navigator)
    if args.action == "inspect":
        result = asdict(reader.classify(reader.capture().image))
    elif args.action == "navigate":
        result = asdict(navigator.navigate(args.target))
    elif args.action == "bonus":
        result = asdict(rewards.observe_bonus())
    elif args.action == "claim":
        result = asdict(rewards.claim_star_bonus())
    else:
        result = asdict(rewards.collect_cart())
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text)
    return 1 if result.get("success") is False else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
