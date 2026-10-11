"""Derive calibrated HUD anchors and anonymized test evidence from native ADB."""

import hashlib
import json
from pathlib import Path
import cv2

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parent = ROOT / "diagnostics/dual_village_gd6/live-read.png"
    image = cv2.imread(str(parent))
    if image is None or image.shape != (900, 1600, 3):
        raise ValueError("Need native 1600x900 capture, no resizing")
    asset_dir = ROOT / "assets/dual_village"
    manifest_path = asset_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # The upper shield border excludes the changing account-level digits.
    entries = {
        "profile_border": ((22, 15, 108, 33), (0, 0, 150, 110)),
        "main_attack_current": ((38, 751, 175, 866), (15, 735, 180, 147)),
    }
    for name, (box, region) in entries.items():
        x0, y0, x1, y1 = box
        path = asset_dir / f"{name}.png"
        cv2.imwrite(str(path), image[y0:y1, x0:x1])
        manifest["anchors"][name] = {
            "path": path.name,
            "region": list(region),
            "threshold": 0.92,
            "dimensions": [x1 - x0, y1 - y0],
            "source_kind": "adb_native_crop",
            "parent": parent.relative_to(ROOT).as_posix(),
            "parent_sha256": digest(parent),
            "crop_xyxy": list(box),
            "sha256": digest(path),
            "language": "en",
        }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    fixture_dir = ROOT / "tests/fixtures/dual_village/hybrid"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    # Retain only the HUD needed for Home; remove account name, resources and
    # the base. This is labeled transformed evidence, never a native full frame.
    result = image.copy()
    result[:] = 0
    boxes = [
        (0, 0, 110, 110),
        (690, 0, 840, 115),
        (0, 300, 140, 190),
        (1440, 585, 160, 150),
        (15, 735, 180, 147),
    ]
    for x, y, w, h in boxes:
        result[y : y + h, x : x + w] = image[y : y + h, x : x + w]
    path = fixture_dir / "main-home-level71.png"
    cv2.imwrite(str(path), result)
    evidence = {
        "source_kind": "transformed_test",
        "parent": parent.relative_to(ROOT).as_posix(),
        "parent_sha256": digest(parent),
        "resolution": [1600, 900],
        "preserved_xywh": boxes,
        "transformation": "Black all pixels except the five HUD regions. No resize.",
        "path": path.name,
        "sha256": digest(path),
    }
    (fixture_dir / "manifest.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    print("Prepared 2 native HUD crops and 1 anonymized transformed fixture.")


if __name__ == "__main__":
    main()
