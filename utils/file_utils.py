"""Filesystem helpers: safe (atomic) writes, unique names, size formatting, checks."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from core.common import ProcessingError


def human_size(num: float) -> str:
    """Format a byte count, e.g. 1536 -> '1.5 KB'."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} GB"


def safe_filename(name: str) -> str:
    """Strip characters that are illegal in Windows file names."""
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if c in bad or ord(c) < 32 else c for c in name).strip(" .")
    return cleaned or "output"


def unique_path(path: str | os.PathLike) -> str:
    """Return `path` or 'name (1).ext', 'name (2).ext'... so nothing is overwritten."""
    p = Path(path)
    if not p.exists():
        return str(p)
    i = 1
    while True:
        cand = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not cand.exists():
            return str(cand)
        i += 1


def ensure_output_dir(directory: str) -> None:
    """Create the directory if needed and verify that we can write into it."""
    if not directory:
        raise ProcessingError("Please choose an output folder.")
    try:
        os.makedirs(directory, exist_ok=True)
        fd, probe = tempfile.mkstemp(dir=directory, prefix=".pdfm_probe_")
        os.close(fd)
        os.remove(probe)
    except OSError:
        raise ProcessingError(f"The output folder is not writable:\n{directory}") from None


def check_disk_space(directory: str, needed_bytes: int) -> None:
    """Raise if the target drive clearly lacks the space (best effort)."""
    try:
        free = shutil.disk_usage(directory).free
    except OSError:
        return
    if free < needed_bytes + 20 * 1024 * 1024:
        raise ProcessingError(
            f"Not enough free disk space in {directory} "
            f"(free: {human_size(free)}, needed about: {human_size(needed_bytes)})."
        )


def atomic_write(final_path: str, writer: Callable[[str], None]) -> str:
    """Write via a temp file in the target folder, publish with os.replace on success.

    `writer(tmp_path)` must create the file at tmp_path. The final file is only
    touched after the writer returned without error; on failure the temp file is removed.
    """
    folder = os.path.dirname(os.path.abspath(final_path))
    ext = os.path.splitext(final_path)[1]
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".pdfm_", suffix=ext + ".tmp")
    os.close(fd)
    try:
        writer(tmp)
        os.replace(tmp, final_path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return final_path
