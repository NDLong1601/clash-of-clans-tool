"""Subprocess execution for desktop operations that do not need a console."""

import os
import subprocess


def run_hidden(*args, **kwargs):
    """Keep console executables such as ADB invisible when started by pythonw."""
    if os.name == "nt":
        kwargs["creationflags"] = (
            kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        )
    return subprocess.run(*args, **kwargs)
