"""Dashboard, category pages, recent files, settings, about, upcoming-feature pages."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu, QPushButton, QScrollArea, QVBoxLayout, QWidget,
                               QMessageBox)

from app.navigation import CATEGORY_TITLES, TOOL_BY_ID, TOOLS, UPCOMING
from app.settings import Settings
from core.file_manager import move_to_trash, open_folder
from ui.components import dialogs
from ui.components.cards import ToolCard
from ui.components.icons import icon
from utils.file_utils import human_size

APP_NAME = "PDF Master"
APP_VERSION = "1.0.0"


def _scrolled(inner: QWidget) -> QScrollArea:
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setWidget(inner)
    sc.setFrameShape(QFrame.NoFrame)
    return sc


def _grid_of(tools, on_click, cols: int = 3) -> QGridLayout:
    g = QGridLayout()
    g.setSpacing(12)
    for i, t in enumerate(tools):
        c = ToolCard(t.title, t.desc, t.icon)
        c.clicked.connect(lambda _=False, tid=t.id: on_click(tid))
        g.addWidget(c, i // cols, i % cols)
    for c in range(cols):
        g.setColumnStretch(c, 1)
    return g


class Dashboard(QWidget):
    tool_requested = Signal(str, dict)
    file_requested = Signal(str)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.settings = settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.inner = QWidget()
        self.inner.setObjectName("page")
        outer.addWidget(_scrolled(self.inner))
        root_lay = QVBoxLayout(self.inner)
        root_lay.setContentsMargins(32, 24, 32, 24)
        root_lay.setSpacing(14)

        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(_logo_pixmap(46))
        head.addWidget(logo)
        col = QVBoxLayout()
        t = QLabel(f"Welcome to {APP_NAME}")
        t.setObjectName("h1")
        sub = QLabel("Your offline PDF toolkit. Files never leave this computer - no account, no cloud.")
        sub.setObjectName("muted")
        col.addWidget(t)
        col.addWidget(sub)
        head.addLayout(col, 1)
        op = QPushButton("Open a PDF to read…")
        op.setObjectName("primary")
        op.clicked.connect(lambda: self.tool_requested.emit("reader", {"browse": True}))
        head.addWidget(op)
        root_lay.addLayout(head)

        srow = QHBoxLayout()
        self.tool_search = QLineEdit()
        self.tool_search.setPlaceholderText("Search 33 PDF tools by name or keyword (Ctrl+K)…  e.g. merge, redact, watermark, word, ocr")
        self.tool_search.setClearButtonEnabled(True)
        self.tool_search.textChanged.connect(self._rebuild_body)
        srow.addWidget(self.tool_search, 1)
        root_lay.addLayout(srow)

        QShortcut(QKeySequence("Ctrl+K"), self, activated=lambda: (self.tool_search.setFocus(), self.tool_search.selectAll()))

        self.lay = QVBoxLayout()
        self.lay.setSpacing(14)
        root_lay.addLayout(self.lay, 1)
        self.refresh()

    def refresh(self) -> None:
        self._rebuild_body()

    def _rebuild_body(self) -> None:
        while self.lay.count():
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._drop(it.layout())
        s = self.settings
        query = self.tool_search.text().strip().lower() if hasattr(self, "tool_search") else ""
        if query:
            matches = [
                t for t in TOOLS
                if query in t.title.lower()
                or query in t.desc.lower()
                or query in t.id.lower()
                or query in CATEGORY_TITLES.get(t.category, "").lower()
            ]
            self._section(f"Matching tools ({len(matches)})")
            if matches:
                self.lay.addLayout(_grid_of(matches, lambda tid: self.tool_requested.emit(tid, {}), 3))
            else:
                empty = QLabel(f"No PDF tools matched '{self.tool_search.text().strip()}'.")
                empty.setObjectName("muted")
                self.lay.addWidget(empty)
            self.lay.addStretch(1)
            return

        # frequently used
        usage = s.get("tool_usage")
        defaults = ["merge", "split", "compress", "pdf2img"]
        ranked = sorted((tid for tid in usage if tid in TOOL_BY_ID and tid != "reader"), key=lambda k: -usage[k])
        freq = (ranked + [d for d in defaults if d not in ranked])[:4]
        self._section("Frequently used tools")
        self.lay.addLayout(_grid_of([TOOL_BY_ID[i] for i in freq], lambda tid: self.tool_requested.emit(tid, {}), 4))

        # quick conversions
        self._section("Quick conversions")
        q = QHBoxLayout()
        for text, tid, preset in (
            ("PDF → JPG", "pdf2img", {"format": "JPG"}),
            ("PDF → PNG", "pdf2img", {"format": "PNG"}),
            ("PDF → TIFF", "pdf2img", {"format": "TIFF"}),
            ("Images → PDF", "img2pdf", {}),
            ("PDF → Word", "pdf2docx", {}),
            ("PDF → Excel", "pdf2xlsx", {}),
            ("PDF → PPTX", "pdf2pptx", {}),
            ("Office → PDF", "office2pdf", {}),
        ):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, tid=tid, p=preset: self.tool_requested.emit(tid, p))
            q.addWidget(b)
        q.addStretch(1)
        self.lay.addLayout(q)

        # all tools grouped
        for cat in ("organize", "convert", "compress", "edit", "security", "ocr", "read"):
            self._section(CATEGORY_TITLES[cat])
            self.lay.addLayout(_grid_of([t for t in TOOLS if t.category == cat],
                                        lambda tid: self.tool_requested.emit(tid, {}), 3))

        # recent
        self._section("Recent documents")
        recent_entries = s.recent_entries(5)
        if not recent_entries:
            m = QLabel("No recent documents yet. Files you open or create will show up here.")
            m.setObjectName("muted")
            self.lay.addWidget(m)
        for entry in recent_entries:
            p = entry.file_path
            pages_txt = f" · {entry.page_count}p" if entry.page_count > 0 else ""
            b = QPushButton(
                f"  {entry.file_name}{pages_txt}    ·    {entry.action} ({entry.last_opened_at})    ·    {os.path.dirname(p)}"
            )
            b.setIcon(icon("doc", "#e5322d", 20))
            b.setStyleSheet("text-align: left;")
            b.clicked.connect(lambda _=False, p=p: self.file_requested.emit(p) if p.lower().endswith(".pdf") else open_folder(p, select_file=True))
            self.lay.addWidget(b)
        self.lay.addStretch(1)

    def _drop(self, layout) -> None:
        while layout.count():
            it = layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._drop(it.layout())

    def _section(self, title: str) -> None:
        l = QLabel(title)
        l.setObjectName("h2")
        self.lay.addSpacing(6)
        self.lay.addWidget(l)


def _logo_pixmap(size: int) -> QPixmap:
    import sys
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QFont, QPainter

    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    png_path = os.path.join(base_dir, "resources", "icons", "app.png")
    if os.path.isfile(png_path):
        src = QPixmap(png_path)
        if not src.isNull():
            pm = src.scaled(size * 2, size * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(2)
            return pm

    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#e5322d"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(0, 0, size * 2, size * 2), size * 0.45, size * 0.45)
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", int(size * 0.55))
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 0, size * 2, size * 2), Qt.AlignCenter, "PDF")
    p.end()
    pm.setDevicePixelRatio(2)
    return pm


class CategoryPage(QWidget):
    tool_requested = Signal(str, dict)

    def __init__(self, category: str, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        inner = QWidget()
        inner.setObjectName("page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(_scrolled(inner))
        v = QVBoxLayout(inner)
        v.setContentsMargins(32, 24, 32, 24)
        t = QLabel(CATEGORY_TITLES[category])
        t.setObjectName("h1")
        v.addWidget(t)
        v.addSpacing(8)
        v.addLayout(_grid_of([x for x in TOOLS if x.category == category],
                             lambda tid: self.tool_requested.emit(tid, {}), 2))
        v.addStretch(1)


class UpcomingPage(QWidget):
    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        title, phase, items = UPCOMING[key]
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 32, 40, 32)
        t = QLabel(title)
        t.setObjectName("h1")
        v.addWidget(t)
        card = QFrame()
        card.setObjectName("card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(20, 16, 20, 16)
        h = QLabel(f"Not available yet - planned for {phase}")
        h.setObjectName("h2")
        cv.addWidget(h)
        m = QLabel("These tools are intentionally not shown as buttons because they are not implemented yet. "
                   "Phase 1 (core tools) comes first. Planned for this section:")
        m.setWordWrap(True)
        m.setObjectName("muted")
        cv.addWidget(m)
        for it in items:
            cv.addWidget(QLabel("•  " + it))
        v.addWidget(card)
        v.addStretch(1)


class RecentPage(QWidget):
    file_requested = Signal(str)
    tool_requested = Signal(str, dict)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.settings = settings
        v = QVBoxLayout(self)
        v.setContentsMargins(32, 24, 32, 24)
        head = QHBoxLayout()
        t = QLabel("Recent Files & History")
        t.setObjectName("h1")
        head.addWidget(t)
        head.addStretch(1)
        self.db_lbl = QLabel(f"SQLite History ({os.path.basename(self.settings.history_db.db_path)})")
        self.db_lbl.setObjectName("muted")
        head.addWidget(self.db_lbl)
        v.addLayout(head)

        frow = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search file name, path, or tool action…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._populate_list)
        frow.addWidget(self.search_edit, 1)
        frow.addWidget(QLabel("Filter by action:"))
        self.action_box = QComboBox()
        self.action_box.setMinimumWidth(180)
        self.action_box.currentTextChanged.connect(self._populate_list)
        frow.addWidget(self.action_box)
        v.addLayout(frow)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda it: self._activate(it.data(Qt.UserRole)))
        v.addWidget(self.list, 3)

        ops_hdr = QLabel("Recent Tool Operations Log")
        ops_hdr.setObjectName("h2")
        v.addWidget(ops_hdr)
        self.ops_list = QListWidget()
        self.ops_list.setMaximumHeight(120)
        v.addWidget(self.ops_list, 1)

        row = QHBoxLayout()
        b_open = QPushButton("Open in Reader")
        b_open.setObjectName("primary")
        b_open.clicked.connect(self._open)
        row.addWidget(b_open)

        self.btn_send_tool = QPushButton("Send to Tool ▾")
        send_menu = QMenu(self.btn_send_tool)
        for label, tid in (
            ("Compress PDF", "compress"),
            ("Split PDF", "split"),
            ("Organize Pages", "organize"),
            ("Edit & Annotate", "annotate"),
            ("Watermark PDF", "watermark"),
            ("Crop Pages", "crop"),
            ("Protect PDF", "protect"),
            ("Redact Content", "redact"),
            ("PDF to Word (.docx)", "pdf2docx"),
            ("PDF to Image", "pdf2img"),
            ("OCR PDF", "ocr"),
        ):
            act = send_menu.addAction(icon(tid if tid != "annotate" else "edit", "#e5322d", 16), label)
            act.triggered.connect(lambda _=False, t=tid: self._send_to_tool(t))
        self.btn_send_tool.setMenu(send_menu)
        row.addWidget(self.btn_send_tool)

        for text, fn in (
            ("Show in folder", self._show),
            ("Remove from list", self._remove),
            ("Move to Recycle Bin", self._trash),
            ("Export CSV…", self._export_csv),
        ):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        c = QPushButton("Clear history")
        c.clicked.connect(self._clear)
        row.addWidget(c)
        v.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        cur_action = self.action_box.currentText() if self.action_box.count() else "All"
        self.action_box.blockSignals(True)
        self.action_box.clear()
        self.action_box.addItem("All")
        for act in self.settings.history_db.distinct_actions():
            self.action_box.addItem(act)
        idx = self.action_box.findText(cur_action)
        self.action_box.setCurrentIndex(idx if idx >= 0 else 0)
        self.action_box.blockSignals(False)
        self._populate_list()

    def _populate_list(self) -> None:
        self.list.clear()
        q = self.search_edit.text().strip() if hasattr(self, "search_edit") else ""
        act = self.action_box.currentText() if hasattr(self, "action_box") else "All"
        entries = self.settings.recent_entries(
            limit=100,
            existing_only=True,
            search=q,
            action_filter="" if act == "All" else act,
        )
        for e in entries:
            pages_info = f" · {e.page_count} page(s)" if e.page_count > 0 else ""
            it = QListWidgetItem(
                f"{e.file_name}   [{e.action}]{pages_info} · {human_size(e.file_size)}\n"
                f"{e.file_path} · Last: {e.last_opened_at} · Opened {e.open_count}×"
            )
            it.setData(Qt.UserRole, e.file_path)
            self.list.addItem(it)

        if hasattr(self, "ops_list"):
            self.ops_list.clear()
            for op in self.settings.history_db.list_operations(limit=20):
                self.ops_list.addItem(f"[{op.created_at}]  {op.tool_id.upper()}  —  {op.summary}")

    def _cur(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _send_to_tool(self, tool_id: str) -> None:
        p = self._cur()
        if not p or not os.path.isfile(p):
            dialogs.info(self, "Send to Tool", "Select a PDF file from the list first.")
            return
        self.tool_requested.emit(tool_id, {"file": p})

    def _activate(self, p: str | None) -> None:
        if not p:
            return
        if p.lower().endswith(".pdf"):
            self.file_requested.emit(p)
        else:
            open_folder(p, select_file=True)

    def _open(self) -> None:
        self._activate(self._cur())

    def _show(self) -> None:
        if p := self._cur():
            open_folder(p, select_file=True)

    def _remove(self) -> None:
        if p := self._cur():
            self.settings.remove_recent(p)
            self.refresh()

    def _trash(self) -> None:
        p = self._cur()
        if not p or not os.path.exists(p):
            return
        res = QMessageBox.question(
            self,
            "Move to Recycle Bin",
            f"Move this file to the Windows Recycle Bin?\n\n{p}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if res == QMessageBox.Yes:
            try:
                move_to_trash(p)
                self.settings.remove_recent(p)
                self.refresh()
            except Exception as e:
                dialogs.error(self, "Move to Recycle Bin", str(e))

    def _export_csv(self) -> None:
        dst, _ = QFileDialog.getSaveFileName(self, "Export History to CSV", "pdf_master_history.csv", "CSV files (*.csv)")
        if dst:
            count = self.settings.history_db.export_csv(dst)
            dialogs.info(self, "Export History", f"Exported {count} history record(s) to:\n{dst}")

    def _clear(self) -> None:
        self.settings.clear_history()
        self.refresh()


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    history_cleared = Signal()

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.s = settings
        v = QVBoxLayout(self)
        v.setContentsMargins(32, 24, 32, 24)
        t = QLabel("Settings")
        t.setObjectName("h1")
        v.addWidget(t)
        card = QFrame()
        card.setObjectName("card")
        g = QGridLayout(card)
        g.setContentsMargins(20, 16, 20, 16)
        g.setHorizontalSpacing(16)
        g.setVerticalSpacing(12)
        from PySide6.QtWidgets import QLineEdit
        self.theme = QComboBox(); self.theme.addItems(["Light", "Dark"])
        self.outdir = QLineEdit(); self.outdir.setPlaceholderText("Ask every time / source folder")
        browse = QPushButton("Browse…"); browse.clicked.connect(self._browse)
        self.fmt = QComboBox(); self.fmt.addItems(["JPG", "PNG", "TIFF"])
        self.dpi = QComboBox(); self.dpi.addItems(["72", "150", "200", "300", "600"])
        self.preset = QComboBox(); self.preset.addItems(["low", "recommended", "high"])
        rows = [("Theme", self.theme), ("Default output folder", self.outdir), ("Default image format", self.fmt),
                ("Default image DPI", self.dpi), ("Default compression preset", self.preset)]
        for i, (lab, w) in enumerate(rows):
            g.addWidget(QLabel(lab), i, 0)
            g.addWidget(w, i, 1)
        g.addWidget(browse, 1, 2)
        g.setColumnStretch(1, 1)
        v.addWidget(card)
        row = QHBoxLayout()
        save = QPushButton("Save settings"); save.setObjectName("primary"); save.clicked.connect(self._save)
        clear = QPushButton("Clear recent file history"); clear.clicked.connect(self._clear_hist)
        reset = QPushButton("Restore defaults"); reset.clicked.connect(self._reset)
        for b in (save, clear, reset):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.msg = QLabel("")
        self.msg.setObjectName("ok")
        v.addWidget(self.msg)
        v.addStretch(1)
        self.load()

    def load(self) -> None:
        s = self.s
        self.theme.setCurrentText(s.get("theme").capitalize())
        self.outdir.setText(s.get("output_dir"))
        self.fmt.setCurrentText(s.get("image_format"))
        self.dpi.setCurrentText(str(s.get("image_dpi")))
        self.preset.setCurrentText(s.get("compression_preset"))

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Default output folder", self.outdir.text())
        if d:
            self.outdir.setText(d)

    def _save(self) -> None:
        s = self.s
        out = self.outdir.text().strip()
        if out and not os.path.isdir(out):
            QMessageBox.warning(self, "Settings", "The default output folder does not exist.")
            return
        s.data.update(theme=self.theme.currentText().lower(), output_dir=out, image_format=self.fmt.currentText(),
                      image_dpi=int(self.dpi.currentText()), compression_preset=self.preset.currentText())
        s.save()
        self.theme_changed.emit(s.get("theme"))
        self.msg.setText("Settings saved. New defaults apply to pages opened from now on.")

    def _clear_hist(self) -> None:
        self.s.clear_history()
        self.history_cleared.emit()
        self.msg.setText("Recent file history cleared.")

    def _reset(self) -> None:
        if QMessageBox.question(self, "Restore defaults", "Restore all settings to their defaults?") == QMessageBox.Yes:
            self.s.reset()
            self.load()
            self.theme_changed.emit(self.s.get("theme"))
            self.msg.setText("Defaults restored.")


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 32, 40, 32)
        card = QFrame()
        card.setObjectName("card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(24, 20, 24, 20)
        logo = QLabel(); logo.setPixmap(_logo_pixmap(64))
        cv.addWidget(logo)
        n = QLabel(f"{APP_NAME} {APP_VERSION}"); n.setObjectName("h1")
        cv.addWidget(n)
        import fitz
        try:
            import PySide6
            qt = PySide6.__version__
        except Exception:
            qt = "?"
        txt = QLabel("A fast, lightweight PDF toolkit that works 100% offline.\n"
                     "No account, no cloud services, no telemetry. Your originals are never modified.\n\n"
                     f"PyMuPDF {fitz.__version__}  ·  PySide6 {qt}  ·  Pillow  ·  pikepdf\n"
                     "PyMuPDF is licensed under AGPL-3.0; see README for licence notes.")
        txt.setWordWrap(True)
        cv.addWidget(txt)
        v.addWidget(card)
        v.addStretch(1)


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main(start_tool='dashboard'))
