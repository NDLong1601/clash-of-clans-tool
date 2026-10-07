"""Per-battle deployment geometry for a cached army bar.

Card positions are stable across attacks; troop entry and spell targets are not.
The red no-deploy boundary is authoritative when visible. A perimeter plan
contains candidates that must be confirmed by the farm module in game.
"""

from dataclasses import dataclass, field
import math
from typing import List, Tuple

import cv2
import numpy as np

from cocmagic.battle_planner import BattlePlan


Point = Tuple[int, int]


def _between(start: Point, end: Point, fraction: float) -> Point:
    return (round(start[0] + (end[0] - start[0]) * fraction),
            round(start[1] + (end[1] - start[1]) * fraction))


@dataclass
class AttackTactics:
    main_points: List[Point]
    flank_points: List[Point]
    entry: Point
    center: Point
    hotspots: List[Point]
    rage_entries: List[Point] = field(default_factory=list)

    @classmethod
    def from_battle(cls, plan: BattlePlan, image: np.ndarray) -> "AttackTactics":
        points = plan.troop_points
        # Pick a broad, usable side rather than trusting the hull's arbitrary
        # first vertex. Keep every main point on the same side of the base.
        seed = max(points, key=lambda p: (
            sum(math.dist(p, q) <= 230 for q in points),
            -math.dist(p, (800, 450))))
        main = sorted((p for p in points if math.dist(p, seed) <= 230),
                      key=lambda p: math.dist(p, seed))
        if len(main) < 2:
            main = sorted(points, key=lambda p: math.dist(p, seed))[:3]
        flank = [p for p in points if p not in main]
        entry = (round(sum(p[0] for p in main) / len(main)),
                 round(sum(p[1] for p in main) / len(main)))
        return cls(main, flank, entry, plan.spell_center,
                   cls._structure_hotspots(image, plan, entry))

    @staticmethod
    def _structure_hotspots(image: np.ndarray, plan: BattlePlan,
                            entry: Point) -> List[Point]:
        """Rank textured areas inside the base as approximate structure groups.

        This deliberately does not label individual defenses. A spell should
        follow the army path if the screenshot has no clear structures.
        """
        if image is None or image.shape[:2] != (900, 1600):
            return []
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 55, 130)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        red = (cv2.inRange(hsv, (0, 100, 75), (12, 255, 255)) |
               cv2.inRange(hsv, (170, 100, 75), (179, 255, 255)))
        edges[cv2.dilate(red, np.ones((7, 7), np.uint8)) > 0] = 0
        hull = plan.boundary.astype(np.float32)
        center = plan.spell_center
        candidates = []
        for y in range(155, 655, 45):
            for x in range(290, 1350, 45):
                if cv2.pointPolygonTest(hull, (float(x), float(y)), True) < 35:
                    continue
                # Target the attack corridor; a dense group on the far side
                # is unlikely to help troops arriving from this entry.
                path_distance = min(math.dist((x, y), _between(entry, center, f))
                                    for f in (0.4, 0.6, 0.8, 1.0))
                if path_distance > 225:
                    continue
                patch = edges[y-30:y+31, x-30:x+31]
                density = float((patch > 0).mean())
                if density < 0.045:
                    continue
                candidates.append((density - path_distance / 4500, (x, y)))
        ranked = sorted(candidates, reverse=True)
        selected = []
        for _, point in ranked:
            if all(math.dist(point, previous) >= 110 for previous in selected):
                selected.append(point)
            if len(selected) == 4:
                break
        return selected

    def troop_targets(self, slot_index: int, start: int, count: int,
                      attack_around: bool) -> List[Point]:
        targets = []
        for offset in range(count):
            index = start + offset
            # With attack-around enabled, most units still form a main push
            # for the heroes; the remaining units cover other edges.
            use_flank = attack_around and self.flank_points and index % 5 >= 3
            group = self.flank_points if use_flank else self.main_points
            targets.append(group[(index + slot_index) % len(group)])
        return targets

    def hero_targets(self, count: int, confirmed_main: List[Point] | None = None) -> List[Point]:
        # Heroes share confirmed troop points on the main approach.
        points = confirmed_main or self.main_points
        return [points[i % len(points)] for i in range(count)]

    def spell_target(self, name: str, index: int) -> Point | None:
        name = name.lower()
        path = lambda fraction: _between(self.entry, self.center, fraction)
        near, middle, deep = path(.38), path(.58), path(.78)
        def hotspot(reference: Point, offset: int = 0) -> Point:
            if not self.hotspots:
                return reference
            ordered = sorted(self.hotspots, key=lambda p: math.dist(p, reference))
            return ordered[offset % len(ordered)]

        if name == "rage":
            if self.rage_entries:
                direction = self.rage_entries[index % len(self.rage_entries)]
                depth = min(.68, .24 + .22 * (index // len(self.rage_entries)))
                return _between(direction, self.center, depth)
            return path((.42, .64)[index % 2])
        if name == "haste":
            return path((.32, .55)[index % 2])
        if name in {"healing", "heal"}:
            return path((.5, .68)[index % 2])
        if name in {"clone", "invisibility", "invis", "recall", "revive"}:
            return path({"clone": .44, "invisibility": .5, "invis": .5,
                         "recall": .33, "revive": .4}[name])
        if name == "jump":
            return middle
        if name == "freeze":
            offsets = ((0, 0), (85, 0), (-85, 0), (0, 80), (0, -80))
            dx, dy = offsets[index % len(offsets)]
            return (self.center[0] + dx, self.center[1] + dy)
        if name in {"ice_block", "overgrowth"}:
            return hotspot(deep, index)
        if name in {"lightning", "earthquake"}:
            # Damage spells can intentionally stack on one structure group.
            return hotspot(deep, index // 3)
        if name in {"poison", "totem"}:
            return hotspot(middle, index)
        if name in {"skeleton", "bat"}:
            target = hotspot(deep, index)
            side = 1 if name == "skeleton" else -1
            return (max(250, min(1350, target[0] + side * 65)), target[1])
        return None
