"""Upgrade a wall group through the builder list, independent of map zoom."""

import sys
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.screen_reader import ScreenReader
from cocmagic.ui_dialogs import CONFIRM_TEMPLATES, find_confirmation_button

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


T_WALL_LABEL = config.asset("wall_1.png")
T_WALL_WORD = config.asset("wall_2.png")
T_BUILDER_AVAILABLE = config.asset("builder_available.png")
T_UPMORE = config.asset("upmore.png")
T_ADD_WALL = config.asset("addwall.png")
T_REMOVE_WALL = config.asset("removewall.png")
T_GOLD_UPGRADE = config.asset("nangcapvangwall.png")
T_ELIXIR_UPGRADE = config.asset("nangcapdauwall.png")
WALL_CONFIRM_BUTTONS = ((config.asset("okay.png"), .67),) + tuple(
    (path, .80) for path in CONFIRM_TEMPLATES)

BUILDER_ICON_REGION = (690, 0, 110, 110)
BUILDER_LIST_OFFSET = (62, -3)  # From the available portrait to the list button.
# Long upgrade names widen the list and move its left edge to x=490.
# Include that text column and the final row above the bottom edge at y=695.
LIST_REGION = (480, 140, 350, 555)
UPMORE_REGION = (610, 625, 190, 155)
ADD_REGION = (630, 625, 170, 155)
ADD_WALL_SIZE = (134, 33)
BUILDER_PORTRAIT_SIZE = (48, 54)
WALL_CONTROL_REGION = (270, 625, 1060, 155)
UPGRADE_ICON_SIZE = (20, 137)
# Price text is above the resource icon strip; the strip moves with its button.
COST_FROM_ICON = {"gold": (-140, -62, 143, 35),
                  "elixir": (-140, -65, 143, 35)}
GOLD_BUTTON_REGION = (800, 625, 180, 155)
ELIXIR_BUTTON_REGION = (975, 625, 180, 155)
GOLD_COST_REGION = (810, 632, 143, 35)
ELIXIR_COST_REGION = (988, 632, 143, 35)


