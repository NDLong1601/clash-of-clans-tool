"""Audit published village/chest vision evidence; private parents are optional.

Checks bytes/dimensions/provenance, not correctness of labels or live behavior.
"""

import argparse
import hashlib
import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]


def audit(root=ROOT):
    errors, checked, parents, missing_parents = [], [], [], []

    def verify(path, expected, dimensions=None, *, optional=False):
        if not path.is_file():
            (missing_parents if optional else errors).append(
                str(path.relative_to(root))
            )
            return
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            errors.append(f"{path.relative_to(root)}: SHA-256 mismatch")
        if dimensions is not None:
            image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if image is None or list(image.shape[1::-1]) != dimensions:
                errors.append(f"{path.relative_to(root)}: decode/dimensions mismatch")
        (parents if optional else checked).append(str(path.relative_to(root)))

    manifests = sorted((root / "assets/dual_village").rglob("manifest.json"))
    manifests += sorted((root / "tests/fixtures/dual_village").rglob("manifest.json"))
    manifests += sorted((root / "assets/event_chest").rglob("manifest.json"))
    manifests += sorted((root / "tests/fixtures/event_chest").rglob("manifest.json"))
    if not manifests:
        errors.append("No dual-village manifests")
    for path in manifests:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = []
        for key in ("anchors", "assets", "fixtures", "inspection_sheets"):
            collection = data.get(key, [])
            entries.extend(
                collection.values() if isinstance(collection, dict) else collection
            )
        if "path" in data and "sha256" in data:
            entries.append(data)
        for entry in entries:
            target = (path.parent / entry["path"]).resolve()
            if not target.is_relative_to(root.resolve()):
                errors.append(f"{path}: published path outside repo")
                continue
            verify(target, entry["sha256"], entry.get("dimensions"))
            if entry.get("parent") and entry.get("parent_sha256"):
                parent = (root / entry["parent"].replace("\\", "/")).resolve()
                if parent.is_relative_to(root.resolve()):
                    verify(parent, entry["parent_sha256"], optional=True)
        for name, digest in data.get("outputs", {}).items():
            verify(path.parent / name, digest)
    # Recheck raw receipts rather than accepting the prose from earlier phases.
    for path in (root / "tests/fixtures/dual_village").rglob("*receipt.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = [data, *data.get("sessions", [])]
        for entry in entries:
            for name in ("source", "source_receipt", "raw_receipt", "source_log"):
                if not isinstance(entry.get(name), str) or not entry.get(
                    name + "_sha256"
                ):
                    continue
                raw = (root / entry[name].replace("\\", "/")).resolve()
                if not raw.is_relative_to(root.resolve()):
                    errors.append(f"{path}: raw receipt outside repo")
                    continue
                verify(raw, entry[name + "_sha256"], optional=True)
                if raw.is_file() and name != "source_log":
                    original = json.loads(raw.read_text(encoding="utf-8"))
                    for key in (
                        "metrics",
                        "builder_metrics",
                        "completed",
                        "passes",
                        "bonus",
                        "cart",
                        "goal_met",
                        "error",
                        "elapsed",
                        "initial_trained",
                    ):
                        if (
                            key in entry
                            and key in original
                            and entry[key] != original[key]
                        ):
                            errors.append(
                                f"{path.relative_to(root)}: raw receipt {key} differs"
                            )
    return {
        "manifests": len(manifests),
        "published_files_checked": len(checked),
        "private_parents_checked": len(parents),
        "private_parents_missing": sorted(set(missing_parents)),
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Optional local JSON report")
    args = parser.parse_args()
    result = audit()
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
