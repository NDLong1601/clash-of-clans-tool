"""Read cached troop-card artwork and the small white count badge."""

from functools import lru_cache
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cocmagic import config


def detect_bar_cards(image: np.ndarray) -> list[tuple[int, int]]:
    """Combine horizontal frames and vertical borders, including gray cards."""
    if image is None or image.shape[:2] != (900, 1600):
        return []
    gray = cv2.cvtColor(image[735:900], cv2.COLOR_BGR2GRAY)
    horizontal = []
    for row in range(2, 160):
        for mask in (image[735 + row, :1520, 0] > 70, gray[row, :1520] > 110,
                     gray[row, :1520] > 155):
            transitions = np.diff(np.r_[False, mask, False].astype(np.int8))
            centers = [(int(start) + int(end)) // 2
                       for start, end in zip(np.flatnonzero(transitions == 1),
                                             np.flatnonzero(transitions == -1))
                       if start >= 40 and 60 <= end - start <= 135]
            for index, center in enumerate(centers):
                chain = [center]
                for other in centers[index + 1:]:
                    if 100 <= other - chain[-1] <= 150:
                        chain.append(other)
                if len(chain) > len(horizontal):
                    horizontal = chain
    dx = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0))
    dy = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1))
    support = np.mean(dx[12:145] > 90, axis=0)
    transitions = np.diff(np.r_[False, support > .55, False].astype(np.int8))
    borders = [round((start + end - 1) / 2)
               for start, end in zip(np.flatnonzero(transitions == 1),
                                     np.flatnonzero(transitions == -1))
               if start >= 40 and end <= 1530]
    candidates = [(x, 4.5) for x in horizontal]
    for left in borders:
        for right in borders:
            if not 96 <= right - left <= 130:
                continue
            top = float(np.max(np.mean(dy[:40, left + 5:right - 5] > 65, axis=1)))
            score = float(support[left] + support[right]) + 2 * top
            if top >= .55 and score >= 3.3:
                candidates.append(((left + right) // 2, score))
    merged = []
    for candidate in sorted(candidates):
        if merged and candidate[0] - merged[-1][0] < 18:
            if candidate[1] > merged[-1][1]:
                merged[-1] = candidate
        else:
            merged.append(candidate)
    paths = []
    for index, (x, score) in enumerate(merged):
        options = [paths[prior] for prior in range(index)
                   if 100 <= x - merged[prior][0] <= 150]
        previous_score, chain = max(options, key=lambda item: item[0], default=(0, []))
        paths.append((previous_score + score, chain + [x]))
    chain = max(paths, key=lambda item: item[0], default=(0, []))[1]
    return [(x, 840) for x in chain] if len(chain) >= 2 else []


@lru_cache(maxsize=1)
def _electro_template() -> np.ndarray:
    path = config.asset("TC_Hoi/Task_General/Use Troop/Main/use_main_use_electro_dragon.png")
    template = cv2.imread(path)
    if template is None:
        raise FileNotFoundError(path)
    return template


@lru_cache(maxsize=1)
def _digit_templates() -> dict[str, np.ndarray]:
    font = ImageFont.truetype(config.asset("Supercell-Magic.otf"), 22)
    templates = {}
    for digit in "0123456789":
        canvas = Image.new("L", (50, 50), 0)
        ImageDraw.Draw(canvas).text((10, 10), digit, font=font, fill=255)
        array = np.asarray(canvas)
        pixels = cv2.findNonZero(array)
        x, y, width, height = cv2.boundingRect(pixels)
        templates[digit] = array[y:y + height, x:x + width]
    return templates


@lru_cache(maxsize=1)
def _count_prefix_template() -> np.ndarray:
    font = ImageFont.truetype(config.asset("Supercell-Magic.otf"), 22)
    canvas = Image.new("L", (50, 50), 0)
    ImageDraw.Draw(canvas).text((10, 10), "x", font=font, fill=255)
    pixels = np.asarray(canvas)
    x, y, width, height = cv2.boundingRect(cv2.findNonZero(pixels))
    return pixels[y:y + height, x:x + width]


def is_electro_card(image: np.ndarray, x: int, y: int) -> bool:
    """Match the art, excluding the count badge and the card border."""
    if image is None or image.shape[:2] != (900, 1600):
        return False
    roi = image[max(0, y - 85):min(900, y + 40), max(0, x - 52):min(1600, x + 52)]
    template = _electro_template()
    best = 0.0
    for width, height in ((70, 55), (75, 60), (70, 70),
                          (65, 55), (78, 62), (80, 65), (90, 73)):
        if height > roi.shape[0] or width > roi.shape[1]:
            continue
        scaled = cv2.resize(template, (width, height), interpolation=cv2.INTER_AREA)
        best = max(best, float(cv2.minMaxLoc(
            cv2.matchTemplate(roi, scaled, cv2.TM_CCOEFF_NORMED))[1]))
    return best >= .60


@lru_cache(maxsize=1)
def _siege_templates() -> tuple[tuple[np.ndarray, float], ...]:
    """Cache scaled siege portraits used on the battle deployment bar."""
    templates = []
    for index in range(1, 19):
        image = cv2.imread(config.asset(f"machine/{index}.png"))
        if image is None:
            continue
        for width, height in ((65, 65), (70, 70), (75, 75),
                              (80, 75), (85, 80), (90, 85), (95, 90)):
            if index <= 9:
                templates.append((cv2.resize(image, (width, height),
                                             interpolation=cv2.INTER_AREA), .49))
        # The alternate portraits are wider crops. Squashing these into a
        # square loses the identifying artwork of the selected siege card.
        for scale in (.85, .95, 1.0, 1.05, 1.1):
            templates.append((cv2.resize(image, None, fx=scale, fy=scale,
                                        interpolation=cv2.INTER_AREA), .60))
    return tuple(templates)


def is_siege_card(image: np.ndarray, x: int, y: int) -> bool:
    """Identify a siege card by its art, wherever it appears on the bar."""
    if image is None or image.shape[:2] != (900, 1600):
        return False
    roi = image[y - 80:y + 55, x - 57:x + 57]
    if roi.shape[:2] != (135, 114):
        return False
    for template, threshold in _siege_templates():
        if template.shape[0] > roi.shape[0] or template.shape[1] > roi.shape[1]:
            continue
        score = float(cv2.minMaxLoc(cv2.matchTemplate(
            roi, template, cv2.TM_CCOEFF_NORMED))[1])
        if score >= threshold:
            return True
    return False


def _count_glyphs(image: np.ndarray, x: int, y: int):
    """Extract the complete count run independently of the selected frame."""
    if image is None or image.shape[:2] != (900, 1600):
        return None
    roi = image[max(0, y - 105):min(900, y - 55),
                max(0, x - 10):min(1600, x + 65)]
    if roi.shape[0] < 35 or roi.shape[1] < 42:
        return None
    white = cv2.inRange(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV),
                        (0, 0, 175), (179, 110, 255))
    # Keep the location of vertical card borders: erasing their tall columns
    # leaves small rounded corners next to the count on selected cards.
    border_columns = np.flatnonzero(np.mean(white > 0, axis=0) > .75)
    white[:, border_columns] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(white)
    glyphs = []
    templates = _digit_templates()
    for index in range(1, count):
        bx, by, width, height, area = map(int, stats[index])
        if not (0 <= by <= 40 and 4 <= width <= 22 and 11 <= height <= 29 and area >= 30):
            continue
        glyph = np.where(labels[by:by + height, bx:bx + width] == index, 255, 0).astype(np.uint8)
        matches = sorted((float(cv2.matchTemplate(
            glyph, cv2.resize(template, (width, height)),
            cv2.TM_CCOEFF_NORMED)[0, 0]), digit)
            for digit, template in templates.items())
        best_score, best_digit = matches[-1]
        prefix_score = float(cv2.matchTemplate(
            glyph, cv2.resize(_count_prefix_template(), (width, height)),
            cv2.TM_CCOEFF_NORMED)[0, 0])
        glyphs.append((bx, by, width, height, best_score, best_digit,
                       best_score - matches[-2][0], prefix_score))
    glyphs.sort()
    # Recognize the complete digit run on the right of the x badge. Never
    # discard an uncertain leading digit and silently turn x10 into x0.
    prefixes = [g for g in glyphs if g[7] >= .70]
    if not prefixes:
        # At some card scales x touches the first digit. Find the x artwork
        # directly rather than treating the joined x5 as one unreadable glyph.
        for width, height in ((16, 15), (17, 16), (18, 17), (19, 18), (20, 19)):
            result = cv2.matchTemplate(white, cv2.resize(_count_prefix_template(),
                                      (width, height)), cv2.TM_CCOEFF_NORMED)
            _, score, _, (bx, by) = cv2.minMaxLoc(result)
            if score >= .80:
                prefixes.append((bx, by, width, height, 0, "", 0, score))
        if not prefixes:
            return None
    prefix = max(prefixes, key=lambda g: g[7])
    # The rounded white card frame can touch the top of a count digit. Cut
    # around the x baseline before segmenting digits so that this frame does
    # not swallow the entire number into one connected component.
    top = max(0, prefix[1] + prefix[3] - 22)
    bottom = min(white.shape[0], prefix[1] + prefix[3] + 2)
    start = prefix[0] + prefix[2] - 1
    band = white[top:bottom, start:].copy()
    frame_columns = (np.mean(band > 0, axis=0) > .85) & (band[-1] > 0) & (
        np.arange(band.shape[1]) >= band.shape[1] - 10)
    band[:, frame_columns] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(band)
    glyphs = []
    for index in range(1, count):
        bx, by, width, height, area = map(int, stats[index])
        if not (4 <= width <= 22 and 11 <= height <= 24 and area >= 30):
            right = start + bx + width
            if (by == 0 and width <= 8 and
                    np.any((border_columns >= right) & (border_columns <= right + 1))):
                # This top-anchored fragment adjoins the erased vertical frame,
                # not a damaged digit. Keep rejecting incomplete digits that
                # have no such border evidence, including the leading 1 in x10.
                continue
            if (bx > 1 and bx < band.shape[1] - 10 and height >= 8 and area >= 12
                    and abs(by + top + height - prefix[1] - prefix[3]) <= 5):
                # An incomplete leading digit must invalidate the whole run.
                return None
            continue
        glyph = np.where(labels[by:by + height, bx:bx + width] == index, 255, 0).astype(np.uint8)
        matches = sorted((float(cv2.matchTemplate(
            glyph, cv2.resize(template, (width, height)),
            cv2.TM_CCOEFF_NORMED)[0, 0]), digit)
            for digit, template in templates.items())
        best_score, digit = matches[-1]
        glyphs.append((bx + start, by + top, width, height, best_score,
                       digit, best_score - matches[-2][0], glyph))
    glyphs.sort(key=lambda g: g[0])
    digits = [g for g in glyphs if g[0] >= prefix[0] + prefix[2] - 1
              and abs(g[1] + g[3] - prefix[1] - prefix[3]) <= 5]
    if not 1 <= len(digits) <= 3:
        return None
    if any(b[0] - a[0] - a[2] > 8 or abs((b[1] + b[3]) - (a[1] + a[3])) > 5
           for a, b in zip(digits, digits[1:])):
        return None
    return digits


def read_card_count(image: np.ndarray, x: int, y: int) -> Optional[int]:
    """Return the complete count, or None when any digit is uncertain."""
    digits = _count_glyphs(image, x, y)
    if digits is None or any(g[4] < .50 or g[6] < .08 for g in digits):
        return None
    return int("".join(g[5] for g in digits))


def count_badge_changed(before: np.ndarray, after: np.ndarray, x: int, y: int) -> bool:
    """Compare digit shapes, excluding border/background and position changes."""
    a, b = _count_glyphs(before, x, y), _count_glyphs(after, x, y)
    if a is None or b is None:
        return False
    if len(a) != len(b):
        return True
    for old, new in zip(a, b):
        mask = cv2.resize(old[7], (new[2], new[3]))
        if float(cv2.matchTemplate(mask, new[7], cv2.TM_CCOEFF_NORMED)[0, 0]) < .78:
            return True
    return False
