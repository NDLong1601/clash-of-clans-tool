"""Builder HUD/army observations. Card lifecycle is independent of main x0 logic.

The native English 1600x900 profile is deliberately explicit. Missing artwork,
camp labels, or ability receipts remain unknown rather than guessed successful.
"""

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
import cv2
import numpy as np

from cocmagic import config
from cocmagic.builder_screen_reader import (
    BuilderScreenReader,
    ScreenKind,
    ScreenObservation,
    Village,
)
from cocmagic.camera_controller import ScreenSpace


class SlotState(str, Enum):
    UNDEPLOYED = "undeployed"
    DEPLOYED = "deployed"
    DEAD = "dead"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class AbilityState(str, Enum):
    READY = "ready"
    USED = "used"
    CHARGING = "charging"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BuilderSlot:
    key: str
    kind: str
    role: str
    point: tuple[int, int]
    box: tuple[int, int, int, int]
    state: SlotState
    ability: AbilityState = AbilityState.UNKNOWN
    count: int | None = None
    health: float | None = None
    remove: tuple[int, int] | None = None
    selected: bool = False


@dataclass(frozen=True)
class ArmyObservation:
    slots: tuple[BuilderSlot, ...] = ()
    valid: bool = False
    reason: str = "Thanh quân chưa rõ"
    choice: tuple[int, int] | None = None
    empty: bool = False
    complete: bool = False


@dataclass(frozen=True)
class BattleObservation:
    valid: bool
    preparing: bool = False
    reason: str = ""


