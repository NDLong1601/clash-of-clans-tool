"""Synchronous builder farming, with bounded transactions and fresh receipts."""

import time
from enum import Enum
import cv2

from cocmagic import config
from cocmagic.builder_vision import BuilderBattleReader, SlotState, AbilityState
from cocmagic.builder_tactics import BuilderTactics
from cocmagic.builder_screen_reader import ScreenKind, Village
from cocmagic.builder_rewards import BuilderRewards
from cocmagic.village_navigator import VillageNavigator
from cocmagic.camera_controller import CameraController, CameraStatus, measure_motion
from cocmagic.village_module import ModuleScreen
from cocmagic.event_chests import EventChestOpener, find_chest_screen


class BuilderPhase(str, Enum):
    CLASSIFY = "classify"
    HOME = "home"
    SETUP = "setup"
    SEARCH = "search"
    DEPLOY = "deploy"
    FIGHT = "fight"
    TRANSITION = "transition"
    RESULT = "result"
    POST = "post"


class BuilderFarmModule:
    def __init__(
        self,
        adb,
        settings,
        *,
        reader=None,
        navigator=None,
        rewards=None,
        camera=None,
        stop_event=None,
        recovery_handler=None,
        clock=time.monotonic,
        home_policy=None,
    ):
        self.adb = adb
        self.settings = config.migrate_settings(settings)
        self.device_serial = adb.device
        self.stop_event = stop_event or getattr(adb, "stop_event", None)
        self.clock = clock
        self.home_policy = home_policy
        self.reader = reader or BuilderBattleReader(adb)
        self.camera = camera or CameraController(
            adb, stop_event=self.stop_event, settle_timeout=5.0, max_frames=12
        )
        self.navigator = navigator or VillageNavigator(
            adb, self.reader, self.camera, stop_event=self.stop_event
        )
        # Cart navigation can need camera recovery after a changed builder
        # viewport; the GĐ4 transaction itself remains finite and verified.
        self.rewards = rewards or BuilderRewards(
            adb, self.reader, self.navigator, timeout=90.0
        )
        self.recovery_handler = recovery_handler
        self.chests = EventChestOpener(adb)
        self.tactics = BuilderTactics(self.settings["builder_deploy_mode"])
        self.halt_reason = None
        self._metrics = {
            "attack_count": 0,
            "battle_count": 0,
            "stage_count": 0,
            "deployed": 0,
            "troop_abilities": 0,
            "hero_abilities": 0,
            "reward_claims": 0,
            "cart_collections": 0,
            "rejected_points": 0,
            "unconfirmed_abilities": 0,
            "recoveries": 0,
            "wall_count": 0,
        }
        self.last_warning = None
        self.last_bonus = None
        self.last_cart = None
        self.setup_verified = False
        self._suspended = False
        self._busy = False
        self._home_proof = False
        self._screen = ModuleScreen.UNKNOWN
        self.confirmed_village = None
        self._home_at = 0.0
        self._generation = 0
        self._tick_generation = 0
        self._reset_runtime()
        self.adb.add_camera_listener(self._camera_changed)

    def _reset_runtime(self):
        self.phase = BuilderPhase.CLASSIFY
        self.phase_at = self.clock()
        self.battle_at = None
        self.stage = 0
        self.seen_fight = False
        self.stage_confirmations = 0
        self.last_progress = self.clock()
        self.progress_signature = None
        self.bar_unclear_since = None
        self.geometry_unclear_since = None
        self.setup_edits = 0
        self.setup_pending_empty = False
        self.camera_operations = 0
        self.selected = False
        self._result_counted = False
        self._return_sent_at = None
        self._find_sent_at = None
        self._deployment_yield_due = False
        self.tactics.reset_battle()

    def stopping(self):
        return self.stop_event is not None and self.stop_event.is_set()

    def wait(self, seconds=0.2):
        if self.stop_event is not None:
            self.stop_event.wait(seconds)
        else:
            time.sleep(seconds)

    def _set_phase(self, phase):
        if self.phase != phase:
            self.phase = phase
            self.phase_at = self.clock()
        self._home_proof = False

    def _fail(self, reason):
        if self.stopping() or self._tick_generation != self._generation:
            return True
        self.halt_reason = reason
        self._home_proof = False
        print("[Builder] " + reason)
        return False

    def _tap(self, point):
        self._home_proof = False
        return bool(
            point
            and not self.stopping()
            and self._tick_generation == self._generation
            and self.adb.tap(*point, jitter=0, delay=0.1) is True
        )

    def _camera_changed(self, revision):
        self.tactics.invalidate_view()
        self._home_proof = False

    @property
    def confirmed_screen(self):
        return self._screen

    @property
    def can_yield(self):
        return (
            self._home_proof
            and self._screen == ModuleScreen.HOME
            and not self._busy
            and self.phase == BuilderPhase.HOME
            and self.clock() - self._home_at < 2.0
            and not self.stopping()
        )

    @property
    def metrics(self):
        return {**self._metrics, "stage": self.stage}

    @property
    def status_line(self):
        bonus = self.last_bonus.state.value if self.last_bonus else "unknown"
        warning = " · " + self.last_warning if self.last_warning else ""
        return (
            self.halt_reason
            or f"Làng đêm · {self.phase.value} · khu {self.stage} · {self._metrics['battle_count']} trận · sao {bonus}"
            + warning
        )

    def suspend(self):
        if not self.can_yield:
            raise RuntimeError("Builder chưa có Home/hậu xử lý ổn định để nhường")
        self._suspended = True
        self._home_proof = False
        self._screen = ModuleScreen.UNKNOWN
        self.tactics.reset_battle()

    def resume(self):
        self._suspended = False
        self.halt_reason = None
        self.setup_verified = False
        self.last_bonus = None
        self.last_cart = None
        self.last_warning = None
        self._reset_runtime()
        self._screen = ModuleScreen.UNKNOWN
        self.confirmed_village = Village.BUILDER
        self.adb.invalidate_cache()

    def reset_after_reload(self):
        self._generation += 1
        self._metrics["recoveries"] += 1
        self.setup_verified = False
        self.last_bonus = None
        self.last_cart = None
        self.last_warning = None
        self.halt_reason = None
        self._screen = ModuleScreen.UNKNOWN
        self.confirmed_village = None
        self._home_proof = False
        self._reset_runtime()
        self.camera.reset_view()
        self.adb.invalidate_cache()

    def invalidate_after_popup(self):
        self._generation += 1
        self.last_bonus = None
        self.last_cart = None
        self._screen = ModuleScreen.UNKNOWN
        self._home_proof = False
        self.tactics.invalidate_view()
        self.adb.invalidate_cache()

    def tick(self, *, yield_requested=None):
        if self.stopping() or self._suspended:
            return True
        if self.halt_reason:
            return False
        self._busy = True
        self._tick_generation = self._generation
        try:
            return self._tick(yield_requested)
        finally:
            self._busy = False

    def _tick(self, yield_requested):
        frame = self.reader.capture()
        if self.stopping():
            return True
        if find_chest_screen(frame.image) is not None:
            self._set_phase(BuilderPhase.RESULT)
            self._screen = ModuleScreen.RESULT
            self.battle_at = None
            chest = self.chests.open(
                frame.image, capture=lambda: self.reader.capture().image,
                wait=self.wait, stopping=self.stopping,
                terminal=lambda image: self.reader.classify(image).kind in (
                    ScreenKind.MAIN_HOME, ScreenKind.BUILDER_HOME, ScreenKind.RESULT),
            )
            return self._fail(chest.error) if chest.error else True
        screen = self.reader.classify(frame.image)
        self.confirmed_village = screen.village
        self._screen = {
            ScreenKind.BUILDER_HOME: ModuleScreen.HOME,
            ScreenKind.MAIN_HOME: ModuleScreen.HOME,
            ScreenKind.ATTACK_MENU: ModuleScreen.MENU,
            ScreenKind.BATTLE: ModuleScreen.BATTLE,
            ScreenKind.RESULT: ModuleScreen.RESULT,
            ScreenKind.MODAL: ModuleScreen.MODAL,
        }.get(screen.kind, ModuleScreen.UNKNOWN)
        now = self.clock()
        if (
            self.battle_at is not None
            and now - self.battle_at > self.settings["builder_battle_timeout"]
        ):
            return self._fail(
                "Timeout trận builder; không rút lui bằng nút chưa xác nhận"
            )
        if screen.kind == ScreenKind.RESULT:
            self._set_phase(BuilderPhase.RESULT)
            if not self._result_counted and screen.village == Village.BUILDER:
                self._metrics["battle_count"] += 1
                self._result_counted = True
            if self._return_sent_at is not None:
                return (
                    self._fail("Return Home chưa đóng result; không tap lặp")
                    if now - self._return_sent_at
                    > self.settings["builder_transition_timeout"]
                    else True
                )
            point = (
                screen.points.get("return")
                if screen.panel == "builder_result"
                else self.reader.match("result_return", frame.image)
            )
            if not self._tap(point):
                return self._fail("Không xác nhận/tap được Return Home")
            self.battle_at = None
            self._return_sent_at = self.clock()
            self._set_phase(BuilderPhase.POST)
            return True
        if screen.kind == ScreenKind.MAIN_HOME:
            self._home_proof = False
            result = self.navigator.navigate(Village.BUILDER, source=Village.MAIN)
            if result.success:
                self.confirmed_village = Village.BUILDER
            return (
                True if result.success or self.stopping() else self._fail(result.reason)
            )
        if screen.panel == "inactivity":
            if not self._tap(screen.points.get("reload")):
                return self._fail("Không reload được popup inactivity builder")
            self.reset_after_reload()
            self.wait(4.0)
            return True
        if screen.panel == "star_reward":
            if self.home_policy:
                self._set_phase(BuilderPhase.POST)
                self.home_policy(self)
                return True
            return self._postprocess()
        if screen.panel == "cart":
            if self.home_policy:
                self._set_phase(BuilderPhase.POST)
                self.home_policy(self)
                return True
            if self.settings["builder_collect_cart"]:
                return self._postprocess(resume_cart=True)
            if not self.rewards._close_cart(time.monotonic() + 15.0):
                return self._fail("Bảng xe đang mở chưa đóng được về Home")
            return self._postprocess()
        if screen.kind == ScreenKind.BUILDER_HOME:
            hold = False
            if self.home_policy:
                if self.phase != BuilderPhase.HOME:
                    self.battle_at = None
                    self._finish_postprocess()
                hold = self.home_policy(self)
                if self.stopping():
                    return True
            elif self.phase != BuilderPhase.HOME:
                # Unexpected Home is reconciled without pretending a result.
                self.battle_at = None
                if not self._postprocess():
                    return False
            proof = self.navigator.confirmed_home(Village.BUILDER)
            if not proof:
                return self._bounded_unknown("Builder Home chưa ổn định")
            self._screen = ModuleScreen.HOME
            self.confirmed_village = Village.BUILDER
            self._home_proof = True
            self._home_at = self.clock()
            if hold or (yield_requested and yield_requested()):
                return True
            self.setup_edits = 0
            if (
                self.settings["builder_auto_setup_baby_dragons"]
                and not self.setup_verified
            ):
                point = self.reader.locate_ui(
                    "army_open", proof[0].image, (0, 580, 130, 135)
                )
                if not self._tap(point):
                    return self._fail("Không nhận diện được nút Choose Army")
                self._set_phase(BuilderPhase.SETUP)
            else:
                if not self._tap(proof[1].points.get("attack")):
                    return self._fail("Không mở được Attack builder")
                self._set_phase(BuilderPhase.SEARCH)
            return True
        if screen.panel == "builder_army":
            return self._setup(frame, screen)
        if screen.kind == ScreenKind.ATTACK_MENU and screen.village == Village.BUILDER:
            if self._find_sent_at is not None:
                return (
                    self._fail("Find Now chưa chuyển màn; không tap lặp")
                    if now - self._find_sent_at
                    > self.settings["builder_prepare_timeout"]
                    else True
                )
            if self.settings["builder_auto_setup_baby_dragons"]:
                lineup = self.reader.read_menu_army(frame.image)
                if not lineup.valid:
                    return self._bounded_unknown(lineup.reason)
                if any(
                    s.kind != "baby_dragon" for s in lineup.slots if s.role != "hero"
                ):
                    self.setup_verified = False
                    if not self._tap(
                        self.reader.locate_ui(
                            "menu_close", frame.image, (1260, 90, 170, 160)
                        )
                    ):
                        return self._fail("Combo đổi; chưa đóng được menu để sửa")
                    self._set_phase(BuilderPhase.HOME)
                    return True
            if not self._tap(self.reader.match("builder_find", frame.image)):
                return self._fail("Không nhận diện/tap được Find Now")
            self.tactics.reset_battle()
            self.stage = 0
            self.seen_fight = False
            self.battle_at = None
            self._result_counted = False
            self._return_sent_at = None
            self._find_sent_at = self.clock()
            self._metrics["attack_count"] += 1
            self._set_phase(BuilderPhase.SEARCH)
            return True
        if screen.kind == ScreenKind.BATTLE and screen.village == Village.BUILDER:
            return self._battle(frame)
        if self.battle_at is not None:
            if self.phase != BuilderPhase.TRANSITION:
                self._set_phase(BuilderPhase.TRANSITION)
            if now - self.phase_at > self.settings["builder_transition_timeout"]:
                return self._fail("Timeout chuyển khu/nhận diện builder")
            return True
        return self._bounded_unknown(screen.reason)

    def _bounded_unknown(self, reason):
        timeout = self.settings["builder_prepare_timeout"]
        if self.clock() - self.phase_at > timeout:
            return self._fail("Timeout chuẩn bị builder: " + reason)
        self._home_proof = False
        return True

    def _setup(self, frame, screen):
        if self.clock() - self.phase_at > self.settings["builder_prepare_timeout"]:
            return self._fail("Timeout Choose Army builder")
        army = self.reader.read_army(frame.image)
        if self.setup_pending_empty and not army.choice:
            return self._fail(
                "Rồng con chưa mở/không đọc được sau khi mở một ô; không xóa thêm quân"
            )
        if not army.valid:
            return self._bounded_unknown(army.reason)
        troops = [s for s in army.slots if s.role != "hero"]
        wrong = [s for s in troops if s.kind != "baby_dragon"]
        if self.setup_edits >= 16 and (wrong or army.choice):
            return self._fail("Thiết lập Rồng con chưa hoàn tất sau 16 sửa đổi")
        if army.choice:
            before = {(s.role, s.point, s.kind) for s in troops}
            if not self._tap(army.choice):
                return self._fail("Rồng con chưa mở/không khả dụng")
            self.setup_edits += 1
            check = self.reader.read_army(self.reader.capture().image)
            after = {(s.role, s.point, s.kind) for s in check.slots if s.role != "hero"}
            if (
                not check.valid
                or len(after) <= len(before)
                or not any(k == "baby_dragon" for _, _, k in after - before)
            ):
                return self._fail("Thêm Rồng con chưa xác nhận; không bấm lặp")
            self.setup_pending_empty = False
            return True
        if wrong:
            if wrong[0].kind == "unknown":
                return self._fail("Loại quân/ô chưa nhận diện; không xóa ô không rõ")
            if not self._tap(wrong[0].remove):
                return self._fail("Không sửa được ô quân builder")
            self.setup_edits += 1
            after = self.reader.capture()
            check = self.reader.read_army(after.image)
            if not check.valid or len(check.slots) >= len(army.slots):
                return self._fail("Bỏ ô chưa có receipt; không xóa tiếp")
            # Fill this vacancy before touching another camp. A locked/unknown
            # baby chooser must never cause the rest of the army to be removed.
            self.setup_pending_empty = True
            return True
        # A disabled chooser is only valid when all observed occupied camps
        # already hold dragons. Empty/locked unlabelled placeholders are skipped.
        if not army.complete:
            return self._fail(
                "Rồng con chưa mở hoặc ô trống không nhận diện được; không chờ vô hạn"
            )
        self.setup_verified = True
        if not self._tap(screen.points.get("close")):
            return self._fail("Không đóng được Choose Army")
        proof = self.navigator.confirmed_home(Village.BUILDER)
        if not proof:
            return self._fail("Choose Army chưa trở về Home")
        if not self._tap(proof[1].points.get("attack")):
            return self._fail("Không mở được menu builder sau thiết lập")
        self._set_phase(BuilderPhase.SEARCH)
        return True

    def _postprocess(self, *, resume_cart=False):
        self._set_phase(BuilderPhase.POST)
        if resume_cart:
            if not self._collect_cart(resume=True):
                return False
            if self.stopping():
                return True
        result = self.rewards.claim_star_bonus()
        self.last_bonus = result.bonus
        self._metrics["reward_claims"] += result.claims
        if self.stopping():
            return True
        if not result.success:
            return self._fail("Hậu xử lý thưởng: " + result.reason)
        if self.settings["builder_collect_cart"] and not resume_cart:
            if not self._collect_cart():
                return False
            if self.stopping():
                return True
        self._finish_postprocess()
        return True  # COMPLETE is informational; builder-only always continues.

    def _finish_postprocess(self):
        self.tactics.reset_battle()
        self._find_sent_at = None
        self.stage = 0
        self.seen_fight = False
        self._set_phase(BuilderPhase.HOME)

    def _collect_cart(self, *, resume=False):
        self.last_cart = (
            self.rewards.collect_cart(resume=True)
            if resume
            else self.rewards.collect_cart()
        )
        self._metrics["cart_collections"] += int(self.last_cart.collected)
        if self.stopping():
            return True
        if not self.last_cart.success or not self.last_cart.returned_home:
            return self._fail("Hậu xử lý xe: " + self.last_cart.reason)
        return True

    def _battle(self, frame):
        battle = self.reader.battle(frame.image)
        army = self.reader.read_bar(frame.image)
        if not army.valid:
            return self._bounded_battle(army.reason)
        self.bar_unclear_since = None
        now = self.clock()
        if self.battle_at is None:
            self.battle_at = now
            self.last_progress = now
        if self.stage == 0:
            # A process may restart inside stage two. A live reinforcement
            # camp identifies the current stage, without a
            # saved battle coordinate or a fake restoration of spent skills.
            if any(s.role == "reinforcement" for s in army.slots):
                self.stage = 1
            self._new_stage()
        elif battle.preparing and self.seen_fight:
            self.stage_confirmations += 1
            if self.stage_confirmations < 2:
                return True
            if self.stage >= 2:
                return self._fail("Khu builder thứ ba không hỗ trợ; cần đối soát")
            self._new_stage()
        self.tactics.observe(army.slots)
        for slot in army.slots:
            if slot.state == SlotState.DEPLOYED:
                self.tactics.deployed_at.setdefault(slot.key, now)
        signature = tuple(
            (s.key, s.state, s.ability, round(s.health or 0, 1)) for s in army.slots
        )
        damage = cv2.resize(frame.image[659:700, 1470:1575], (24, 8)) // 32
        # With no deployed troops left, an unused optional hero can keep the
        # battle open until its timer expires. A changing native timer proves
        # progress even when damage/army stay constant; the total battle
        # deadline still bounds this wait. Mask white glyphs, not map motion.
        timer = cv2.inRange(
            frame.image[49:91, 735:865], (205, 205, 205), (255, 255, 255)
        )
        timer = cv2.resize(timer, (65, 21), interpolation=cv2.INTER_NEAREST)
        signature = (signature, damage.tobytes(), timer.tobytes())
        if signature != self.progress_signature:
            self.progress_signature = signature
            self.last_progress = now
        if not battle.preparing:
            self.seen_fight = True
        if now - self.last_progress > self.settings["builder_no_progress_timeout"]:
            return self._fail("Watchdog builder: trận không tiến triển trong giới hạn")
        self._set_phase(BuilderPhase.DEPLOY)
        available = [
            s
            for s in army.slots
            if s.state == SlotState.UNDEPLOYED
            and (s.role != "hero" or self.settings["builder_use_available_hero"])
        ]
        # A slow observation cycle may span a hero's entire recharge. Permit
        # at most one skill between deployment attempts while camps remain.
        if available and self._deployment_yield_due:
            self._deployment_yield_due = False
            return self._deploy(frame, available[0])
        for slot in army.slots:
            if self.tactics.skill_due(
                slot, now, self.settings["builder_baby_ability_delay"]
            ):
                self._deployment_yield_due = bool(available)
                return self._ability(slot)
        for slot in army.slots:
            if (
                slot.role == "hero"
                and self.settings["builder_use_available_hero"]
                and slot.state == SlotState.DEPLOYED
                and slot.ability == AbilityState.READY
                and slot.key not in self.tactics.hero_waiting
                and now - self.tactics.hero_attempted.get(slot.key, -1e9)
                > self.settings["builder_hero_ability_interval"]
            ):
                self._deployment_yield_due = bool(available)
                return self._ability(slot)
        if available:
            self._deployment_yield_due = False
            return self._deploy(frame, available[0])
        self._set_phase(BuilderPhase.FIGHT)
        return True

    def _new_stage(self):
        self.stage += 1
        self._metrics["stage_count"] += 1
        self.seen_fight = False
        self.stage_confirmations = 0
        self._deployment_yield_due = False
        self.tactics.reset_stage()
        self.camera_operations = 0
        self.selected = False
        self.bar_unclear_since = None
        self.geometry_unclear_since = None
        self.last_progress = self.clock()
        self.camera.reset_view()

    def _bounded_battle(self, reason, *, geometry=False):
        field = "geometry_unclear_since" if geometry else "bar_unclear_since"
        since = getattr(self, field)
        if since is None:
            since = self.clock()
            setattr(self, field, since)
        if self.clock() - since > self.settings["builder_transition_timeout"]:
            return self._fail("Thanh quân/chuyển khu chưa rõ: " + reason)
        return True

    def _deploy(self, frame, slot):
        if (
            self.tactics.attempts.get(slot.key, 0)
            >= self.settings["builder_point_retries"]
        ):
            return self._fail("Điểm thả bị từ chối quá giới hạn: " + slot.key)
        # Map can change outside our camera API. Never reuse a point after that.
        if self.tactics.reference is not None:
            motion = measure_motion(self.tactics.reference, frame.image)
            if not motion.valid or motion.changed:
                self.adb.mark_camera_input()
        if self.tactics.plan is None:
            plan = self.tactics.build(frame.image, self.adb.camera_revision)
            if (
                plan is None
                and self.settings["camera_auto_adjust"]
                and not self.selected
                and self.camera_operations < 3
            ):
                result = self.camera.zoom(0.65, context="battle", troop_selected=False)
                self.camera_operations += 1
                if result.status not in (CameraStatus.SUCCESS, CameraStatus.UNCHANGED):
                    if result.status == CameraStatus.STOPPED or self.stopping():
                        return True
                    reason = getattr(result, "reason", "")
                    if result.status == CameraStatus.ERROR and reason in (
                        "Ảnh trước chưa ổn định",
                        "Ảnh sau chưa ổn định hoặc không xác nhận được camera",
                    ):
                        # No map input is authorized by an unsettled camera.
                        # Retry only from a fresh tick, within existing budgets.
                        self.last_warning = "Camera chưa ổn định; chờ ảnh mới"
                        return self._bounded_battle(self.last_warning, geometry=True)
                    return self._fail(
                        "Camera builder: " + str(result.status.value) + " · " + reason
                    )
                return True
            if plan is None and not self.selected:
                # Selecting an undeployed camp reveals the red boundary. It is
                # a HUD-only action; no speculative deployment coordinate.
                if not self._tap(slot.point):
                    return self._fail("Không chọn được ô để quan sát biên")
                self.selected = True
                return True
            if plan is None:
                return self._bounded_battle(
                    "Không lập được biên hiện tại; không thả mù", geometry=True
                )
        self.geometry_unclear_since = None
        self.last_warning = None
        # Fresh card state immediately before selection (never ability-tap a
        # deployed card) and fresh geometry before the map input.
        if self.tactics.point(slot, self.adb.camera_revision) is None:
            return self._fail("Không còn điểm thả hợp lệ quanh biên nhìn thấy")
        before = self.reader.capture()
        current = self.reader.read_bar(before.image)
        selected = next((s for s in current.slots if s.key == slot.key), None)
        if not current.valid or not selected or selected.state != SlotState.UNDEPLOYED:
            return True
        revision = self.adb.camera_revision
        if not selected.selected and not self._tap(selected.point):
            return self._fail("Tap chọn quân builder thất bại")
        self.selected = True
        fresh = self.reader.capture()
        if not self.reader.battle(fresh.image).valid or self.stopping():
            return True
        motion = measure_motion(before.image, fresh.image)
        if not motion.valid or motion.changed or revision != self.adb.camera_revision:
            self.adb.mark_camera_input()
            return True
        # Selecting an undeployed camp reveals the actual forbidden boundary.
        # Replace pre-selection structure probes before sending a map tap.
        if self.tactics.plan is None:
            return True
        if self.tactics.plan.source == "builder_visual_footprint":
            if self.tactics.build(fresh.image, revision) is None:
                return self._bounded_battle("Biên sau chọn quân chưa rõ", geometry=True)
        point = self.tactics.point(slot, revision)
        if not point:
            return self._fail("Không còn điểm thả hợp lệ quanh biên nhìn thấy")
        if not self._tap(point):
            return self._fail("Input thả quân builder thất bại/chưa đối soát")
        deployed = False
        for _ in range(3):
            after = self.reader.capture()
            check = self.reader.read_bar(after.image)
            observed = next((s for s in check.slots if s.key == slot.key), None)
            if (
                check.valid
                and observed
                and observed.state in (SlotState.DEPLOYED, SlotState.DEAD)
            ):
                deployed = True
                break
            if self.stopping() or not self.reader.battle(after.image).valid:
                return True
            self.wait()
        self.tactics.receipt(slot, point, deployed, self.clock())
        if deployed:
            self._metrics["deployed"] += 1
            self.last_progress = self.clock()
        else:
            self._metrics["rejected_points"] += 1
        return True

    def _ability(self, slot):
        before = self.reader.read_bar(self.reader.capture().image)
        current = next((s for s in before.slots if s.key == slot.key), None)
        if (
            not before.valid
            or not current
            or current.state != SlotState.DEPLOYED
            or current.ability != AbilityState.READY
        ):
            return True
        if slot.role == "hero":
            self.tactics.hero_attempted[slot.key] = self.clock()
            self.tactics.hero_waiting.add(slot.key)
        else:
            self.tactics.attempted_abilities.add(slot.key)
        if not self._tap(current.point):
            return self._fail("Input kỹ năng chưa đối soát: " + slot.key)
        for _ in range(4):
            after = self.reader.capture()
            check = self.reader.read_bar(after.image)
            observed = next((s for s in check.slots if s.key == slot.key), None)
            if check.valid and observed and observed.state == SlotState.DEAD:
                # Death is not an ability receipt. Retain the attempted ledger,
                # report uncertainty and continue with the remaining live army.
                self._metrics["unconfirmed_abilities"] += 1
                self.last_warning = "Kỹ năng chưa đối soát trước khi chết: " + slot.key
                return True
            expected = (
                AbilityState.CHARGING if slot.role == "hero" else AbilityState.USED
            )
            if (
                check.valid
                and observed
                and observed.state == SlotState.DEPLOYED
                and observed.ability == expected
            ):
                if slot.role == "hero":
                    self.tactics.hero_waiting.discard(slot.key)
                    self._metrics["hero_abilities"] += 1
                else:
                    self.tactics.used_abilities.add(slot.key)
                    self._metrics["troop_abilities"] += 1
                self.last_progress = self.clock()
                return True
            if self.stopping() or not self.reader.battle(after.image).valid:
                return True
            self.wait()
        # A tap is not proof. One-shot troops are never tapped again; hero also
        # stays disarmed until a charging frame then fresh READY is observed.
        return self._fail(
            "Kỹ năng chưa có receipt đổi state; không bấm lặp: " + slot.key
        )
