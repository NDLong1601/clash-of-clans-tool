"""Builder perimeter distribution and one-shot ability ledger, scoped to a battle."""

import math
import cv2
import numpy as np
from cocmagic.battle_planner import BattlePlanner, BattlePlan
from cocmagic.builder_vision import AbilityState, SlotState
from cocmagic.camera_controller import ScreenSpace


class BuilderTactics:
    def __init__(self, mode="around"):
        self.mode = mode
        self.planner = BattlePlanner()
        self.reset_battle()

    def reset_battle(self):
        self.used_abilities = set()
        self.attempted_abilities = set()
        self.deployed_at = {}
        self.hero_attempted = {}
        self.hero_waiting = set()
        self.reset_stage()

    def reset_stage(self):
        self.invalidate_view()
        self.attempts = {}
        self.deployed_at.clear()

    def invalidate_view(self):
        """Pixel history expires with the view; battle receipts do not."""
        self.plan = None
        self.reference = None
        self.confirmed_point = None
        self.rejected = set()
        self.accepted = []

    def observe(self, slots):
        for slot in slots:
            if slot.role == "hero" and slot.ability == AbilityState.CHARGING:
                self.hero_waiting.discard(slot.key)
            if (
                slot.role != "hero"
                and slot.ability == AbilityState.USED
                and slot.state in (SlotState.DEPLOYED, SlotState.DEAD)
            ):
                self.used_abilities.add(slot.key)

    def build(self, image, revision):
        self.plan = self.planner.plan(image, camera_revision=revision)
        if self.plan is None:
            self.plan = self._builder_boundary(image, revision)
        if self.plan is None:
            self.plan = self._visible_footprint(image, revision)
        self.reference = image.copy() if self.plan else None
        self.confirmed_point = None
        return self.plan

    @staticmethod
    def _builder_boundary(image, revision):
        """Builder lines can be thin, dark and deeply stepped around buildings.

        Require long isometric segments across the current map. Only supported
        outer edges authorize bounded probes; no standard diamond is assumed.
        """
        if image is None or image.shape != (900, 1600, 3):
            return None
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        red = cv2.inRange(hsv, (0, 90, 60), (18, 255, 210))
        red[ScreenSpace.map_mask(image.shape) == 0] = 0
        lines = cv2.HoughLinesP(
            red, 1, np.pi / 180, threshold=20, minLineLength=45, maxLineGap=8
        )
        if lines is None:
            return None
        segments = []
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            dx, dy = int(x2 - x1), int(y2 - y1)
            if dx and 0.5 < abs(dy / dx) < 1.1 and math.hypot(dx, dy) > 55:
                segments.append(((int(x1), int(y1)), (int(x2), int(y2))))
        if len(segments) < 6 or sum(math.dist(a, b) for a, b in segments) < 500:
            return None
        hull = cv2.convexHull(
            np.asarray([p for pair in segments for p in pair], np.int32)
        ).reshape(-1, 2)
        if cv2.contourArea(hull) < 150000 or np.ptp(hull, axis=0).min() < 250:
            return None
        center = tuple(np.mean(hull, axis=0).astype(int))
        nearby = cv2.dilate(red, np.ones((9, 9), np.uint8))
        points = []
        for a, b in zip(hull, np.roll(hull, -1, axis=0)):
            edge = np.linspace(a, b, max(2, int(math.dist(a, b) / 5))).astype(int)
            if np.mean(nearby[edge[:, 1], edge[:, 0]] > 0) < 0.18:
                continue
            for fraction in np.linspace(0.2, 0.8, max(2, int(math.dist(a, b) / 80))):
                p = a + (b - a) * fraction
                outward = p - center
                p = np.rint(p + outward / max(1, np.linalg.norm(outward)) * 55).astype(
                    int
                )
                point = tuple(map(int, p))
                if (
                    ScreenSpace.map_point(point)
                    and 140 < point[1] < 645
                    and cv2.pointPolygonTest(hull.astype(np.float32), point, False) < 0
                    and all(math.dist(point, q) > 55 for q in points)
                ):
                    points.append(point)
        if len(points) < 4:
            return None
        return BattlePlan(
            points,
            center,
            0.65,
            hull,
            "builder_red_segments",
            camera_revision=revision,
            camera_tracked=True,
        )

    @staticmethod
    def _visible_footprint(image, revision):
        """Derive bounded probe points from *current* visible builder structures.

        Stage 2 can omit the red deployment line. Warm wall/roof components
        give a conservative occupied footprint. Every returned point must still
        be accepted by the game before it can be reused or counted as deployed.
        Blank or sparsely decorated scenes cannot authorize map input.
        """
        if image is None or image.shape != (900, 1600, 3):
            return None
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        warm = cv2.inRange(hsv, (7, 55, 55), (32, 255, 255))
        mask = ScreenSpace.map_mask(image.shape, "battle")
        warm[mask == 0] = 0
        warm[:150] = 0
        warm[650:] = 0
        warm[:, :330] = 0
        warm[:, 1270:] = 0
        closed = cv2.morphologyEx(warm, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        count, _, stats, _ = cv2.connectedComponentsWithStats(closed)
        core = [
            (x, y, w, h, area)
            for x, y, w, h, area in stats[1:]
            if area >= 1200 and 520 < x + w // 2 < 1130 and 160 < y + h // 2 < 630
        ]
        if len(core) < 3:
            return None
        x1 = min(x for x, _, _, _, _ in core)
        x2 = max(x + w for x, _, w, _, _ in core)
        y1 = min(y for _, y, _, _, _ in core)
        y2 = max(y + h for _, y, _, h, _ in core)
        if x2 - x1 < 230 or y2 - y1 < 180:
            return None
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        candidates = [
            (x1 - 90, cy),
            (x2 + 90, cy),
            (cx, y1 - 80),
            (cx, y2 + 80),
            (x1 - 70, y1 - 35),
            (x2 + 70, y1 - 35),
            (x1 - 70, y2 + 35),
            (x2 + 70, y2 + 35),
            (x1 - 140, cy - 70),
            (x2 + 140, cy + 70),
        ]
        points = []
        for x, y in candidates:
            x, y = int(x), int(y)
            if ScreenSpace.map_point((x, y)) and 140 < y < 650 and 250 < x < 1350:
                points.append((x, y))
        if len(points) < 4:
            return None
        boundary = np.asarray([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], np.int32)
        return BattlePlan(
            points,
            (cx, cy),
            0.5,
            boundary,
            "builder_visual_footprint",
            camera_revision=revision,
            camera_tracked=True,
        )

    def point(self, slot, revision):
        if self.plan is None or self.plan.camera_revision != revision:
            return None
        if self.mode == "single_point" and self.confirmed_point:
            return self.confirmed_point
        candidates = [
            p
            for p in self.plan.troop_points
            if p not in self.rejected and ScreenSpace.map_point(p)
        ]
        if not candidates:
            return None
        if self.mode == "around" and self.accepted:
            # Maximise angular separation first, then distance. This distributes
            # successive camps over visible supported edges, including clipping.
            center = self.plan.spell_center

            def separation(p):
                a = math.atan2(p[1] - center[1], p[0] - center[0])
                return min(
                    abs(
                        math.atan2(
                            math.sin(
                                a - math.atan2(q[1] - center[1], q[0] - center[0])
                            ),
                            math.cos(
                                a - math.atan2(q[1] - center[1], q[0] - center[0])
                            ),
                        )
                    )
                    for q in self.accepted
                )

            return max(
                candidates,
                key=lambda p: (
                    separation(p),
                    min(math.dist(p, q) for q in self.accepted),
                ),
            )
        return candidates[0]

    def receipt(self, slot, point, deployed, now):
        self.attempts[slot.key] = self.attempts.get(slot.key, 0) + 1
        if deployed:
            self.confirmed_point = point
            self.accepted.append(point)
            self.deployed_at[slot.key] = now
        else:
            self.rejected.add(point)
            if self.confirmed_point == point:
                self.confirmed_point = None

    def skill_due(self, slot, now, delay):
        return (
            slot.kind == "baby_dragon"
            and slot.state == SlotState.DEPLOYED
            and slot.ability == AbilityState.READY
            and slot.key not in self.used_abilities
            and slot.key not in self.attempted_abilities
            and slot.key in self.deployed_at
            and now - self.deployed_at[slot.key] >= delay
        )
