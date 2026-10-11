"""Finite reward/cart transactions, verified after every input."""

from dataclasses import dataclass
import time

import numpy as np

from cocmagic.builder_screen_reader import (
    BuilderScreenReader,
    ScreenKind,
    StarBonusReader,
    StarBonusState,
    StarBonusObservation,
    Village,
)
from cocmagic.village_navigator import VillageNavigator


@dataclass(frozen=True)
class RewardResult:
    success: bool
    reason: str
    bonus: StarBonusObservation
    claims: int = 0


@dataclass(frozen=True)
class CartResult:
    success: bool
    reason: str
    collected: bool = False
    returned_home: bool = False
    defending: bool = False
    unavailable: bool = False


class BuilderRewards:
    def __init__(
        self,
        adb,
        reader=None,
        navigator=None,
        bonus_reader=None,
        *,
        timeout=35.0,
        max_claims=3,
    ):
        self.adb = adb
        self.reader = reader or BuilderScreenReader(adb)
        self.navigator = navigator or VillageNavigator(adb, self.reader)
        self.bonus_reader = bonus_reader or StarBonusReader(self.reader)
        self.timeout = min(90.0, max(1.0, timeout))
        self.max_claims = min(5, max(1, max_claims))

    def _unknown(self, reason):
        self.bonus_reader.reset()
        return StarBonusObservation(StarBonusState.UNKNOWN, time.monotonic(), reason)

    def observe_bonus(self, *, deadline=None, max_frames=12):
        self.bonus_reader.reset()
        deadline = deadline or time.monotonic() + self.timeout
        observation = self._unknown("Chưa quan sát được")
        for _ in range(max_frames):
            if self.navigator.stopping() or time.monotonic() >= deadline:
                break
            observation = self.bonus_reader.observe(self.reader.capture())
            if observation.state != StarBonusState.UNKNOWN:
                break
            self.navigator.wait()
        return observation

    def claim_star_bonus(self):
        with self.adb.input_lock:
            deadline = time.monotonic() + self.timeout
            for claims in range(self.max_claims + 1):
                observation = self.observe_bonus(deadline=deadline)
                if observation.state in (
                    StarBonusState.AVAILABLE,
                    StarBonusState.COMPLETE,
                ):
                    return RewardResult(
                        True, "Đã đọc lại thưởng trên Home", observation, claims
                    )
                if (
                    observation.state != StarBonusState.CLAIMABLE
                    or claims >= self.max_claims
                ):
                    return RewardResult(
                        False,
                        "Không xác nhận được thưởng hoặc hết ngân sách",
                        observation,
                        claims,
                    )
                fresh = self.reader.capture()
                screen = self.reader.classify(fresh.image)
                point = screen.points.get("claim")
                if (
                    screen.panel != "star_reward"
                    or screen.village != Village.BUILDER
                    or not point
                    or self.navigator.stopping()
                    or time.monotonic() >= deadline
                    or self.adb.tap(*point, delay=0.1) is not True
                ):
                    return RewardResult(
                        False,
                        "Tap nhận thưởng thất bại",
                        self._unknown("Chưa đối soát tap"),
                        claims,
                    )
                # Never replay the same button while the panel remains visible.
                closed = False
                for _ in range(16):
                    if self.navigator.stopping() or time.monotonic() >= deadline:
                        break
                    self.navigator.wait()
                    screen = self.reader.classify(self.reader.capture().image)
                    if screen.kind == ScreenKind.BUILDER_HOME:
                        closed = True
                        break
                    if (
                        screen.kind not in (ScreenKind.LOADING, ScreenKind.UNKNOWN)
                        and screen.panel != "star_reward"
                    ):
                        break
                if not closed:
                    return RewardResult(
                        False,
                        "Bảng chưa đóng; không bấm lại",
                        self._unknown("Không xác nhận Home sau nhận"),
                        claims + 1,
                    )
                # A subsequent panel gets its own fresh observation and budget;
                # Home with another star task returns AVAILABLE immediately.
            return RewardResult(False, "Hết ngân sách", self._unknown("Hết ngân sách"))

    def collect_cart(self, *, resume=False):
        with self.adb.input_lock:
            deadline = time.monotonic() + self.timeout
            if not resume:
                home = self.navigator.confirmed_home(Village.BUILDER, deadline=deadline)
                if not home:
                    return CartResult(False, "Chưa xác nhận builder Home; không mở xe")
                found, _ = self.navigator.locate(
                    "cart_object", Village.BUILDER, deadline
                )
                if not found:
                    return CartResult(False, "Không tìm được xe ở camera hiện tại")
                frame = self.reader.capture()
                screen = self.reader.classify(frame.image)
                point = self.reader.map_target(frame.image, "cart_object")
                if (
                    screen.kind != ScreenKind.BUILDER_HOME
                    or not point
                    or self.navigator.stopping()
                    or time.monotonic() >= deadline
                    or frame.revision != self.adb.camera_revision
                    or self.adb.tap(*point, delay=0.1) is not True
                ):
                    return CartResult(False, "Không mở được xe")
            frame, panel = self._wait_cart(deadline)
            if panel is None:
                return CartResult(
                    False, "Không xác nhận đúng bảng xe; không tap Collect/close mù"
                )
            collected, defending = False, bool(panel.points.get("cart_defending"))
            valid = False
            reason = "Trạng thái xe chưa rõ"
            # Recheck the exact panel/button immediately before collection.
            fresh, check = self._wait_cart(deadline)
            if check is None:
                # A vanished/unreadable panel invalidates the previous Collect
                # coordinate. Closing also requires its own new observation.
                returned = self._close_cart(deadline)
                return CartResult(
                    False,
                    "Bảng xe đổi trước Collect; hủy input cũ",
                    returned_home=returned,
                )
            panel, frame = check, fresh
            enabled, disabled = (
                panel.points.get("cart_collect"),
                panel.points.get("cart_disabled"),
            )
            if enabled and disabled:
                reason = "Nút Collect mâu thuẫn"
            elif disabled and (panel.points.get("cart_empty") or defending):
                valid, reason = True, "Xe trống/đang phòng thủ; kết thúc hữu hạn"
            elif disabled:
                # An exact, stable disabled Collect is a receipt of unavailable
                # input, even with money left (e.g. full storage). Do not claim
                # empty/collected or wait for that button to become enabled.
                valid, reason = (
                    True,
                    "Collect bị khóa; chưa xác định nguyên nhân, giữ nguyên tiền trong xe",
                )
            elif enabled:
                if (
                    not self.navigator.stopping()
                    and time.monotonic() < deadline
                    and self.adb.tap(*enabled, delay=0.1) is True
                ):
                    before = frame.image
                    for _ in range(12):
                        if self.navigator.stopping() or time.monotonic() >= deadline:
                            break
                        self.navigator.wait()
                        after, state = self._wait_cart(deadline, max_frames=1)
                        if state is None:
                            break
                        # A changed counter/bar plus a disabled button is a
                        # receipt. Animation or changed rows alone is not.
                        delta = np.abs(
                            before[735:803, 590:1030].astype(np.int16)
                            - after.image[735:803, 590:1030]
                        ).mean()
                        if (
                            state.points.get("cart_disabled")
                            and not state.points.get("cart_collect")
                            and delta > 1.5
                        ):
                            settled, final = self._wait_cart(deadline)
                            if final and final.points.get("cart_disabled"):
                                stable = (
                                    np.abs(
                                        after.image[735:803, 590:1030].astype(np.int16)
                                        - settled.image[735:803, 590:1030]
                                    ).mean()
                                    < 5
                                )
                                if stable:
                                    valid, collected, reason = (
                                        True,
                                        True,
                                        "Đã đối soát counter/bar đổi và Collect disabled",
                                    )
                                    defending = bool(final.points.get("cart_defending"))
                                    break
                    if not valid:
                        reason = "Tap thu chưa có thay đổi được xác nhận; không thu lặp"
                else:
                    reason = "Tap Collect thất bại"
            returned = self._close_cart(deadline)
            self.bonus_reader.reset()
            return CartResult(
                valid and returned,
                reason if returned else reason + "; chưa xác nhận trở về Home",
                collected,
                returned,
                defending,
                bool(disabled and not enabled),
            )

    def _wait_cart(self, deadline, max_frames=6):
        previous = None
        for _ in range(max_frames):
            if self.navigator.stopping() or time.monotonic() >= deadline:
                break
            frame = self.reader.capture()
            screen = self.reader.classify(frame.image)
            if screen.panel == "cart" and screen.points.get("close"):
                if max_frames == 1:
                    return frame, screen
                if previous and frame.image is not previous[0].image:
                    delta = np.abs(
                        previous[0].image[735:803, 590:1030].astype(np.int16)
                        - frame.image[735:803, 590:1030]
                    ).mean()
                    if (
                        frame.sequence > previous[0].sequence
                        and frame.captured_at - previous[0].captured_at >= 0.15
                        and screen.points.keys() == previous[1].points.keys()
                        and delta < 5
                    ):
                        return frame, screen
                previous = (frame, screen)
            if screen.kind in (
                ScreenKind.BATTLE,
                ScreenKind.RESULT,
                ScreenKind.ATTACK_MENU,
            ):
                break
            self.navigator.wait()
        return None, None

    def _close_cart(self, deadline):
        # Closing is also a transaction; only a fresh verified cart close is
        # accepted, and caller learns whether Home was actually restored.
        # Reserve a bounded cleanup window even after a collection timeout.
        deadline = max(deadline, time.monotonic() + 5)
        frame, panel = self._wait_cart(deadline, max_frames=3)
        if (
            not panel
            or self.navigator.stopping()
            or time.monotonic() >= deadline
            or self.adb.tap(*panel.points["close"], delay=0.1) is not True
        ):
            return False
        return (
            self.navigator.confirmed_home(Village.BUILDER, deadline=deadline)
            is not None
        )
