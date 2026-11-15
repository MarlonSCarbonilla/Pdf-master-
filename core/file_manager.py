"""OS-facing file helpers."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os
import subprocess
import sys


def move_to_trash(path: str) -> None:
    """Send a file to the Recycle Bin (never a permanent delete)."""
    from send2trash import send2trash  # imported lazily

    send2trash(os.path.abspath(path))


def open_folder(path: str, select_file: bool = False) -> None:
    """Open a folder in Explorer, optionally selecting a file inside it."""
    if sys.platform != "win32":
        return
    if select_file and os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        os.startfile(folder)  # type: ignore[attr-defined]
