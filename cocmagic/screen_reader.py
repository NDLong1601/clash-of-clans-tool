#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CocMagic — screen_reader.py
Đọc tài nguyên (Gold, Elixir, Dark Elixir) bằng digit template matching.
Tái sử dụng digit_templates từ assets XMagic.
"""

import os
from collections import Counter
from typing import Optional, Tuple, List

import numpy as np
import cv2

from cocmagic import config
from cocmagic.adb_controller import ADBController


# ─── Vung toa do tai nguyen tren man hinh 1600x900 ────────
# Vung Available Loot tren man hinh tim tran (scout screen)
LOOT_REGIONS = {
    "gold":   (70, 125, 200, 40),
    "elixir": (70, 175, 200, 40),
    "dark":   (70, 225, 200, 40),
}

# Vung tai nguyen tai nha (home screen) -- resource bar BEN PHAI man hinh 1600x900
HOME_REGIONS = {
    "gold":   (1150, 10, 340, 60),   # gold bar
    "elixir": (1150, 85, 340, 60),   # elixir bar
    "dark":   (1150, 155, 340, 60),  # dark elixir bar
}


class ScreenReader:
    """Đọc tài nguyên và thông tin từ màn hình bằng Supercell-Magic font OCR."""

    def __init__(self, adb: ADBController):
        self.adb         = adb
        self._digit_tpls = {}          # cache: digit → cv2 img
        self._font_rendered = {}       # Supercell-Magic rendered templates
        self._digit_dir  = config.asset("digit_templates")
        self._load_font_templates()
        self._load_digit_templates()

    # ─── Load templates ─────────────────────────────────────

    def _load_font_templates(self):
        """Pre-render các chữ số 0-9 bằng font Supercell-Magic chuẩn CoC."""
        from PIL import Image, ImageFont, ImageDraw
        font_path = config.asset("Supercell-Magic.otf")
        if not os.path.exists(font_path):
            font_path = os.path.join(config.BASE_DIR, "assets", "Supercell-Magic.otf")
        if not os.path.exists(font_path):
            return

        try:
            font = ImageFont.truetype(font_path, 22)
            for ch in "0123456789":
                im = Image.new("L", (50, 50), 0)
                draw = ImageDraw.Draw(im)
                draw.text((10, 10), ch, font=font, fill=255)
                arr = np.array(im)
                pts = cv2.findNonZero(arr)
                if pts is not None:
                    x, y, w, h = cv2.boundingRect(pts)
                    self._font_rendered[ch] = arr[y:y+h, x:x+w]
            if len(self._font_rendered) == 10:
                print("[ScreenReader] Loaded Supercell-Magic font OCR templates OK")
        except Exception as e:
            print(f"[ScreenReader] WARN: Could not load Supercell font: {e}")

    def _load_digit_templates(self):
        """Fallback: load 0-9 templates từ assets/digit_templates/."""
        if not os.path.isdir(self._digit_dir):
            return
        for i in range(10):
            digit_str = str(i)
            sub_dir = os.path.join(self._digit_dir, digit_str)
            if os.path.isdir(sub_dir):
                pngs = sorted([f for f in os.listdir(sub_dir) if f.endswith(".png")])
                if pngs:
                    path = os.path.join(sub_dir, pngs[0])
                    tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                    if tpl is not None:
                        self._digit_tpls[digit_str] = tpl
            elif os.path.exists(sub_dir + ".png"):
                tpl = cv2.imread(sub_dir + ".png", cv2.IMREAD_GRAYSCALE)
                if tpl is not None:
                    self._digit_tpls[digit_str] = tpl

    # ─── Public API ─────────────────────────────────────────

    def read_loot(self, screenshot: Optional[np.ndarray] = None) -> dict:
        """
        Đọc số loot (gold, elixir, dark) từ màn hình tìm trận (scouting screen).
        Trả về dict {"gold": int, "elixir": int, "dark": int}.
        """
        img = screenshot if screenshot is not None else self.adb.screenshot()
        if img is None:
            return {"gold": 0, "elixir": 0, "dark": 0}

        result = {}
        for key, region in LOOT_REGIONS.items():
            result[key] = self._read_scout_number(img, region)
        return result

    def _read_scout_number(self, img_bgr: np.ndarray, region: Tuple[int, int, int, int]) -> int:
        """Đọc số loot tại màn hình do thám bằng Supercell-Magic font matching."""
        rx, ry, rw, rh = region
        h_img, w_img = img_bgr.shape[:2]
        rx = max(0, rx); ry = max(0, ry)
        rw = min(rw, w_img - rx); rh = min(rh, h_img - ry)
        if rw <= 0 or rh <= 0:
            return 0

        crop = img_bgr[ry:ry+rh, rx:rx+rw]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY)

        if self._font_rendered:
            contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            boxes = []
            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                if 14 <= h <= 25 and 5 <= w <= 22 and x >= 8:
                    boxes.append((x, y, w, h))
            boxes.sort(key=lambda b: b[0])

            valid_boxes = []
            last_end = None
            for b in boxes:
                if last_end is None:
                    valid_boxes.append(b)
                    last_end = b[0] + b[2]
                else:
                    if b[0] - last_end <= 18:
                        valid_boxes.append(b)
                        last_end = b[0] + b[2]
                    else:
                        break

            digits = []
            for x, y, w, h in valid_boxes:
                dcrop = th[y:y+h, x:x+w]
                best_ch = None
                best_val = -1
                for ch, tpl in self._font_rendered.items():
                    tpl_res = cv2.resize(tpl, (w, h), interpolation=cv2.INTER_AREA)
                    v = float(cv2.matchTemplate(dcrop, tpl_res, cv2.TM_CCOEFF_NORMED)[0, 0])
                    if v > best_val:
                        best_val = v
                        best_ch = ch
                if best_ch is not None:
                    digits.append(best_ch)
            if digits:
                try:
                    return int(''.join(digits))
                except ValueError:
                    pass

        # Fallback: multi-scale template matching
        return self._read_number_in_region(img_bgr, region, threshold=0.65, cut_left=False)

    def read_home_resources(self, screenshot: Optional[np.ndarray] = None) -> dict:
        """
        Đọc tài nguyên tại màn hình chính (home).
        Trả về dict {"gold": int, "elixir": int, "dark": int}.
        """
        img = screenshot if screenshot is not None else self.adb.screenshot()
        if img is None:
            return {"gold": 0, "elixir": 0, "dark": 0}

        # Home bars use white glyphs with a black outline. The generic loot
        # matcher can return zero for this larger UI font, so segment its
        # white character cores in tight, icon-free crops instead.
        regions = {
            "gold": (1330, 25, 205, 45),
            "elixir": (1330, 105, 205, 50),
            "dark": (1350, 209, 185, 30),
        }
        return {key: self.read_ui_number(img, region, min_digits=4)
                for key, region in regions.items()}

    def read_ui_number(self, image: np.ndarray, region: Tuple[int, int, int, int],
                       min_digits: int = 1, max_digits: int = 10,
                       small_text: bool = False) -> int:
        """Read isolated white CoC digits; return 0 when segmentation is uncertain."""
        if image is None or not self._font_rendered:
            return 0
        x, y, w, h = region
        roi = image[y:y+h, x:x+w]
        if roi.size == 0:
            return 0
        if small_text:
            return self._read_small_ui_number(roi, min_digits, max_digits)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (0, 0, 175), (179, 100, 255))
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        boxes = sorted(((bx, by, bw, bh) for bx, by, bw, bh, area in stats[1:]
                        if 13 <= bh <= 29 and 5 <= bw <= 25 and area >= 40),
                       key=lambda item: item[0])
        if not min_digits <= len(boxes) <= max_digits:
            return 0
        digits = []
        for bx, by, bw, bh in boxes:
            glyph = mask[by:by+bh, bx:bx+bw]
            scores = []
            for digit, template in self._font_rendered.items():
                scaled = cv2.resize(template, (bw, bh), interpolation=cv2.INTER_LINEAR)
                _, binary = cv2.threshold(scaled, 100, 255, cv2.THRESH_BINARY)
                score = float(cv2.matchTemplate(glyph, binary,
                                                cv2.TM_CCOEFF_NORMED)[0, 0])
                scores.append((score, digit))
            score, digit = max(scores)
            if score < 0.38:
                return 0
            digits.append(digit)
        return int("".join(digits))

    def _read_small_ui_number(self, roi: np.ndarray,
                              min_digits: int, max_digits: int) -> int:
        """Read grouped prices on bright buttons without losing small glyphs.

        The normal HUD mask joins white price digits to the button background.
        Try brighter masks, split touching digit cores, and require agreement
        between masks on a complete number with three-digit thousands groups.
        """
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        candidates = []
        for brightness in (175, 185, 190, 195, 200, 205, 210):
            mask = cv2.inRange(hsv, (0, 0, brightness), (179, 100, 255))
            _, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
            boxes = sorted((tuple(int(v) for v in (bx, by, bw, bh))
                            for bx, by, bw, bh, area in stats[1:]
                            if 8 <= bh <= 29 and 3 <= bw <= 65 and area >= 20))
            separated = []
            for bx, by, bw, bh in boxes:
                if bw <= 1.45 * bh:
                    separated.append((bx, by, bw, bh))
                    continue
                if bw > 2.6 * bh:
                    break
                glyph = mask[by:by + bh, bx:bx + bw]
                projection = np.count_nonzero(glyph, axis=0)
                start, end = int(bw * .4), int(bw * .6) + 1
                cut = start + int(np.argmin(projection[start:end]))
                for left, right in ((0, cut), (cut + 1, bw)):
                    points = cv2.findNonZero(glyph[:, left:right])
                    if points is None:
                        break
                    gx, gy, gw, gh = cv2.boundingRect(points)
                    separated.append((bx + left + gx, by + gy, gw, gh))
                else:
                    continue
                break
            else:
                if not min_digits <= len(separated) <= max_digits:
                    continue
                bottoms = [by + bh for _, by, _, bh in separated]
                if max(bottoms) - min(bottoms) > 3:
                    continue
                gaps = {index: separated[index][0] -
                        (separated[index - 1][0] + separated[index - 1][2])
                        for index in range(1, len(separated))}
                separators = set(range(len(separated) - 3, 0, -3))
                spaces = [gap for index, gap in gaps.items() if index in separators]
                within = [gap for index, gap in gaps.items() if index not in separators]
                if (not spaces or min(spaces) <= max(within, default=0) + 1 or
                        min(gaps.values()) < 0 or
                        max(spaces) > np.median([box[3] for box in separated]) * 1.2):
                    continue
                digits = []
                for bx, by, bw, bh in separated:
                    if not (3 <= bw <= 1.45 * bh and 8 <= bh <= 29):
                        break
                    glyph = mask[by:by + bh, bx:bx + bw]
                    scores = []
                    for digit, template in self._font_rendered.items():
                        scaled = cv2.resize(template, (bw, bh),
                                            interpolation=cv2.INTER_LINEAR)
                        _, binary = cv2.threshold(scaled, 100, 255, cv2.THRESH_BINARY)
                        score = float(cv2.matchTemplate(glyph, binary,
                                                        cv2.TM_CCOEFF_NORMED)[0, 0])
                        scores.append((score, digit))
                    score, digit = max(scores)
                    if score < .45:
                        break
                    digits.append(digit)
                else:
                    # Missing/merged zeros must not turn 10 000 000 into 1 000 000.
                    if digits[0] != "0":
                        candidates.append(int("".join(digits)))
        votes = Counter(candidates)
        agreed = [value for value, count in votes.items() if count >= 2]
        return agreed[0] if len(agreed) == 1 else 0

    # ─── Core digit OCR ─────────────────────────────────────

    def _read_number_in_region(
        self,
        img_bgr: np.ndarray,
        region: Tuple[int, int, int, int],
        threshold: float = 0.70,
        cut_left: bool = True,
    ) -> int:
        """
        Crop vung region tu img, nhan dien cac chu so bang multi-scale template matching.
        Tra ve so nguyen doc duoc.
        """
        if not self._digit_tpls:
            return 0

        rx, ry, rw, rh = region
        h_img, w_img = img_bgr.shape[:2]
        rx = max(0, rx); ry = max(0, ry)
        rw = min(rw, w_img - rx); rh = min(rh, h_img - ry)
        if rw <= 0 or rh <= 0:
            return 0

        crop = img_bgr[ry:ry+rh, rx:rx+rw]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        # Preprocessing: nguong de lay so (mau vang/trang nen sang, nen toi)
        _, gray_thresh = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)

        if cut_left:
            # Bo qua 40% ben trai (icon + thanh trang thai tai home)
            left_cut = int(rw * 0.40)
            gray_right = gray_thresh[:, left_cut:]
        else:
            gray_right = gray_thresh

        SCALES = [1.2, 1.4, 1.6, 1.8]  # Scale pho bien cho font CoC

        best_found: List[Tuple[int, str]] = []
        best_score = 0.0
        best_digits = 0

        for scale in SCALES:
            found_at_scale: List[Tuple[int, str]] = []
            score_sum = 0.0

            for digit_char, tpl_orig in self._digit_tpls.items():
                new_h = max(1, int(tpl_orig.shape[0] * scale))
                new_w = max(1, int(tpl_orig.shape[1] * scale))

                if gray_right.shape[0] < new_h or gray_right.shape[1] < new_w:
                    continue

                tpl_scaled = cv2.resize(tpl_orig, (new_w, new_h),
                                        interpolation=cv2.INTER_LINEAR)
                _, tpl_thresh = cv2.threshold(tpl_scaled, 127, 255, cv2.THRESH_BINARY)

                res = cv2.matchTemplate(gray_right, tpl_thresh, cv2.TM_CCOEFF_NORMED)
                locs = np.where(res >= threshold)
                xs = locs[1].tolist()

                # NMS theo chieu ngang -- dung window nho hon de khong merge cac chu so
                # CoC dung khoang cach rong giua nhom 3 so: "5 142 898"
                NMS_WIN = max(2, new_w // 2)  # window bang 1/2 chieu rong chu so
                used = [False] * len(xs)
                for i, x in enumerate(xs):
                    if used[i]:
                        continue
                    used[i] = True
                    score_at_x = float(res[locs[0][i], x])
                    for j in range(i + 1, len(xs)):
                        if not used[j] and abs(xs[j] - x) < NMS_WIN:
                            used[j] = True
                    found_at_scale.append((x, digit_char))
                    score_sum += score_at_x

            n = len(found_at_scale)
            # Chon scale co nhieu chu so nhat (va hop le <= 10 chu so)
            if 1 <= n <= 10 and (n > best_digits or (n == best_digits and score_sum > best_score)):
                best_score  = score_sum
                best_digits = n
                best_found  = found_at_scale

        if not best_found:
            return 0

        best_found.sort(key=lambda t: t[0])
        number_str = "".join(ch for _, ch in best_found)
        try:
            return int(number_str)
        except ValueError:
            return 0

    # ─── Helper ─────────────────────────────────────────────

    def loot_meets_threshold(self, loot: dict, settings: dict) -> bool:
        """Gold hoặc Elixir đạt ngưỡng; Dark Elixir là điều kiện riêng nếu bật."""
        min_g = settings.get("min_gold",   0)
        min_e = settings.get("min_elixir", 0)
        min_d = settings.get("min_dark",   0)
        resource_checks = []
        if min_g > 0:
            resource_checks.append(loot.get("gold", 0) >= min_g)
        if min_e > 0:
            resource_checks.append(loot.get("elixir", 0) >= min_e)
        main_resources_ok = any(resource_checks) if resource_checks else True
        return main_resources_ok and (min_d <= 0 or loot.get("dark", 0) >= min_d)

    def format_loot(self, loot: dict) -> str:
        """Format loot dict để in ra terminal."""
        g = loot.get("gold",   0)
        e = loot.get("elixir", 0)
        d = loot.get("dark",   0)
        return f"Gold={g:,}  Elixir={e:,}  Dark={d:,}"
