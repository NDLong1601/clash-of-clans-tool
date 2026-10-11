"""Export audited native GĐ5 crops. Offline utility; never sends game input."""

import hashlib
import json
from pathlib import Path
import cv2

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "diagnostics/dual_village_gd5"
DEST = ROOT / "assets/dual_village/builder"


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    # Boxes are native ADB crop evidence, never runtime map targets.
    crops = {
        "army_title": ("army", (635, 107, 978, 159)),
        "army_close": ("army", (1410, 101, 1471, 159)),
        "army_open": ("menu", (28, 621, 94, 687)),
        "starting": ("army", (185, 198, 337, 231)),
        "starting_ready": ("army", (152, 199, 181, 232)),
        "reinforcements": ("army", (1139, 198, 1395, 231)),
        "baby_dragon": ("scout", (268, 782, 347, 832)),
        "battle_machine": ("scout", (118, 754, 202, 833)),
        "battle_machine_active": ("hero-deployed", (120, 733, 197, 812)),
        "battle_copter": ("current", (114, 750, 205, 837)),
        "baby_choice": ("army-empty", (565, 706, 637, 758)),
        "raged_barbarian": ("army-empty", (312, 580, 384, 636)),
        "boxer_giant": ("army-empty", (438, 580, 510, 636)),
        "bomber": ("army-empty", (564, 580, 636, 636)),
        "cannon_cart": ("army-empty", (690, 580, 762, 636)),
        "sneaky_archer": ("army-empty", (312, 706, 384, 762)),
        "beta_minion": ("army-empty", (438, 706, 510, 762)),
        "night_witch": ("army-empty", (690, 706, 762, 762)),
        "baby_remove": ("army", (386, 371, 415, 394)),
        "battle_starts": ("scout", (710, 17, 892, 43)),
        "battle_ends": ("hero-deployed", (721, 17, 880, 43)),
        "defender": ("scout", (84, 17, 182, 43)),
        "attacker": ("scout", (1413, 17, 1513, 43)),
        "surrender": ("hero-deployed", (41, 611, 184, 644)),
        "end_battle": ("hero-ability", (40, 611, 184, 644)),
        "damage": ("hero-deployed", (1360, 628, 1544, 655)),
        "menu_close": ("menu", (1330, 138, 1389, 188)),
        "inactivity_title": ("live-around-4/frame-0136", (419, 367, 617, 398)),
        "inactivity_reload": ("live-around-4/frame-0136", (418, 515, 564, 539)),
        "builder_result_title": ("live-around-6/frame-0022", (696, 324, 910, 357)),
        "builder_result_return": ("live-around-6/frame-0022", (699, 720, 902, 802)),
        "cart_native_gd5": ("live-single-3/frame-0011", (962, 441, 1010, 482)),
        "battle_machine_charged": ("live-single-4/frame-0045", (118, 741, 202, 822)),
        "battle_machine_charging": ("live-single-4/frame-0038", (118, 741, 202, 822)),
        "battle_machine_cooldown": ("live-single-4/frame-0060", (118, 741, 202, 822)),
        "battle_machine_low_health": ("live-single-4/frame-0070", (118, 741, 202, 822)),
        "battle_copter_charged": ("live-single-4/frame-0130", (118, 742, 202, 824)),
        "battle_copter_charging": ("live-single-4/frame-0110", (118, 742, 202, 824)),
        "battle_machine_sweep": ("live-around-8/frame-0036", (118, 741, 202, 822)),
        "cart_defending_native": ("live-around-12/frame-0034", (676, 182, 925, 210)),
        "menu_count_one": ("menu", (367, 346, 392, 368)),
        "battle_machine_menu": ("menu", (277, 349, 349, 414)),
        "baby_dragon_survivor": ("live-single-5/frame-0113", (768, 802, 844, 850)),
    }
    manifest = {
        "resolution": [1600, 900],
        "language": "en",
        "serial": "127.0.0.1:16416",
        "assets": {},
    }
    for name, (parent, box) in crops.items():
        path = SOURCE / (parent + ".png")
        im = cv2.imread(str(path))
        if im is None:
            raise FileNotFoundError(path)
        x1, y1, x2, y2 = box
        out = DEST / (name + ".png")
        cv2.imwrite(str(out), im[y1:y2, x1:x2])
        manifest["assets"][name] = {
            "path": out.name,
            "source_kind": "adb_native_crop",
            "parent": str(path.relative_to(ROOT)),
            "crop_xyxy": box,
            "parent_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        }
    for index, left in enumerate((258, 385, 512, 638, 765, 891, 1017), 1):
        parent = "scout" if index < 7 else "current"
        path = SOURCE / (parent + ".png")
        im = cv2.imread(str(path))
        box = (left, 738, left + 25, 767)
        out = DEST / f"camp_{index}.png"
        cv2.imwrite(str(out), im[738:767, left : left + 25])
        manifest["assets"][out.stem] = {
            "path": out.name,
            "source_kind": "adb_native_crop",
            "parent": str(path.relative_to(ROOT)),
            "crop_xyxy": box,
            "parent_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        }
    (DEST / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
