"""Procedurally drawn, consistent line icons (no external image assets needed)."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    import main as _main_bootstrap  # noqa: F401

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

_cache: dict[tuple, QIcon] = {}


def _page(p: QPainter, r: QRectF) -> None:
    p.drawRoundedRect(QRectF(r.x() + 5, r.y() + 2, r.width() - 10, r.height() - 4), 3, 3)


def _badge(p: QPainter, u: float, label: str) -> None:
    f = QFont("Segoe UI", max(6, int(6.5 * u)))
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(6 * u, 7 * u, 12 * u, 10 * u), Qt.AlignCenter, label)


def _draw(name: str, p: QPainter, s: float) -> None:
    r = QRectF(0, 0, s, s)
    u = s / 24.0
    P = lambda x, y: QPointF(x * u, y * u)  # noqa: E731
    if name == "dashboard":
        for x, y in ((4, 4), (14, 4), (4, 14), (14, 14)):
            p.drawRoundedRect(QRectF(x * u, y * u, 6 * u, 6 * u), 1.5 * u, 1.5 * u)
    elif name in ("merge", "split", "organize", "remove", "extract", "rotate", "reader", "doc"):
        _page(p, r)
        if name == "merge":
            p.drawLine(P(8, 9), P(12, 13)); p.drawLine(P(16, 9), P(12, 13)); p.drawLine(P(12, 13), P(12, 18))
        elif name == "split":
            p.drawLine(P(12, 8), P(12, 12)); p.drawLine(P(12, 12), P(8, 17)); p.drawLine(P(12, 12), P(16, 17))
        elif name == "organize":
            for y in (9, 13, 17):
                p.drawLine(P(8, y), P(16, y))
        elif name == "remove":
            p.drawLine(P(9, 10), P(15, 16)); p.drawLine(P(15, 10), P(9, 16))
        elif name == "extract":
            p.drawLine(P(8, 13), P(16, 13)); p.drawLine(P(13, 10), P(16, 13)); p.drawLine(P(13, 16), P(16, 13))
        elif name == "rotate":
            p.drawArc(QRectF(8 * u, 8 * u, 8 * u, 8 * u), 40 * 16, 270 * 16); p.drawLine(P(15, 7), P(16, 11)); p.drawLine(P(16, 11), P(12, 11))
        elif name == "reader":
            p.drawEllipse(QRectF(8 * u, 9 * u, 8 * u, 6 * u)); p.drawEllipse(QRectF(11 * u, 11 * u, 2 * u, 2 * u))
    elif name == "remove_blank":
        _page(p, r)
        pen = QPen(p.pen()); pen.setStyle(Qt.DashLine); p.setPen(pen)
        p.drawLine(P(8, 8), P(16, 16)); p.drawLine(P(16, 8), P(8, 16))
    elif name == "compare":
        p.drawRoundedRect(QRectF(3 * u, 4 * u, 8 * u, 16 * u), 2 * u, 2 * u)
        p.drawRoundedRect(QRectF(13 * u, 4 * u, 8 * u, 16 * u), 2 * u, 2 * u)
        p.drawLine(P(5, 9), P(9, 9)); p.drawLine(P(15, 9), P(19, 9))
        p.drawLine(P(5, 13), P(9, 13)); p.drawLine(P(15, 15), P(19, 15))
    elif name == "batch_rename":
        _page(p, r)
        p.drawRect(QRectF(7 * u, 10 * u, 10 * u, 5 * u))
        p.drawLine(P(14, 9), P(14, 16))
    elif name in ("pdf2img", "extract_images"):
        _page(p, r); p.drawLine(P(8, 17), P(11, 12)); p.drawLine(P(11, 12), P(13, 15)); p.drawLine(P(13, 15), P(15, 11)); p.drawLine(P(15, 11), P(17, 17))
    elif name == "img2pdf":
        p.drawRoundedRect(QRectF(3 * u, 5 * u, 18 * u, 14 * u), 2 * u, 2 * u)
        p.drawLine(P(6, 16), P(10, 11)); p.drawLine(P(10, 11), P(13, 14)); p.drawLine(P(13, 14), P(15, 12)); p.drawLine(P(15, 12), P(19, 16))
        p.drawEllipse(QRectF(14 * u, 7 * u, 3 * u, 3 * u))
    elif name == "word":
        _page(p, r); _badge(p, u, "W")
    elif name == "excel":
        _page(p, r); _badge(p, u, "X")
    elif name == "ppt":
        _page(p, r); _badge(p, u, "P")
    elif name == "office2pdf":
        _page(p, r); _badge(p, u, "PDF")
    elif name == "extract_text":
        _page(p, r)
        for y in (8, 11, 14, 17):
            p.drawLine(P(8, y), P(16 if y < 17 else 13, y))
    elif name == "compress":
        _page(p, r)
        p.drawLine(P(12, 7), P(12, 11)); p.drawLine(P(10, 9), P(12, 11)); p.drawLine(P(14, 9), P(12, 11))
        p.drawLine(P(12, 18), P(12, 14)); p.drawLine(P(10, 16), P(12, 14)); p.drawLine(P(14, 16), P(12, 14))
    elif name == "repair":
        _page(p, r)
        p.drawLine(P(9, 15), P(15, 9))
        p.drawEllipse(QRectF(13.5 * u, 7.5 * u, 3 * u, 3 * u))
        p.drawEllipse(QRectF(7.5 * u, 13.5 * u, 3 * u, 3 * u))
    elif name == "grayscale":
        p.drawEllipse(QRectF(5 * u, 5 * u, 14 * u, 14 * u))
        path = QPainterPath()
        path.moveTo(P(12, 5)); path.arcTo(QRectF(5 * u, 5 * u, 14 * u, 14 * u), 90, -180); path.closeSubpath()
        p.fillPath(path, p.pen().color())
    elif name == "flatten":
        p.drawLine(P(6, 8), P(12, 5)); p.drawLine(P(12, 5), P(18, 8)); p.drawLine(P(18, 8), P(12, 11)); p.drawLine(P(12, 11), P(6, 8))
        p.drawLine(P(6, 13), P(12, 16)); p.drawLine(P(12, 16), P(18, 13))
        p.drawLine(P(6, 17), P(12, 20)); p.drawLine(P(12, 20), P(18, 17))
    elif name == "edit":
        p.drawLine(P(5, 19), P(8, 18)); p.drawLine(P(8, 18), P(19, 7)); p.drawLine(P(19, 7), P(17, 5)); p.drawLine(P(17, 5), P(6, 16)); p.drawLine(P(6, 16), P(5, 19))
    elif name == "page_numbers":
        _page(p, r); _badge(p, u, "#1")
    elif name == "header_footer":
        _page(p, r)
        p.drawLine(P(7, 6), P(17, 6))
        p.drawLine(P(7, 18), P(17, 18))
    elif name == "watermark":
        _page(p, r)
        p.drawLine(P(8, 16), P(16, 8))
        p.drawEllipse(QRectF(9 * u, 9 * u, 6 * u, 6 * u))
    elif name == "crop":
        p.drawLine(P(7, 3), P(7, 17)); p.drawLine(P(7, 17), P(21, 17))
        p.drawLine(P(3, 7), P(17, 7)); p.drawLine(P(17, 7), P(17, 21))
    elif name == "metadata":
        _page(p, r)
        p.drawEllipse(QRectF(11 * u, 7 * u, 2 * u, 2 * u))
        p.drawLine(P(12, 11), P(12, 17))
    elif name in ("security", "protect"):
        p.drawRoundedRect(QRectF(6 * u, 11 * u, 12 * u, 9 * u), 2 * u, 2 * u)
        p.drawArc(QRectF(8 * u, 5 * u, 8 * u, 10 * u), 0, 180 * 16)
        p.drawEllipse(QRectF(11 * u, 14 * u, 2 * u, 2 * u))
    elif name == "unlock":
        p.drawRoundedRect(QRectF(6 * u, 11 * u, 12 * u, 9 * u), 2 * u, 2 * u)
        p.drawArc(QRectF(11 * u, 4 * u, 8 * u, 10 * u), 0, 180 * 16)
    elif name == "redact":
        _page(p, r)
        p.fillRect(QRectF(8 * u, 9 * u, 8 * u, 2.5 * u), p.pen().color())
        p.fillRect(QRectF(8 * u, 13.5 * u, 6 * u, 2.5 * u), p.pen().color())
    elif name == "sign":
        _page(p, r)
        path = QPainterPath()
        path.moveTo(P(8, 16)); path.cubicTo(P(10, 11), P(12, 18), P(14, 13)); path.quadTo(P(15, 15), P(17, 14))
        p.drawPath(path)
        p.drawLine(P(8, 18), P(16, 18))
    elif name == "ocr":
        p.drawLine(P(4, 8), P(4, 4)); p.drawLine(P(4, 4), P(8, 4)); p.drawLine(P(16, 4), P(20, 4)); p.drawLine(P(20, 4), P(20, 8))
        p.drawLine(P(4, 16), P(4, 20)); p.drawLine(P(4, 20), P(8, 20)); p.drawLine(P(16, 20), P(20, 20)); p.drawLine(P(20, 20), P(20, 16))
        p.drawLine(P(8, 12), P(16, 12))
    elif name == "recent":
        p.drawEllipse(QRectF(4 * u, 4 * u, 16 * u, 16 * u)); p.drawLine(P(12, 8), P(12, 12)); p.drawLine(P(12, 12), P(15, 14))
    elif name == "settings":
        for y, x in ((7, 9), (12, 15), (17, 8)):
            p.drawLine(P(4, y), P(20, y)); p.setBrush(p.pen().color()); p.drawEllipse(QRectF((x - 1.8) * u, (y - 1.8) * u, 3.6 * u, 3.6 * u)); p.setBrush(Qt.NoBrush)
    elif name == "about":
        p.drawEllipse(QRectF(4 * u, 4 * u, 16 * u, 16 * u)); p.drawLine(P(12, 11), P(12, 16)); p.drawPoint(P(12, 8))
    elif name in ("back", "open"):
        if name == "back":
            p.drawLine(P(15, 5), P(8, 12)); p.drawLine(P(8, 12), P(15, 19))
        else:
            p.drawRoundedRect(QRectF(3 * u, 7 * u, 18 * u, 12 * u), 2 * u, 2 * u); p.drawLine(P(3, 10), P(21, 10))
    elif name in ("zoom_in", "zoom_out", "search"):
        p.drawEllipse(QRectF(4 * u, 4 * u, 12 * u, 12 * u)); p.drawLine(P(14, 14), P(20, 20))
        if name != "search":
            p.drawLine(P(7, 10), P(13, 10))
        if name == "zoom_in":
            p.drawLine(P(10, 7), P(10, 13))
    elif name in ("up", "down"):
        y0, y1 = (15, 9) if name == "up" else (9, 15)
        p.drawLine(P(6, y0), P(12, y1)); p.drawLine(P(12, y1), P(18, y0))
    elif name in ("rot_left", "rot_right"):
        p.drawArc(QRectF(5 * u, 6 * u, 14 * u, 14 * u), 30 * 16, 280 * 16)
        if name == "rot_right":
            p.drawLine(P(18, 6), P(17, 10)); p.drawLine(P(17, 10), P(13, 9))
        else:
            p.drawLine(P(6, 6), P(7, 10)); p.drawLine(P(7, 10), P(11, 9))
    elif name == "fit_width":
        p.drawLine(P(3, 12), P(21, 12)); p.drawLine(P(3, 12), P(7, 8)); p.drawLine(P(3, 12), P(7, 16)); p.drawLine(P(21, 12), P(17, 8)); p.drawLine(P(21, 12), P(17, 16))
    elif name == "fit_page":
        p.drawRoundedRect(QRectF(6 * u, 3 * u, 12 * u, 18 * u), 2 * u, 2 * u)
    elif name == "print":
        p.drawRoundedRect(QRectF(3 * u, 9 * u, 18 * u, 8 * u), 2 * u, 2 * u); p.drawRect(QRectF(7 * u, 3 * u, 10 * u, 6 * u)); p.drawRect(QRectF(7 * u, 14 * u, 10 * u, 6 * u))
    elif name == "thumbs":
        for x, y in ((4, 4), (13, 4), (4, 13), (13, 13)):
            p.drawRect(QRectF(x * u, y * u, 7 * u, 7 * u))
    elif name == "duplicate":
        p.drawRoundedRect(QRectF(4 * u, 8 * u, 11 * u, 12 * u), 2 * u, 2 * u); p.drawRoundedRect(QRectF(9 * u, 4 * u, 11 * u, 12 * u), 2 * u, 2 * u)
    elif name == "continuous":
        p.drawRect(QRectF(6 * u, 3 * u, 12 * u, 7 * u)); p.drawRect(QRectF(6 * u, 12 * u, 12 * u, 9 * u))
    else:
        _page(p, r)


def icon(name: str, color: str = "#6b7280", size: int = 24) -> QIcon:
    key = (name, color, size)
    if key in _cache:
        return _cache[key]
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(scale)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), max(1.4, size / 14), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    _draw(name, p, float(size))
    p.end()
    ic = QIcon(pm)
    _cache[key] = ic
    return ic


def clear_cache() -> None:
    _cache.clear()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main())
