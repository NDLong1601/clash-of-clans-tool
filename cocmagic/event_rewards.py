"""Recognize the event's reward panel and resource labels, never troop rewards."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cocmagic import config


RESOURCE_NAMES = {"dark": "Dark Elixir", "elixir": "Elixir", "gold": "Gold"}
REFERENCE_SIZE = (1050, 591)


@dataclass(frozen=True)
class RewardChoice:
    resource: str
    point: tuple[int, int]


@dataclass(frozen=True)
class RewardPanel:
    choices: tuple[RewardChoice, ...]

    def preferred(self, resource: str = "dark") -> Optional[RewardChoice]:
        order = list(dict.fromkeys((resource, "dark", "elixir", "gold")))
        return next((choice for name in order for choice in self.choices
                     if choice.resource == name), None)


@lru_cache(maxsize=1)
def _title_template():
    template = cv2.imread(config.asset("event_reward_title.png"), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(config.asset("event_reward_title.png"))
    return template


@lru_cache(maxsize=1)
def _resource_labels():
    font = ImageFont.truetype(config.asset("Supercell-Magic.otf"), 18)
    templates = {}
    for resource, name in RESOURCE_NAMES.items():
        canvas = Image.new("L", (260, 50))
        ImageDraw.Draw(canvas).text((4, 3), name, font=font, fill=255)
        pixels = np.asarray(canvas)
        x, y, w, h = cv2.boundingRect(cv2.findNonZero(pixels))
        templates[resource] = pixels[y:y + h, x:x + w]
    return templates


def _read_resource(image, box) -> Optional[str]:
    x, y, w, h = box
    # Labels sit below the reward artwork/quantity, inside the bright frame.
    roi = image[y + round(h * .65):y + round(h * .82), x + 10:x + w - 10]
    white = cv2.inRange(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV),
                        (0, 0, 175), (179, 110, 255))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(white)
    glyphs = [i for i in range(1, count)
              if 3 <= stats[i, 2] <= 25 and 10 <= stats[i, 3] <= 26
              and stats[i, 4] >= 20]
    if not glyphs:
        return None
    mask = np.where(np.isin(labels, glyphs), 255, 0).astype(np.uint8)
    lx, ly, lw, lh = cv2.boundingRect(cv2.findNonZero(mask))
    text = mask[ly:ly + lh, lx:lx + lw]
    best_name, best_score = None, .64
    for name, template in _resource_labels().items():
        ratio = template.shape[1] / template.shape[0]
        if abs(lw / lh / ratio - 1) > .20:
            continue
        scaled = cv2.resize(template, (lw, lh), interpolation=cv2.INTER_AREA)
        score = float(cv2.matchTemplate(text, scaled, cv2.TM_CCOEFF_NORMED)[0, 0])
        if score > best_score:
            best_name, best_score = name, score
    return best_name


def find_reward_panel(image: np.ndarray) -> Optional[RewardPanel]:
    """Require the title and three framed cards before choosing a resource.

    Coordinates scale with the supplied screenshot. An empty panel means the
    title/cards are animating or no resource is recognized. Three reward
    frames without a title also block inputs until the banner settles.
    """
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        return None
    height, width = image.shape[:2]
    if width < 600 or abs(width / height - 16 / 9) > .06:
        return None
    normalized = cv2.resize(image, REFERENCE_SIZE, interpolation=cv2.INTER_AREA)
    title_roi = cv2.cvtColor(normalized[55:150, 230:820], cv2.COLOR_BGR2GRAY)
    score = float(cv2.minMaxLoc(cv2.matchTemplate(
        title_roi, _title_template(), cv2.TM_CCOEFF_NORMED))[1])
    title_visible = score >= .80
    hsv = cv2.cvtColor(normalized[140:455, 180:870], cv2.COLOR_BGR2HSV)
    bright = cv2.inRange(hsv, (0, 0, 135), (179, 105, 255))
    # Event rarity also uses a gold frame. Requiring three silver frames
    # rejected a perfectly readable Dark Elixir card in the recorded battle.
    bright |= cv2.inRange(hsv, (12, 70, 155), (40, 255, 255))
    contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = sorted((cv2.boundingRect(c) for c in contours
                    if cv2.contourArea(c) > 30_000), key=lambda box: box[0])
    boxes = [(x + 180, y + 140, w, h) for x, y, w, h in boxes
             if 150 <= w <= 215 and 220 <= h <= 300]
    if (len(boxes) != 3 or max(b[1] for b in boxes) - min(b[1] for b in boxes) > 20
            or any(not 185 <= b[0] - a[0] <= 240 for a, b in zip(boxes, boxes[1:]))):
        return RewardPanel(()) if title_visible else None
    if not title_visible:
        return RewardPanel(())
    choices = []
    for box in boxes:
        resource = _read_resource(normalized, box)
        if resource:
            x, y, w, h = box
            point = (round((x + w / 2) * width / REFERENCE_SIZE[0]),
                     round((y + h / 2) * height / REFERENCE_SIZE[1]))
            choices.append(RewardChoice(resource, point))
    return RewardPanel(tuple(choices))
