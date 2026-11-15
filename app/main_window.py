from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from app.navigation import SIDEBAR, TOOL_BY_ID, UPCOMING
from app.settings import Settings
from app.theme import stylesheet
from ui.components.icons import icon


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("PDF Master")
        self.resize(1200, 760)
        self.setMinimumSize(950, 650)
        self.setAcceptDrops(True)
        self.pages: dict[str, QWidget] = {}
        self._history: list[str] = []
        self._current = ""

        root = QWidget()
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(220)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 12)
        sv.setSpacing(0)
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(16, 14, 16, 10)
        brand_row.setSpacing(10)
        from ui.dashboard import _logo_pixmap

        brand_ico = QLabel()
        brand_ico.setPixmap(_logo_pixmap(26))
        brand_row.addWidget(brand_ico)
        brand = QLabel("PDF Master")
        brand.setObjectName("brand")
        brand.setStyleSheet("padding: 0px;")
        brand_row.addWidget(brand, 1)
        sv.addLayout(brand_row)
        self.nav_buttons: dict[str, QPushButton] = {}
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for key, label, ic in SIDEBAR:
            b = QPushButton("  " + label)
            b.setCheckable(True)
            b.setIcon(icon(ic, "#6b7280", 20))
            b.setIconSize(QSize(20, 20))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.navigate(k))
            grp.addButton(b)
            sv.addWidget(b)
            self.nav_buttons[key] = b
            if key in ("cat:ocr", "recent"):
                sv.addSpacing(10)
        sv.addStretch(1)
        self.btn_theme_toggle = QPushButton("  Dark Mode")
        self.btn_theme_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_theme_toggle.setToolTip("Toggle Light / Dark theme (Ctrl+T)")
        self.btn_theme_toggle.clicked.connect(self.toggle_theme)
        sv.addWidget(self.btn_theme_toggle)
        ver = QLabel("  Offline · v1.0")
        ver.setObjectName("muted")
        sv.addWidget(ver)
        h.addWidget(side)

        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)
        self._setup_shortcuts()
        self.apply_theme()
        self.navigate("dashboard")

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+D"), self, activated=lambda: self.navigate("dashboard"))
        QShortcut(QKeySequence("Ctrl+H"), self, activated=lambda: self.navigate("recent"))
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self.toggle_theme)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=lambda: self.navigate("settings"))
        QShortcut(QKeySequence("Alt+Left"), self, activated=self.go_back)

    # ------------------------------------------------------------ theme
    def toggle_theme(self) -> None:
        cur = self.settings.get("theme")
        new_theme = "light" if cur == "dark" else "dark"
        self.settings.set("theme", new_theme)
        self.apply_theme()
        sp = self.pages.get("settings")
        if sp and hasattr(sp, "load"):
            sp.load()

    def apply_theme(self) -> None:
        dark = self.settings.get("theme") == "dark"
        QApplication.instance().setStyleSheet(stylesheet(dark))
        if hasattr(self, "btn_theme_toggle"):
            self.btn_theme_toggle.setText("  ☀  Light Mode" if dark else "  ☾  Dark Mode")

    # ------------------------------------------------------------ pages
    def _build(self, key: str) -> QWidget:
        from ui import dashboard as d
        if key == "dashboard":
            w = d.Dashboard(self.settings)
            w.tool_requested.connect(self.open_tool)
            w.file_requested.connect(self.open_viewer)
        elif key.startswith("cat:") and key[4:] in UPCOMING:
            w = d.UpcomingPage(key[4:])
        elif key.startswith("cat:"):
            w = d.CategoryPage(key[4:])
            w.tool_requested.connect(self.open_tool)
        elif key == "recent":
            w = d.RecentPage(self.settings)
            w.file_requested.connect(self.open_viewer)
            if hasattr(w, "tool_requested"):
                w.tool_requested.connect(self.open_tool)
        elif key == "settings":
            w = d.SettingsPage(self.settings)
            w.theme_changed.connect(lambda _t: self.apply_theme())
            w.history_cleared.connect(lambda: self._refresh_lists())
        elif key == "about":
            w = d.AboutPage()
        elif key.startswith("tool:"):
            w = TOOL_BY_ID[key[5:]].create(self.settings)
            w.back_requested.connect(self.go_back)
            if hasattr(w, "open_in_viewer"):
                w.open_in_viewer.connect(self.open_viewer)
            if hasattr(w, "tool_requested"):
                w.tool_requested.connect(self.open_tool)
        else:
            raise KeyError(key)
        self.stack.addWidget(w)
        self.pages[key] = w
        return w

    def _refresh_lists(self) -> None:
        for k in ("dashboard", "recent"):
            w = self.pages.get(k)
            if w:
                w.refresh()

    def navigate(self, key: str, remember: bool = True) -> QWidget:
        w = self.pages.get(key) or self._build(key)
        if remember and self._current and self._current != key and not self._current.startswith("tool:"):
            self._history.append(self._current)
        if key in ("dashboard", "recent") and hasattr(w, "refresh"):
            w.refresh()
        self.stack.setCurrentWidget(w)
        self._current = key
        nav = key
        if key.startswith("tool:"):
            cat = TOOL_BY_ID[key[5:]].category
            nav = f"cat:{cat}" if f"cat:{cat}" in self.nav_buttons else "dashboard"
        self.nav_buttons[nav].setChecked(True)
        return w

    def go_back(self) -> None:
        target = self._history.pop() if self._history else "dashboard"
        self.navigate(target, remember=False)

    def open_tool(self, tool_id: str, preset: dict | None = None) -> None:
        preset = dict(preset or {})
        browse = preset.pop("browse", False)
        file_path = preset.pop("file", None)
        w = self.navigate(f"tool:{tool_id}")
        if tool_id == "reader":
            if file_path and os.path.isfile(file_path):
                w.open_file(file_path)
            elif browse:
                w.open_dialog()
            return
        if file_path and hasattr(w, "load_file"):
            w.load_file(file_path)
        if preset:
            w.apply_preset(**preset)

    def open_viewer(self, path: str) -> None:
        if not os.path.exists(path):
            QMessageBox.warning(self, "File not found", f"The file no longer exists:\n{path}")
            return
        w = self.navigate("tool:reader")
        w.open_file(path)

    # ------------------------------------------------------------ events
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and self._current in ("dashboard", "recent"):
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            f = u.toLocalFile()
            if f.lower().endswith(".pdf"):
                self.open_viewer(f)
                break

    def closeEvent(self, e):
        busy = [w for w in self.pages.values() if getattr(w, "is_busy", lambda: False)()]
        if busy:
            r = QMessageBox.question(self, "Operation running",
                                     "A task is still running. Cancel it and exit?", QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                e.ignore()
                return
        for w in self.pages.values():
            if hasattr(w, "shutdown"):
                w.shutdown()
        e.accept()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main())
