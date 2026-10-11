"""Use the production VM lease before any live probe can send input."""

from contextlib import contextmanager
from pathlib import Path

from cocmagic import config
from cocmagic.device_manager import resolve_device_ownership
from cocmagic.hybrid_runtime import HybridRuntimeStore


@contextmanager
def owned_input(adb):
    ownership = resolve_device_ownership(adb.adb, adb.device)
    store = HybridRuntimeStore(
        Path(config.DATA_DIR) / "runtime",
        adb.device,
        device_identity=ownership.identity,
        runtime_serial=ownership.runtime_serial,
        legacy_serials=ownership.aliases,
    )
    # Acquire outside the finally block: a rejected probe must not release
    # the gestures of the worker that already owns this VM.
    store.acquire()
    try:
        yield store
    finally:
        try:
            adb.release_touch()
        finally:
            store.close()
