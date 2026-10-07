import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

print("=== CocMagic Core -- Full Test ===")

from cocmagic import config
print("[OK] config")

from cocmagic import adb_controller
print("[OK] adb_controller")

from cocmagic import screen_reader
print("[OK] screen_reader")

from cocmagic.modules.farm_module import FarmModule, FarmState
print("[OK] farm_module")

from cocmagic.battle_planner import BattlePlanner
print("[OK] battle_planner")

from cocmagic.modules.hero_module import HeroModule
print("[OK] hero_module")

from cocmagic.modules.wall_module import WallModule
print("[OK] wall_module")

from cocmagic.bot_engine import BotEngine
print("[OK] bot_engine")

from cocmagic import main
print("[OK] main")

# The deployment planner now derives points from each opponent's red boundary.

# Test settings
s = config.load_settings()
print("[OK] Settings loaded: min_gold=%d" % s["min_gold"])

# Test asset paths
import os
key_assets = [
    "find.png", "findmatch.png", "okay.png", "base.png",
    "king.png", "queen.png", "wall.png",
    "Connection_lostt.png", "1star.png", "2star.png",
]
all_ok = True
for a in key_assets:
    p = config.asset(a)
    status = "OK" if os.path.exists(p) else "MISSING"
    if status == "MISSING":
        all_ok = False
    print("  [%s] %s" % (status, a))

print()
if all_ok:
    print("=== ALL CHECKS PASSED ===")
else:
    print("=== SOME ASSETS MISSING (check above) ===")
