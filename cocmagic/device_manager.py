"""Discover local Android emulators without choosing a device implicitly."""

import re
import socket
import subprocess
from dataclasses import dataclass

from cocmagic import config
from cocmagic.process_utils import run_hidden
EMU_SERIAL = re.compile(r"emulator-\d+\Z")
LOCAL_SERIAL = re.compile(r"(?:127\.0\.0\.1|localhost):(\d+)\Z")


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    state: str
    identity: str | None = None


def normalize_serial(value: str) -> str:
    """Accept a local ADB port or an emulator serial, never a remote host."""
    value = str(value).strip()
    if value.isdecimal():
        value = f"127.0.0.1:{value}"
    match = LOCAL_SERIAL.fullmatch(value)
    if match:
        port = int(match.group(1))
        if 1 <= port <= 65535:
            return f"127.0.0.1:{port}"
    if EMU_SERIAL.fullmatch(value):
        return value
    raise ValueError("Chỉ hỗ trợ cổng ADB nội bộ hoặc serial emulator-NNNN.")


def is_local_emulator(serial: str) -> bool:
    try:
        normalize_serial(serial)
        return True
    except ValueError:
        return False


def parse_devices(output: str) -> list[DeviceInfo]:
    """Keep only local emulators in the ready state."""
    devices = []
    seen = set()
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[1] != "device":
            continue
        if not is_local_emulator(fields[0]):
            continue
        serial = normalize_serial(fields[0])
        if serial not in seen:
            devices.append(DeviceInfo(serial, "device"))
            seen.add(serial)
    return devices


def deduplicate_devices(devices: list[DeviceInfo],
                        preferred_serials=()) -> list[DeviceInfo]:
    """Prefer a saved serial, then a MuMu port, for aliases of one VM."""
    preferred = {serial: index for index, serial in enumerate(preferred_serials)}

    def priority(device):
        if device.serial in preferred:
            return (0, preferred[device.serial])
        match = LOCAL_SERIAL.fullmatch(device.serial)
        if match:
            port = int(match.group(1))
            if 16384 <= port < 16384 + 16 * 32 and (port - 16384) % 32 == 0:
                return (1, port)
        if device.serial.startswith("emulator-"):
            return (2, device.serial)
        return (3, device.serial)

    result = []
    seen = set()
    for device in sorted(devices, key=priority):
        identity = device.identity or device.serial
        if identity not in seen:
            result.append(device)
            seen.add(identity)
    return result


def discover_devices(adb_path: str = config.ADB_PATH,
                     extra_serials=()) -> list[DeviceInfo]:
    """Connect reachable known local ports, then list ADB-ready emulators."""
    run_hidden([adb_path, "start-server"], capture_output=True, timeout=10)
    current = run_hidden([adb_path, "devices", "-l"],
                             capture_output=True, text=True, timeout=8)
    if current.returncode:
        raise OSError(current.stderr.strip() or "Không đọc được danh sách ADB.")
    connected = {device.serial for device in parse_devices(current.stdout)}
    ports = set(config.ADB_SCAN_PORTS)
    ports.update(16384 + 32 * index for index in range(16))
    for serial in extra_serials:
        match = LOCAL_SERIAL.fullmatch(normalize_serial(serial))
        if match:
            ports.add(int(match.group(1)))
    for port in sorted(ports):
        serial = f"127.0.0.1:{port}"
        if serial in connected:
            continue
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                pass
            run_hidden([adb_path, "connect", serial],
                           capture_output=True, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            continue
    result = run_hidden([adb_path, "devices", "-l"],
                            capture_output=True, text=True, timeout=8)
    if result.returncode:
        raise OSError(result.stderr.strip() or "Không đọc được danh sách ADB.")
    devices = []
    for device in parse_devices(result.stdout):
        try:
            identity = run_hidden(
                [adb_path, "-s", device.serial, "shell", "cat",
                 "/proc/sys/kernel/random/boot_id"],
                capture_output=True, text=True, timeout=3,
            )
            boot_id = identity.stdout.strip() if identity.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            boot_id = ""
        devices.append(DeviceInfo(device.serial, device.state,
                                  f"boot:{boot_id}" if boot_id else None))
    return deduplicate_devices(devices, extra_serials)


def device_label(serial: str) -> str:
    if serial.startswith("127.0.0.1:"):
        return f"Giả lập {serial.rsplit(':', 1)[1]}"
    return serial