class WallModule:
    """Upgrade only when an ordinary builder and an affordable quote exist."""

    def __init__(self, adb: ADBController, reader: ScreenReader, settings: dict,
                 stop_event=None):
        self.adb = adb
        self.reader = reader
        self.settings = settings
        self.stop_event = stop_event
        self.last_interacted = False
        self._builder_list_open = False
        self.walls_upgraded = 0
        self.last_upgrade_verified = False
        self._position_cache: dict[str, Tuple[int, int]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("upgrade_walls", True))

    @property
    def wall_type(self) -> str:
        return self.settings.get("wall_type", "gold")

    def run(self) -> bool:
        """Keep upgrading affordable wall groups before farming resumes."""
        self.last_interacted = False
        if not self.enabled:
            return False

        upgraded_any = False
        while True:
            if self.stop_event is not None and self.stop_event.is_set():
                return upgraded_any
            self.last_upgrade_verified = False
            if not self._upgrade_one_batch():
                return upgraded_any
            upgraded_any = True
            if not self.last_upgrade_verified:
                # A closed dialog without a readable debit can count for this
                # batch, but cannot safely authorize another purchase.
                print("[Wall] Chưa đối soát được số dư; dừng nâng tiếp lượt này.")
                return True
            print("[Wall] Quét lại tài nguyên để nâng tiếp trước khi farm.")

    def _upgrade_one_batch(self) -> bool:
        """Try one batch using a fresh screenshot and the current wall price."""
        self._builder_list_open = False
        image = self.adb.screenshot()
        if image is None or image.shape[:2] != (900, 1600):
            if image is not None:
                self._position_cache.clear()
            return False
        resources = self.reader.read_home_resources(image)
        minimum = max(0, int(self.settings.get("wall_resource", 0)))
        reserve = max(0, int(self.settings.get("wall_reserve", 0)))
        if not any(resources.get(kind, 0) >= max(1, minimum)
                   and resources.get(kind, 0) > reserve
                   for kind in self._allowed_resources()):
            print(f"[Wall] Kho chưa đạt ngưỡng: {resources}.")
            return False

        if not self._builder_available(image):
            print("[Wall] Không thấy chân dung thợ thường rảnh; "
                  "đang là thợ thuê hoặc giao diện chưa rõ, bỏ qua nâng tường.")
            return False

        try:
            portrait = self._position_cache.get("builder")
            if portrait is None:
                return False
            builder_button = (portrait[0] + BUILDER_LIST_OFFSET[0],
                              portrait[1] + BUILDER_LIST_OFFSET[1])
            if not self.adb.tap(*builder_button, jitter=0, delay=0.15):
                return False
            self.last_interacted = True
            self._builder_list_open = True
            image = self.adb.screenshot()
            row = self._find_wall_row(image)
            for _ in range(9):
                if row is not None:
                    break
                if image is None:
                    return False
                rx, ry, rw, rh = LIST_REGION
                before = image[ry:ry + rh, rx:rx + rw].copy()
                self.adb.swipe(820, 590, 820, 250, 420)
                image = self.adb.screenshot()
                if image is None:
                    return False
                row = self._find_wall_row(image)
                if row is None and np.mean(cv2.absdiff(
                        before, image[ry:ry + rh, rx:rx + rw])) < 2.0:
                    break
            if row is None:
                print("[Wall] Không tìm thấy dòng Wall x trong danh sách thợ.")
                return False
            available_count = self._listed_wall_count(image, row)
            print(f"[Wall] Đã tìm thấy Wall x tại {row}.")
            if not self.adb.tap(*row, jitter=0, delay=0.2):
                return False
            self._builder_list_open = False
            image = self.adb.screenshot()
            upmore = self._find(T_UPMORE, image, UPMORE_REGION, .85)
            if available_count == 1:
                print("[Wall] Chỉ còn một viên; nâng trực tiếp viên đang chọn.")
            elif upmore is None:
                print("[Wall] Chọn Wall x nhưng không thấy Upgrade More.")
                return False
            else:
                if not self.adb.tap(*upmore, jitter=0, delay=0.2):
                    return False
                image = self.adb.screenshot()
                image, plus, minus = self._wait_for_group_controls(image)
                if plus is None or minus is None:
                    print("[Wall] Upgrade More chưa mở đúng chế độ Add/Remove Wall.")
                    return False

            image, unit = self._wait_for_costs(image)
            if unit is None:
                print("[Wall] Không đọc chắc chắn giá nâng một viên.")
                return False
            choice = self._choose_batch(resources, unit)
            if choice is None:
                print(f"[Wall] Chưa đủ vàng hoặc dầu tím cho một viên: {resources}, {unit}.")
                return False
            kind, count = choice
            if available_count is not None:
                count = min(count, available_count)
            for selected in range(2, count + 1):
                plus = self._add_wall_button(image)
                if plus is None:
                    print("[Wall] Không còn thấy nút Add Wall; dừng.")
                    return False
                if not self.adb.tap(plus[0], plus[1] - 40, jitter=0, delay=0.08):
                    return False
                image = self.adb.screenshot(use_cache=False)
                image, prices = self._wait_for_costs(
                    image, kind, unit[kind] * selected)
                if prices is None:
                    print(f"[Wall] Giá sau Add Wall không khớp {selected} viên; dừng.")
                    return False
            image = self.adb.screenshot(use_cache=False)
            price = self._read_costs(image)
            latest = self.reader.read_home_resources(image)
            if (price is None or price[kind] != count * unit[kind] or
                    latest.get(kind, 0) - reserve < price[kind]):
                print("[Wall] Giá hoặc số dư thay đổi trước khi xác nhận; dừng.")
                return False
            button = self._upgrade_button(kind, image)
            if button is None:
                print(f"[Wall] Không thấy nút nâng bằng {kind}.")
                return False
            print(f"[Wall] Chọn {count} viên × {unit[kind]:,} = {price[kind]:,} "
                  f"{kind}; kho {latest[kind]:,}.")
            if not self.adb.tap(button[0] - 65, button[1] + 10,
                                jitter=0, delay=0.2):
                return False
            image = self.adb.screenshot()
            if not self._confirm_upgrade(image, kind, latest[kind], price[kind]):
                return False
            self.walls_upgraded += count
            if self.last_upgrade_verified:
                print(f"[Wall] Đã nâng {count} viên bằng {kind}, chi {price[kind]:,}. "
                      f"Tổng phiên: {self.walls_upgraded} viên.")
            else:
                print(f"[Wall] Đã xác nhận nâng {count} viên bằng {kind}; "
                      f"OCR chưa đối soát được số dư. Tổng phiên: {self.walls_upgraded} viên.")
            return True
        except Exception as exc:
            print(f"[Wall] Lỗi xử lý nâng tường: {exc}")
            return False
        finally:
            try:
                self._close_panels()
            except Exception as exc:
                print(f"[Wall] Không đóng được bảng nâng tường: {exc}")

    def _allowed_resources(self) -> Tuple[str, ...]:
        if self.wall_type == "both":
            return ("gold", "elixir")
        if self.wall_type in ("gold", "elixir"):
            return (self.wall_type,)
        return ()

    def _builder_available(self, image: np.ndarray) -> bool:
        """The ordinary builder portrait is the authoritative Home indicator.

        The counter can show 1 while the remaining slot is a hireable Goblin
        Builder. The portrait changes in that state, so subtracting a fixed
        number from the counter incorrectly rejects a real 1/5 builder.
        """
        return self._find_cached("builder", T_BUILDER_AVAILABLE, image,
                                 BUILDER_ICON_REGION, .72,
                                 BUILDER_PORTRAIT_SIZE) is not None

    def _choose_batch(self, resources: dict, unit: dict) -> Optional[Tuple[str, int]]:
        reserve = max(0, int(self.settings.get("wall_reserve", 0)))
        minimum = max(0, int(self.settings.get("wall_resource", 0)))
        limit = max(1, min(100, int(self.settings.get("wall_max_batch", 50))))
        options = []
        for kind in self._allowed_resources():
            available, price = resources.get(kind, 0), unit.get(kind, 0)
            if price > 0 and available >= max(1, minimum):
                count = min(limit, (available - reserve) // price)
                if count > 0:
                    options.append((count, kind))
        if not options:
            return None
        count, kind = max(options)
        return kind, count

    def _read_costs(self, image: np.ndarray) -> Optional[dict]:
        if image is None:
            return None
        prices = {}
        for kind in ("gold", "elixir"):
            button = self._upgrade_button(kind, image)
            prices[kind] = 0
            if button is not None:
                dx, dy, width, height = COST_FROM_ICON[kind]
                region = (button[0] + dx, button[1] + dy, width, height)
                prices[kind] = self.reader.read_ui_number(
                    image, region, min_digits=4, small_text=True)
        return prices if any(prices.values()) else None

    def _upgrade_button(self, kind: str, image: np.ndarray):
        template = T_GOLD_UPGRADE if kind == "gold" else T_ELIXIR_UPGRADE
        return self._find_cached(f"upgrade_{kind}", template, image,
                                 WALL_CONTROL_REGION, .84, UPGRADE_ICON_SIZE)

    def _add_wall_button(self, image: np.ndarray):
        gold = self._upgrade_button("gold", image)
        if gold is None:
            return None
        # +1 is immediately left of Gold. +10, when present, is farther left.
        # Use this relationship to avoid pressing +10 after a layout change.
        region = (gold[0] - 324, WALL_CONTROL_REGION[1],
                  170, WALL_CONTROL_REGION[3])
        return self._find_cached("add_wall", T_ADD_WALL, image,
                                 region, .84, ADD_WALL_SIZE)

    def _wait_for_costs(self, image: np.ndarray, kind: Optional[str] = None,
                        expected: Optional[int] = None):
        """Allow the price animation to settle using fresh, bounded captures."""
        for attempt in range(4):
            if self.stop_event is not None and self.stop_event.is_set():
                return image, None
            prices = self._read_costs(image)
            if prices is not None:
                if kind is not None:
                    if prices.get(kind, 0) == expected:
                        return image, prices
                elif any(prices.get(resource, 0) > 0
                         for resource in self._allowed_resources()):
                    return image, prices
            if attempt < 3:
                image = self._next_wall_frame()
                if image is None:
                    return image, None
        return image, None

    def _wait_for_group_controls(self, image: np.ndarray):
        """Wait for Upgrade More's Add/Remove controls to finish appearing."""
        plus = minus = None
        for attempt in range(4):
            if self.stop_event is not None and self.stop_event.is_set():
                return image, None, None
            plus = self._add_wall_button(image)
            # Remove Wall is dimmed when just one wall is selected.
            minus = self._find(T_REMOVE_WALL, image, WALL_CONTROL_REGION, .60)
            if (plus is not None and minus is not None and
                    100 <= plus[0] - minus[0] <= 410 and
                    abs(plus[1] - minus[1]) <= 20):
                return image, plus, minus
            if attempt < 3:
                image = self._next_wall_frame()
                if image is None:
                    break
        return image, None, None

    def _next_wall_frame(self) -> Optional[np.ndarray]:
        if self.stop_event is None:
            time.sleep(.15)
        elif self.stop_event.wait(.15):
            return None
        return self.adb.screenshot(use_cache=False)

    def _find_wall_row(self, image: np.ndarray) -> Optional[Tuple[int, int]]:
        if image is None or image.shape[:2] != (900, 1600):
            return None
        label = self._find(T_WALL_LABEL, image, LIST_REGION, .90)
        if label is None:
            return None
        rx, ry, rw, rh = LIST_REGION
        left, top = max(rx, label[0] - 48), max(ry, label[1] - 22)
        right, bottom = min(rx + rw, label[0] + 48), min(ry + rh, label[1] + 22)
        word = self._find(T_WALL_WORD, image,
                          (left, top, right - left, bottom - top), .88)
        if (word is None or abs(word[1] - label[1]) > 8 or
                abs(word[0] - (label[0] - 8)) > 10):
            return None
        return (label[0] + 35, label[1])

    def _listed_wall_count(self, image: np.ndarray, row) -> Optional[int]:
        """Read the number after Wall x so the batch cannot exceed that row."""
        region = (row[0] - 3, row[1] - 14, 48, 28)
        count = self.reader.read_ui_number(image, region, min_digits=1, max_digits=3)
        if isinstance(count, (int, np.integer)) and 1 <= count <= 999:
            return int(count)
        return None

    def _find(self, template: str, image: np.ndarray, region, threshold):
        if image is None:
            return None
        return self.adb.find_template(template, threshold, image, region=region)

    def _find_cached(self, key: str, template: str, image: np.ndarray,
                     region: Tuple[int, int, int, int], threshold: float,
                     size: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Recheck a saved position on this frame, then scan the full region."""
        if image is None:
            return None
        if image.shape[:2] != (900, 1600):
            self._position_cache.clear()
            return None

        cached = self._position_cache.get(key)
        if cached is not None:
            x, y = cached
            width, height = size
            padding = 18
            rx, ry, rw, rh = region
            left = max(rx, x - width // 2 - padding)
            top = max(ry, y - height // 2 - padding)
            right = min(rx + rw, x + (width + 1) // 2 + padding)
            bottom = min(ry + rh, y + (height + 1) // 2 + padding)
            if right - left >= width and bottom - top >= height:
                point = self._find(template, image,
                                   (left, top, right - left, bottom - top),
                                   threshold)
                if (point is not None and abs(point[0] - x) <= padding and
                        abs(point[1] - y) <= padding):
                    self._position_cache[key] = (int(point[0]), int(point[1]))
                    return self._position_cache[key]

        point = self._find(template, image, region, threshold)
        if point is not None:
            self._position_cache[key] = (int(point[0]), int(point[1]))
            return self._position_cache[key]
        return None

    def _confirmation_button(self, image: np.ndarray) -> Optional[Tuple[int, int]]:
        """Use the saved Okay position only after the modal is verified again."""
        if image is None:
            return None
        if image.shape[:2] != (900, 1600):
            self._position_cache.clear()
            return None

        cached = self._position_cache.get("confirm")
        if cached is not None:
            x, y = cached
            region = (max(0, x - 140), max(0, y - 75),
                      min(1600, x + 140) - max(0, x - 140),
                      min(900, y + 75) - max(0, y - 75))
            point = find_confirmation_button(self.adb, image,
                                             WALL_CONFIRM_BUTTONS,
                                             region=region)
            if (point is not None and abs(point[0] - x) <= 25 and
                    abs(point[1] - y) <= 25):
                self._position_cache["confirm"] = point
                return point

        point = find_confirmation_button(self.adb, image, WALL_CONFIRM_BUTTONS)
        if point is not None:
            self._position_cache["confirm"] = point
        return point

    def _confirm_upgrade(self, image: np.ndarray, kind: str,
                         balance_before: int, expected_price: int) -> bool:
        """Accept Upgrade Walls, then verify the debit or visible Home return."""
        self.last_upgrade_verified = False
        for _ in range(4):
            okay = self._confirmation_button(image)
            if okay is not None:
                if not self.adb.tap(*okay, jitter=0, delay=0.2):
                    return False
                print("[Wall] Đã bấm Okay xác nhận Upgrade Walls.")
                break
            if self._is_gem_dialog(image):
                print("[Wall] Game yêu cầu Goblin Builder/Gems; hủy nâng tường.")
                return False
            time.sleep(0.4)
            image = self.adb.screenshot()
        else:
            print("[Wall] Không thấy hộp thoại xác nhận Upgrade Walls; không tính thành công.")
            return False

        spent = 0
        home_frames = 0
        for _ in range(12):
            image = self.adb.screenshot()
            if image is not None:
                if self._confirmation_button(image) is not None:
                    time.sleep(0.4)
                    continue
                if self._is_gem_dialog(image):
                    print("[Wall] Xác nhận dẫn tới hộp thoại Gems; hủy.")
                    return False
                after = self.reader.read_home_resources(image)
                remaining = after.get(kind, 0)
                spent = balance_before - remaining
                if spent == expected_price and (
                        remaining > 0 or self._builder_available(image)):
                    self.last_upgrade_verified = True
                    return True
                # During the closing animation the HUD can be dimmed and OCR
                # returns zero or an incomplete number. Keep polling instead
                # of declaring a completed purchase unsuccessful immediately.
                if (self._builder_available(image) and
                        self._find_cached("add_wall", T_ADD_WALL, image,
                                          ADD_REGION, .84, ADD_WALL_SIZE) is None):
                    home_frames += 1
            time.sleep(0.4)
        if home_frames >= 2:
            print(f"[Wall] Hộp thoại đã đóng và đã về Home; "
                  f"OCR chưa xác nhận số dư ({spent:,} / {expected_price:,}).")
            return True
        print("[Wall] Hộp thoại nâng tường chưa đóng về Home; không ghi nhận nâng.")
        return False

    @staticmethod
    def _is_gem_dialog(image: np.ndarray) -> bool:
        if image is None:
            return False
        patch = image[230:540, 650:1330]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        white = (hsv[:, :, 1] < 75) & (hsv[:, :, 2] > 175)
        if float(white.mean()) <= .38:
            return False
        # The video shows *two* green gem offers side by side. A normal wall
        # confirmation may also be light, but has a single confirm button.
        offers = cv2.cvtColor(image[455:625, 760:1410], cv2.COLOR_BGR2HSV)
        green = cv2.inRange(offers, (30, 80, 80), (85, 255, 255))
        _, _, stats, _ = cv2.connectedComponentsWithStats(green)
        buttons = []
        for x, y, w, h, area in stats[1:]:
            if w < 100 or h < 40 or area < 4000:
                continue
            # A green patch of village scenery can sit beside the single
            # Okay button. Gem offers are both on the modal's light panel.
            left, top = 760 + x, 455 + y
            backdrop = image[top - 60:top - 10,
                             left + int(w * .2):left + int(w * .8)]
            if backdrop.size == 0:
                continue
            backdrop_hsv = cv2.cvtColor(backdrop, cv2.COLOR_BGR2HSV)
            light = (backdrop_hsv[:, :, 1] < 75) & (backdrop_hsv[:, :, 2] > 175)
            if float(light.mean()) > .55:
                buttons.append((x, y))
        return any(abs(x1 - x2) >= 170 and abs(y1 - y2) <= 25
                   for x1, y1 in buttons for x2, y2 in buttons if x1 < x2)

    def _close_panels(self):
        # Only send Back for a gem prompt; Back on an idle home screen can open
        # the game's exit confirmation instead of cleaning up.
        image = self.adb.screenshot()
        if self._is_gem_dialog(image):
            self.adb.back()
            image = self.adb.screenshot()
        # If verification failed, cancel explicitly instead of tapping through
        # the modal and leaving the next farm tick on an obstructed screen.
        if self._confirmation_button(image) is not None:
            print("[Wall] Hủy hộp thoại nâng tường chưa được xác nhận.")
            self.adb.back()
            return
        if self._builder_list_open:
            self.adb.tap(1170, 700, jitter=0, delay=0.1)
            return
        if image is not None and (self._find(T_UPMORE, image, UPMORE_REGION, .85) or
                                  self._add_wall_button(image)):
            self.adb.tap(800, 455, jitter=0, delay=0.1)
