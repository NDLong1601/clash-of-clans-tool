"""Persist independent emulator profiles beside settings.json."""

import json
import os
import tempfile
from copy import deepcopy

from cocmagic.config import migrate_settings
from cocmagic.device_manager import device_label, normalize_serial


class InstanceStore:
    def __init__(self, path: str, default_settings: dict):
        self.path = path
        self.default_settings = migrate_settings(default_settings)
        self.instances: dict[str, dict] = {}

    def load(self) -> dict[str, dict]:
        if not os.path.exists(self.path):
            return self.instances
        with open(self.path, "r", encoding="utf-8") as source:
            raw = json.load(source)
        if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("instances"), list):
            raise ValueError("instances.json không đúng định dạng phiên bản 1.")
        loaded = {}
        for item in raw["instances"]:
            if not isinstance(item, dict) or not isinstance(item.get("settings"), dict):
                raise ValueError("Có cấu hình giả lập không hợp lệ trong instances.json.")
            serial = normalize_serial(item.get("serial", ""))
            if serial in loaded:
                raise ValueError(f"Cổng {serial} bị lặp trong instances.json.")
            settings = migrate_settings(item["settings"], self.default_settings)
            loaded[serial] = {
                **deepcopy(item),
                "serial": serial,
                "name": str(item.get("name") or device_label(serial)),
                "settings": settings,
            }
        self.instances = loaded
        return loaded

    def add(self, serial: str, name: str | None = None) -> dict:
        serial = normalize_serial(serial)
        if serial not in self.instances:
            profile = {
                "serial": serial,
                "name": name or device_label(serial),
                "settings": deepcopy(self.default_settings),
            }
            self.instances[serial] = profile
            try:
                self.save()
            except OSError:
                del self.instances[serial]
                raise
        return self.instances[serial]

    def update_settings(self, serial: str, settings: dict) -> None:
        serial = normalize_serial(serial)
        if serial not in self.instances:
            raise KeyError(serial)
        previous = self.instances[serial]["settings"]
        self.instances[serial]["settings"] = migrate_settings({**previous, **deepcopy(settings)})
        try:
            self.save()
        except OSError:
            self.instances[serial]["settings"] = previous
            raise

    def remove(self, serial: str) -> None:
        serial = normalize_serial(serial)
        if serial in self.instances:
            profile = self.instances.pop(serial)
            try:
                self.save()
            except OSError:
                self.instances[serial] = profile
                raise

    def save(self) -> None:
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        payload = {"version": 1, "instances": list(self.instances.values())}
        name = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder,
                                             prefix=".instances-", suffix=".tmp",
                                             delete=False) as target:
                name = target.name
                json.dump(payload, target, ensure_ascii=False, indent=2)
                target.flush()
                os.fsync(target.fileno())
            os.replace(name, self.path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)
