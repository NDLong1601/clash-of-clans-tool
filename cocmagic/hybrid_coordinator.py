"""Hybrid policy in the input-owning worker; wall schedule, monotonic budgets."""

from datetime import datetime, timedelta, timezone
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cocmagic.builder_screen_reader import StarBonusState, Village, ScreenKind
from cocmagic.run_coordinator import RunCoordinator
from cocmagic.village_module import ModuleScreen
from cocmagic.recovery import RuntimeWriteError


def vietnam_timezone():
    try:
        return ZoneInfo("Asia/Ho_Chi_Minh")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=7), "UTC+07:00")


class HybridClock:
    def __init__(self):
        self.tz = vietnam_timezone()

    def now(self):
        return datetime.now(self.tz)

    def monotonic(self):
        return time.monotonic()


class HybridCoordinator(RunCoordinator):
    def __init__(
        self, serial, modules, store, settings, *, stop_event=None, clock=None
    ):
        builder = modules["builder"]
        super().__init__(
            serial,
            modules,
            "builder",
            stop_event=stop_event,
            switch_village=builder.navigator.switch_village,
        )
        self.clock = clock or HybridClock()
        self.tz = vietnam_timezone()
        self.hour, self.minute = map(int, settings["hybrid_check_time"].split(":"))
        self.budget = settings["hybrid_builder_budget_seconds"]
        self.max_battles = settings["hybrid_max_battles"]
        self.store = store
        self.runtime = store.load()
        # Persisted COMPLETE is historical, never permission to skip startup.
        self.runtime.pending_builder_check = True
        self.runtime.pending_reason = "startup"
        self.runtime.last_bonus_state = "unknown"
        self.runtime.bonus_progress = None
        self.runtime.builder_incomplete = True
        self.runtime.retry_count = 0
        self.runtime.retry_date = None
        self.runtime.next_retry_at = None
        self.reason = "Startup: xác nhận Làng đêm và đọc thưởng sao"
        self._retry_deadline = None
        self._unknown_deadline = 0.0
        self._unknown_attempts = 0
        self._return_error = None
        self._cycle_started = self.clock.monotonic()
        self._cycle_battles = builder.metrics["battle_count"]
        self._last_progress = None
        self._same_progress_battles = 0
        self._observed_battles = self._cycle_battles
        self._observed_claims = builder.metrics["reward_claims"]
        self._startup_classified = False
        builder.home_policy = self._builder_home
        self.store.save(self.runtime)

    def now(self):
        now = self.clock.now()
        if now.utcoffset() is None:
            raise ValueError("Hybrid wall clock phải có timezone")
        return now.astimezone(self.tz)

    def cutoff(self, now):
        return now.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)

    def _save(self):
        try:
            self.store.save(self.runtime)
        except OSError as error:
            self._halt_reason = str(error)
            self.runtime.last_error = str(error)
            self.runtime.builder_incomplete = True
            self.runtime.pending_builder_check = True
            raise RuntimeWriteError(str(error)) from error

    def reset_after_reload(self):
        super().reset_after_reload()
        self._startup_classified = False
        self.runtime.last_bonus_state = "unknown"
        self.runtime.bonus_progress = None
        self.runtime.builder_incomplete = True
        self.runtime.pending_builder_check = True
        self.runtime.pending_reason = "recovery"
        self.reason = "Recovery: chờ game và đọc lại làng/thưởng, chưa hoàn thành"
        if self.active_id == "main":
            self.request_switch("builder", self.reason)
        # Keep cycle/retry budgets: reload must not buy another infinite trip.
        self._save()

    def _poll_schedule(self):
        if self.stopping():
            return
        now = self.now()
        runtime = self.runtime
        due = (
            now >= self.cutoff(now)
            and runtime.last_daily_check_date != now.date().isoformat()
        )
        if due and runtime.last_daily_request_date != now.date().isoformat():
            # Morning startup/retries never spend the scheduled window's
            # budget. This is a request marker, NOT a successful daily check.
            runtime.last_daily_request_date = now.date().isoformat()
            runtime.retry_count = 0
            runtime.next_retry_at = None
            self._retry_deadline = None
            self._save()
        if self.active_id == "builder":
            builder = self.modules["builder"]
            if (
                self.clock.monotonic() - self._cycle_started >= self.budget
                or builder.metrics["battle_count"] - self._cycle_battles
                >= self.max_battles
            ):
                self._return_error = (
                    self._return_error
                    or "Hết ngân sách chuỗi thưởng builder; chưa hoàn thành"
                )
            return
        new_day = runtime.retry_date != now.date().isoformat()
        retry = runtime.pending_builder_check and runtime.last_error is not None
        if not due and not retry:
            return
        if not new_day and runtime.retry_count >= 3:
            return
        if (
            not new_day
            and self._retry_deadline is not None
            and self.clock.monotonic() < self._retry_deadline
        ):
            return
        if self.pending is None:
            runtime.pending_builder_check = True
            runtime.builder_incomplete = True
            runtime.pending_reason = "daily" if due else "retry"
            self.reason = (
                "Đến lịch kiểm tra thưởng" if due else "Thử lại kiểm tra builder"
            )
            self.request_switch("builder", self.reason)
            self._save()

    def _switch_requested(self):
        # Farm's pre-Attack callback also polls after a long train/wall tick.
        self._poll_schedule()
        return super()._switch_requested()

    def _record(self, bonus):
        runtime = self.runtime
        runtime.last_bonus_state = bonus.state.value
        runtime.bonus_progress = (
            list(bonus.progress) if bonus.progress is not None else None
        )
        if bonus.state in (StarBonusState.AVAILABLE, StarBonusState.COMPLETE):
            now = self.now()
            runtime.last_valid_bonus_check_at = now.isoformat()
            if now >= self.cutoff(now):
                runtime.last_daily_check_date = now.date().isoformat()
            runtime.pending_builder_check = False
            runtime.pending_reason = None
            runtime.next_retry_at = None
            runtime.last_error = None
            runtime.builder_incomplete = bonus.state != StarBonusState.COMPLETE
            self._unknown_attempts = 0
        self._save()

    def _finish_error(self, message):
        runtime = self.runtime
        runtime.last_error = message
        runtime.builder_incomplete = True
        runtime.pending_builder_check = True
        runtime.pending_reason = "retry"
        now = self.now()
        if runtime.retry_date != now.date().isoformat():
            runtime.retry_count = 0
        runtime.retry_date = now.date().isoformat()
        runtime.retry_count += 1
        self._retry_deadline = self.clock.monotonic() + 300.0
        runtime.next_retry_at = (
            (now + timedelta(seconds=300)).isoformat()
            if runtime.retry_count < 3
            else None
        )
        self.reason = message + " · về main nếu xác nhận được Home"
        self._save()

    def _cart_before_main(self, builder):
        # Hybrid departure always checks the cart, even with builder-only
        # collection disabled. No waiting for unfinished defenses.
        cart = builder.rewards.collect_cart()
        builder.last_cart = cart
        builder._metrics["cart_collections"] += int(cart.collected)
        if self.stopping():
            return False
        if not cart.success or not cart.returned_home:
            self._return_error = (
                self._return_error or "Thu xe trước main: " + cart.reason
            )
            if not builder.navigator.confirmed_home(Village.BUILDER):
                self._halt_reason = (
                    "Thu xe lỗi và chưa xác nhận Home; dừng riêng instance"
                )
                self._finish_error(self._return_error)
                return False
        return True

    def _builder_home(self, builder):
        """Return True to hold at Home; called before any builder setup/Attack."""
        if self.stopping():
            return True
        if self.pending is not None and self.pending.target == "main":
            return True
        self._poll_schedule()
        if self._return_error:
            if self._cart_before_main(builder):
                self._finish_error(self._return_error)
                self.request_switch("main", self.reason)
            return True
        if self.clock.monotonic() < self._unknown_deadline:
            return True
        frame = builder.reader.capture()
        screen = builder.reader.classify(frame.image)
        if screen.panel == "cart":
            cart = builder.rewards.collect_cart(resume=True)
            builder.last_cart = cart
            builder._metrics["cart_collections"] += int(cart.collected)
            if not cart.success or not cart.returned_home:
                self._return_error = "Bảng xe chưa đối soát: " + cart.reason
                return True
        bonus = self._observe_bonus(builder)
        if bonus is None:
            return True
        if bonus.state == StarBonusState.AVAILABLE:
            battles = builder.metrics["battle_count"]
            signature = bonus.progress
            if battles != self._observed_battles and signature is not None:
                self._same_progress_battles = (
                    self._same_progress_battles + 1
                    if signature == self._last_progress
                    and builder.metrics["reward_claims"] == self._observed_claims
                    else 0
                )
            self._observed_battles = battles
            self._observed_claims = builder.metrics["reward_claims"]
            self._last_progress = signature
            if self._same_progress_battles >= 4:
                self._return_error = (
                    "Tiến độ sao không đổi qua nhiều trận; chưa hoàn thành"
                )
                return True
            self.reason = "Còn thưởng sao · tiếp tục Làng đêm"
            return False
        self.reason = "Đã xác nhận hết sao · thu xe rồi về Làng chính"
        if self._cart_before_main(builder):
            if self._return_error:
                self._finish_error(self._return_error)
            else:
                # Cart/defense effects can expose another task. A new reward
                # panel is handled and Attack is read again before departure.
                after_cart = self._observe_bonus(builder)
                if after_cart is None:
                    return True
                if after_cart.state == StarBonusState.AVAILABLE:
                    self.reason = "Sau thu xe còn thưởng sao · tiếp tục Làng đêm"
                    return False
            self.request_switch("main", self.reason)
        return True

    def _observe_bonus(self, builder):
        result = builder.rewards.claim_star_bonus()
        builder.last_bonus = result.bonus
        builder._metrics["reward_claims"] += result.claims
        if self.stopping():
            return None
        if result.success:
            self._record(result.bonus)
        if not result.success or result.bonus.state not in (
            StarBonusState.AVAILABLE,
            StarBonusState.COMPLETE,
        ):
            self._unknown_attempts += 1
            self.runtime.last_bonus_state = "unknown"
            self.runtime.bonus_progress = None
            self.runtime.last_error = "Chưa đọc hợp lệ thưởng: " + result.reason
            self.runtime.builder_incomplete = True
            self.runtime.pending_builder_check = True
            self.runtime.pending_reason = "unknown"
            self._unknown_deadline = self.clock.monotonic() + 15.0
            self.runtime.next_retry_at = (
                self.now() + timedelta(seconds=15)
            ).isoformat()
            self._save()
            if self._unknown_attempts >= 3:
                self._return_error = "UNKNOWN sau 3 lần đọc; chưa hoàn thành thưởng"
            return None
        self._unknown_deadline = 0.0
        return result.bonus

    def _recover_builder(self, error):
        """Only fresh clear Home permits fallback; battle/modal never does."""
        builder = self.modules["builder"]
        self._return_error = error
        self._finish_error(error)
        proof = builder.navigator.confirmed_home()
        if not proof:
            self._halt_reason = (
                error + "; không xác nhận Home để phục hồi, dừng riêng instance"
            )
            return False
        if proof[1].village == Village.BUILDER:
            if not self._cart_before_main(builder):
                return False
            if not builder.navigator.navigate(
                Village.MAIN, source=Village.BUILDER
            ).success:
                self._halt_reason = error + "; chưa xác nhận về main"
                return False
        elif proof[1].village != Village.MAIN:
            self._halt_reason = error + "; làng chưa rõ"
            return False
        if self.stopping():
            return True
        # The old builder is never ticked again until resume invalidates it.
        self.active_id = "main"
        self._confirmed_village = "main"
        self.modules["main"].resume()
        with self._request_lock:
            self._pending = None
        return True

    def tick(self):
        with self._input_lock:
            if self.stopping():
                return True
            if self._halt_reason:
                return False
            if not self._startup_classified:
                self._startup_classified = True
                builder = self.modules["builder"]
                frame = builder.reader.capture()
                screen = builder.reader.classify(frame.image)
                # A restart in a main battle must finish the main transaction
                # before startup navigation. Home itself is handled by builder.
                main = self.modules["main"]
                if screen.village == Village.BUILDER:
                    self.active_id = "builder"
                    builder._suspended = False
                    with self._request_lock:
                        self._pending = None
                main_transaction = (
                    screen.village is None
                    and hasattr(main, "_classify_screen")
                    and main._classify_screen(frame.image)
                    in (
                        ModuleScreen.BATTLE,
                        ModuleScreen.SCOUT,
                        ModuleScreen.RESULT,
                        ModuleScreen.MENU,
                    )
                )
                if (
                    screen.village == Village.MAIN
                    and screen.kind != ScreenKind.MAIN_HOME
                ) or main_transaction:
                    self.active_id = "main"
                    self.modules["main"].reset_after_reload()
                    self.request_switch("builder", self.reason)
            self._poll_schedule()
            before = self.active_id
            okay = super().tick()
            if not okay and before == "builder" and self._halt_reason is None:
                okay = self._recover_builder(
                    self.modules["builder"].halt_reason or "Builder không tiến triển"
                )
            if not okay:
                self.runtime.last_error = self.halt_reason
                self.runtime.builder_incomplete = True
                self.runtime.pending_builder_check = True
                self.runtime.pending_reason = "error"
                self._save()
            if self.active_id == "builder" and before != "builder":
                self._cycle_started = self.clock.monotonic()
                self._cycle_battles = self.modules["builder"].metrics["battle_count"]
                self._unknown_attempts = 0
                self._unknown_deadline = 0.0
                self._return_error = None
                self._same_progress_battles = 0
                self._last_progress = None
                self._observed_battles = self._cycle_battles
                self._observed_claims = self.modules["builder"].metrics["reward_claims"]
            return okay

    def status(self):
        result = super().status()
        now = self.now()
        next_check = self.cutoff(now)
        if self.runtime.last_daily_check_date == now.date().isoformat():
            next_check += timedelta(days=1)
        return {
            **result,
            "run_mode": "hybrid",
            "hybrid_reason": self.reason,
            "builder_bonus_state": self.runtime.last_bonus_state,
            **vars(self.runtime),
            "next_daily_check_at": next_check.isoformat(),
        }
