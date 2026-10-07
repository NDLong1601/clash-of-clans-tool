import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUTPUT_DIR = ROOT / "diagnostics"
OUTPUT_DIR.mkdir(exist_ok=True)

from cocmagic import config
import cv2
from cocmagic.adb_controller import ADBController, find_adb_port

# Ket noi
port = find_adb_port(config.ADB_PATH)
print("Port:", port)
adb = ADBController(config.ADB_HOST, port, config.ADB_PATH)
adb.connect()

# Chup man hinh
img = adb.screenshot()
if img is None:
    print("FAILED: screenshot")
    sys.exit(1)

h, w = img.shape[:2]
print("Screenshot resolution: %dx%d" % (w, h))

# Luu screenshot
cv2.imwrite(str(OUTPUT_DIR / "debug_screen.png"), img)
print(f"Saved: {OUTPUT_DIR / 'debug_screen.png'}")

# Test cac template
print()
print("=== Template matching (threshold=0.70) ===")
templates = [
    "find.png", "findmatch.png", "bang.png",
    "base.png", "base2.png", "okay.png",
    "gold.png", "elixir.png", "king.png", "queen.png",
]
THRESH = 0.70
for tpl_name in templates:
    tpl_path = config.asset(tpl_name)
    if not os.path.exists(tpl_path):
        print("  [MISSING] " + tpl_name)
        continue
    tpl = cv2.imread(tpl_path)
    if tpl is None:
        print("  [LOAD ERR] " + tpl_name)
        continue
    th, tw = tpl.shape[:2]
    if img.shape[0] < th or img.shape[1] < tw:
        print("  [TOO BIG] %s (%dx%d > screen %dx%d)" % (tpl_name, tw, th, w, h))
        continue
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    status = "FOUND" if max_val >= THRESH else "MISS "
    print("  [%s] %-25s score=%.3f at (%d,%d)  tpl=%dx%d" % (
        status, tpl_name, max_val, max_loc[0], max_loc[1], tw, th))

# Check OCR regions
print()
print("=== OCR region check (gold/elixir) ===")
from cocmagic.screen_reader import ScreenReader, HOME_REGIONS
reader = ScreenReader(adb)
home_res = reader.read_home_resources(img)
print("Home resources:", home_res)

# Crop gold region va luu
for key, region in HOME_REGIONS.items():
    rx, ry, rw, rh = region
    crop = img[ry:ry+rh, rx:rx+rw]
    fname = OUTPUT_DIR / f"debug_home_{key}.png"
    cv2.imwrite(str(fname), crop)
    print("  Saved crop: " + str(fname) + " region=%s" % str(region))
