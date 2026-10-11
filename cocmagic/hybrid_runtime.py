"""Atomic runtime with a VM input lease shared by its ADB aliases."""

from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from cocmagic.recovery import RuntimeWriteError


@dataclass
class HybridRuntime:
    last_valid_bonus_check_at: str | None = None
    last_daily_check_date: str | None = None
    last_daily_request_date: str | None = None
    last_bonus_state: str = "unknown"
    bonus_progress: list[int] | None = None
    pending_builder_check: bool = True
    pending_reason: str | None = "startup"
    next_retry_at: str | None = None
    retry_count: int = 0
    retry_date: str | None = None
    last_error: str | None = None
    builder_incomplete: bool = True


class HybridRuntimeStore:
    def __init__(
        self,
        directory,
        serial,
        *,
        device_identity=None,
        runtime_serial=None,
        legacy_serials=(),
        log=print,
    ):
        self.serial = serial
        self.runtime_serial = runtime_serial or serial
        self.directory = Path(directory)
        self.path = self._runtime_path(self.runtime_serial)
        self._legacy_paths = [
            (self._runtime_path(alias), alias)
            for alias in dict.fromkeys((serial, *legacy_serials))
            if alias != self.runtime_serial
        ]
        if device_identity is not None and (
            not isinstance(device_identity, str) or not device_identity
        ):
            raise ValueError("Danh tính input không hợp lệ")
        digest = (
            hashlib.sha256(device_identity.encode("utf-8")).hexdigest()[:32]
            if device_identity
            else None
        )
        self.identity_lock_path = (
            self.directory / f"input-{digest}.lock" if digest else None
        )
        self.log = log
        self._lock_file = None
        self._alias_lock_files = []
        self._identity_lock_file = None
        self._owner = None

    def _runtime_path(self, serial):
        digest = hashlib.sha256(serial.encode("utf-8")).hexdigest()[:20]
        name = re.sub(r"[^a-zA-Z0-9_-]", "_", serial)[:40]
        return self.directory / f"{name}-{digest}.json"

    def _acquire_file(self, path):
        stream = path.open("a+b")
        try:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                if stream.read(1) == b"":
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            stream.close()
            raise RuntimeError(
                f"Đã có input/runtime writer cho giả lập {self.serial}"
            ) from error
        return stream

    def acquire(self):
        if self._lock_file is not None:
            raise RuntimeError("Runtime writer đã được mở")
        self.directory.mkdir(parents=True, exist_ok=True)
        opened = []
        try:
            if self.identity_lock_path is not None:
                self._identity_lock_file = self._acquire_file(self.identity_lock_path)
            # Hold every verified transport's legacy lock as well. This also
            # rejects an older owner after reboot or a newly discovered alias
            # changes which transport is chosen for the canonical runtime.
            paths = {
                self.path.with_suffix(".lock"),
                *(p.with_suffix(".lock") for p, _ in self._legacy_paths),
            }
            for path in sorted(paths):
                opened.append((path, self._acquire_file(path)))
        except Exception:
            for _, stream in reversed(opened):
                stream.close()
            if self._identity_lock_file is not None:
                self._identity_lock_file.close()
                self._identity_lock_file = None
            raise
        self._lock_file = next(
            stream for path, stream in opened if path == self.path.with_suffix(".lock")
        )
        self._alias_lock_files = [
            stream for _, stream in opened if stream is not self._lock_file
        ]
        self._owner = threading.get_ident()
        return self

    def _check_owner(self):
        if self._lock_file is None or self._owner != threading.get_ident():
            raise RuntimeError("Chỉ bot worker sở hữu runtime được đọc/ghi")

    def load(self):
        self._check_owner()
        try:
            source, expected_serial = self.path, self.runtime_serial
            if not source.exists():
                legacy = [(p, alias) for p, alias in self._legacy_paths if p.exists()]
                if legacy:
                    source, expected_serial = max(
                        legacy, key=lambda item: item[0].stat().st_mtime_ns
                    )
            raw = json.loads(source.read_text(encoding="utf-8"))
            if raw.get("version") != 1 or raw.get("serial") != expected_serial:
                raise ValueError("version/serial không khớp")
            data = raw["runtime"]
            if set(data) != {f.name for f in fields(HybridRuntime)}:
                raise ValueError("runtime thiếu/thừa trường")
            for key in ("last_valid_bonus_check_at", "next_retry_at"):
                if data[key] is not None:
                    if datetime.fromisoformat(data[key]).utcoffset() is None:
                        raise ValueError("timestamp thiếu timezone")
            for key in (
                "last_daily_check_date",
                "last_daily_request_date",
                "retry_date",
            ):
                if data[key] is not None:
                    date.fromisoformat(data[key])
            if data["last_bonus_state"] not in (
                "available",
                "claimable",
                "complete",
                "unknown",
            ):
                raise ValueError("bonus state không hợp lệ")
            if (
                type(data["retry_count"]) is not int
                or not 0 <= data["retry_count"] <= 100
            ):
                raise ValueError("retry_count không hợp lệ")
            for key in ("pending_builder_check", "builder_incomplete"):
                if type(data[key]) is not bool:
                    raise ValueError("cờ runtime không hợp lệ")
            for key in ("pending_reason", "last_error"):
                if data[key] is not None and not isinstance(data[key], str):
                    raise ValueError("lý do/lỗi không hợp lệ")
            progress = data["bonus_progress"]
            if progress is not None and (
                not isinstance(progress, list)
                or len(progress) != 2
                or any(type(n) is not int for n in progress)
                or not 0 <= progress[0] <= progress[1]
                or progress[1] <= 0
            ):
                raise ValueError("tiến độ sao không hợp lệ")
            if source != self.path:
                self.log(
                    f"[Hybrid runtime] {self.serial}: đọc lịch sử alias; lần lưu tiếp dùng runtime chung."
                )
            return HybridRuntime(**data)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            self.log(
                f"[Hybrid runtime] {self.serial}: runtime thiếu/hỏng ({error}); "
                "phục hồi UNKNOWN, bắt buộc đọc màn hình startup."
            )
            return HybridRuntime(
                last_error="Runtime thiếu/hỏng; đang kiểm tra lại màn hình"
            )

    def save(self, runtime):
        self._check_owner()
        payload = {
            "version": 1,
            "serial": self.runtime_serial,
            "runtime": asdict(runtime),
        }
        descriptor, temporary = tempfile.mkstemp(
            prefix=self.path.stem + "-", suffix=".tmp", dir=self.directory
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            for attempt in range(3):
                try:
                    os.replace(temporary, self.path)
                    break
                except OSError as error:
                    # Windows scanners/readers can briefly hold the destination.
                    # Keep the atomic replace; never truncate the previous runtime.
                    if (
                        getattr(error, "winerror", None) not in (5, 32, 33)
                        or attempt == 2
                    ):
                        raise
                    time.sleep(0.05 * (attempt + 1))
        except OSError as error:
            raise RuntimeWriteError(
                f"Không lưu được runtime {self.serial}: {error}"
            ) from error
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def close(self):
        if self._lock_file is not None:
            self._check_owner()
            # Closing the descriptor releases the process lock on both OSes.
            self._lock_file.close()
            self._lock_file = None
            for stream in self._alias_lock_files:
                stream.close()
            self._alias_lock_files.clear()
            if self._identity_lock_file is not None:
                self._identity_lock_file.close()
                self._identity_lock_file = None
            self._owner = None
