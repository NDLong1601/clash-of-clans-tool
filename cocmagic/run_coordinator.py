"""One synchronous input owner per worker/ADB serial; no village navigation here."""

from dataclasses import dataclass
import threading
from typing import Callable

from cocmagic.village_module import VillageModule, ModuleScreen
from cocmagic.recovery import RecoveryInterrupted


@dataclass(frozen=True)
class SwitchRequest:
    target: str
    reason: str


class RunCoordinator:
    def __init__(
        self,
        serial: str,
        modules: dict[str, VillageModule],
        active: str,
        stop_event=None,
        switch_village: Callable[[str, str], bool] | None = None,
    ):
        if active not in modules or any(
            m.device_serial != serial for m in modules.values()
        ):
            raise ValueError(
                "Coordinator cần các module cùng serial và module active hợp lệ."
            )
        self.serial = serial
        self.modules = dict(modules)
        self.active_id = active
        self.stop_event = stop_event
        # GĐ4 supplies navigation which must confirm the destination. Absence
        # deliberately leaves requests pending, never fakes a village switch.
        self.switch_village = switch_village
        self._input_lock = threading.RLock()
        self._request_lock = threading.Lock()
        self._pending: SwitchRequest | None = None
        self._ticking = False
        self._transition_target: str | None = None
        self._halt_reason: str | None = None
        self._confirmed_village = None

    @property
    def active(self) -> VillageModule:
        return self.modules[self.active_id]

    @property
    def pending(self) -> SwitchRequest | None:
        with self._request_lock:
            return self._pending

    def request_switch(self, target: str, reason: str) -> None:
        if target not in self.modules:
            raise ValueError(f"Module {target} chưa khả dụng.")
        with self._request_lock:
            self._pending = (
                SwitchRequest(target, reason)
                if target != self.active_id or self._transition_target is not None
                else None
            )

    def _switch_requested(self) -> bool:
        return self.pending is not None

    def stopping(self) -> bool:
        return self.stop_event is not None and self.stop_event.is_set()

    def exclusive(self, action):
        """Engine popup input uses the same lock as ticks and navigation.

        Recovery callbacks may reenter this lock on the tick's thread. Modules
        must not launch background input tasks or call another module directly.
        """
        with self._input_lock:
            if self.stopping():
                return False
            return action()

    def tick(self) -> bool:
        with self._input_lock:
            if self.stopping():
                return True
            if self.halt_reason:
                return False
            if self._ticking:
                raise RuntimeError("Không được tick lồng nhau trên cùng serial.")
            self._ticking = True
            try:
                if not self.active.tick(yield_requested=self._switch_requested):
                    return False
                village = getattr(self.active, "confirmed_village", None)
                if village is not None:
                    self._confirmed_village = village.value
                elif (
                    self.active.confirmed_screen != ModuleScreen.UNKNOWN
                    and not hasattr(self.active, "confirmed_village")
                ):
                    self._confirmed_village = self.active_id
                else:
                    self._confirmed_village = None
                request = self.pending
                if (
                    self.stopping()
                    or request is None
                    or not self.active.can_yield
                    or self.switch_village is None
                ):
                    return True
                source = self.active_id
                try:
                    with self._request_lock:
                        # The request may have been canceled/replaced after the
                        # tick. Re-read it before claiming the navigation input.
                        request = self._pending
                        if request is None:
                            return True
                        self._transition_target = request.target
                    if self.stopping():
                        return True
                    self.active.suspend()
                    if self.stopping():
                        return True
                    confirmed = self.switch_village(source, request.target)
                    if self.stopping():
                        return True
                    if confirmed is not True:
                        self._halt_reason = (
                            "Chuyển làng chưa xác nhận được đích; dừng để kiểm tra."
                        )
                        return False
                    self.active_id = request.target
                    self._confirmed_village = request.target
                    self.active.resume()
                except RecoveryInterrupted:
                    raise
                except Exception as error:
                    if self.stopping():
                        return True
                    self._halt_reason = f"Chuyển làng thất bại: {error}"
                    return False
                finally:
                    with self._request_lock:
                        self._transition_target = None
                with self._request_lock:
                    # A newer request arriving during navigation stays pending.
                    if self._pending is request or (
                        self._pending is not None
                        and self._pending.target == self.active_id
                    ):
                        self._pending = None
                return True
            finally:
                self._ticking = False

    def reset_after_reload(self):
        with self._input_lock:
            self._confirmed_village = None
            for module in self.modules.values():
                module.reset_after_reload()
            # Recovery may interrupt navigation after suspend but before resume.
            if hasattr(self.active, "_suspended"):
                self.active._suspended = False
            with self._request_lock:
                self._pending = None

    def invalidate_after_popup(self):
        with self._input_lock:
            self.active.invalidate_after_popup()

    @property
    def halt_reason(self) -> str | None:
        return self._halt_reason or self.active.halt_reason

    def status(self) -> dict:
        with self._input_lock:
            request = self.pending
            metrics = {
                key: dict(module.metrics) for key, module in self.modules.items()
            }
            return {
                "status": self.halt_reason or self.active.status_line,
                "serial": self.serial,
                "active_module": self.active_id,
                "run_mode": self.active_id,
                "actual_village": self._confirmed_village or "unknown",
                "confirmed_screen": self.active.confirmed_screen.value,
                "halt_reason": self.halt_reason,
                "switch_target": request.target if request else None,
                "switch_reason": request.reason if request else None,
                "module_metrics": metrics,
                "wall_count": sum(m.get("wall_count", 0) for m in metrics.values()),
                "builder_bonus_state": (
                    getattr(
                        getattr(self.active, "last_bonus", None), "state", None
                    ).value
                    if getattr(self.active, "last_bonus", None) is not None
                    else None
                ),
                "builder_stage": getattr(self.active, "stage", None),
                "builder_can_yield": self.active.can_yield
                if self.active_id == "builder"
                else None,
            }
