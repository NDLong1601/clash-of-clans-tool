"""
debug_extract_digits.py
Crop va luu cac chu so thuc te tu man hinh CoC de tao digit templates moi.
Chay script nay khi dang o HOME screen CoC.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUTPUT_DIR = ROOT / "diagnostics"
OUTPUT_DIR.mkdir(exist_ok=True)

import cv2
from cocmagic import config
from cocmagic.adb_controller import ADBController, find_adb_port

port = find_adb_port(config.ADB_PATH)
adb = ADBController(config.ADB_HOST, port, config.ADB_PATH)
adb.connect()
img = adb.screenshot()

# Crop Gold region -> chi lay phan so
rx, ry, rw, rh = 1150, 10, 340, 60
crop = img[ry:ry+rh, rx:rx+rw]
gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
_, thresh = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)

# Chi lay phan ben phai (noi co so)
left_cut = int(rw * 0.40)
right_part = thresh[:, left_cut:]

# Luu anh toan phan
cv2.imwrite(str(OUTPUT_DIR / "debug_extract_full.png"), right_part)
print(f"Saved: {OUTPUT_DIR / 'debug_extract_full.png'}")
print("Image shape:", right_part.shape)
print()

# Tim contours de phan tach cac chu so
contours, _ = cv2.findContours(right_part, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
print("Found %d contours" % len(contours))

# Luu tung contour co kich thuoc hop ly
digit_dir = OUTPUT_DIR / "extracted_digits"
digit_dir.mkdir(exist_ok=True)
digit_crops = []
for i, cnt in enumerate(contours):
    x, y, w, h = cv2.boundingRect(cnt)
    # Bo qua contour qua nho hoac qua lon
    if w < 5 or h < 10 or w > 50 or h > 50:
        continue
    digit_crop = right_part[y:y+h, x:x+w]
    digit_crops.append((x, y, w, h, digit_crop))

# Sap xep tu trai sang phai
digit_crops.sort(key=lambda t: t[0])
print("Valid digit crops:", len(digit_crops))

for i, (x, y, w, h, dcrop) in enumerate(digit_crops):
    fname = digit_dir / ("digit_%02d_x%d.png" % (i, x))
    cv2.imwrite(str(fname), dcrop)
    print("  [%d] x=%d y=%d w=%d h=%d -> %s" % (i, x, y, w, h, fname))

# Luu anh debug voi contours danh dau
debug_color = cv2.cvtColor(right_part, cv2.COLOR_GRAY2BGR)
for x, y, w, h, _ in digit_crops:
    cv2.rectangle(debug_color, (x, y), (x+w, y+h), (0, 255, 0), 1)
cv2.imwrite(str(OUTPUT_DIR / "debug_extract_contours.png"), debug_color)
print()
print("Saved: debug_extract_contours.png")
print()
print(f"-> Xem anh trong {OUTPUT_DIR}")
print(f"-> Cac chu so da duoc crop vao thu muc {digit_dir}")
print("-> Doi ten cac file thanh ten chu so tuong ung (0.png, 1.png, ...)")
print("-> Roi copy vao assets/digit_templates/ de thay the")
