"""Small synchronous contract shared by village farming modules."""

from enum import Enum
from typing import Callable, Protocol


class ModuleScreen(str, Enum):
    UNKNOWN = "unknown"
    HOME = "home"
    MENU = "menu"
    SCOUT = "scout"
    BATTLE = "battle"
    RESULT = "result"
    MODAL = "modal"


class VillageModule(Protocol):
    device_serial: str
    halt_reason: str | None

    def tick(self, *, yield_requested: Callable[[], bool] | None = None) -> bool:
        """Finish current work; check the request immediately before a new match."""
        ...

    @property
    def confirmed_screen(self) -> ModuleScreen:
        """Last recognized screen; UNKNOWN after invalidation, never permission to yield alone."""
        ...

    @property
    def can_yield(self) -> bool:
        """Fresh Home observation, no modal, batch or unfinished reconciliation."""
        ...

    @property
    def status_line(self) -> str: ...

    @property
    def metrics(self) -> dict[str, int]: ...

    def suspend(self) -> None:
        """Only at can_yield; keep session setup and statistics."""
        ...

    def resume(self) -> None:
        """After confirmed village navigation; invalidate screen/map coordinates."""
        ...

    def reset_after_reload(self) -> None:
        """Abort stale input and classify a new frame before acting."""
        ...

    def invalidate_after_popup(self) -> None:
        """Reclassify without discarding battle work for a dismiss-only popup."""
        ...
