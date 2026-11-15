"""Generate high-resolution application icons (app.png, app.ico, app.svg) for PDF Master."""
from __future__ import annotations

import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)


def render_master_icon(size: int = 1024) -> QImage:
    """Render a 1024x1024 modern desktop app icon using Qt vector graphics."""
    _app = QGuiApplication.instance() or QGuiApplication([])
    img = QImage(size, size, QImage.Format_RGBA8888)
    img.fill(Qt.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    s = float(size)

    # 1. Outer soft ambient shadow under the squircle
    shadow_rect = QRectF(s * 0.06, s * 0.075, s * 0.88, s * 0.88)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 50))
    p.drawRoundedRect(shadow_rect, s * 0.22, s * 0.22)

    # 2. Main squircle background with rich crimson gradient
    bg_rect = QRectF(s * 0.06, s * 0.055, s * 0.88, s * 0.88)
    bg_grad = QLinearGradient(bg_rect.topLeft(), bg_rect.bottomRight())
    bg_grad.setColorAt(0.0, QColor("#FF524B"))
    bg_grad.setColorAt(0.45, QColor("#E5322D"))
    bg_grad.setColorAt(1.0, QColor("#9E1410"))
    p.setBrush(bg_grad)
    p.setPen(QPen(QColor(255, 255, 255, 65), s * 0.012))
    p.drawRoundedRect(bg_rect, s * 0.22, s * 0.22)

    # Subtle top-left glow inside the squircle
    glow = QRadialGradient(QPointF(s * 0.28, s * 0.22), s * 0.55)
    glow.setColorAt(0.0, QColor(255, 255, 255, 55))
    glow.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(glow)
    p.drawRoundedRect(bg_rect, s * 0.22, s * 0.22)

    # 3. Back stacked page hint (gives depth of multi-page toolkit)
    back_page = QRectF(s * 0.27, s * 0.16, s * 0.50, s * 0.64)
    p.save()
    p.translate(back_page.center())
    p.rotate(6.0)
    p.translate(-back_page.center())
    p.setBrush(QColor(255, 255, 255, 75))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(back_page, s * 0.04, s * 0.04)
    p.restore()

    # 4. Main white document sheet with dog-ear folded corner
    doc_x, doc_y = s * 0.22, s * 0.16
    doc_w, doc_h = s * 0.54, s * 0.68
    fold = s * 0.145
    r = s * 0.042

    def make_doc_path(dx: float = 0.0, dy: float = 0.0) -> QPainterPath:
        x0, y0 = doc_x + dx, doc_y + dy
        x1, y1 = x0 + doc_w, y0 + doc_h
        path = QPainterPath()
        path.moveTo(x0 + r, y0)
        path.lineTo(x1 - fold, y0)
        path.lineTo(x1, y0 + fold)
        path.lineTo(x1, y1 - r)
        path.quadTo(x1, y1, x1 - r, y1)
        path.lineTo(x0 + r, y1)
        path.quadTo(x0, y1, x0, y1 - r)
        path.lineTo(x0, y0 + r)
        path.quadTo(x0, y0, x0 + r, y0)
        path.closeSubpath()
        return path

    # Document drop shadow
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(80, 5, 5, 85))
    p.drawPath(make_doc_path(0, s * 0.022))

    # Document body
    doc_grad = QLinearGradient(QPointF(doc_x, doc_y), QPointF(doc_x, doc_y + doc_h))
    doc_grad.setColorAt(0.0, QColor("#FFFFFF"))
    doc_grad.setColorAt(1.0, QColor("#F8FAFC"))
    p.setBrush(doc_grad)
    p.drawPath(make_doc_path())

    # 5. Dog-ear corner flap
    flap = QPainterPath()
    x1, y0 = doc_x + doc_w, doc_y
    flap.moveTo(x1 - fold, y0)
    flap.lineTo(x1, y0 + fold)
    flap.lineTo(x1 - fold + r * 0.5, y0 + fold)
    flap.quadTo(x1 - fold, y0 + fold, x1 - fold, y0 + fold - r * 0.5)
    flap.closeSubpath()

    # Flap shadow
    flap_shadow = QPainterPath()
    flap_shadow.moveTo(x1 - fold, y0 + fold)
    flap_shadow.lineTo(x1, y0 + fold)
    flap_shadow.lineTo(x1 - fold, y0 + fold * 1.28)
    flap_shadow.closeSubpath()
    p.setBrush(QColor(229, 50, 45, 45))
    p.drawPath(flap_shadow)

    flap_grad = QLinearGradient(QPointF(x1 - fold, y0), QPointF(x1, y0 + fold))
    flap_grad.setColorAt(0.0, QColor("#FEE2E2"))
    flap_grad.setColorAt(1.0, QColor("#FECACA"))
    p.setBrush(flap_grad)
    p.drawPath(flap)

    # 6. Stylized content lines on upper document
    line_pen = QPen(QColor("#CBD5E1"), s * 0.024, Qt.SolidLine, Qt.RoundCap)
    p.setPen(line_pen)
    p.drawLine(QPointF(doc_x + s * 0.075, doc_y + s * 0.13), QPointF(doc_x + s * 0.28, doc_y + s * 0.13))
    p.drawLine(QPointF(doc_x + s * 0.075, doc_y + s * 0.21), QPointF(doc_x + doc_w - s * 0.08, doc_y + s * 0.21))
    p.drawLine(QPointF(doc_x + s * 0.075, doc_y + s * 0.28), QPointF(doc_x + doc_w - s * 0.13, doc_y + s * 0.28))

    # 7. Prominent "PDF" ribbon badge across the lower half of the document
    badge_rect = QRectF(s * 0.16, s * 0.51, s * 0.66, s * 0.22)
    badge_shadow = badge_rect.translated(0, s * 0.016)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(110, 10, 10, 95))
    p.drawRoundedRect(badge_shadow, s * 0.055, s * 0.055)

    badge_grad = QLinearGradient(badge_rect.topLeft(), badge_rect.bottomRight())
    badge_grad.setColorAt(0.0, QColor("#EF4444"))
    badge_grad.setColorAt(0.5, QColor("#DC2626"))
    badge_grad.setColorAt(1.0, QColor("#991B1B"))
    p.setBrush(badge_grad)
    p.setPen(QPen(QColor("#FFFFFF"), s * 0.012))
    p.drawRoundedRect(badge_rect, s * 0.055, s * 0.055)

    # "PDF" typography inside the ribbon
    font = QFont("Segoe UI", int(s * 0.115))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, s * 0.008)
    p.setFont(font)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(badge_rect.adjusted(0, -s * 0.006, 0, -s * 0.006), Qt.AlignCenter, "PDF")

    p.end()
    return img


SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FF524B"/>
      <stop offset="45%" stop-color="#E5322D"/>
      <stop offset="100%" stop-color="#9E1410"/>
    </linearGradient>
    <linearGradient id="badge" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#EF4444"/>
      <stop offset="50%" stop-color="#DC2626"/>
      <stop offset="100%" stop-color="#991B1B"/>
    </linearGradient>
  </defs>
  <rect x="30" y="28" width="452" height="452" rx="112" fill="url(#bg)" stroke="#ffffff" stroke-opacity="0.25" stroke-width="6"/>
  <g transform="rotate(6 266 246)">
    <rect x="138" y="82" width="256" height="328" rx="20" fill="#ffffff" fill-opacity="0.3"/>
  </g>
  <path d="M134 82 H314 L388 156 V408 A22 22 0 0 1 366 430 H134 A22 22 0 0 1 112 408 V104 A22 22 0 0 1 134 82 Z" fill="#ffffff"/>
  <path d="M314 82 L388 156 H328 A14 14 0 0 1 314 142 Z" fill="#FECACA"/>
  <line x1="152" y1="148" x2="256" y2="148" stroke="#CBD5E1" stroke-width="12" stroke-linecap="round"/>
  <line x1="152" y1="190" x2="348" y2="190" stroke="#CBD5E1" stroke-width="12" stroke-linecap="round"/>
  <line x1="152" y1="226" x2="322" y2="226" stroke="#CBD5E1" stroke-width="12" stroke-linecap="round"/>
  <rect x="82" y="262" width="338" height="112" rx="28" fill="url(#badge)" stroke="#ffffff" stroke-width="6"/>
  <text x="251" y="340" font-family="Segoe UI, Arial, sans-serif" font-size="82" font-weight="800" fill="#ffffff" text-anchor="middle" letter-spacing="3">PDF</text>
</svg>
"""


def generate_icons() -> tuple[str, str, str]:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "resources", "icons")
    os.makedirs(out_dir, exist_ok=True)

    qimg = render_master_icon(1024)
    ptr = qimg.bits()
    pil_master = Image.frombytes("RGBA", (qimg.width(), qimg.height()), bytes(ptr))

    png_path = os.path.join(out_dir, "app.png")
    ico_path = os.path.join(out_dir, "app.ico")
    svg_path = os.path.join(out_dir, "app.svg")

    pil_512 = pil_master.resize((512, 512), Image.Resampling.LANCZOS)
    pil_512.save(png_path, format="PNG", optimize=True)

    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    pil_master.save(ico_path, format="ICO", sizes=ico_sizes)

    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(SVG_TEMPLATE)

    return png_path, ico_path, svg_path


if __name__ == "__main__":
    png, ico, svg = generate_icons()
    print(f"Generated:\n  PNG: {png}\n  ICO: {ico}\n  SVG: {svg}")
