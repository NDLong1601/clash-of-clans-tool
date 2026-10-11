#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CocMagic — modules/hero_module.py
Quản lý Heroes: detect trạng thái và deploy trong trận.
"""

import time
import os
import glob
from functools import lru_cache
from typing import Optional, List, Tuple

import cv2
import numpy as np

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.troop_vision import detect_bar_cards


# ─── Cấu hình Hero ──────────────────────────────────────────
# Tọa độ icon hero trên thanh quân dưới màn hình (1600x900)
# Thứ tự từ trái → phải trong giao diện attack

HERO_ICONS: dict = {
    # key: template path, (tap_x, tap_y khi thả hero vào field)
    # Template dùng để detect hero READY (không mờ)
    "king":        {"tpl": config.asset("king.png"),        "icon_tpl": config.asset("iconking.png")},
    "queen":       {"tpl": config.asset("queen.png"),       "icon_tpl": config.asset("iconqueen.png")},
    "warden":      {"tpl": config.asset("warden.png"),      "icon_tpl": config.asset("iconwarden.png")},
    "royal_champ": {"tpl": config.asset("royal.png"),       "icon_tpl": config.asset("iconroyal.png")},
    "prince":      {"tpl": config.asset("prince.png"),      "icon_tpl": config.asset("iconprince.png")},
    "luke":        {"tpl": config.asset("luke.png"),        "icon_tpl": config.asset("iconduke.png")},
}

# Vùng scan thanh hero bên dưới (tìm icon hero sẵn sàng)
HERO_BAR_REGION = (0, 780, 1600, 120)   # (x, y, w, h) — phần dưới màn hình


@lru_cache(maxsize=1)
def _portrait_templates():
    templates = {}
    for name in HERO_ICONS:
        paths = [config.asset(f"hero_portraits/{name}.png")]
        paths.extend(glob.glob(config.asset(f"hero_portraits/{name}_*.png")))
        for path in paths:
            if not os.path.exists(path):
                continue
            portrait = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if portrait is None:
                continue
            templates.setdefault(name, []).extend(
                cv2.resize(portrait, None, fx=scale, fy=scale)
                for scale in (.9, 1.0, 1.1))
    return templates


class HeroModule:
    """Phát hiện và deploy heroes trong trận."""

    def __init__(self, adb: ADBController, settings: dict):
        self.adb      = adb
        self.settings = settings

    def get_enabled_heroes(self) -> List[str]:
        """Trả về list tên hero đã bật trong settings."""
        enabled = []
        for name in HERO_ICONS:
            if self.settings.get(f"use_{name}", False):
                enabled.append(name)
        return enabled

    @staticmethod
    def portrait_point(icon_x: int, icon_y: int) -> Tuple[int, int]:
        """Avoid the Warden's mode selector and siege arrows at the card foot."""
        return icon_x, icon_y - 50

    @staticmethod
    def has_deployed_health(image, icon_x: int, icon_y: int) -> bool:
        """Recognize a framed health strip, not grass behind an idle portrait."""
        if image is None or image.shape[:2] != (900, 1600):
            return False
        roi = image[icon_y - 140:icon_y - 100, icon_x - 40:icon_x + 40]
        if roi.shape[:2] != (40, 80):
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        dark_rows = np.flatnonzero(np.mean(hsv[:, 5:-5, 2] < 95, axis=1) > .8)
        color = (((hsv[:, :, 0] >= 32) & (hsv[:, :, 0] <= 90)) |
                 (hsv[:, :, 0] < 12) | (hsv[:, :, 0] > 170)) & (
                     hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 95)
        return any(8 <= bottom - top <= 18 and
                   float(np.max(color[top + 1:bottom, 5:-5].mean(axis=1))) >= .12
                   for top in dark_rows for bottom in dark_rows if bottom > top)

    def find_ready_heroes(self, screenshot=None,
                          enabled_only: bool = True,
                          cards=None) -> List[Tuple[str, int, int]]:
        """
        Quét màn hình tìm hero đang sẵn sàng (không mờ/sleeping).
        Trả về list [(hero_name, cx, cy), ...].
        """
        img     = screenshot if screenshot is not None else self.adb.screenshot()
        enabled = self.get_enabled_heroes() if enabled_only else HERO_ICONS
        ready   = []

        for name in enabled:
            info = HERO_ICONS[name]
            # Thử với template icon nhỏ trước
            pos = self.adb.find_template(
                info["icon_tpl"],
                threshold=config.LOOSE_THRESHOLD,
                screenshot=img,
                region=HERO_BAR_REGION
            )
            if pos is None:
                pos = self.adb.find_template(
                    info["tpl"],
                    threshold=config.LOOSE_THRESHOLD,
                    screenshot=img,
                    region=HERO_BAR_REGION
                )
            if pos:
                ready.append((name, pos[0], pos[1]))

        cards = detect_bar_cards(img) if cards is None else cards
        # Matching a small icon returns its artwork center, not the card center.
        # Normalize the tap/health-strip coordinates to the actual card frame.
        ready = [(name, *min(cards, key=lambda p: abs(p[0] - x)))
                 if cards and min(abs(p[0] - x) for p in cards) <= 55 else (name, x, y)
                 for name, x, y in ready]
        if img is not None and img.shape[:2] == (900, 1600):
            for x, y in cards:
                if any(abs(x - hx) <= 50 for _, hx, _ in ready):
                    continue
                roi = cv2.cvtColor(img[755:890, x - 57:x + 57], cv2.COLOR_BGR2GRAY)
                scores = []
                for name, templates in _portrait_templates().items():
                    if name not in enabled or any(h[0] == name for h in ready):
                        continue
                    score = max(float(cv2.minMaxLoc(cv2.matchTemplate(
                        roi, template, cv2.TM_CCOEFF_NORMED))[1]) for template in templates)
                    scores.append((score, name))
                scores.sort(reverse=True)
                if scores and scores[0][0] >= .78 and (
                        len(scores) == 1 or scores[0][0] - scores[1][0] >= .06):
                    ready.append((scores[0][1], x, y))
        return ready

    def deploy_heroes(self, drop_positions: List[Tuple[int, int]], screenshot=None):
        """
        Deploy tất cả hero sẵn sàng vào các vị trí drop_positions.
        drop_positions: list [(x,y)] — vị trí thả hero trên battlefield.
        """
        if not drop_positions:
            return

        ready = self.find_ready_heroes(screenshot)
        if not ready:
            print("[Hero] Không có hero sẵn sàng")
            return

        print(f"[Hero] Deploy {len(ready)} hero(es): {[h[0] for h in ready]}")

        for i, (name, icon_x, icon_y) in enumerate(ready):
            # Chọn vị trí drop theo thứ tự (lặp vòng nếu ít điểm)
            drop_x, drop_y = drop_positions[i % len(drop_positions)]

            # 1. Tap icon hero để chọn
            self.adb.tap(*self.portrait_point(icon_x, icon_y), jitter=3)
            time.sleep(0.3)

            # 2. Tap vị trí field để thả
            self.adb.tap(drop_x, drop_y, jitter=10)
            time.sleep(config.DELAY_BETWEEN_HEROES)
            print(f"  [Hero] {name} → ({drop_x},{drop_y})")

    @staticmethod
    def warden_health_fraction(screenshot, icon_x: int, icon_y: int) -> Optional[float]:
        """Read the green health strip above the deployed Warden portrait."""
        if screenshot is None or screenshot.shape[:2] != (900, 1600):
            return None
        roi = screenshot[icon_y - 124:icon_y - 109,
                         icon_x - 40:icon_x + 40]
        if roi.shape != (15, 80, 3):
            return None
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        green = ((hsv[:, :, 0] >= 32) & (hsv[:, :, 0] <= 90) &
                 (hsv[:, :, 1] >= 85) & (hsv[:, :, 2] >= 75))
        # Pick the strongest horizontal strip; the portrait frame may shift
        # several pixels between emulator themes.
        coverage = float(np.max(green[:, 5:-5].mean(axis=1)))
        if coverage >= .04:
            return coverage
        purple_frame = ((hsv[:, :, 0] >= 115) & (hsv[:, :, 0] <= 170) &
                        (hsv[:, :, 1] >= 80))
        return 0.0 if float(np.mean(purple_frame)) >= .15 else None

    def activate_ability(self, screenshot=None, exclude=None):
        """
        Kích hoạt ability của tất cả hero khi có thể.
        (Tìm nút ability xuất hiện trong trận)
        """
        # Ability thường xuất hiện dưới dạng nút tròn cạnh icon hero
        # Khi hero đang trên field, ability button sẽ hiển thị
        # Đơn giản: tap lại vào vùng hero bar để activate
        img = screenshot if screenshot is not None else self.adb.screenshot()
        if img is None:
            return
        ready = self.find_ready_heroes(img)
        for name, ix, iy in ready:
            if exclude and name in exclude:
                continue
            # Double-tap icon = activate ability (trong trận)
            self.adb.tap(*self.portrait_point(ix, iy), jitter=3)
            time.sleep(0.2)
