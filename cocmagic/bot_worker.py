"""One bot per process so stdout and mutable module state stay isolated."""

from contextlib import redirect_stderr, redirect_stdout
import traceback


class EventWriter:
    def __init__(self, events):
        self.events = events

    def write(self, value):
        if value:
            self.events.put({"kind": "log", "text": str(value)})

    def flush(self):
        pass


def run_instance(serial: str, settings: dict, events, stop_event):
    # Imports stay inside the child process. Tk is never imported here.
    from cocmagic.bot_engine import BotEngine
    from cocmagic.license_client import LicenseClient, LicenseError

    writer = EventWriter(events)
    result = False
    try:
        with redirect_stdout(writer), redirect_stderr(writer):
            client = LicenseClient.from_config()
            if client.policy.enabled:
                try:
                    client.check()
                except LicenseError as error:
                    print(f"[License] {error}; bot trên {serial} không được khởi động.")
                    return
            engine = BotEngine(settings.copy(), device_serial=serial,
                               stop_event=stop_event,
                               status_callback=lambda value: events.put(
                                   {"kind": "status", **value}))
            result = engine.start()
    except BaseException:
        events.put({"kind": "log", "text": traceback.format_exc()})
    finally:
        events.put({"kind": "done", "stopped": stop_event.is_set(),
                    "ok": bool(result)})