class BuilderBattleReader(BuilderScreenReader):
    def __init__(self, adb=None):
        super().__init__(adb)
        directory = Path(config.asset("dual_village/builder"))
        self.art = {p.stem: cv2.imread(str(p)) for p in directory.glob("*.png")}

    def locate_ui(
        self, name, image, region, threshold=0.89, scales=(1.0,), grayscale=False
    ):
        template = self.art.get(name)
        if image is None or image.shape != (900, 1600, 3) or template is None:
            return None
        x, y, w, h = region
        roi = image[y : y + h, x : x + w]
        if grayscale:
            roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        best = (threshold, None)
        for scale in scales:
            t = cv2.resize(template, None, fx=scale, fy=scale)
            if t.shape[0] > h or t.shape[1] > w:
                continue
            _, score, _, pos = cv2.minMaxLoc(
                cv2.matchTemplate(roi, t, cv2.TM_CCOEFF_NORMED)
            )
            if np.isfinite(score) and score >= best[0]:
                best = (
                    score,
                    (x + pos[0] + t.shape[1] // 2, y + pos[1] + t.shape[0] // 2),
                )
        return best[1]

    def map_target(self, image, name):
        if name == "cart_object":
            candidate = self.locate_ui(
                "cart_native_gd5",
                image,
                (190, 115, 1210, 585),
                threshold=0.78,
                scales=(0.65, 0.8, 1.0, 1.2, 1.4, 1.65),
            )
            if candidate and ScreenSpace.map_point(candidate, "home"):
                return candidate
        point = super().map_target(image, name)
        return point

    def classify(self, image):
        screen = super().classify(image)
        # Recovery/rewards/cart precede HUD still visible behind an overlay.
        if screen.kind == ScreenKind.MODAL and (
            screen.panel or screen.reason.startswith("Connection lost")
        ):
            return self._cart_defense(image, screen)
        if image is not None and image.shape == (900, 1600, 3):
            result_title = self.locate_ui(
                "builder_result_title", image, (500, 270, 600, 150), threshold=0.88
            )
            result_return = self.locate_ui(
                "builder_result_return", image, (510, 650, 600, 210), threshold=0.91
            )
            if result_title and result_return:
                return ScreenObservation(
                    ScreenKind.RESULT,
                    "Builder total damage + Return Home",
                    Village.BUILDER,
                    "builder_result",
                    {"return": result_return},
                    "en",
                )
            title = self.locate_ui("army_title", image, (400, 75, 800, 130))
            close = self.locate_ui("army_close", image, (1260, 70, 260, 160))
            if (
                title
                and close
                and self.locate_ui("starting", image, (120, 180, 500, 65))
            ):
                return ScreenObservation(
                    ScreenKind.MODAL,
                    "Choose Army + Starting + close",
                    Village.BUILDER,
                    "builder_army",
                    {"close": close},
                    "en",
                )
            battle = self.battle(image, _screen=screen)
            if battle.valid:
                return ScreenObservation(
                    ScreenKind.BATTLE, battle.reason, Village.BUILDER, language="en"
                )
        return screen

    def _cart_defense(self, image, screen):
        if screen.panel == "cart":
            defending = self.locate_ui(
                "cart_defending_native", image, (620, 145, 420, 115), threshold=0.91
            )
            if defending:
                screen = replace(
                    screen, points={**screen.points, "cart_defending": defending}
                )
        return screen

    def battle(self, image, *, _screen=None):
        base = _screen if _screen is not None else super().classify(image)
        if base.kind == ScreenKind.MODAL:
            return BattleObservation(
                False, reason="Modal chặn HUD builder; không gửi input trận"
            )
        defender = self.locate_ui("defender", image, (50, 5, 190, 65))
        attacker = self.locate_ui("attacker", image, (1340, 5, 230, 65))
        starts = self.locate_ui(
            "battle_starts", image, (640, 5, 340, 70), grayscale=True
        )
        ends = self.locate_ui(
            "battle_ends", image, (640, 5, 340, 70), threshold=0.80, grayscale=True
        )
        if defender and attacker and (starts or ends):
            return BattleObservation(
                True, bool(starts), "Builder defender/attacker + timer heading"
            )
        return BattleObservation(
            False, reason="Không đủ HUD builder; không dùng damage 100% làm result"
        )

    @staticmethod
    def rectangles(image, region, *, min_height=100):
        x, y, w, h = region
        roi = image[y : y + h, x : x + w]
        edges = cv2.Canny(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), 45, 120)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for c in contours:
            px, py, cw, ch = cv2.boundingRect(c)
            if 85 <= cw <= 130 and min_height <= ch <= 195:
                box = (x + px, y + py, cw, ch)
                if not any(abs(box[0] - b[0]) < 12 for b in boxes):
                    boxes.append(box)
                else:
                    i = next(i for i, b in enumerate(boxes) if abs(box[0] - b[0]) < 12)
                    if cw * ch > boxes[i][2] * boxes[i][3]:
                        boxes[i] = box
        return sorted(boxes)

    def portrait(self, image, box):
        x, y, w, h = box
        roi = cv2.cvtColor(image[y : y + h, x : x + w], cv2.COLOR_BGR2GRAY)
        scores = []
        for name in (
            "baby_dragon",
            "baby_dragon_survivor",
            "battle_machine",
            "battle_machine_active",
            "battle_copter",
            "battle_machine_charged",
            "battle_machine_charging",
            "battle_machine_cooldown",
            "battle_machine_low_health",
            "battle_copter_charged",
            "battle_copter_charging",
            "battle_machine_sweep",
            "battle_machine_menu",
            "raged_barbarian",
            "boxer_giant",
            "bomber",
            "cannon_cart",
            "sneaky_archer",
            "beta_minion",
            "night_witch",
        ):
            kind = (
                "battle_machine"
                if name.startswith("battle_machine")
                else "battle_copter"
                if name.startswith("battle_copter")
                else "baby_dragon"
                if name.startswith("baby_dragon")
                else name
            )
            template = self.art.get(name)
            if template is None:
                continue
            template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            for scale in (0.85, 1.0, 1.15, 1.3, 1.45):
                t = cv2.resize(template, None, fx=scale, fy=scale)
                if t.shape[0] > h or t.shape[1] > w:
                    continue
                score = float(
                    cv2.minMaxLoc(cv2.matchTemplate(roi, t, cv2.TM_CCOEFF_NORMED))[1]
                )
                scores.append((score, kind))
        scores.sort(reverse=True)
        if (
            scores
            and scores[0][0] >= 0.63
            and (
                len(scores) < 2
                or scores[0][0]
                - next(
                    (score for score, kind in scores[1:] if kind != scores[0][1]), 0.0
                )
                > 0.08
            )
        ):
            return scores[0][1].replace("_active", "")
        return "unknown"

    def read_army(self, image):
        screen = self.classify(image)
        if screen.panel != "builder_army":
            return ArmyObservation(reason="Không có Choose Army xác nhận")
        divider = self.locate_ui("reinforcements", image, (800, 180, 640, 65))
        if not divider:
            return ArmyObservation(reason="Không đọc được nhóm tiếp viện")
        slots = []
        empty = False
        for box in self.rectangles(image, (140, 245, 1280, 185), min_height=140):
            x, y, w, h = box
            kind = self.portrait(image, box)
            remove = self.locate_ui(
                "baby_remove", image, (x + w - 45, y + h - 55, 45, 55), threshold=0.87
            )
            if not remove:
                empty = True  # Unlabelled placeholder is not authorization to tap.
                continue
            role = (
                "hero"
                if kind in ("battle_machine", "battle_copter")
                else ("reinforcement" if x > divider[0] - 140 else "primary")
            )
            slots.append(
                BuilderSlot(
                    f"{role}:{x}",
                    kind,
                    role,
                    (x + w // 2, y + h // 2),
                    box,
                    SlotState.UNDEPLOYED,
                    remove=remove,
                )
            )
        choice = self.locate_ui(
            "baby_choice",
            image,
            (140, 540, 1280, 280),
            threshold=0.77,
            scales=(1.0, 1.1),
        )
        if choice:
            px, py = choice
            hsv = cv2.cvtColor(
                image[py - 20 : py + 20, px - 25 : px + 25], cv2.COLOR_BGR2HSV
            )
            if np.mean(hsv[:, :, 1] > 70) < 0.35:
                choice = None  # gray/unavailable/unopened troop
        troops = [s for s in slots if s.role != "hero"]
        complete = bool(
            self.locate_ui("starting_ready", image, (140, 190, 65, 60))
            and self.locate_ui("starting_ready", image, (1090, 190, 65, 60))
        )
        return ArmyObservation(
            tuple(slots),
            bool(troops) or choice is not None,
            "Choose Army đã đọc",
            choice,
            empty,
            complete,
        )

    def camp_number(self, image, x, w):
        roi = image[704:775, x : x + min(w, 60)]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = ((hsv[:, :, 1] < 60) & (hsv[:, :, 2] > 195)).astype(np.uint8) * 255
        scores = []
        for i in range(1, 9):
            t = self.art.get(f"camp_{i}")
            if t is None:
                continue
            th = cv2.cvtColor(t, cv2.COLOR_BGR2HSV)
            binary = ((th[:, :, 1] < 60) & (th[:, :, 2] > 195)).astype(np.uint8) * 255
            _, score, _, pos = cv2.minMaxLoc(
                cv2.matchTemplate(mask, binary, cv2.TM_CCOEFF_NORMED)
            )
            scores.append((score, i, pos[1] + 704))
        scores.sort(reverse=True)
        return (
            (scores[0][1], scores[0][2])
            if scores and scores[0][0] > 0.75 and scores[0][0] - scores[1][0] > 0.05
            else (None, None)
        )

    def read_menu_army(self, image):
        screen = self.classify(image)
        if screen.kind != ScreenKind.ATTACK_MENU or screen.village != Village.BUILDER:
            return ArmyObservation(reason="Không có menu builder mới")
        slots = []
        for index, box in enumerate(
            self.rectangles(image, (250, 330, 715, 130), min_height=70)
        ):
            x, y, w, h = box
            kind = self.portrait(image, box)
            hero = kind in ("battle_machine", "battle_copter")
            count = (
                1
                if not hero
                and self.locate_ui(
                    "menu_count_one", image, (x, y, w, 35), threshold=0.85
                )
                else None
            )
            slots.append(
                BuilderSlot(
                    f"menu:{index}",
                    kind,
                    "hero" if hero else "troop",
                    (x + w // 2, y + h // 2),
                    box,
                    SlotState.UNDEPLOYED,
                    count=count,
                )
            )
        troops = [s for s in slots if s.role == "troop"]
        valid = bool(troops) and all(s.kind != "unknown" for s in slots)
        return ArmyObservation(
            tuple(slots),
            valid,
            "Đọc lại quân ở menu" if valid else "Quân ở menu chưa rõ",
        )

    def read_bar(self, image):
        if not self.battle(image).valid:
            return ArmyObservation(reason="Không có HUD trận builder")
        # Find frames from the current image; no assumed hero offset/card count.
        boxes = self.rectangles(image, (75, 700, 1440, 198))
        # The white cooldown sweep can join the hero frame to the map in Canny.
        # Locate its native portrait again across the *whole* current bar; never
        # borrow the previous battle's hero coordinate or assume a first slot.
        for name in (
            "battle_machine",
            "battle_machine_active",
            "battle_machine_charging",
            "battle_machine_cooldown",
            "battle_machine_sweep",
            "battle_copter",
            "battle_copter_charging",
        ):
            point = self.locate_ui(
                name,
                image,
                (75, 728, 1440, 162),
                threshold=0.82,
                scales=(0.85, 1.0, 1.15),
                grayscale=True,
            )
            if point and not any(
                abs(point[0] - (x + w // 2)) < 30 for x, _, w, _ in boxes
            ):
                x = max(75, point[0] - 56)
                if self.camp_number(image, x, 112)[0] is None:
                    boxes.append((x, 700, 112, 190))
        boxes.sort()
        slots = []
        for raw in boxes:
            x, _, w, _ = raw
            box = (x, 700, w, 190)
            kind = self.portrait(image, box)
            if kind == "unknown":
                # Dashed placeholders/empty space must not become active troops.
                roi = image[775:870, x + 5 : x + w - 5]
                if np.std(roi) < 18:
                    continue
                slots.append(
                    BuilderSlot(
                        f"unknown:{x}",
                        kind,
                        "unknown",
                        (x + w // 2, 810),
                        box,
                        SlotState.UNKNOWN,
                    )
                )
                continue
            hero = kind in ("battle_machine", "battle_copter")
            number, label_y = (
                self.camp_number(image, x, w) if not hero else (None, None)
            )
            if not hero and number is None:
                slots.append(
                    BuilderSlot(
                        f"unknown:{x}",
                        kind,
                        "troop",
                        (x + w // 2, 810),
                        box,
                        SlotState.UNKNOWN,
                    )
                )
                continue
            roi = image[778:843, x + 8 : x + w - 8]
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            dead = float(np.mean(hsv[:, :, 1] > 65)) < 0.12
            # Selected cards rise slightly; deployed cards rise by a full header.
            health = (
                image[747:771, x + 6 : x + w - 6]
                if not hero
                else image[710:728, x + 6 : x + w - 6]
            )
            hh = cv2.cvtColor(health, cv2.COLOR_BGR2HSV)
            green = (
                (hh[:, :, 0] > 28)
                & (hh[:, :, 0] < 90)
                & (hh[:, :, 1] > 120)
                & (hh[:, :, 2] > 110)
            )
            health_pixels = (
                (hh[:, :, 1] > (60 if hero else 120))
                & (hh[:, :, 2] > 110)
                & ((hh[:, :, 0] < 90) | (hh[:, :, 0] > 170))
            )
            # The numeric camp label moves up by exactly one header height
            # after deployment. Unraised stage-two survivors can show a green
            # health preview at y747; color alone would falsely mark them used.
            if hero:
                # Color behind an unraised portrait can be grass. The native
                # health frame has two long horizontal edges at its HUD height.
                border = cv2.cvtColor(
                    image[707:733, x + 3 : x + w - 3], cv2.COLOR_BGR2GRAY
                )
                rows = (
                    np.where(cv2.Canny(border, 30, 80).mean(axis=1) / 255 > 0.40)[0]
                    + 707
                )
                framed = any(rows < 718) and any(rows > 724)
                deployed = bool(framed and np.mean(health_pixels) > 0.015)
            else:
                deployed = label_y < 725
            if hero and deployed:
                dead = False  # white skill cooldown can desaturate a living portrait
            # After a one-shot ability the raised top is dark; green health
            # still proves deployment. In stage2 survivor health is at y780.
            purple = image[
                715 if deployed else 740 : 735 if deployed else 765, x + 42 : x + w - 4
            ]
            pp = cv2.cvtColor(purple, cv2.COLOR_BGR2HSV)
            ready = (
                float(
                    np.mean(
                        (pp[:, :, 0] > 125) & (pp[:, :, 0] < 165) & (pp[:, :, 1] > 100)
                    )
                )
                > 0.45
            )
            ability = AbilityState.READY if ready else AbilityState.USED
            if hero:
                # Builder heroes recharge. White cooldown veil is a separate
                # observation; elapsed time alone never makes a hero ready.
                charge = cv2.cvtColor(
                    image[691:711, x + 5 : x + w - 5], cv2.COLOR_BGR2HSV
                )
                charged = (
                    np.mean(
                        (charge[:, :, 0] > 125)
                        & (charge[:, :, 0] < 165)
                        & (charge[:, :, 1] > 100)
                    )
                    > 0.10
                )
                veil = np.mean((hsv[:, :, 1] < 55) & (hsv[:, :, 2] > 140)) > 0.50
                ability = (
                    AbilityState.READY
                    if deployed and charged and not veil
                    else AbilityState.CHARGING
                )
            state = (
                SlotState.DEAD
                if dead
                else SlotState.DEPLOYED
                if deployed
                else SlotState.UNDEPLOYED
            )
            if hero and dead and not deployed:
                state = SlotState.UNAVAILABLE
            # Selection enlarges the whole card and lifts its label by 10 px.
            # Header color varies by camp and must not decide selection.
            selected = bool(
                not hero
                and state == SlotState.UNDEPLOYED
                and 725 <= label_y < 733
                and w >= 115
            )
            if dead:
                ability = AbilityState.USED
            elif not hero and not deployed and not ready:
                ability = AbilityState.UNKNOWN
            slots.append(
                BuilderSlot(
                    kind if hero else f"camp:{number}",
                    kind,
                    "hero" if hero else "reinforcement" if number >= 7 else "troop",
                    (x + w // 2, 810),
                    box,
                    state,
                    ability,
                    health=float(green.mean()) if deployed else None,
                    selected=selected,
                )
            )
        troops = [s for s in slots if s.role in ("troop", "reinforcement")]
        valid = bool(troops) and not any(s.state == SlotState.UNKNOWN for s in slots)
        return ArmyObservation(
            tuple(slots),
            valid,
            "Thanh builder mới" if valid else "Ô chưa nhận diện; không dùng cache cũ",
        )
