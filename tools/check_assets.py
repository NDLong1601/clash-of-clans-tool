import sys
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

print("=== CocMagic Core -- Full Test ===")

from cocmagic import config
print("[OK] config")

for module_name in (
    "adb_controller", "screen_reader", "modules.farm_module", "battle_planner",
    "modules.hero_module", "modules.wall_module", "bot_engine", "main",
    "builder_screen_reader", "builder_vision", "modules.builder_farm_module",
    "camera_controller", "hybrid_coordinator", "hybrid_runtime", "village_navigator",
    "event_chests",
):
    import_module(f"cocmagic.{module_name}")
    print(f"[OK] {module_name}")

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
    "event_chest/claim_button.png", "event_chest/result_troops.png",
    "event_chest/result_troops_native.png",
    "event_chest/room_torch.png", "event_chest/room_door.png",
    "event_chest/chest_lock.png", "event_chest/chest_lock_glow.png",
    "event_chest/continue_button.png", "event_chest/reward_torch.png",
    "event_chest/reward_column.png",
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
    sys.exit(1)
