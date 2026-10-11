"""Conservative, calibrated screen/bonus observations; no input in this module."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import itertools
import json
import re
import time

import cv2
import numpy as np

from cocmagic import config
from cocmagic.camera_controller import measure_motion
from cocmagic.ui_dialogs import find_inactivity_reload


class Village(str, Enum):
    MAIN = "main"
    BUILDER = "builder"


class ScreenKind(str, Enum):
    MAIN_HOME = "main_home"
    BUILDER_HOME = "builder_home"
    ATTACK_MENU = "attack_menu"
    BATTLE = "battle"
    RESULT = "result"
    MODAL = "modal"
    LOADING = "loading"
    UNKNOWN = "unknown"


class StarBonusState(str, Enum):
    AVAILABLE = "available"
    CLAIMABLE = "claimable"
    COMPLETE = "complete"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Capture:
    image: np.ndarray | None = field(repr=False)
    sequence: int
    captured_at: float
    revision: int


@dataclass(frozen=True)
class ScreenObservation:
    kind: ScreenKind
    reason: str
    village: Village | None = None
    panel: str | None = None
    points: dict = field(default_factory=dict)
    language: str | None = None


@dataclass(frozen=True)
class StarBonusObservation:
    state: StarBonusState
    captured_at: float
    reason: str
    region: tuple[int, int, int, int] | None = None
    progress: tuple[int, int] | None = None
    captures: tuple[int, ...] = ()


class BonusProgressOCR:
    """Optional strict x/y glyph read. Uncertain glyphs return None, never 0."""

    def __init__(self):
        from PIL import Image, ImageDraw, ImageFont

        self.glyphs = {}
        path = Path(config.asset("Supercell-Magic.otf"))
        if not path.exists():
            return
        font = ImageFont.truetype(str(path), 24)
        for char in "0123456789/":
            canvas = Image.new("L", (60, 60))
            ImageDraw.Draw(canvas).text((8, 4), char, font=font, fill=255)
            mask = np.where(np.asarray(canvas) > 175, 255, 0).astype(np.uint8)
            points = cv2.findNonZero(mask)
            if points is not None:
                x, y, w, h = cv2.boundingRect(points)
                self.glyphs[char] = mask[y : y + h, x : x + w]

    def __call__(self, roi):
        if not self.glyphs or roi is None or roi.shape[:2] != (70, 175):
            return None
        # Badge counter sits above Attack: ignore the axes/text below and the
        # star artwork at the left. OCR is not a fallback star detector.
        hsv = cv2.cvtColor(roi[:38, 42:160], cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (0, 0, 185), (179, 90, 255))
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        boxes = sorted(
            (x, y, w, h)
            for x, y, w, h, area in stats[1:]
            if 9 <= h <= 35 and 3 <= w <= 30 and area >= 18
        )
        if not 3 <= len(boxes) <= 7:
            return None
        text = ""
        for x, y, w, h in boxes:
            glyph = mask[y : y + h, x : x + w]
            scores = []
            for char, template in self.glyphs.items():
                scaled = cv2.resize(template, (w, h), interpolation=cv2.INTER_AREA)
                binary = np.where(scaled > 100, 255, 0).astype(np.uint8)
                score = float(
                    cv2.matchTemplate(glyph, binary, cv2.TM_CCOEFF_NORMED)[0, 0]
                )
                scores.append((score, char))
            scores.sort(reverse=True)
            if scores[0][0] < 0.65 or scores[0][0] - scores[1][0] < 0.07:
                return None
            text += scores[0][1]
        return text if re.fullmatch(r"\d+/\d+", text) else None


class BuilderScreenReader:
    """1600x900 English native HUD. Uncalibrated sizes/languages fail closed.

    The asset manifest records actual content/source, including generated and
    transformed-video evidence which still requires native live verification.
    Map objects are searched anew at several scales, never cached coordinates.
    """

    bonus_region = (20, 690, 175, 70)

    def __init__(self, adb=None, asset_dir=None):
        self.adb = adb
        self.asset_dir = Path(asset_dir or config.asset("dual_village"))
        self.spec = json.loads(
            (self.asset_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self._templates = {}
        self._sequence = itertools.count(1)

    def capture(self):
        # Cache bypass is part of the capture contract, not a caller option.
        image = self.adb.screenshot(use_cache=False)
        return Capture(
            image, next(self._sequence), time.monotonic(), self.adb.camera_revision
        )

    def match(self, name, image, *, region=None, scales=None):
        if image is None or image.shape != (900, 1600, 3):
            return None
        spec = self.spec["anchors"].get(name)
        if spec is None:
            return None
        template = self._templates.get(name)
        if template is None:
            template = cv2.imread(str(self.asset_dir / spec["path"]))
            if template is None:
                return None
            self._templates[name] = template
        x, y, w, h = region or spec["region"]
        roi = image[y : y + h, x : x + w]
        if not roi.size:
            return None
        best = None
        for scale in scales or spec.get("scales", [1.0]):
            tw, th = round(template.shape[1] * scale), round(template.shape[0] * scale)
            if min(tw, th) < 8 or tw > roi.shape[1] or th > roi.shape[0]:
                continue
            resized = cv2.resize(template, (tw, th), interpolation=cv2.INTER_AREA)
            score_map = cv2.matchTemplate(roi, resized, cv2.TM_CCOEFF_NORMED)
            _, score, _, pos = cv2.minMaxLoc(score_map)
            if np.isfinite(score) and score >= spec.get("threshold", 0.90):
                if best is None or score > best[0]:
                    best = (score, (x + pos[0] + tw // 2, y + pos[1] + th // 2))
        return best[1] if best else None

    @staticmethod
    def _panel_blocks_home(image):
        # Blocking geometry only: this never authorizes a button tap.
        center = cv2.cvtColor(image[240:540, 440:1160], cv2.COLOR_BGR2HSV)
        if np.mean((center[:, :, 1] < 65) & (center[:, :, 2] >= 65)) > 0.83:
            return True
        hsv = cv2.cvtColor(image[120:680, 200:1400], cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (0, 0, 65), (179, 65, 250))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return any(
            w > 650 and h > 230 and cv2.contourArea(c) > 0.88 * w * h
            for c in contours
            for _, _, w, h in [cv2.boundingRect(c)]
        )

    def classify(self, image):
        if image is None or image.shape != (900, 1600, 3) or image.dtype != np.uint8:
            return ScreenObservation(
                ScreenKind.UNKNOWN, "Ảnh thiếu hoặc resolution chưa hiệu chỉnh"
            )
        reload = find_inactivity_reload(image)
        if reload:
            return ScreenObservation(
                ScreenKind.MODAL,
                "Anyone there + RELOAD GAME",
                panel="inactivity",
                points={"reload": reload},
                language="en",
            )
        if self.match("connection_title", image):
            return ScreenObservation(
                ScreenKind.MODAL, "Connection lost; chưa được phép input"
            )
        hits = {}

        def hit(name):
            if name not in hits:
                hits[name] = self.match(name, image)
            return hits[name]

        master, worker = hit("master_builder"), hit("main_builder")
        builder_attack = hit("builder_attack") or (
            hit("home_attack_label") if master else None
        )
        main_attack = (
            hit("main_attack")
            or hit("main_attack_current")
            or (hit("home_attack_label") if worker else None)
        )
        builder = master is not None and builder_attack is not None
        main = worker is not None and main_attack is not None
        village = (
            Village.BUILDER
            if builder and not main
            else Village.MAIN
            if main and not builder
            else None
        )
        # Known blocking screens precede Home even if the HUD shows behind them.
        cart_title = hit("cart_title")
        cart_close = hit("cart_close")
        if cart_title and cart_close:
            points = {"close": cart_close}
            for key in (
                "cart_collect",
                "cart_disabled",
                "cart_empty",
                "cart_defending",
            ):
                point = hit(key)
                if point:
                    points[key] = point
            # Enabled/disabled buttons share lettering and shape. Correlation
            # alone cannot establish whether collection is possible.
            for key in ("cart_collect", "cart_disabled"):
                if key not in points:
                    continue
                px, py = points[key]
                button = cv2.cvtColor(
                    image[py - 25 : py + 25, px - 80 : px + 80], cv2.COLOR_BGR2HSV
                )
                green = np.mean(
                    (button[:, :, 0] > 30)
                    & (button[:, :, 0] < 90)
                    & (button[:, :, 1] > 90)
                )
                grey = np.mean(button[:, :, 1] < 45)
                if (key == "cart_collect" and green < 0.45) or (
                    key == "cart_disabled" and grey < 0.60
                ):
                    points.pop(key)
            return ScreenObservation(
                ScreenKind.MODAL,
                "Đúng title và nút đóng xe",
                Village.BUILDER,
                "cart",
                points,
                "en",
            )
        reward_title, reward_star, reward_button = (
            hit("reward_title"),
            hit("reward_star"),
            hit("reward_button"),
        )
        blue = (
            cv2.inRange(
                cv2.cvtColor(image[170:700, 430:1170], cv2.COLOR_BGR2HSV),
                (95, 140, 130),
                (135, 255, 255),
            ).mean()
            / 255
        )
        if reward_title and reward_star and blue > 0.40:
            # A main Star Bonus panel must never become builder CLAIMABLE.
            points = (
                {"claim": reward_button}
                if reward_button and builder and not main
                else {}
            )
            return ScreenObservation(
                ScreenKind.MODAL,
                "Title/sao/bảng thưởng; cần nút và builder HUD",
                village,
                "star_reward",
                points,
                "en",
            )
        if hit("builder_menu_title") and hit("builder_find"):
            return ScreenObservation(
                ScreenKind.ATTACK_MENU,
                "Start Attack + Find Now + close",
                Village.BUILDER,
                language="en",
            )
        if hit("main_menu_title") and hit("main_find"):
            return ScreenObservation(
                ScreenKind.ATTACK_MENU,
                "Multiplayer + Find a Match",
                Village.MAIN,
                language="en",
            )
        if hit("result_return") and (hit("result_title") or hit("result_loot")):
            return ScreenObservation(
                ScreenKind.RESULT, "Result banner/loot + Return Home"
            )
        if hit("battle_end") and (hit("battle_damage") or hit("battle_loot")):
            return ScreenObservation(ScreenKind.BATTLE, "Battle HUD + kết thúc trận")
        if hit("loading_cloud") and not builder and not main:
            return ScreenObservation(ScreenKind.LOADING, "Mẫu mây chuyển cảnh")
        if hit("connection_title") or self._panel_blocks_home(image):
            return ScreenObservation(
                ScreenKind.MODAL, "Modal chặn hoặc bảng chưa có handler"
            )
        common = (
            hit("chat")
            and hit("settings")
            and (hit("profile") or hit("profile_border"))
        )
        if common and village:
            kind = (
                ScreenKind.BUILDER_HOME
                if village == Village.BUILDER
                else ScreenKind.MAIN_HOME
            )
            return ScreenObservation(
                kind,
                "HUD chung + Attack riêng + chân dung thợ đúng làng",
                village,
                points={"attack": builder_attack or main_attack},
                language="en",
            )
        return ScreenObservation(
            ScreenKind.UNKNOWN, "Anchor thiếu/mâu thuẫn; không suy làng từ màu nền"
        )

    def home_is_clear(self, image, village):
        """Fast fresh-frame guard used inside camera's settling loop."""
        if image is None or image.shape != (900, 1600, 3):
            return False
        if self._panel_blocks_home(image):
            return False
        if self.match("cart_title", image) or self.match("connection_title", image):
            return False
        blue = (
            cv2.inRange(
                cv2.cvtColor(image[170:700, 430:1170], cv2.COLOR_BGR2HSV),
                (95, 140, 130),
                (135, 255, 255),
            ).mean()
            / 255
        )
        if blue > 0.40:
            return False
        portrait = "master_builder" if village == Village.BUILDER else "main_builder"
        if village == Village.BUILDER:
            attack = self.match("builder_attack", image) or self.match(
                "home_attack_label", image
            )
        else:
            attack = (
                self.match("main_attack", image)
                or self.match("main_attack_current", image)
                or self.match("home_attack_label", image)
            )
        profile = self.match("profile", image) or self.match("profile_border", image)
        return bool(
            attack
            and profile
            and all(self.match(name, image) for name in (portrait, "chat", "settings"))
        )

    def map_target(self, image, name):
        # Camera's home input mask also excludes buttons and resource HUD.
        from cocmagic.camera_controller import ScreenSpace

        names = [name] + self.spec.get("variants", {}).get(name, [])
        for candidate in names:
            point = self.match(candidate, image)
            if point and ScreenSpace.map_point(point, "home"):
                return point
        return None


