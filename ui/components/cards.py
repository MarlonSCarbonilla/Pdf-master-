from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    import main as _main_bootstrap  # noqa: F401

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.components.icons import icon

ACCENT = "#e5322d"


class ToolCard(QPushButton):
    """Clickable rounded card: icon + title + description."""

    def __init__(self, title: str, desc: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("toolcard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(74)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        ic = QLabel()
        ic.setPixmap(icon(icon_name, ACCENT, 30).pixmap(30, 30))
        ic.setAttribute(Qt.WA_TransparentForMouseEvents)
        ic.setFixedWidth(36)
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("h2")
        d = QLabel(desc)
        d.setObjectName("muted")
        d.setWordWrap(True)
        for w in (t, d):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            w.setStyleSheet("background: transparent; border: none;")
        col.addWidget(t)
        col.addWidget(d)
        lay.addLayout(col, 1)
        self.setToolTip(desc)


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main())
