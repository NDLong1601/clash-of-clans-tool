#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CocMagic — adb_controller.py
ADB wrapper: connect, tap, swipe, screenshot, template matching bằng OpenCV.
"""

import time
import os
import random
import struct
from typing import Optional, List, Tuple

import numpy as np
import cv2

from cocmagic import config
from cocmagic.process_utils import run_hidden
class ADBController:
    """Điều khiển BlueStacks qua ADB."""

    def __init__(self, host: str = config.ADB_HOST,
                 port: int = config.ADB_PORT,
                 adb_path: str = config.ADB_PATH,
                 serial: str = None, settings: dict = None,
                 stop_event=None):
        self.device  = serial or f"{host}:{port}"
        self.adb     = adb_path
        self.stop_event = stop_event
        self._cached_screenshot: Optional[np.ndarray] = None
        self._screenshot_ts: float = 0.0
        self._template_cache: dict = {}
        self._match_positions: dict = {}
        self._frame_matches: dict = {}
        self._raw_screenshot_supported = True
        self.verbose = bool((settings if settings is not None else config.load_settings()).get("verbose"))

    # ─── Kết nối ───────────────────────────────────────────

    def connect(self) -> bool:
        if ":" in self.device:
            self._run(["connect", self.device])
        out = self._run(["-s", self.device, "get-state"])
        ok = out.strip() == "device"
        status_tag = "[OK]" if ok else "[FAIL]"
        print(f"[ADB] {status_tag} connect {self.device}: {out.strip()}")
        return ok

    def disconnect(self):
        self._run(["disconnect", self.device])

    # ─── Thao tác cơ bản ────────────────────────────────────

    def tap(self, x: int, y: int, jitter: int = 0,
            delay: Optional[float] = None) -> bool:
        """Tap tại (x, y). Nếu jitter > 0, thêm ngẫu nhiên ±jitter px."""
        if self._stopping():
            return False
        if jitter:
            x += random.randint(-jitter, jitter)
            y += random.randint(-jitter, jitter)
        x = max(0, min(config.ANDROID_W - 1, x))
        y = max(0, min(config.ANDROID_H - 1, y))
        if not self._shell(f"input tap {x} {y}"):
            return False
        if self.verbose:
            print(f"  [tap] ({x},{y})")
        wait = config.DELAY_AFTER_TAP if delay is None else max(0.0, delay)
        if wait:
            time.sleep(wait)
        return True

    def tap_many(self, points: List[Tuple[int, int]], interval: float = 0.05) -> bool:
        """Send one short group of taps through one persistent ADB shell session.

        Only numeric, screen-clamped coordinates enter the shell script. The
        caller must verify game state between groups, never batch UI transitions.
        """
        if self._stopping():
            return False
        if not points:
            return True
        commands = []
        for i, (x, y) in enumerate(points):
            x = max(0, min(config.ANDROID_W - 1, int(x)))
            y = max(0, min(config.ANDROID_H - 1, int(y)))
            commands.append(f"input tap {x} {y}")
            if i + 1 < len(points) and interval > 0:
                commands.append(f"sleep {max(0.01, interval):.3f}")
        script = "\n".join(commands) + "\nexit\n"
        self.invalidate_cache()
        try:
            result = run_hidden(
                [self.adb, "-s", self.device, "shell"],
                input=script.encode("ascii"), capture_output=True,
                timeout=max(config.ADB_COMMAND_TIMEOUT, len(points) * 0.7 + 2),
            )
            if result.returncode != 0:
                print(f"[ADB] tap_many error: {result.stderr.decode(errors='replace').strip()}")
                return False
            return True
        except Exception as exc:
            print(f"[ADB] tap_many error: {exc}")
            return False

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        """Swipe từ (x1,y1) → (x2,y2) trong duration_ms ms."""
        if self._stopping():
            return
        dur = max(50, duration_ms)
        self._shell(f"input swipe {x1} {y1} {x2} {y2} {dur}")
        time.sleep(config.DELAY_AFTER_SWIPE)

    def long_press(self, x: int, y: int, duration_ms: int = 800):
        if self._stopping():
            return
        self._shell(f"input swipe {x} {y} {x} {y} {duration_ms}")
        time.sleep(duration_ms / 1000 + 0.3)

    def key_event(self, keycode: int):
        """Gửi key event Android (vd: 4 = BACK)."""
        if self._stopping():
            return
        self._shell(f"input keyevent {keycode}")
        time.sleep(0.3)

    def back(self):
        self.key_event(4)

    # ─── Screenshot ─────────────────────────────────────────

    def screenshot(self, use_cache: bool = True,
                   cache_ttl: float = 0.35) -> Optional[np.ndarray]:
        """
        Chụp màn hình → numpy array BGR.
        use_cache=True: tái dùng ảnh cũ nếu chưa quá cache_ttl giây.
        """
        if self._stopping():
            return None
        now = time.monotonic()
        if use_cache and self._cached_screenshot is not None:
            if now - self._screenshot_ts < cache_ttl:
                return self._cached_screenshot

        try:
            img_bgr = None
            if self._raw_screenshot_supported:
                result = run_hidden(
                    [self.adb, "-s", self.device, "exec-out", "screencap"],
                    capture_output=True, timeout=config.SCREENSHOT_TIMEOUT,
                )
                if result.returncode == 0 and result.stdout:
                    img_bgr = self._decode_raw_screenshot(result.stdout)
                if img_bgr is None:
                    self._raw_screenshot_supported = False
            if img_bgr is None:
                result = run_hidden(
                    [self.adb, "-s", self.device, "exec-out", "screencap", "-p"],
                    capture_output=True, timeout=config.SCREENSHOT_TIMEOUT,
                )
                if result.returncode == 0 and result.stdout:
                    img_bgr = cv2.imdecode(np.frombuffer(result.stdout, np.uint8),
                                           cv2.IMREAD_COLOR)
            if img_bgr is None:
                return None
            self._cached_screenshot = img_bgr
            self._screenshot_ts = time.monotonic()
            self._frame_matches.clear()
            return img_bgr
        except Exception as e:
            print(f"[ADB] screenshot error: {e}")
            return None

    def invalidate_cache(self):
        self._cached_screenshot = None
        self._frame_matches.clear()

    @staticmethod
    def _decode_raw_screenshot(data: bytes) -> Optional[np.ndarray]:
        """Decode packed RGBA screencap frames with old/new Android headers.

        Unsupported pixel formats or incomplete transfers use the PNG fallback.
        """
        if len(data) < 12:
            return None
        width, height, pixel_format = struct.unpack_from("<3I", data)
        if not (0 < width <= 8192 and 0 < height <= 8192) or pixel_format not in (1, 2):
            return None
        header_size = len(data) - width * height * 4
        if header_size not in (12, 16):
            return None
        rgba = np.frombuffer(data, np.uint8, offset=header_size).reshape(height, width, 4)
        return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)

    # ─── Template Matching ───────────────────────────────────

    def find_template(
        self,
        template_path: str,
        threshold: float = config.DEFAULT_THRESHOLD,
        screenshot: Optional[np.ndarray] = None,
        region: Optional[Tuple[int, int, int, int]] = None,  # (x, y, w, h)
    ) -> Optional[Tuple[int, int]]:
        """
        Tìm template trong screenshot hiện tại.
        Trả về (cx, cy) tâm của match đầu tiên, hoặc None.
        """
        img = screenshot if screenshot is not None else self.screenshot()
        if img is None:
            return None

        if not os.path.exists(template_path):
            print(f"[ADB] WARN: template không tồn tại: {template_path}")
            return None

        tpl = self._load_template(template_path)
        if tpl is None:
            return None

        # A frame is immutable until the next ADB input/capture. Repeated
        # checks of it can reuse both positive and negative recognition results.
        frame_key = (template_path, threshold, region)
        cache_frame = img is self._cached_screenshot
        if cache_frame and frame_key in self._frame_matches:
            return self._frame_matches[frame_key]

        frame_shape = img.shape[:2]

        # Crop region nếu có
        ox, oy = 0, 0
        if region:
            rx, ry, rw, rh = region
            img  = img[ry:ry+rh, rx:rx+rw]
            ox, oy = rx, ry

        th, tw = tpl.shape[:2]
        if img.shape[0] < th or img.shape[1] < tw:
            return None

        position_key = (template_path, region, frame_shape)
        previous = self._match_positions.get(position_key)
        if previous is not None:
            px, py = previous[0] - ox, previous[1] - oy
            pad = 12
            left, top = max(0, px - tw // 2 - pad), max(0, py - th // 2 - pad)
            right = min(img.shape[1], px + (tw + 1) // 2 + pad)
            bottom = min(img.shape[0], py + (th + 1) // 2 + pad)
            crop = img[top:bottom, left:right]
            if crop.shape[0] >= th and crop.shape[1] >= tw:
                match = cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED)
                _, score, _, point = cv2.minMaxLoc(match)
                if score >= threshold:
                    found = (ox + left + point[0] + tw // 2,
                             oy + top + point[1] + th // 2)
                    self._match_positions[position_key] = found
                    if cache_frame:
                        self._frame_matches[frame_key] = found
                    return found

        result  = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            cx = ox + max_loc[0] + tw // 2
            cy = oy + max_loc[1] + th // 2
            found = (cx, cy)
            self._match_positions[position_key] = found
            if cache_frame:
                self._frame_matches[frame_key] = found
            return found
        self._match_positions.pop(position_key, None)
        if cache_frame:
            self._frame_matches[frame_key] = None
        return None

    def find_all_templates(
        self,
        template_path: str,
        threshold: float = config.DEFAULT_THRESHOLD,
        screenshot: Optional[np.ndarray] = None,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> List[Tuple[int, int]]:
        """
        Tìm TẤT CẢ vị trí match của template (dùng NMS).
        Trả về list [(cx, cy), ...].
        """
        img = screenshot if screenshot is not None else self.screenshot()
        if img is None:
            return []

        if not os.path.exists(template_path):
            return []

        tpl = self._load_template(template_path)
        if tpl is None:
            return []

        ox, oy = 0, 0
        if region:
            rx, ry, rw, rh = region
            img  = img[ry:ry+rh, rx:rx+rw]
            ox, oy = rx, ry

        th, tw = tpl.shape[:2]
        if img.shape[0] < th or img.shape[1] < tw:
            return []

        result  = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        locs    = np.where(result >= threshold)

        # NMS đơn giản: nhóm các điểm gần nhau
        points  = list(zip(locs[1], locs[0]))  # (x, y)
        if not points:
            return []

        centers = []
        used    = [False] * len(points)
        for i, (px, py) in enumerate(points):
            if used[i]:
                continue
            used[i] = True
            cx, cy  = px, py
            for j, (qx, qy) in enumerate(points):
                if not used[j] and abs(qx - px) < tw and abs(qy - py) < th:
                    used[j] = True
            centers.append((ox + cx + tw // 2, oy + cy + th // 2))

        return centers

    def find_and_tap(
        self,
        template_path: str,
        threshold: float = config.DEFAULT_THRESHOLD,
        screenshot: Optional[np.ndarray] = None,
        region: Optional[Tuple[int, int, int, int]] = None,
        jitter: int = 3,
    ) -> bool:
        """Tìm template và tap ngay nếu tìm thấy. Trả về True nếu thành công."""
        pos = self.find_template(template_path, threshold, screenshot, region)
        if pos:
            return self.tap(pos[0], pos[1], jitter=jitter)
        return False

    def wait_for_template(
        self,
        template_path: str,
        timeout: float = 30.0,
        threshold: float = config.DEFAULT_THRESHOLD,
        poll_interval: float = 1.0,
    ) -> Optional[Tuple[int, int]]:
        """
        Chờ template xuất hiện trong timeout giây.
        Trả về vị trí hoặc None nếu timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.invalidate_cache()
            pos = self.find_template(template_path, threshold)
            if pos:
                return pos
            time.sleep(poll_interval)
        return None

    def is_visible(
        self,
        template_path: str,
        threshold: float = config.DEFAULT_THRESHOLD,
        screenshot: Optional[np.ndarray] = None,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> bool:
        """Kiểm tra template trong toàn màn hình hoặc trong vùng (x, y, w, h)."""
        return self.find_template(template_path, threshold, screenshot, region=region) is not None

    def _load_template(self, path: str) -> Optional[np.ndarray]:
        """Keep decoded templates in memory for the duration of this bot run."""
        if path not in self._template_cache:
            self._template_cache[path] = cv2.imread(path, cv2.IMREAD_COLOR)
        return self._template_cache[path]

    # ─── Pixel color ────────────────────────────────────────

    def get_pixel(self, x: int, y: int,
                  screenshot: Optional[np.ndarray] = None) -> Optional[Tuple[int, int, int]]:
        """Trả về (R, G, B) tại tọa độ (x, y)."""
        img = screenshot if screenshot is not None else self.screenshot()
        if img is None:
            return None
        b, g, r = img[y, x]
        return (int(r), int(g), int(b))

    # ─── ADB internal ───────────────────────────────────────

    def _run(self, args: list) -> str:
        self.invalidate_cache()
        try:
            r = run_hidden(
                [self.adb] + args,
                capture_output=True, text=True,
                timeout=config.ADB_COMMAND_TIMEOUT
            )
            return r.stdout + r.stderr
        except Exception as e:
            return str(e)

    def _shell(self, cmd: str) -> bool:
        if self._stopping():
            return False
        self.invalidate_cache()
        try:
            result = run_hidden(
                [self.adb, "-s", self.device, "shell", cmd],
                capture_output=True,
                timeout=config.ADB_COMMAND_TIMEOUT
            )
            if result.returncode != 0:
                print(f"[ADB] shell error '{cmd}': {result.stderr.decode(errors='replace').strip()}")
                return False
            return True
        except Exception as e:
            print(f"[ADB] shell error '{cmd}': {e}")
            return False

    def _stopping(self) -> bool:
        return self.stop_event is not None and self.stop_event.is_set()


def find_adb_port(adb_path: str = config.ADB_PATH) -> Optional[int]:
    """
    Tu dong tim port ADB cua MuMu Player.
    Thu tu: start-server -> adb devices -> MuMuManager -> scan port thu cong.
    """
    import os

    # ── 0. Khoi dong ADB daemon truoc ──────────────────────────
    # Day la buoc quan trong nhat — daemon chua chay thi connect luon that bai
    print("[ADB] Starting ADB server...")
    try:
        run_hidden(
            [adb_path, "start-server"],
            capture_output=True, timeout=10
        )
    except Exception as e:
        print(f"[ADB] start-server warning: {e}")

    # ── 1. Doc danh sach devices da ket noi (adb devices) ──────
    try:
        r = run_hidden(
            [adb_path, "devices"],
            capture_output=True, text=True, timeout=5
        )
        lines = r.stdout.strip().splitlines()
        for line in lines[1:]:   # bo dong "List of devices attached"
            line = line.strip()
            if not line or "offline" in line or "unauthorized" in line:
                continue
            if "device" in line or "emulator" in line:
                # Lay device ID (127.0.0.1:PORT hoac emulator-PORT)
                device_id = line.split()[0]
                if ":" in device_id:
                    # Dang 127.0.0.1:PORT
                    port_str = device_id.split(":")[-1]
                    if port_str.isdigit():
                        port = int(port_str)
                        print(f"[ADB] Found device via 'adb devices': {device_id}")
                        return port
                elif device_id.startswith("emulator-"):
                    # Dang emulator-5554 -> ADB port = 5554+1 = 5555
                    emu_port = int(device_id.split("-")[1])
                    adb_port = emu_port + 1
                    print(f"[ADB] Found emulator: {device_id} -> ADB port {adb_port}")
                    return adb_port
    except Exception as e:
        print(f"[ADB] devices warning: {e}")

    # ── 2. Thu MuMu Player Manager API ─────────────────────────
    mumu_dir     = os.path.dirname(os.path.dirname(adb_path))   # nx_main -> MuMuPlayer
    mumu_manager = os.path.join(mumu_dir, "MuMuManager.exe")

    if os.path.exists(mumu_manager):
        try:
            r = run_hidden(
                [mumu_manager, "adb", "-v", "0"],
                capture_output=True, text=True, timeout=5
            )
            for line in r.stdout.splitlines():
                if "port" in line.lower():
                    parts = line.strip().split(":")
                    if len(parts) >= 2:
                        port_str = parts[-1].strip()
                        if port_str.isdigit():
                            port = int(port_str)
                            print(f"[ADB] MuMuManager -> port {port}")
                            return port
        except Exception:
            pass

    # ── 3. Scan thu cong danh sach port ────────────────────────
    print("[ADB] Scanning ports:", config.ADB_SCAN_PORTS)
    for port in config.ADB_SCAN_PORTS:
        try:
            r = run_hidden(
                [adb_path, "connect", f"127.0.0.1:{port}"],
                capture_output=True, text=True, timeout=3
            )
            out = r.stdout + r.stderr
            if "connected" in out.lower() or "already" in out.lower():
                print(f"[ADB] Connected at port {port}")
                return port
        except Exception:
            pass

    return None
