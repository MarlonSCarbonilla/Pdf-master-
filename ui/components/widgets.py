"""Tiny layout helpers for option panels."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    import main as _main_bootstrap  # noqa: F401

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


def hint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("muted")
    lab.setWordWrap(True)
    return lab


def labeled(label: str, widget: QWidget) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(QLabel(label))
    lay.addWidget(widget, 1)
    return w


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main())
