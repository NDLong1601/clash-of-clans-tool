"""Bounded, image-verified camera changes in map space, excluding fixed HUD."""

from dataclasses import dataclass, field
from enum import Enum
import math
import time

import cv2
import numpy as np

from cocmagic.camera_backend import SerialGestureBackend
from cocmagic.troop_vision import detect_bar_cards, read_card_count
from cocmagic import config
from cocmagic.ui_dialogs import find_confirmation_button, find_inactivity_reload
from cocmagic.recovery import RecoveryInterrupted
from cocmagic.event_rewards import find_reward_panel


class CameraStatus(str, Enum):
    SUCCESS = "success"
    UNCHANGED = "unchanged"
    ERROR = "error"
    UNSUPPORTED = "unsupported"
    STOPPED = "stopped"


class ScreenSpace:
    """Calibrated 1600x900 HUD; other sizes need separate calibration."""

    resolution = (1600, 900)

    @staticmethod
    def map_mask(shape, context="battle"):
        if shape[:2] != (900, 1600) or context not in ("home", "scout", "battle"):
            return None
        mask = np.zeros((900, 1600), np.uint8)
        if context == "home":
            mask[115:700, 190:1400] = 255
            mask[:350, 1240:] = 0
        else:
            mask[100:720, 80:1520] = 255
            mask[:285, :310] = 0
            mask[:195, 1300:] = 0
            mask[:135, 620:980] = 0
            mask[555:, :250] = 0
            mask[540:, 1260:] = 0
            mask[650:, 250:1271] = 0
        return mask

    @classmethod
    def map_point(cls, point, context="battle"):
        mask = cls.map_mask((900, 1600), context)
        x, y = map(int, point)
        return mask is not None and 0 <= x < 1600 and 0 <= y < 900 and bool(mask[y, x])

    @classmethod
    def safe_path(cls, start, end, context):
        return all(
            cls.map_point(
                (
                    round(start[0] + (end[0] - start[0]) * f),
                    round(start[1] + (end[1] - start[1]) * f),
                ),
                context,
            )
            for f in np.linspace(0, 1, 40)
        )


def army_selection(image):
    """Selected native cards have a long white frame. Unknown bars fail closed.

    The Practice capture verifies this frame independently of the farm's
    selected-card bookkeeping; a fresh scout is not assumed deselected merely
    because the bot has not yet clicked a card.
    """
    if (
        image is None
        or image.shape[:2] != (900, 1600)
        or len(detect_bar_cards(image)) < 3
    ):
        return None
    hsv = cv2.cvtColor(image[755:881, :1530], cv2.COLOR_BGR2HSV)
    white = (hsv[:, :, 1] < 65) & (hsv[:, :, 2] > 210)
    columns = white.mean(axis=0) > 0.82
    return bool(np.any(columns[:-1] & columns[1:]))


@dataclass
class MotionEvidence:
    valid: bool = False
    changed: bool = False
    scale: float = 1.0
    dx: float = 0.0
    dy: float = 0.0
    inliers: int = 0
    reason: str = "Không đo được hình học bản đồ"


def measure_motion(before, after, context="battle"):
    """Track textured map features, never the army bar or resource HUD.

    A coherent similarity transform and spatial coverage distinguish camera
    motion from blinking roofs/troops. This transform is evidence only: targets
    are rebuilt from a new image, never translated with this estimate.
    """
    if before is None or after is None or before.shape != after.shape:
        return MotionEvidence(reason="Ảnh thiếu/đổi kích thước")
    mask = ScreenSpace.map_mask(before.shape, context)
    if mask is None:
        return MotionEvidence(reason="Resolution/context chưa hiệu chỉnh")
    g1, g2 = (cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) for im in (before, after))
    orb = cv2.ORB_create(nfeatures=2200, fastThreshold=12)
    k1, d1 = orb.detectAndCompute(g1, mask)
    k2, d2 = orb.detectAndCompute(g2, mask)
    if d1 is None or d2 is None:
        return MotionEvidence()
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(d1, d2, k=2)
    matches = [
        m
        for pair in pairs
        if len(pair) == 2
        for m, n in [pair]
        if m.distance < 0.72 * n.distance
    ]
    if len(matches) < 18:
        return MotionEvidence()
    src = np.float32([k1[m.queryIdx].pt for m in matches])
    dst = np.float32([k2[m.trainIdx].pt for m in matches])
    matrix, inside = cv2.estimateAffinePartial2D(
        src, dst, method=cv2.RANSAC, ransacReprojThreshold=3, maxIters=2000
    )
    if matrix is None or inside is None:
        return MotionEvidence()
    selected = inside.ravel().astype(bool)
    count = int(selected.sum())
    if (
        count < 18
        or count / len(matches) < 0.55
        or np.ptp(src[selected], axis=0).min() < 140
    ):
        return MotionEvidence(inliers=count, reason="Thiếu độ phủ/inlier camera")
    scale = math.hypot(matrix[0, 0], matrix[1, 0])
    rotation = math.atan2(matrix[1, 0], matrix[0, 0])
    if not 0.35 <= scale <= 2.8 or abs(rotation) > 0.035:
        return MotionEvidence(inliers=count, reason="Biến đổi camera không hợp lệ")
    center = np.array([800.0, 450.0])
    moved = matrix[:, :2] @ center + matrix[:, 2] - center
    changed = abs(scale - 1) > 0.012 or np.linalg.norm(moved) > 4
    return MotionEvidence(
        True,
        bool(changed),
        float(scale),
        float(moved[0]),
        float(moved[1]),
        count,
        "Đo được biến đổi map; HUD bị loại khỏi matcher",
    )


