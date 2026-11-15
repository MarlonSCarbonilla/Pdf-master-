"""Small rotating-file logger stored in %APPDATA%/PDFMaster/logs."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import logging
import os
from logging.handlers import RotatingFileHandler


def data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "PDFMaster")
    os.makedirs(path, exist_ok=True)
    return path


def get_logger(name: str = "pdfmaster") -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    try:
        logs = os.path.join(data_dir(), "logs")
        os.makedirs(logs, exist_ok=True)
        h = RotatingFileHandler(os.path.join(logs, "app.log"), maxBytes=512_000, backupCount=2, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
    except OSError:
        log.addHandler(logging.NullHandler())
    return log
