"""Parent-side lifecycle and event routing for an emulator bot process."""

import multiprocessing
import queue
from copy import deepcopy

from cocmagic.bot_worker import run_instance


class BotSession:
    def __init__(self, serial: str, worker_target=run_instance, context=None):
        self.serial = serial
        self.worker_target = worker_target
        self.context = context or multiprocessing.get_context("spawn")
        self.process = None
        self.events = None
        self.stop_event = None
        self._reported_exit = False

    def is_alive(self) -> bool:
        return self.process is not None and self.process.is_alive()

    def start(self, settings: dict) -> None:
        if self.is_alive():
            raise RuntimeError(f"Bot trên {self.serial} đang chạy.")
        if self.events is not None:
            self.events.close()
            self.events = None
        self.events = self.context.Queue()
        self.stop_event = self.context.Event()
        self._reported_exit = False
        self.process = self.context.Process(
            target=self.worker_target,
            args=(self.serial, deepcopy(settings), self.events, self.stop_event),
            name=f"CocMagic-{self.serial}",
        )
        try:
            self.process.start()
        except Exception:
            self.events.close()
            self.process = None
            self.events = None
            self.stop_event = None
            raise

    def stop(self) -> None:
        if self.is_alive():
            self.stop_event.set()

    def poll(self, limit: int = 250) -> list[dict]:
        items = []
        drained = False
        if self.events is not None:
            for _ in range(limit):
                try:
                    event = self.events.get_nowait()
                    if isinstance(event, dict) and event.get('serial', self.serial) == self.serial:
                        items.append(event)
                except queue.Empty:
                    drained = True
                    break
        if (self.process is not None and not self.is_alive() and
                not self._reported_exit and drained):
            self.process.join(timeout=0)
            items.append({"kind": "exited", "code": self.process.exitcode})
            self._reported_exit = True
        return items

    def terminate(self) -> None:
        """Only for explicit forced shutdown after cooperative stop stalls."""
        if self.is_alive():
            self.process.terminate()
            self.process.join(timeout=3)
