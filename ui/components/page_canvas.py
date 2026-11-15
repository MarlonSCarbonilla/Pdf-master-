"""Interactive PDF page preview canvas with click-and-drag region / crop selection."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    import main as _main_bootstrap  # noqa: F401

from typing import Optional

import fitz
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from core.pdf_render import render_pixmap
from utils.validators import open_pdf

MM = 72.0 / 25.4


class _CanvasView(QWidget):
    rect_dragged = Signal(float, float, float, float)  # x_mm, y_mm, w_mm, h_mm
    crop_dragged = Signal(float, float, float, float)  # top_mm, bottom_mm, left_mm, right_mm

    def __init__(self, interactive_rect: bool = False, crop_mode: bool = False, parent=None):
        super().__init__(parent)
        self.interactive_rect = interactive_rect
        self.crop_mode = crop_mode
        self.setMinimumSize(210, 250)
        self._pixmap: Optional[QPixmap] = None
        self._page_w_pt: float = 595.0
        self._page_h_pt: float = 842.0
        self._box_mm: Optional[tuple[float, float, float, float]] = None
        self._crop_mm: Optional[tuple[float, float, float, float]] = None
        self._drag_start: Optional[QPointF] = None
        self._drag_cur: Optional[QPointF] = None
        if interactive_rect or crop_mode:
            self.setCursor(Qt.CrossCursor)

    def set_page_image(self, pm: Optional[QPixmap], w_pt: float = 595.0, h_pt: float = 842.0) -> None:
        self._pixmap = pm
        self._page_w_pt = max(1.0, w_pt)
        self._page_h_pt = max(1.0, h_pt)
        self.update()

    def set_box_mm(self, x_mm: float, y_mm: float, w_mm: float, h_mm: float) -> None:
        self._box_mm = (x_mm, y_mm, w_mm, h_mm)
        self.update()

    def set_crop_mm(self, top_mm: float, bottom_mm: float, left_mm: float, right_mm: float) -> None:
        self._crop_mm = (top_mm, bottom_mm, left_mm, right_mm)
        self.update()

    def _target_rect(self) -> QRectF:
        if not self._pixmap or self._pixmap.isNull():
            return QRectF()
        avail = self.rect().adjusted(6, 6, -6, -6)
        scaled = self._pixmap.size().scaled(avail.size(), Qt.KeepAspectRatio)
        x = avail.x() + (avail.width() - scaled.width()) / 2.0
        y = avail.y() + (avail.height() - scaled.height()) / 2.0
        return QRectF(x, y, scaled.width(), scaled.height())

    def _px_to_mm(self, pt: QPointF) -> tuple[float, float]:
        tr = self._target_rect()
        if tr.width() <= 1 or tr.height() <= 1:
            return 0.0, 0.0
        rx = max(0.0, min(1.0, (pt.x() - tr.x()) / tr.width()))
        ry = max(0.0, min(1.0, (pt.y() - tr.y()) / tr.height()))
        w_mm = self._page_w_pt / MM
        h_mm = self._page_h_pt / MM
        return rx * w_mm, ry * h_mm

    def _mm_to_px_rect(self, x_mm: float, y_mm: float, w_mm: float, h_mm: float) -> QRectF:
        tr = self._target_rect()
        page_w_mm = self._page_w_pt / MM
        page_h_mm = self._page_h_pt / MM
        sx = tr.width() / max(1.0, page_w_mm)
        sy = tr.height() / max(1.0, page_h_mm)
        return QRectF(tr.x() + x_mm * sx, tr.y() + y_mm * sy, w_mm * sx, h_mm * sy)

    def mousePressEvent(self, e):
        if (self.interactive_rect or self.crop_mode) and self._pixmap and e.button() == Qt.LeftButton:
            self._drag_start = e.position()
            self._drag_cur = e.position()
            self.update()

    def mouseMoveEvent(self, e):
        if self._drag_start is not None:
            self._drag_cur = e.position()
            self._emit_drag()
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag_start is not None:
            self._drag_cur = e.position()
            self._emit_drag()
            self._drag_start = None
            self._drag_cur = None
            self.update()

    def _emit_drag(self) -> None:
        if not self._drag_start or not self._drag_cur:
            return
        x1, y1 = self._px_to_mm(self._drag_start)
        x2, y2 = self._px_to_mm(self._drag_cur)
        x0, y0 = min(x1, x2), min(y1, y2)
        w, h = max(5.0, abs(x2 - x1)), max(5.0, abs(y2 - y1))
        if self.interactive_rect:
            self._box_mm = (x0, y0, w, h)
            self.rect_dragged.emit(round(x0, 1), round(y0, 1), round(w, 1), round(h, 1))
        elif self.crop_mode:
            page_w_mm = self._page_w_pt / MM
            page_h_mm = self._page_h_pt / MM
            top = max(0.0, y0)
            left = max(0.0, x0)
            bottom = max(0.0, page_h_mm - (y0 + h))
            right = max(0.0, page_w_mm - (x0 + w))
            self._crop_mm = (top, bottom, left, right)
            self.crop_dragged.emit(round(top, 1), round(bottom, 1), round(left, 1), round(right, 1))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self._pixmap or self._pixmap.isNull():
            p.setPen(self.palette().mid().color())
            p.drawText(self.rect(), Qt.AlignCenter, "Select a PDF to preview")
            return
        tr = self._target_rect()
        p.fillRect(tr.adjusted(2, 2, 2, 2), QColor(0, 0, 0, 35))
        p.drawPixmap(tr.toRect(), self._pixmap)

        if self.interactive_rect and self._box_mm:
            r = self._mm_to_px_rect(*self._box_mm)
            p.fillRect(r, QColor(229, 50, 45, 45))
            pen = QPen(QColor(229, 50, 45), 1.6, Qt.DashLine)
            p.setPen(pen)
            p.drawRect(r)
        elif self.crop_mode and self._crop_mm:
            top, bottom, left, right = self._crop_mm
            page_w_mm = self._page_w_pt / MM
            page_h_mm = self._page_h_pt / MM
            r = self._mm_to_px_rect(left, top, max(5.0, page_w_mm - left - right), max(5.0, page_h_mm - top - bottom))
            pen = QPen(QColor(25, 118, 210), 1.8, Qt.DashLine)
            p.setPen(pen)
            p.drawRect(r)


class PagePreviewCard(QFrame):
    """Side card showing a PDF page preview and optional interactive rectangle/crop selection."""

    rect_selected = Signal(float, float, float, float)
    crop_selected = Signal(float, float, float, float)

    def __init__(self, interactive_rect: bool = False, crop_mode: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._path: Optional[str] = None
        self._password: Optional[str] = None
        lay = QVBoxLayout(self)
        hdr = QLabel("Page Preview (drag on page to select area)" if (interactive_rect or crop_mode) else "Page Preview")
        hdr.setObjectName("muted")
        lay.addWidget(hdr)
        self.canvas = _CanvasView(interactive_rect=interactive_rect, crop_mode=crop_mode)
        self.canvas.rect_dragged.connect(self.rect_selected)
        self.canvas.crop_dragged.connect(self.crop_selected)
        lay.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Page:"))
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.valueChanged.connect(self.refresh)
        row.addWidget(self.page_spin)
        self.total_lbl = QLabel("/ 0")
        row.addWidget(self.total_lbl)
        row.addStretch(1)
        lay.addLayout(row)

    def set_document(self, path: Optional[str], password: Optional[str] = None) -> None:
        self._path = path
        self._password = password
        if not path:
            self.page_spin.setMaximum(1)
            self.total_lbl.setText("/ 0")
            self.canvas.set_page_image(None)
            return
        self.refresh()

    def refresh(self) -> None:
        if not self._path:
            self.canvas.set_page_image(None)
            return
        try:
            doc = open_pdf(self._path, self._password)
        except Exception:
            self.canvas.set_page_image(None)
            return
        try:
            n = doc.page_count
            self.page_spin.blockSignals(True)
            self.page_spin.setMaximum(n)
            pno = min(self.page_spin.value(), n) - 1
            self.page_spin.blockSignals(False)
            self.total_lbl.setText(f"/ {n}")
            page = doc[pno]
            pix = render_pixmap(page, 72)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            self.canvas.set_page_image(QPixmap.fromImage(img), page.rect.width, page.rect.height)
        finally:
            doc.close()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main())