class StarBonusReader:
    def __init__(self, reader, *, progress_ocr=None, minimum_interval=0.15):
        self.reader = reader
        self.progress_ocr = (
            progress_ocr if progress_ocr is not None else BonusProgressOCR()
        )
        self.minimum_interval = max(0.12, minimum_interval)
        self.previous = None

    def reset(self):
        self.previous = None

    def observe(self, capture):
        screen = self.reader.classify(capture.image)
        old = self.previous
        self.previous = None

        def result(state, reason, progress=None, ids=None):
            return StarBonusObservation(
                state,
                capture.captured_at,
                reason,
                self.reader.bonus_region,
                progress,
                ids or (capture.sequence,),
            )

        if (
            screen.panel == "star_reward"
            and screen.village == Village.BUILDER
            and screen.points.get("claim")
        ):
            return result(
                StarBonusState.CLAIMABLE, "Bảng thưởng builder có nút nhận đúng"
            )
        if screen.kind != ScreenKind.BUILDER_HOME:
            return result(
                StarBonusState.UNKNOWN,
                "Chưa xác nhận builder Home rõ, không modal/loading",
            )
        image = capture.image
        star = self.reader.match(
            "bonus_star", image, region=self.reader.bonus_region
        ) or self.reader.match(
            "bonus_star_native", image, region=self.reader.bonus_region
        )
        clear_absence = self.reader.match("builder_no_star_button", image) is not None
        progress = None
        if self.progress_ocr:
            try:
                x, y, w, h = self.reader.bonus_region
                text = str(self.progress_ocr(image[y : y + h, x : x + w]))
                found = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text)
                if found:
                    progress = tuple(map(int, found.groups()))
            except Exception:
                pass  # OCR is optional and never establishes COMPLETE.
        if progress is not None and (progress[1] <= 0 or progress[0] > progress[1]):
            return result(StarBonusState.UNKNOWN, "OCR tiến độ mâu thuẫn", progress)
        # Bright flying effects/occlusion outside the anchored star also block
        # negative evidence. A no-star button alone is not sufficient.
        x, y, w, h = self.reader.bonus_region
        hsv = cv2.cvtColor(image[y : y + h, x : x + w], cv2.COLOR_BGR2HSV)
        transient = np.mean((hsv[:, :, 1] < 60) & (hsv[:, :, 2] > 215)) > 0.045
        above = hsv[:25]
        # Natural dark map shadows above an intact Attack button aren't a
        # covering panel. Require a broad dark band, rather than 8% scattered
        # dark scenery pixels (native GĐ5 Home after battle exposed this).
        occluded = (
            np.mean(np.mean(above[:, :, 2] < 15, axis=1) > 0.65) > 0.45
            or np.mean((above[:, :, 1] < 12) & (above[:, :, 2] < 200)) > 0.25
        )
        if not star and (
            not clear_absence or transient or occluded or progress is not None
        ):
            return result(
                StarBonusState.UNKNOWN,
                "Vùng sao/nút bị che, hiệu ứng hoặc dấu hiệu mâu thuẫn",
                progress,
            )
        self.previous = (capture, bool(star))
        if old is None or old[1] != bool(star):
            return result(
                StarBonusState.UNKNOWN, "Chờ ảnh mới độc lập thứ hai", progress
            )
        before = old[0]
        if (
            capture.sequence <= before.sequence
            or image is before.image
            or capture.captured_at - before.captured_at < self.minimum_interval
            or capture.revision != before.revision
        ):
            self.previous = None
            return result(
                StarBonusState.UNKNOWN, "Ảnh lặp/quá gần hoặc camera đổi", progress
            )
        motion = measure_motion(before.image, image, "home")
        roi1 = before.image[y : y + h, x : x + w].astype(np.int16)
        delta = np.abs(roi1 - image[y : y + h, x : x + w]).mean()
        if not motion.valid or motion.changed or delta > 5:
            self.previous = None
            return result(StarBonusState.UNKNOWN, "Ảnh/vùng sao chưa ổn định", progress)
        return result(
            StarBonusState.AVAILABLE if star else StarBonusState.COMPLETE,
            "Sao còn trên Home"
            if star
            else "Hai ảnh Home mới ổn định, nút rõ và không sao",
            progress,
            (before.sequence, capture.sequence),
        )
