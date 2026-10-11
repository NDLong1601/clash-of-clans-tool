"""Serial-scoped Android gestures. No desktop focus or independent swipe pinch."""

from dataclasses import dataclass
import re
import uuid

from cocmagic.process_utils import run_hidden
from cocmagic.recovery import remote_job_cleanup


@dataclass(frozen=True)
class TouchDevice:
    path: str
    xmax: int
    ymax: int
    rotation: int
    resolution: tuple[int, int]  # width, height, NOT an inferred UI scale

    def raw_point(self, point):
        x, y = point
        w, h = self.resolution
        if self.rotation == 1:
            return round((h - 1 - y) * self.xmax / (h - 1)), round(
                x * self.ymax / (w - 1)
            )
        raise ValueError("Touch rotation chưa được kiểm chứng")


class SerialGestureBackend:
    name = "adb_swipe / evdev_mt_slots"

    def __init__(self, adb):
        self.adb = adb
        self.touch = None
        self._gesture_released = None
        self.reason = "Chưa khảo sát multi-touch trên serial này"

    def _read(self, command):
        if self.adb._stopping():
            raise RuntimeError("Đã dừng; không gửi tiếp command probe")
        r = run_hidden(
            [self.adb.adb, "-s", self.adb.device, "shell", command],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode:
            raise RuntimeError(r.stderr.strip() or command)
        return r.stdout

    def probe(self, resolution=(1600, 900)) -> bool:
        """Narrow support for the MuMu Android 15 device verified in GĐ3.

        A SYN_REPORT permission check has no contact. Reject changed rotation,
        resolution, axes, active contacts or another touchscreen, rather than
        guessing raw coordinates. Never enable root/change device permissions.
        """
        self.touch = None
        try:
            events = self._read("getevent -lp")
            match = re.search(
                r"add device \d+: (/dev/input/event\d+)\s+name:\s+\"Xiaomi Touchscreen\"(.*?)(?=add device|\Z)",
                events,
                re.S,
            )
            if not match:
                raise ValueError("Không có Xiaomi Touchscreen đã kiểm chứng")
            path, axes = match.groups()
            if not all(
                code in axes
                for code in (
                    "ABS_MT_SLOT",
                    "ABS_MT_TRACKING_ID",
                    "ABS_MT_POSITION_X",
                    "ABS_MT_POSITION_Y",
                )
            ):
                raise ValueError("Thiếu protocol B multi-touch")
            xmax = int(re.search(r"ABS_MT_POSITION_X\s+:.*?max (\d+)", axes).group(1))
            ymax = int(re.search(r"ABS_MT_POSITION_Y\s+:.*?max (\d+)", axes).group(1))
            dump = self._read("dumpsys input")
            block = re.search(
                r"Device \d+: Xiaomi Touchscreen\n(.*?)(?=\n  Device |\n    Input Controller:|\Z)",
                dump,
                re.S,
            ).group(1)
            if "Last Raw Touch: pointerCount=0" not in block:
                raise ValueError("Touchscreen còn điểm chạm; không giành input")
            if "orientation=1, logicalFrame=[0, 0, 1600, 900]" not in block:
                raise ValueError("Viewport/rotation chưa hỗ trợ")
            if (xmax, ymax, resolution) != (900, 1600, (1600, 900)):
                raise ValueError("Raw axes/resolution chưa được kiểm chứng")
            self._read(f"sendevent {path} 0 0 0")
            self.touch = TouchDevice(path, xmax, ymax, 1, resolution)
            self.reason = "MuMu Android 15: protocol B, 2 slots, serial-scoped"
            return True
        except Exception as exc:
            self.reason = str(exc)
            return False

    def pan(self, start, end, duration_ms=350):
        self._gesture_released = None
        return self.adb.swipe(*start, *end, duration_ms=duration_ms)

    def zoom(self, center, factor, duration_ms=350):
        """Both contacts share each SYN_REPORT in one shell script.

        The script releases its own slots on exit/signal; host finally also
        terminates the uniquely named remote job and releases after timeout or
        Stop. A submitted gesture is bounded; Stop never submits a new one.
        """
        touch = self.touch
        if touch is None or self.adb._stopping():
            return False
        # Revalidate device/viewport and absence of human touches every time.
        if not self.probe(touch.resolution):
            return False
        if self.adb._stopping():
            return False
        touch = self.touch
        cx, cy = center
        radius = 180
        steps = 10
        token = uuid.uuid4().hex
        pidfile = f"/data/local/tmp/cocmagic-camera-{token}.pid"
        event = f"sendevent {touch.path}"
        releases = [
            f"{event} {values}"
            for values in ("3 47 0", "3 57 -1", "3 47 1", "3 57 -1", "0 0 0")
        ]
        release = "; ".join(releases)
        script = [
            f"echo $$ > {pidfile}",
            f"trap '{release}; rm -f {pidfile}' EXIT",
            "trap 'exit 1' HUP INT TERM",
            "set -e",
        ]
        for step in range(steps + 1):
            distance = radius * (1 + (factor - 1) * step / steps)
            for slot, sign in ((0, -1), (1, 1)):
                rx, ry = touch.raw_point((round(cx + sign * distance), cy))
                script.append(f"{event} 3 47 {slot}")
                if step == 0:
                    script.append(f"{event} 3 57 {32000 + slot}")
                script.extend((f"{event} 3 53 {rx}", f"{event} 3 54 {ry}"))
            script.extend(
                (
                    f"{event} 0 0 0",
                    f"sleep {max(150, min(700, duration_ms)) / steps / 1000:.3f}",
                )
            )
        ok = False
        cleanup_ok = False
        self._gesture_released = False
        try:
            if self.adb._stopping():
                return False
            r = run_hidden(
                [self.adb.adb, "-s", self.adb.device, "shell", "sh -s"],
                input=("\n".join(script) + "\n").encode("ascii"),
                capture_output=True,
                timeout=5,
            )
            ok = r.returncode == 0 and not self.adb._stopping()
        except Exception as exc:
            self.reason = f"Pinch thất bại: {exc}"
        finally:
            try:
                # Ignore stop for cleanup. A unique pidfile prevents killing
                # another worker's gesture or leaving a timed-out script alive.
                cleanup = (
                    remote_job_cleanup(pidfile)
                    + "; "
                    + "; ".join(f"{cmd} || cleanup_rc=1" for cmd in releases)
                    + "; exit $cleanup_rc"
                )
                r = run_hidden(
                    [self.adb.adb, "-s", self.adb.device, "shell", cleanup],
                    capture_output=True,
                    timeout=3,
                )
                cleanup_ok = r.returncode == 0
            except Exception:
                self.reason = "Không xác nhận được release multi-touch"
            self.adb.invalidate_cache()
            self._gesture_released = cleanup_ok
        return ok and cleanup_ok

    def release(self):
        return self.adb.release_touch() and self._gesture_released is not False
