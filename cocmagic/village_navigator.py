"""Bounded synchronous navigation using GĐ3 camera, with destination proof."""

from dataclasses import dataclass
import time

from cocmagic.builder_screen_reader import BuilderScreenReader, ScreenKind, Village
from cocmagic.camera_controller import CameraController, CameraStatus, measure_motion


@dataclass(frozen=True)
class NavigationResult:
    success: bool
    reason: str
    village: Village | None = None
    boat_taps: int = 0
    camera_operations: int = 0


class VillageNavigator:
    def __init__(
        self,
        adb,
        reader=None,
        camera=None,
        *,
        stop_event=None,
        timeout=45.0,
        max_camera_operations=6,
        max_boat_taps=2,
    ):
        self.adb = adb
        self.reader = reader or BuilderScreenReader(adb)
        self.camera = camera or CameraController(
            adb, stop_event=stop_event, settle_timeout=5.0, max_frames=12
        )
        self.stop_event = stop_event or getattr(adb, "stop_event", None)
        self.timeout = min(90.0, max(1.0, timeout))
        self.max_camera_operations = min(8, max(0, max_camera_operations))
        self.max_boat_taps = min(3, max(1, max_boat_taps))
        self.last_result = None

    def stopping(self):
        return self.stop_event is not None and self.stop_event.is_set()

    def wait(self, seconds=0.25):
        if self.stop_event is None:
            time.sleep(seconds)
        else:
            self.stop_event.wait(seconds)

    def confirmed_home(self, expected=None, *, deadline=None, max_frames=8):
        previous = None
        deadline = deadline or time.monotonic() + 5
        for _ in range(max_frames):
            if self.stopping() or time.monotonic() >= deadline:
                break
            frame = self.reader.capture()
            screen = self.reader.classify(frame.image)
            if screen.kind in (ScreenKind.MAIN_HOME, ScreenKind.BUILDER_HOME):
                if expected is None or screen.village == expected:
                    if previous and previous[1].village == screen.village:
                        motion = measure_motion(previous[0].image, frame.image, "home")
                        if (
                            frame.image is not previous[0].image
                            and frame.sequence > previous[0].sequence
                            and frame.captured_at - previous[0].captured_at >= 0.15
                            and motion.valid
                            and not motion.changed
                        ):
                            return frame, screen
                    previous = (frame, screen)
                else:
                    previous = None
            elif screen.kind in (
                ScreenKind.BATTLE,
                ScreenKind.RESULT,
                ScreenKind.MODAL,
                ScreenKind.ATTACK_MENU,
            ):
                return None
            else:
                previous = None
            self.wait()
        return None

    def locate(self, name, village, deadline):
        """Search from fresh Home frames after every gesture; map coords expire."""
        operations = 0
        # Zoom wide, then move toward the relevant shore. Repeated zoom-limit
        # calls are suppressed by the existing camera backend.
        direction = (360, -230) if village == Village.MAIN else (-400, 220)
        actions = [
            ("pan", direction),
            ("zoom", 0.6),
            ("pan", direction),
            ("zoom", 0.6),
            ("pan", direction),
            ("pan", (-direction[0], -direction[1])),
        ]
        for index in range(self.max_camera_operations + 1):
            if self.stopping() or time.monotonic() >= deadline:
                return None, operations
            confirmed = self.confirmed_home(village, deadline=deadline, max_frames=6)
            if not confirmed:
                return None, operations
            frame, _ = confirmed
            point = self.reader.map_target(frame.image, name)
            if point:
                return (frame, point), operations
            if index >= self.max_camera_operations:
                break
            # Guard camera's internal fresh capture too, so a newly arriving
            # builder reward/unknown panel cannot slip between the two guards.
            original = self.camera.frame_clear
            self.camera.frame_clear = lambda im: (
                original(im) and self.reader.home_is_clear(im, village)
            )
            try:
                kind, value = actions[index % len(actions)]
                if kind == "zoom":
                    result = self.camera.zoom(
                        value, context="home", troop_selected=False
                    )
                else:
                    result = self.camera.pan(
                        (800, 420),
                        (800 + value[0], 420 + value[1]),
                        context="home",
                        troop_selected=False,
                    )
            finally:
                self.camera.frame_clear = original
            operations += 1
            if result.status not in (CameraStatus.SUCCESS, CameraStatus.UNCHANGED):
                # A released gesture can outlast its settle window. Discard its
                # coordinates and independently prove fresh Home on the next
                # iteration. Never retry an input/release failure this way.
                if (
                    result.status == CameraStatus.ERROR
                    and getattr(result, "reason", "")
                    == "Ảnh sau chưa ổn định hoặc không xác nhận được camera"
                ):
                    continue
                return None, operations
        return None, operations

    def navigate(self, target, *, source=None):
        target = Village(target)
        source = Village(source) if source is not None else None
        with self.adb.input_lock:
            self.last_result = self._navigate(target, source)
            return self.last_result

    def _navigate(self, target, source):
        deadline = time.monotonic() + self.timeout
        confirmed = self.confirmed_home(deadline=deadline)
        if not confirmed:
            return NavigationResult(
                False, "Không có Home ổn định; không thao tác thuyền"
            )
        current = confirmed[1].village
        if current == target:
            return NavigationResult(True, "Đã xác nhận làng đích", target)
        if source is not None and current != source:
            return NavigationResult(False, "Làng hiện tại không khớp nguồn", current)
        operations = 0
        for taps in range(1, self.max_boat_taps + 1):
            found, count = self.locate(
                "main_boat" if current == Village.MAIN else "builder_boat",
                current,
                deadline,
            )
            operations += count
            if not found or self.stopping() or time.monotonic() >= deadline:
                return NavigationResult(
                    False,
                    "Không tìm được thuyền an toàn trong ngân sách",
                    current,
                    taps - 1,
                    operations,
                )
            # Re-read immediately before tap; don't use a saved pre-pan point.
            fresh = self.reader.capture()
            screen = self.reader.classify(fresh.image)
            point = self.reader.map_target(
                fresh.image, "main_boat" if current == Village.MAIN else "builder_boat"
            )
            if (
                screen.village != current
                or screen.kind not in (ScreenKind.MAIN_HOME, ScreenKind.BUILDER_HOME)
                or not point
            ):
                return NavigationResult(
                    False,
                    "Màn hình/điểm thuyền đổi trước tap",
                    current,
                    taps - 1,
                    operations,
                )
            revision = fresh.revision
            if (
                revision != self.adb.camera_revision
                or self.stopping()
                or self.adb.tap(*point, delay=0.1) is not True
            ):
                return NavigationResult(
                    False, "Tap thuyền thất bại/đã dừng", current, taps, operations
                )
            # The village transition invalidates geometry even without a pan.
            self.camera.reset_view()
            if self.confirmed_home(target, deadline=deadline, max_frames=16):
                return NavigationResult(
                    True,
                    "Hai ảnh mới xác nhận đúng làng đích",
                    target,
                    taps,
                    operations,
                )
            # Retry only if the original Home is still independently proven.
            if not self.confirmed_home(current, deadline=deadline, max_frames=6):
                return NavigationResult(
                    False,
                    "Sau tap không xác nhận được Home; không tap lại",
                    None,
                    taps,
                    operations,
                )
        return NavigationResult(
            False,
            "Hết số lần tap; chưa xác nhận đích",
            current,
            self.max_boat_taps,
            operations,
        )

    def switch_village(self, source, target):
        """RunCoordinator callback, synchronous under its exclusive input lock."""
        return self.navigate(target, source=source).success
