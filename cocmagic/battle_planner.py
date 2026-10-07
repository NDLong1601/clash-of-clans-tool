"""Plan troop drops outside the red border or around the construction diamond."""

from dataclasses import dataclass
import math
from typing import List, Optional, Tuple

import cv2
import numpy as np


Point = Tuple[int, int]


@dataclass
class BattlePlan:
    troop_points: List[Point]
    spell_center: Point
    confidence: float
    boundary: np.ndarray
    source: str = "red_boundary"

    @property
    def requires_probe(self) -> bool:
        return self.source != "red_boundary"


class BattlePlanner:
    """Use deployment geometry; scenery color and decorations are not barriers."""

    # The construction grid has a fixed isometric footprint at 1600x900.
    # Scenery can cover its surrounding ground with paths, trees or ornaments.
    CONSTRUCTION_DIAMOND = np.asarray(((800, 75), (1430, 440),
                                      (800, 805), (170, 440)), dtype=np.int32)

    def plan(self, image: np.ndarray) -> Optional[BattlePlan]:
        if image is None or image.shape[:2] != (900, 1600):
            return None

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        red = (cv2.inRange(hsv, (0, 105, 90), (12, 255, 255)) |
               cv2.inRange(hsv, (170, 105, 90), (179, 255, 255)))

        # UI, loot text, and troop bar also contain red; exclude them first.
        red[:100] = 0
        red[720:] = 0
        red[:, :80] = 0
        red[:, 1520:] = 0
        red[:275, :300] = 0
        red[:130, 620:980] = 0
        red[550:, :230] = 0
        red[540:, 1270:] = 0

        lines = cv2.HoughLinesP(red, 1, np.pi / 180, threshold=22,
                                minLineLength=35, maxLineGap=12)
        if lines is None:
            return self._perimeter_plan(image)

        endpoints = []
        for x1, y1, x2, y2 in lines[:, 0]:
            if math.hypot(int(x2) - int(x1), int(y2) - int(y1)) > 45:
                endpoints.extend(((int(x1), int(y1)), (int(x2), int(y2))))
        if len(endpoints) < 8:
            return self._perimeter_plan(image)

        hull = cv2.convexHull(np.asarray(endpoints, dtype=np.int32)).reshape(-1, 2)
        area = cv2.contourArea(hull)
        if not 180_000 <= area <= 900_000 or not self._outline_supported(hull, red):
            return self._perimeter_plan(image)

        moments = cv2.moments(hull)
        if not moments["m00"]:
            return self._perimeter_plan(image)
        center = np.array((moments["m10"] / moments["m00"],
                           moments["m01"] / moments["m00"]), dtype=float)

        points: List[Point] = []
        for i, start in enumerate(hull):
            end = hull[(i + 1) % len(hull)]
            distance = float(np.linalg.norm(end - start))
            steps = max(1, int(distance // 85))
            for step in range(steps):
                edge = start + (end - start) * ((step + 0.5) / steps)
                outward = edge - center
                length = float(np.linalg.norm(outward))
                if length == 0:
                    continue
                x, y = np.rint(edge + outward / length * 35).astype(int)
                x, y = int(x), int(y)
                if not (220 < x < 1400 and 135 < y < 620):
                    continue
                if (x < 320 and y < 300) or (x > 1300 and y > 520):
                    continue
                if cv2.pointPolygonTest(hull.astype(np.float32), (float(x), float(y)), False) >= 0:
                    continue
                # The supported red line defines the restriction. A tree,
                # statue or different ground hue outside it is still usable.
                if all(math.hypot(x - px, y - py) >= 55 for px, py in points):
                    points.append((x, y))

        if len(points) < 4:
            return self._perimeter_plan(image)
        # Every selected point is outside the conservative hull and UI zones.
        confidence = min(1.0, len(endpoints) / 30) * min(1.0, len(points) / 8)
        if confidence < 0.45:
            return self._perimeter_plan(image)
        spell_center = (int(round(center[0])), int(round(center[1])))
        return BattlePlan(points, spell_center, confidence, hull)

    @staticmethod
    def _outline_supported(hull: np.ndarray, red: np.ndarray) -> bool:
        """Reject hulls made by unrelated red roofs, decorations and UI.

        The real deployment line occupies a substantial part of several hull
        edges. Scattered red objects can yield a large convex hull but leave
        the long lines between its vertices almost entirely unsupported.
        """
        nearby = cv2.dilate(red, np.ones((9, 9), np.uint8))
        lengths = []
        supported = []
        for index, start in enumerate(hull):
            end = hull[(index + 1) % len(hull)]
            length = float(np.linalg.norm(end - start))
            if length < 70:
                continue
            count = max(2, int(length / 4))
            xs = np.linspace(start[0], end[0], count).astype(int)
            ys = np.linspace(start[1], end[1], count).astype(int)
            fraction = float(np.mean(nearby[ys, xs] > 0))
            lengths.append(length)
            supported.append(fraction)
        if not lengths:
            return False
        weighted = sum(a * b for a, b in zip(lengths, supported)) / sum(lengths)
        return weighted >= .30 and sum(value >= .35 for value in supported) >= 3

    @staticmethod
    def perimeter_point_visible(point: Point) -> bool:
        """Keep candidates on the game canvas and away from battle controls."""
        x, y = point
        return (110 <= x <= 1490 and 135 <= y <= 695
                and not (x < 310 and y < 285)       # player and available loot
                and not (x > 1300 and y < 195)     # resource bars
                and not (x < 250 and y > 555)      # End Battle / Surrender
                and not (x > 1260 and y > 540)     # damage meter / Next
                and not (250 <= x <= 1270 and y > 650))  # army popovers

    @classmethod
    def _perimeter_plan(cls, image: np.ndarray) -> Optional[BattlePlan]:
        """Probe several rings around the fixed construction footprint.

        This works with unfamiliar scenery and with obscured/offscreen red
        lines. Neither the color nor local texture of a candidate excludes it:
        decorative objects do not affect deployment. The farm module confirms
        each initial point by a decrease in the selected troop's count.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 160)
        board = edges[170:630, 370:1230]
        cells = np.asarray([[np.mean(cell > 0) for cell in np.array_split(row, 4, axis=1)]
                            for row in np.array_split(board, 3)])
        occupied = cells >= .025
        if (float(np.mean(board > 0)) < .025 or np.count_nonzero(occupied) < 4
                or np.count_nonzero(occupied.any(axis=0)) < 2
                or np.count_nonzero(occupied.any(axis=1)) < 2):
            return None  # Blank/loading image or isolated UI text, no visible base.

        diamond = cls.CONSTRUCTION_DIAMOND
        center = np.asarray((800, 440), dtype=float)
        sides = [[] for _ in range(4)]
        # The first ring allows for buildings reaching the construction edge.
        # Wider and narrower alternatives cover large bases and scenic paths.
        for offset in (90, 135, 50, 25):
            for side, start in enumerate(diamond):
                end = diamond[(side + 1) % 4]
                tangent = (end - start).astype(float)
                normal = np.asarray((tangent[1], -tangent[0]))
                normal /= np.linalg.norm(normal)
                if np.dot(normal, (start + end) / 2 - center) < 0:
                    normal *= -1
                for fraction in (.2, .35, .5, .65, .8):
                    edge = start + tangent * fraction
                    point = tuple(map(int, np.rint(edge + normal * offset)))
                    if (cls.perimeter_point_visible(point)
                            and all(math.dist(point, prior) >= 45 for prior in sides[side])):
                        sides[side].append(point)
        # Cycle the four sides before trying additional offsets on one side.
        # A scenic feature on one side must not prevent trying another edge.
        selected = [side[index] for index in range(max(map(len, sides)))
                    for side in sides if index < len(side)][:28]
        if len(selected) < 4:
            return None
        return BattlePlan(selected, (800, 440), .55, diamond.copy(), "outer_perimeter")
