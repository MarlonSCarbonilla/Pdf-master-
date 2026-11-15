"""Combine images into one PDF."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import io
import os
from typing import Optional, Sequence

import fitz
from PIL import Image, ImageOps

from core.common import JobContext, ProcessingError, ctx_or_default
from utils.file_utils import atomic_write
from utils.validators import check_image_file

# page sizes in PDF points (1/72 inch), portrait
PAGE_SIZES = {"A4": (595.28, 841.89), "Letter": (612.0, 792.0), "Legal": (612.0, 1008.0)}
FIT_MODES = ("fit", "stretch", "original")  # keep aspect / ignore aspect / no scaling (shrink only)
MM = 72 / 25.4


def _image_dpi(im: Image.Image) -> float:
    dpi = im.info.get("dpi")
    try:
        if dpi and 20 <= float(dpi[0]) <= 2400:
            return float(dpi[0])
    except (TypeError, ValueError, IndexError):
        pass
    return 96.0


def _frames(path: str):
    """Yield prepared RGB/L Pillow images (all frames of multi-page TIFF)."""
    with Image.open(path) as im:
        n = getattr(im, "n_frames", 1)
        for f in range(n):
            im.seek(f)
            frame = ImageOps.exif_transpose(im) if f == 0 else im.copy()
            dpi = _image_dpi(im)
            if frame.mode in ("RGBA", "LA", "P") or "transparency" in frame.info:
                rgba = frame.convert("RGBA")
                bg = Image.new("RGB", rgba.size, "white")
                bg.paste(rgba, mask=rgba.split()[3])
                frame = bg
            elif frame.mode not in ("RGB", "L"):
                frame = frame.convert("RGB")
            else:
                frame = frame.copy()
            yield frame, dpi, (im.format or "")


def images_to_pdf(
    images: Sequence[str],
    output: str,
    page_size: str = "A4",
    orientation: str = "auto",
    margin_mm: float = 10,
    fit: str = "fit",
    ctx: Optional[JobContext] = None,
) -> str:
    """Create a PDF with one page per image.

    page_size: 'A4' | 'Letter' | 'Legal' | 'Original' (page = image size)
    orientation: 'portrait' | 'landscape' | 'auto' (match image) - ignored for Original
    fit: 'fit' keep aspect, 'stretch' fill ignoring aspect, 'original' natural size
    """
    ctx = ctx_or_default(ctx)
    if not images:
        raise ProcessingError("Add at least one image.")
    if fit not in FIT_MODES:
        raise ProcessingError("Invalid fit mode.")
    if page_size != "Original" and page_size not in PAGE_SIZES:
        raise ProcessingError("Invalid page size.")
    if margin_mm < 0 or margin_mm > 100:
        raise ProcessingError("Margin must be between 0 and 100 mm.")
    problems = []
    for p in images:
        try:
            check_image_file(p)
        except ProcessingError as e:
            problems.append(str(e))
    if problems:
        raise ProcessingError("Cannot create the PDF, problems found:\n- " + "\n- ".join(problems))

    doc = fitz.open()
    try:
        total = len(images)
        margin = margin_mm * MM
        for i, path in enumerate(images):
            ctx.report(i, total, f"Adding {os.path.basename(path)}")
            for frame, dpi, fmtname in _frames(path):
                try:
                    wpx, hpx = frame.size
                    nat_w, nat_h = wpx / dpi * 72, hpx / dpi * 72
                    if page_size == "Original":
                        pw, ph = nat_w + 2 * margin, nat_h + 2 * margin
                    else:
                        pw, ph = PAGE_SIZES[page_size]
                        land = orientation == "landscape" or (orientation == "auto" and wpx > hpx)
                        if land:
                            pw, ph = ph, pw
                    aw, ah = pw - 2 * margin, ph - 2 * margin
                    if aw < 10 or ah < 10:
                        raise ProcessingError("Margins are too large for this page size.")
                    if fit == "stretch":
                        w, h = aw, ah
                    else:
                        scale = min(aw / nat_w, ah / nat_h)
                        if fit == "original":
                            scale = min(scale, 1.0)
                        w, h = nat_w * scale, nat_h * scale
                    x0, y0 = (pw - w) / 2, (ph - h) / 2
                    page = doc.new_page(width=pw, height=ph)
                    buf = io.BytesIO()
                    if fmtname == "JPEG" and frame.mode in ("RGB", "L"):
                        frame.save(buf, "JPEG", quality=92)
                    else:
                        frame.save(buf, "PNG")
                    page.insert_image(fitz.Rect(x0, y0, x0 + w, y0 + h), stream=buf.getvalue())
                finally:
                    frame.close()
        ctx.report(total, total, "Saving PDF")
        atomic_write(output, lambda tmp: doc.save(tmp, garbage=3, deflate=True))
    finally:
        doc.close()
    return output