@dataclass
class CameraResult:
    status: CameraStatus
    reason: str
    revision: int
    before: np.ndarray | None = field(default=None, repr=False)
    after: np.ndarray | None = field(default=None, repr=False)
    motion: MotionEvidence | None = None
    attempts: int = 0


class CameraController:
    def __init__(
        self, adb, backend=None, *, stop_event=None, settle_timeout=3.0, max_frames=8
    ):
        self.adb = adb
        self.backend = backend or SerialGestureBackend(adb)
        self.stop_event = stop_event or getattr(adb, "stop_event", None)
        self.settle_timeout = min(5.0, max(0.1, settle_timeout))
        self.max_frames = min(12, max(2, max_frames))
        self.zoom_limits = set()
        self.adb.add_camera_listener(lambda revision: self.zoom_limits.clear())

    @property
    def revision(self):
        value = getattr(self.adb, "camera_revision", 0)
        return value if isinstance(value, int) else 0

    def stopping(self):
        return self.stop_event is not None and self.stop_event.is_set() is True

    def reset_view(self):
        self.zoom_limits.clear()
        self.adb.mark_camera_input()

    def _wait(self, seconds):
        if self.stop_event is None:
            time.sleep(seconds)
        else:
            self.stop_event.wait(seconds)

    def frame_clear(self, image):
        """Known modals invalidate camera context even over an unchanged map."""
        if image is None or ScreenSpace.map_mask(image.shape) is None:
            return False
        if (
            find_inactivity_reload(image) is not None
            or find_reward_panel(image) is not None
            or find_confirmation_button(self.adb, image) is not None
        ):
            return False
        for name in ("connection_lost_title.png", "Another_devicee.png"):
            found = self.adb.find_template(
                config.asset(name), 0.80, image, region=(330, 280, 900, 300)
            )
            if isinstance(found, tuple):
                return False
        return True

    def wait_stable(self, context):
        deadline = time.monotonic() + self.settle_timeout
        previous = None
        consecutive = 0
        for _ in range(self.max_frames):
            if self.stopping() or time.monotonic() >= deadline:
                break
            image = self.adb.screenshot(use_cache=False)
            if not self.frame_clear(image):
                return None
            if previous is not None:
                motion = measure_motion(previous, image, context)
                consecutive = (
                    consecutive + 1 if motion.valid and not motion.changed else 0
                )
                if consecutive >= 2:
                    return image
            previous = image
            self._wait(0.12)
        return None

    def _gesture(self, action, context, troop_selected, expected):
        with self.adb.input_lock:
            return self._execute_gesture(action, context, troop_selected, expected)

    def _execute_gesture(self, action, context, troop_selected, expected):
        if self.stopping():
            return CameraResult(
                CameraStatus.STOPPED, "Đã dừng trước gesture", self.revision
            )
        if context not in ("home", "scout", "battle") or troop_selected is not False:
            return CameraResult(
                CameraStatus.UNSUPPORTED,
                "Không camera khi quân đã chọn hoặc selection không rõ",
                self.revision,
            )
        before = self.wait_stable(context)
        if before is None:
            return CameraResult(
                CameraStatus.STOPPED if self.stopping() else CameraStatus.ERROR,
                "Ảnh trước chưa ổn định",
                self.revision,
            )
        if not self.frame_clear(before):
            return CameraResult(
                CameraStatus.ERROR,
                "Modal/context che bản đồ; không gửi camera",
                self.revision,
                before,
            )
        if context != "home" and army_selection(before) is not False:
            return CameraResult(
                CameraStatus.UNSUPPORTED,
                "Ảnh chưa xác nhận quân chưa chọn",
                self.revision,
                before,
            )
        ok = False
        released = False
        try:
            if self.stopping():
                return CameraResult(
                    CameraStatus.STOPPED, "Dừng trước input", self.revision, before
                )
            self.adb.mark_camera_input()
            ok = action() is True
        except RecoveryInterrupted:
            raise
        except Exception as exc:
            return CameraResult(
                CameraStatus.STOPPED if self.stopping() else CameraStatus.ERROR,
                f"Gesture lỗi: {exc}",
                self.revision,
                before,
                attempts=1,
            )
        finally:
            try:
                released = self.backend.release() is True
            except Exception:
                released = False
            self.adb.invalidate_cache()
        if self.stopping():
            return CameraResult(
                CameraStatus.STOPPED,
                "Đã dừng; release xác nhận"
                if released
                else "Đã dừng; release chưa xác nhận",
                self.revision,
                before,
                attempts=1,
            )
        if not ok or not released:
            return CameraResult(
                CameraStatus.ERROR,
                "Input/release thất bại; bỏ tọa độ cũ",
                self.revision,
                before,
                attempts=1,
            )
        after = self.wait_stable(context)
        evidence = measure_motion(before, after, context)
        status = CameraStatus.ERROR
        reason = "Ảnh sau chưa ổn định hoặc không xác nhận được camera"
        if after is not None and evidence.valid:
            status = (
                CameraStatus.SUCCESS if evidence.changed else CameraStatus.UNCHANGED
            )
            reason = (
                evidence.reason
                if evidence.changed
                else "Bản đồ không đổi; có thể đã chạm giới hạn"
            )
            if evidence.changed and not expected(evidence):
                status, reason = (
                    CameraStatus.ERROR,
                    "Bản đồ đổi nhưng không khớp hướng/loại gesture yêu cầu",
                )
            if context != "home":
                for x, y in detect_bar_cards(before):
                    old, new = (
                        read_card_count(before, x, y),
                        read_card_count(after, x, y),
                    )
                    if old is not None and new is not None and old != new:
                        status, reason = (
                            CameraStatus.ERROR,
                            "Số quân đổi trong gesture; không tiếp tục triển khai",
                        )
                        break
        return CameraResult(
            CameraStatus.STOPPED if self.stopping() else status,
            reason,
            self.revision,
            before,
            after,
            evidence,
            1,
        )

    def pan(self, start, end, *, context="home", troop_selected=None):
        if not ScreenSpace.safe_path(start, end, context):
            return CameraResult(
                CameraStatus.UNSUPPORTED, "Đường drag chạm HUD", self.revision
            )
        dx, dy = end[0] - start[0], end[1] - start[1]
        return self._gesture(
            lambda: self.backend.pan(start, end),
            context,
            troop_selected,
            lambda m: abs(m.scale - 1) < 0.035 and m.dx * dx + m.dy * dy > 0,
        )

    def zoom(self, factor, *, context="home", troop_selected=None):
        if not 0.55 <= factor <= 1.65 or factor == 1:
            return CameraResult(
                CameraStatus.UNSUPPORTED, "Hệ số zoom vượt giới hạn", self.revision
            )
        direction = "out" if factor < 1 else "in"
        if direction in self.zoom_limits:
            return CameraResult(
                CameraStatus.UNCHANGED,
                "Giới hạn zoom đã xác nhận; không gửi thêm",
                self.revision,
            )
        if self.stopping():
            return CameraResult(CameraStatus.STOPPED, "Đã dừng", self.revision)
        if troop_selected is not False:
            return CameraResult(
                CameraStatus.UNSUPPORTED, "Selection chưa an toàn", self.revision
            )
        if self.backend.touch is None and not self.backend.probe(
            ScreenSpace.resolution
        ):
            return CameraResult(
                CameraStatus.UNSUPPORTED, self.backend.reason, self.revision
            )
        result = self._gesture(
            lambda: self.backend.zoom((800, 410), factor),
            context,
            troop_selected,
            lambda m: (m.scale - 1) * (factor - 1) > 0,
        )
        if result.status == CameraStatus.UNCHANGED:
            self.zoom_limits.add(direction)
        elif result.status == CameraStatus.SUCCESS:
            self.zoom_limits.discard("in" if direction == "out" else "out")
        return result

    def normalize(self, *, context="home", troop_selected=None, max_attempts=3):
        """Reach the wide zoom limit with a finite budget; no fixed-diamond claim."""
        start = time.monotonic()
        for attempt in range(max(1, min(4, max_attempts))):
            result = self.zoom(0.6, context=context, troop_selected=troop_selected)
            if result.status != CameraStatus.SUCCESS or time.monotonic() - start > 20:
                return result
        return CameraResult(
            CameraStatus.ERROR,
            "Hết ngân sách chuẩn hóa; chưa chứng minh giới hạn zoom",
            self.revision,
            after=result.after,
            attempts=attempt + 1,
        )
