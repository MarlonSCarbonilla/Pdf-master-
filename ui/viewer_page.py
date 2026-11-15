"""Lightweight PDF reader: continuous/single page, zoom, fit modes, search, thumbnails, rotate, print."""
from __future__ import annotations

import os
import sys
from collections import OrderedDict
from typing import Optional

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import main as _main_bootstrap  # ensures .venv & project root on sys.path  # noqa: F401

import fitz
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractScrollArea, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QListWidget, QListWidgetItem, QPushButton, QSpinBox, QSplitter,
                               QToolButton, QVBoxLayout, QWidget, QSizePolicy)

from app.settings import Settings
from core.common import PasswordRequired, ProcessingError
from ui.components import dialogs
from ui.components.icons import icon
from ui.components.thumbnails import CACHE, THUMB_W, ThumbnailLoader, _to_pixmap
from utils.validators import open_pdf

GAP = 14          # px between pages in continuous mode
MARGIN = 14


class PageView(QAbstractScrollArea):
    """Custom scroll area that paints only visible pages and caches a few rendered pages."""

    page_changed = Signal(int)
    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: Optional[fitz.Document] = None
        self.sizes: list[tuple[float, float]] = []   # page size in points (unrotated by view)
        self.zoom = 1.0                              # 1.0 == 100% (96 dpi)
        self.fit_mode: Optional[str] = "width"       # 'width' | 'page' | None
        self.continuous = True
        self.view_rot = 0
        self.current = 0
        self._tops: list[int] = []
        self._heights: list[int] = []
        self._widths: list[int] = []
        self._cache: "OrderedDict[tuple, QImage]" = OrderedDict()
        self.hits: dict[int, list[fitz.Rect]] = {}
        self.active_hit: Optional[tuple[int, int]] = None
        self.viewport().setBackgroundRole(self.backgroundRole())
        self.setFocusPolicy(Qt.StrongFocus)
        self.verticalScrollBar().setSingleStep(40)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._bg = QColor("#7a7f89")

    # ------------------------------------------------------------ document
    def set_document(self, doc: Optional[fitz.Document]) -> None:
        self.doc = doc
        self._cache.clear()
        self.hits.clear()
        self.active_hit = None
        self.current = 0
        self.view_rot = 0
        self.sizes = []
        if doc:
            for i in range(doc.page_count):
                r = doc[i].rect
                self.sizes.append((r.width, r.height))
        self.fit_mode = "width"
        self._relayout()
        self.verticalScrollBar().setValue(0)
        self.viewport().update()

    def page_count(self) -> int:
        return len(self.sizes)

    def _scale(self) -> float:
        return self.zoom * 96.0 / 72.0

    def _page_dims(self, i: int) -> tuple[float, float]:
        w, h = self.sizes[i]
        return (h, w) if self.view_rot in (90, 270) else (w, h)

    def _apply_fit(self) -> None:
        if not self.sizes or not self.fit_mode:
            return
        vw = max(50, self.viewport().width() - 2 * MARGIN - (0 if self.verticalScrollBar().isVisible() else 0))
        vh = max(50, self.viewport().height() - 2 * MARGIN)
        w, h = self._page_dims(self.current)
        if self.fit_mode == "width":
            s = vw / w
        else:
            s = min(vw / w, vh / h)
        self.zoom = max(0.05, min(8.0, s * 72.0 / 96.0))

    def _relayout(self) -> None:
        if not self.sizes:
            self.verticalScrollBar().setRange(0, 0)
            self.horizontalScrollBar().setRange(0, 0)
            return
        self._apply_fit()
        s = self._scale()
        self._tops, self._heights, self._widths = [], [], []
        y = MARGIN
        for i in range(len(self.sizes)):
            w, h = self._page_dims(i)
            self._tops.append(y)
            self._widths.append(int(w * s))
            self._heights.append(int(h * s))
            if self.continuous:
                y += int(h * s) + GAP
        total_h = (y - GAP + MARGIN) if self.continuous else self._heights[self.current] + 2 * MARGIN
        vp = self.viewport()
        self.verticalScrollBar().setRange(0, max(0, total_h - vp.height()))
        self.verticalScrollBar().setPageStep(vp.height())
        max_w = max(self._widths) + 2 * MARGIN
        self.horizontalScrollBar().setRange(0, max(0, max_w - vp.width()))
        self.horizontalScrollBar().setPageStep(vp.width())
        self.zoom_changed.emit(self.zoom)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        keep = self.current
        self._relayout()
        if self.continuous and self._tops:
            self.verticalScrollBar().setValue(self._tops[keep] - MARGIN)

    # ------------------------------------------------------------ navigation
    def goto(self, page: int) -> None:
        if not self.sizes:
            return
        page = max(0, min(page, len(self.sizes) - 1))
        if self.continuous:
            self.verticalScrollBar().setValue(max(0, self._tops[page] - MARGIN))
        else:
            self.current = page
            self._relayout()
            self.verticalScrollBar().setValue(0)
            self.viewport().update()
        self._set_current(page)

    def _set_current(self, page: int) -> None:
        if page != self.current or not self.continuous:
            self.current = page
        self.page_changed.emit(page)

    def _on_scroll(self, _v: int) -> None:
        if self.continuous and self._tops:
            mid = self.verticalScrollBar().value() + self.viewport().height() // 3
            idx = 0
            for i, t in enumerate(self._tops):
                if t <= mid:
                    idx = i
                else:
                    break
            if idx != self.current:
                self.current = idx
                self.page_changed.emit(idx)
        self.viewport().update()

    def set_continuous(self, on: bool) -> None:
        keep = self.current
        self.continuous = on
        self._relayout()
        if on and self._tops:
            self.verticalScrollBar().setValue(max(0, self._tops[keep] - MARGIN))
        else:
            self.verticalScrollBar().setValue(0)
        self.viewport().update()

    def set_zoom(self, z: float) -> None:
        keep = self.current
        self.fit_mode = None
        self.zoom = max(0.1, min(8.0, z))
        self._relayout()
        if self.continuous and self._tops:
            self.verticalScrollBar().setValue(max(0, self._tops[keep] - MARGIN))
        self.viewport().update()

    def set_fit(self, mode: str) -> None:
        keep = self.current
        self.fit_mode = mode
        self._relayout()
        if self.continuous and self._tops:
            self.verticalScrollBar().setValue(max(0, self._tops[keep] - MARGIN))
        self.viewport().update()

    def rotate_view(self, delta: int) -> None:
        keep = self.current
        self.view_rot = (self.view_rot + delta) % 360
        self._cache.clear()
        self._relayout()
        if self.continuous and self._tops:
            self.verticalScrollBar().setValue(max(0, self._tops[keep] - MARGIN))
        self.viewport().update()

    # ------------------------------------------------------------ rendering
    def _render(self, i: int) -> QImage:
        dpr = self.devicePixelRatioF()
        s = self._scale()
        key = (i, round(s * dpr, 3), self.view_rot)
        img = self._cache.get(key)
        if img is not None:
            self._cache.move_to_end(key)
            return img
        mat = fitz.Matrix(s * dpr, s * dpr).prerotate(self.view_rot)
        pix = self.doc[i].get_pixmap(matrix=mat, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        img.setDevicePixelRatio(dpr)
        self._cache[key] = img
        while len(self._cache) > 8:
            self._cache.popitem(last=False)
        return img

    def _page_rect_px(self, i: int) -> QRect:
        """Page rectangle in viewport coordinates."""
        hs = self.horizontalScrollBar().value()
        vs = self.verticalScrollBar().value()
        w, h = self._widths[i], self._heights[i]
        vw = self.viewport().width()
        x = max(MARGIN, (vw - w) // 2) - hs if w + 2 * MARGIN <= vw else MARGIN - hs
        y = (self._tops[i] - vs) if self.continuous else (MARGIN - vs)
        return QRect(x, y, w, h)

    def _visible_pages(self) -> list[int]:
        if not self.sizes:
            return []
        if not self.continuous:
            return [self.current]
        top = self.verticalScrollBar().value()
        bot = top + self.viewport().height()
        return [i for i in range(len(self.sizes)) if self._tops[i] + self._heights[i] >= top and self._tops[i] <= bot]

    def paintEvent(self, e):
        p = QPainter(self.viewport())
        p.fillRect(self.viewport().rect(), self._bg)
        if not self.doc:
            p.setPen(QColor("#e6e8ec"))
            p.drawText(self.viewport().rect(), Qt.AlignCenter, "Open a PDF to start reading")
            return
        for i in self._visible_pages():
            r = self._page_rect_px(i)
            p.fillRect(r.adjusted(3, 3, 3, 3), QColor(0, 0, 0, 50))
            p.drawImage(r.topLeft(), self._render(i))
            self._paint_hits(p, i, r)

    def _paint_hits(self, p: QPainter, i: int, r: QRect) -> None:
        rects = self.hits.get(i)
        if not rects:
            return
        s = self._scale()
        mat = fitz.Matrix(s, s).prerotate(self.view_rot)
        origin = (self.doc[i].rect * mat)
        for k, fr in enumerate(rects):
            t = fr * mat
            q = QRectF(r.x() + t.x0 - origin.x0, r.y() + t.y0 - origin.y0, t.width, t.height)
            active = self.active_hit == (i, k)
            p.fillRect(q, QColor(255, 140, 0, 130) if active else QColor(255, 235, 59, 120))

    def hit_scroll_to(self, page: int, k: int) -> None:
        self.active_hit = (page, k)
        self.goto(page)
        rect = self.hits[page][k]
        s = self._scale()
        mat = fitz.Matrix(s, s).prerotate(self.view_rot)
        origin = self.doc[page].rect * mat
        y = (rect * mat).y0 - origin.y0
        if self.continuous:
            self.verticalScrollBar().setValue(max(0, int(self._tops[page] + y - self.viewport().height() / 3)))
        else:
            self.verticalScrollBar().setValue(max(0, int(y - self.viewport().height() / 3)))
        self.viewport().update()

    # ------------------------------------------------------------ input
    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.set_zoom(self.zoom * (1.15 if e.angleDelta().y() > 0 else 1 / 1.15))
            e.accept()
            return
        if not self.continuous and self.sizes:
            sb = self.verticalScrollBar()
            d = e.angleDelta().y()
            if d < 0 and sb.value() >= sb.maximum() and self.current < len(self.sizes) - 1:
                self.goto(self.current + 1)
                return
            if d > 0 and sb.value() <= sb.minimum() and self.current > 0:
                self.goto(self.current - 1)
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
                return
        super().wheelEvent(e)

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_PageDown, Qt.Key_Right) and not (self.continuous and k == Qt.Key_PageDown):
            self.goto(self.current + 1)
        elif k in (Qt.Key_PageUp, Qt.Key_Left) and not (self.continuous and k == Qt.Key_PageUp):
            self.goto(self.current - 1)
        elif k == Qt.Key_Home:
            self.goto(0)
        elif k == Qt.Key_End:
            self.goto(len(self.sizes) - 1)
        else:
            super().keyPressEvent(e)

    def clear_cache(self) -> None:
        self._cache.clear()


class ViewerPage(QWidget):
    back_requested = Signal()
    file_opened = Signal(str)
    tool_requested = Signal(str, dict)

    TOOL_ID = "reader"

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.settings = settings
        self.doc: Optional[fitz.Document] = None
        self.path: Optional[str] = None
        self._password: Optional[str] = None
        self._loader: Optional[ThumbnailLoader] = None
        self._hit_list: list[tuple[int, int]] = []
        self._hit_pos = -1
        self._build()

    # ------------------------------------------------------------ UI
    def _tb(self, name: str, tip: str, slot, checkable: bool = False) -> QToolButton:
        b = QToolButton()
        b.setIcon(icon(name, "#6b7280", 20))
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.setAutoRaise(True)
        b.clicked.connect(slot)
        return b

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget()
        bar.setObjectName("card")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 6, 10, 6)
        back = QPushButton(" Back")
        back.setIcon(icon("back", "#6b7280", 18))
        back.setObjectName("link")
        back.clicked.connect(self.back_requested)
        bl.addWidget(back)
        op = QPushButton("Open PDF…")
        op.setObjectName("primary")
        op.clicked.connect(self.open_dialog)
        bl.addWidget(op)
        from PySide6.QtWidgets import QMenu

        self.btn_send_tool = QPushButton("Send to Tool ▾")
        self.btn_send_tool.setToolTip("Open the current PDF in any processing tool")
        send_menu = QMenu(self.btn_send_tool)
        for label, tid in (
            ("Compress PDF", "compress"),
            ("Split PDF", "split"),
            ("Organize Pages", "organize"),
            ("Edit & Annotate", "annotate"),
            ("Watermark PDF", "watermark"),
            ("Crop Pages", "crop"),
            ("Protect PDF (Password)", "protect"),
            ("Redact Sensitive Content", "redact"),
            ("Sign PDF", "sign"),
            ("PDF to Word (.docx)", "pdf2docx"),
            ("PDF to Image (JPG/PNG)", "pdf2img"),
            ("OCR PDF", "ocr"),
        ):
            act = send_menu.addAction(icon(tid if tid != "annotate" else "edit", "#e5322d", 16), label)
            act.triggered.connect(lambda _=False, t=tid: self._send_to_tool(t))
        self.btn_send_tool.setMenu(send_menu)
        bl.addWidget(self.btn_send_tool)
        self.b_thumbs = self._tb("thumbs", "Show/hide thumbnails", self._toggle_thumbs, True)
        self.b_thumbs.setChecked(True)
        bl.addWidget(self.b_thumbs)
        bl.addWidget(self._tb("up", "Previous page", lambda: self.view.goto(self.view.current - 1)))
        self.spin = QSpinBox()
        self.spin.setMinimum(1)
        self.spin.setMaximum(1)
        self.spin.setKeyboardTracking(False)
        self.spin.valueChanged.connect(lambda v: self.view.goto(v - 1))
        bl.addWidget(self.spin)
        self.total = QLabel("/ 0")
        bl.addWidget(self.total)
        bl.addWidget(self._tb("down", "Next page", lambda: self.view.goto(self.view.current + 1)))
        bl.addSpacing(8)
        bl.addWidget(self._tb("zoom_out", "Zoom out (Ctrl + wheel)", lambda: self.view.set_zoom(self.view.zoom / 1.2)))
        self.zoom_lbl = QLabel("100%")
        self.zoom_lbl.setMinimumWidth(44)
        bl.addWidget(self.zoom_lbl)
        bl.addWidget(self._tb("zoom_in", "Zoom in (Ctrl + wheel)", lambda: self.view.set_zoom(self.view.zoom * 1.2)))
        bl.addWidget(self._tb("fit_width", "Fit width", lambda: self.view.set_fit("width")))
        bl.addWidget(self._tb("fit_page", "Fit page", lambda: self.view.set_fit("page")))
        bl.addSpacing(8)
        self.b_cont = self._tb("continuous", "Continuous scrolling (off = single page)", self._toggle_cont, True)
        self.b_cont.setChecked(True)
        bl.addWidget(self.b_cont)
        bl.addWidget(self._tb("rot_left", "Rotate view left", lambda: self.view.rotate_view(-90)))
        bl.addWidget(self._tb("rot_right", "Rotate view right", lambda: self.view.rotate_view(90)))
        bl.addWidget(self._tb("print", "Print…", self.print_doc))
        bl.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search text…")
        self.search.setFixedWidth(190)
        self.search.returnPressed.connect(self.do_search)
        bl.addWidget(self.search)
        bl.addWidget(self._tb("up", "Previous match", lambda: self._step_hit(-1)))
        bl.addWidget(self._tb("down", "Next match", lambda: self._step_hit(1)))
        self.hit_lbl = QLabel("")
        self.hit_lbl.setObjectName("muted")
        self.hit_lbl.setMinimumWidth(70)
        bl.addWidget(self.hit_lbl)
        root.addWidget(bar)

        split = QSplitter()
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListView.ListMode)
        self.thumbs.setIconSize(QSize(THUMB_W, int(THUMB_W * 1.42)))
        self.thumbs.setUniformItemSizes(True)
        self.thumbs.setMinimumWidth(THUMB_W + 40)
        self.thumbs.currentRowChanged.connect(self._thumb_clicked)
        split.addWidget(self.thumbs)
        self.view = PageView()
        self.view.page_changed.connect(self._on_page)
        self.view.zoom_changed.connect(lambda z: self.zoom_lbl.setText(f"{round(z * 100)}%"))
        split.addWidget(self.view)
        split.setStretchFactor(1, 1)
        split.setSizes([170, 900])
        root.addWidget(split, 1)

        self.info = QLabel("No document open.")
        self.info.setObjectName("muted")
        self.info.setContentsMargins(12, 4, 12, 4)
        root.addWidget(self.info)

        QShortcut(QKeySequence.Find, self, activated=lambda: (self.search.setFocus(), self.search.selectAll()))
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_dialog)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self.print_doc)
        QShortcut(QKeySequence("Ctrl+="), self, activated=lambda: self.view.set_zoom(self.view.zoom * 1.2))
        QShortcut(QKeySequence("Ctrl+-"), self, activated=lambda: self.view.set_zoom(self.view.zoom / 1.2))
        QShortcut(QKeySequence("F3"), self, activated=lambda: self._step_hit(1))

    # ------------------------------------------------------------ opening
    def _send_to_tool(self, tool_id: str) -> None:
        if not self.path or not os.path.isfile(self.path):
            dialogs.info(self, "Send to Tool", "Open a PDF document first.")
            return
        self.tool_requested.emit(tool_id, {"file": self.path})

    def open_dialog(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF files (*.pdf)")
        if f:
            self.open_file(f)

    def open_file(self, path: str) -> bool:
        pw: Optional[str] = None
        for attempt in range(4):
            try:
                doc = open_pdf(path, pw)
                break
            except PasswordRequired:
                pw = dialogs.ask_password(self, path, wrong=attempt > 0)
                if pw is None:
                    return False
            except ProcessingError as e:
                if "Wrong password" in str(e):
                    pw = dialogs.ask_password(self, path, wrong=True)
                    if pw is None:
                        return False
                    continue
                dialogs.error(self, "Cannot open PDF", str(e))
                return False
        else:
            return False
        self.close_document()
        self.doc, self.path, self._password = doc, path, pw
        self.view.set_document(doc)
        n = doc.page_count
        self.spin.setMaximum(n)
        self.spin.setValue(1)
        self.total.setText(f"/ {n}")
        self.search.clear()
        self.hit_lbl.setText("")
        self._load_thumbs(n)
        self.info.setText(f"{os.path.basename(path)} · {n} page(s)")
        self.settings.add_recent(path, action="PDF Reader", page_count=n)
        self.file_opened.emit(path)
        return True

    def close_document(self) -> None:
        self._stop_thumbs()
        self.view.set_document(None)
        self.thumbs.clear()
        if self.doc:
            self.doc.close()
        self.doc = None
        self.path = None

    def _stop_thumbs(self) -> None:
        if self._loader:
            self._loader.stop()
            self._loader.wait(2000)
            self._loader = None

    def _load_thumbs(self, n: int) -> None:
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        for i in range(n):
            it = QListWidgetItem(str(i + 1))
            it.setTextAlignment(Qt.AlignHCenter)
            self.thumbs.addItem(it)
        self.thumbs.blockSignals(False)
        self._loader = ThumbnailLoader(self.path, self._password, n)
        self._loader.ready.connect(lambda i, w, h, d: self.thumbs.item(i).setIcon(QIcon(_to_pixmap(w, h, d))) if i < self.thumbs.count() else None)
        self._loader.start()

    # ------------------------------------------------------------ slots
    def _toggle_thumbs(self) -> None:
        self.thumbs.setVisible(self.b_thumbs.isChecked())

    def _toggle_cont(self) -> None:
        self.view.set_continuous(self.b_cont.isChecked())

    def _on_page(self, i: int) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(i + 1)
        self.spin.blockSignals(False)
        self.thumbs.blockSignals(True)
        self.thumbs.setCurrentRow(i)
        self.thumbs.blockSignals(False)

    def _thumb_clicked(self, row: int) -> None:
        if row >= 0:
            self.view.goto(row)

    # ------------------------------------------------------------ search
    def do_search(self) -> None:
        text = self.search.text().strip()
        if not self.doc or not text:
            return
        self.view.hits.clear()
        self.view.active_hit = None
        self._hit_list = []
        for i in range(self.doc.page_count):
            rects = self.doc[i].search_for(text)
            if rects:
                self.view.hits[i] = rects
                self._hit_list += [(i, k) for k in range(len(rects))]
            if len(self._hit_list) > 5000:
                break
        if not self._hit_list:
            self.hit_lbl.setText("No matches")
            self.view.viewport().update()
            if not any(self.doc[i].get_text("text").strip() for i in range(min(self.doc.page_count, 5))):
                self.info.setText("This document has no selectable text (it may be scanned). OCR is needed to search it.")
            return
        # start from the current page
        start = next((j for j, (pg, _) in enumerate(self._hit_list) if pg >= self.view.current), 0)
        self._hit_pos = start
        self._show_hit()

    def _step_hit(self, d: int) -> None:
        if not self._hit_list:
            self.do_search()
            return
        self._hit_pos = (self._hit_pos + d) % len(self._hit_list)
        self._show_hit()

    def _show_hit(self) -> None:
        pg, k = self._hit_list[self._hit_pos]
        self.view.hit_scroll_to(pg, k)
        self.hit_lbl.setText(f"{self._hit_pos + 1} / {len(self._hit_list)}")

    # ------------------------------------------------------------ print
    def print_doc(self) -> None:
        if not self.doc:
            dialogs.info(self, "Print", "Open a PDF first.")
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        dlg.setOption(QPrintDialog.PrintPageRange, True)
        dlg.setMinMax(1, self.doc.page_count)
        if dlg.exec() != QPrintDialog.Accepted:
            return
        first = printer.fromPage() or 1
        last = printer.toPage() or self.doc.page_count
        painter = QPainter()
        if not painter.begin(printer):
            dialogs.error(self, "Print", "Could not start the printer.")
            return
        try:
            dpi = min(max(printer.resolution(), 150), 300)
            for k, i in enumerate(range(first - 1, last)):
                if k:
                    printer.newPage()
                pix = self.doc[i].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72).prerotate(self.view.view_rot), alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                page_rect = printer.pageRect(QPrinter.DevicePixel).toRect()
                scaled = img.size().scaled(page_rect.size(), Qt.KeepAspectRatio)
                target = QRect(page_rect.x() + (page_rect.width() - scaled.width()) // 2,
                               page_rect.y() + (page_rect.height() - scaled.height()) // 2,
                               scaled.width(), scaled.height())
                painter.drawImage(target, img)
        finally:
            painter.end()

    def shutdown(self) -> None:
        self.close_document()

    def is_busy(self) -> bool:
        return False


if __name__ == "__main__":
    from main import main

    raise SystemExit(main(start_tool="reader"))

