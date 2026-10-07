"""Client for the optional pilot license API, shared by GUI and CLI."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cocmagic import config


POLICY_FILE = Path(config.DATA_DIR) / "license-config.json"
KEY_FILE = Path(config.DATA_DIR) / "license-key.bin"
KEY_PATTERN = re.compile(r"^CM[A-F0-9]{48}$")
MESSAGES = {
    "unknown_key": "Key không tồn tại.",
    "revoked": "Key đã bị thu hồi.",
    "expired": "Key đã hết hạn.",
    "another_machine": "Key đã kích hoạt trên máy khác.",
    "invalid_input": "Key hoặc mã máy không hợp lệ.",
    "invalid_key": "Key không đúng định dạng.",
    "unauthorized": "Không có quyền truy cập API.",
    "server_error": "Máy chủ cấp phép đang lỗi.",
}


class LicenseError(Exception):
    def __init__(self, code: str, message: str | None = None, *, temporary: bool = False):
        self.code = code
        self.temporary = temporary
        super().__init__(message or MESSAGES.get(code, code))


@dataclass(frozen=True)
class LicensePolicy:
    enabled: bool = False
    api_url: str = ""
    check_interval_seconds: int = 600
    offline_grace_seconds: int = 1800


@dataclass(frozen=True)
class LicenseCheck:
    expires_at: int | None
    server_time: int

    def label(self) -> str:
        if self.expires_at is None:
            return "Key hợp lệ · vĩnh viễn"
        from datetime import datetime
        end = datetime.fromtimestamp(self.expires_at).strftime("%d/%m/%Y %H:%M")
        return f"Key hợp lệ · hết hạn {end}"


def load_policy(path: Path = POLICY_FILE) -> LicensePolicy:
    if not path.exists():
        return LicensePolicy()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("config must be an object")
        enabled = value.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        if not enabled:
            return LicensePolicy()
        api_url = str(value.get("api_url", "")).strip().rstrip("/")
        if not (api_url.startswith("https://") or
                api_url.startswith("http://127.0.0.1:") or
                api_url.startswith("http://localhost:")):
            raise ValueError("API phải dùng HTTPS, trừ địa chỉ chạy thử cục bộ")
        check = int(value.get("check_interval_seconds", 600))
        grace = int(value.get("offline_grace_seconds", 1800))
        if not 30 <= check <= 86400 or not 0 <= grace <= 86400:
            raise ValueError("Chu kỳ kiểm tra hoặc thời gian ân hạn không hợp lệ")
        return LicensePolicy(True, api_url, check, grace)
    except (OSError, ValueError, TypeError) as error:
        raise LicenseError("bad_config", f"Cấu hình cấp phép không hợp lệ: {error}") from error


def normalize_key(raw: str) -> str:
    if not isinstance(raw, str):
        raise LicenseError("invalid_key")
    normalized = re.sub(r"[\s-]", "", raw.strip().upper())
    if not KEY_PATTERN.fullmatch(normalized):
        raise LicenseError("invalid_key")
    return normalized


def machine_id() -> str:
    """Stable host identifier; the emulator ADB serial is deliberately excluded."""
    if os.name != "nt":
        raise LicenseError("unsupported_host", "Bản cấp phép thử nghiệm cần máy Windows.")
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        if not isinstance(guid, str) or not guid.strip():
            raise ValueError("MachineGuid trống")
    except (OSError, ValueError) as error:
        raise LicenseError("machine_id_unavailable", f"Không đọc được mã máy: {error}") from error
    return hashlib.sha256(("cocmagic-license-v1:" + guid.strip().lower()).encode()).hexdigest()


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _protect(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise LicenseError("unsupported_host", "Lưu key an toàn chỉ hỗ trợ Windows.")
    input_buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    input_blob = _DataBlob(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                          wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    operation.restype = wintypes.BOOL
    flags = 0 if decrypt else 0x4  # CRYPTPROTECT_LOCAL_MACHINE
    if not operation(ctypes.byref(input_blob), None, None, None, None,
                     flags, ctypes.byref(output_blob)):
        raise LicenseError("key_storage", "Không mở được key đã lưu trên máy này.")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))


class LicenseClient:
    def __init__(self, policy: LicensePolicy, *, key_file: Path = KEY_FILE,
                 device_id: str | None = None):
        self.policy = policy
        self.key_file = Path(key_file)
        self._device_id = device_id

    @classmethod
    def from_config(cls) -> "LicenseClient":
        return cls(load_policy())

    @property
    def device_id(self) -> str:
        if self._device_id is None:
            self._device_id = machine_id()
        return self._device_id

    def read_key(self) -> str:
        if not self.key_file.exists():
            raise LicenseError("missing_key", "Chưa nhập key cấp phép.")
        try:
            value = _protect(self.key_file.read_bytes(), decrypt=True).decode("ascii")
            return normalize_key(value)
        except (OSError, UnicodeError) as error:
            raise LicenseError("key_storage", f"Không đọc được key đã lưu: {error}") from error

    def save_key(self, key: str) -> None:
        normalized = normalize_key(key)
        protected = _protect(normalized.encode("ascii"), decrypt=False)
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.key_file.with_suffix(".tmp")
        try:
            temporary.write_bytes(protected)
            os.replace(temporary, self.key_file)
        finally:
            if temporary.exists():
                temporary.unlink()

    def check(self, key: str | None = None, *, remember: bool = False) -> LicenseCheck:
        if not self.policy.enabled:
            return LicenseCheck(None, int(time.time()))
        normalized = normalize_key(key) if key is not None else self.read_key()
        payload = json.dumps({"key": normalized, "machineId": self.device_id}).encode("utf-8")
        request = Request(
            self.policy.api_url + "/v1/license/check", data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "CocMagicLicenseClient/1.0",
            },
        )
        try:
            with urlopen(request, timeout=8) as response:
                result = json.load(response)
        except HTTPError as error:
            try:
                result = json.load(error)
                code = result.get("code", "http_error")
            except (OSError, ValueError):
                code = "http_error"
            raise LicenseError(code, temporary=error.code >= 500) from error
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise LicenseError("network_error", f"Không liên hệ được dịch vụ key: {error}",
                               temporary=True) from error
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise LicenseError(str(result.get("code", "invalid_response")) if isinstance(result, dict)
                               else "invalid_response")
        expires_at = result.get("expiresAt")
        server_time = result.get("serverTime")
        if (expires_at is not None and not isinstance(expires_at, int)) or not isinstance(server_time, int):
            raise LicenseError("invalid_response", "API trả về dữ liệu cấp phép không hợp lệ.")
        if expires_at is not None and expires_at <= server_time:
            raise LicenseError("expired")
        if remember:
            self.save_key(normalized)
        return LicenseCheck(expires_at, server_time)
