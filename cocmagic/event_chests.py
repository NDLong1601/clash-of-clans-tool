"""Optional post-battle Claim → four chest hits → Continue transaction."""

from dataclasses import dataclass
from functools import lru_cache
import time

import cv2
import numpy as np

from cocmagic import config


REFERENCE_SIZE = (1050, 591)


@lru_cache(maxsize=None)
def _template(name):
    path = config.asset(f"event_chest/{name}.png")
    image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(path)
    return image


def _match(gray, name, region, threshold=.88):
    x, y, w, h = region
    target = _template(name)
    roi = gray[y:y + h, x:x + w]
    if any(a < b for a, b in zip(roi.shape, target.shape)):
        return None
    _, score, _, point = cv2.minMaxLoc(cv2.matchTemplate(roi, target, cv2.TM_CCOEFF_NORMED))
    if score < threshold:
        return None
    return x + point[0] + target.shape[1] // 2, y + point[1] + target.shape[0] // 2


@dataclass(frozen=True)
class ChestScreen:
    kind: str                  # claim | room | reward
    point: tuple[int, int] | None = None
    remaining: int | None = None
    cached: bool = False


def find_chest_screen(image, cached_point=None):
    """Require event-specific artwork, never a generic green Claim button.

    Cache coordinates belong to the supplied resolution. A room with four
    hammers but no chest yet is recognized for waiting, without a tap point.
    """
    if (image is None or image.ndim != 3 or image.shape[2] != 3 or
            image.dtype != np.uint8):
        return None
    height, width = image.shape[:2]
    if width < 600 or abs(width / height - 16 / 9) > .03:
        return None
    normalized = cv2.resize(image, REFERENCE_SIZE, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(normalized, cv2.COLOR_BGR2GRAY)

    def scaled(point):
        return (round(point[0] * width / 1050), round(point[1] * height / 591))

    claim = _match(gray, "claim_button", (380, 450, 300, 125), .90)
    # Text anti-aliasing differs between native ADB and the recorded window;
    # the larger chest/button artwork remains the strict primary anchor.
    if claim and (_match(gray, "result_troops", (380, 340, 300, 100), .78) or
                  _match(gray, "result_troops_native", (380, 340, 300, 100), .88)):
        return ChestScreen("claim", scaled(claim))
    # The reward view has a different camera from the hammer/chest view.
    continuation = _match(gray, "continue_button", (380, 470, 300, 120), .80)
    if (continuation and _match(gray, "reward_torch", (210, 0, 130, 160)) and
            _match(gray, "reward_column", (810, 0, 160, 340))):
        return ChestScreen("reward", scaled(continuation))
    if not (_match(gray, "room_torch", (255, 0, 170, 285), .90) and
            _match(gray, "room_door", (0, 0, 220, 370), .75)):
        return None
    hsv = cv2.cvtColor(normalized, cv2.COLOR_BGR2HSV)
    bright = [float(np.mean((hsv[479:514, x-10:x+10, 1] < 65) &
                            (hsv[479:514, x-10:x+10, 2] > 130)))
              for x in (450, 497, 544, 591)]
    # During a hit the active hammer grows, but still counts as unconsumed
    # until it turns into a dark outline. Ambiguous animation waits.
    remaining = (sum(value >= .22 for value in bright)
                 if all(value >= .22 or value <= .06 for value in bright) else None)
    point, cached = None, False
    if cached_point is not None:
        cx, cy = round(cached_point[0] * 1050 / width), round(cached_point[1] * 591 / height)
        point = _match(gray, "chest_lock", (max(0, cx-60), max(0, cy-55), 120, 110), .75)
        if point is None:
            glow = _match(gray, "chest_lock_glow", (max(0, cx-60), max(0, cy-15), 120, 110), .85)
            point = (glow[0], glow[1] - 25) if glow else None
        cached = point is not None
    if point is None:
        point = _match(gray, "chest_lock", (350, 170, 350, 245), .75)
    if point is None:
        glow = _match(gray, "chest_lock_glow", (350, 170, 350, 245), .85)
        point = (glow[0], glow[1] - 25) if glow else None
    return ChestScreen("room", scaled(point) if point else None, remaining, cached)


@dataclass(frozen=True)
class ChestResult:
    handled: bool
    image: np.ndarray | None
    error: str | None = None


class EventChestOpener:
    """Bounded input owned by the active village module, independent of event_mode."""

    def __init__(self, adb, *, clock=time.monotonic):
        self.adb = adb
        self.clock = clock
        self.position = None
        self.resolution = None
        self.opened = 0
        self.cache_hits = 0

    def reset(self):
        self.position = self.resolution = None

    def _observe(self, image):
        if image is not None and image.shape[:2] != self.resolution:
            self.reset()
        return find_chest_screen(image, self.position)

    def open(self, image, *, capture, wait, stopping, terminal):
        scene = self._observe(image)
        if scene is None:
            return ChestResult(False, image)
        started = self.clock()
        claimed = continued = exhausted = False
        pending_count = None
        pending_at = started
        retries = hits = 0
        target = None
        print("[Chest] Phát hiện thưởng rương; nhận và mở tự động.")
        for _ in range(120):
            if stopping():
                return ChestResult(True, image)
            now = self.clock()
            if now - started > 25:
                break
            point = None
            if scene is None:
                if image is not None and terminal(image):
                    self.opened += int(continued)
                    print("[Chest] Đã nhận thưởng; tiếp tục train.")
                    return ChestResult(True, image)
            elif scene.kind == "claim":
                if not claimed:
                    point = scene.point
                    claimed = True
            elif scene.kind == "reward":
                if not continued:
                    point = scene.point
                    continued = True
            elif not continued and not exhausted:
                if target is None and scene.point is not None and scene.remaining:
                    target = self.position = scene.point
                    self.resolution = image.shape[:2]
                    self.cache_hits += int(scene.cached)
                    print(f"[Chest] Vị trí rương {target}" + (" · dùng cache" if scene.cached else " · đã cache"))
                remaining = scene.remaining
                if remaining == 0 and hits:
                    exhausted = True
                elif target is not None and remaining:
                    if pending_count is None or remaining < pending_count:
                        point = target
                        retries = 0
                    elif remaining == pending_count and now - pending_at >= 1.5:
                        # An unchanged hammer is evidence that the game may
                        # have ignored a hit during its arrival animation.
                        if retries >= 2:
                            return ChestResult(True, image, "Rương không nhận click sau 3 lần; cần kiểm tra màn hình.")
                        point = target
                        retries += 1
                    if point:
                        pending_count, pending_at = remaining, now
                        hits += 1
                        if hits > 8:
                            return ChestResult(True, image, "Rương chưa mở sau 8 click; không click tiếp.")
            if point is not None:
                if stopping():
                    return ChestResult(True, image)
                if self.adb.tap(*point, jitter=0, delay=0) is not True:
                    return ChestResult(True, image, "Input mở rương chưa xác nhận; dừng thao tác.")
            wait(.12)
            image = capture()
            scene = self._observe(image)
        return ChestResult(True, image, "Timeout nhận/mở rương; giữ màn hình để kiểm tra.")
