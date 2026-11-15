"""Rendering: thumbnails, previews and image export (PyMuPDF + Pillow). No Qt here."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional, Sequence

import fitz
from PIL import Image

from core.common import JobContext, ProcessingError, ctx_or_default
from utils.file_utils import atomic_write, safe_filename, unique_path
from utils.validators import open_pdf, parse_page_ranges

DPI_CHOICES = (72, 150, 200, 300, 600)
FORMATS = ("JPG", "PNG", "TIFF")
MAX_PIXELS = 300_000_000  # refuse absurd renders (protects 4 GB machines)


def render_pixmap(page: fitz.Page, dpi: float = 72, rotate: int = 0) -> fitz.Pixmap:
    """Render one page at `dpi`, optional extra clockwise rotation, no alpha."""
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale).prerotate(rotate)
    r = page.rect * mat
    if r.width * r.height > MAX_PIXELS:
        raise ProcessingError("This page is too large to render at the chosen resolution. Pick a lower DPI.")
    return page.get_pixmap(matrix=mat, alpha=False)


def render_thumbnail(page: fitz.Page, width: int = 120) -> tuple[int, int, bytes]:
    """Return (w, h, RGB bytes) with the given pixel width."""
    rect = page.rect
    scale = width / max(rect.width, 1)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    data = bytes(pix.samples)
    w, h = pix.width, pix.height
    pix = None
    return w, h, data


class ThumbnailCache:
    """Byte-bounded LRU cache of rendered thumbnails keyed by (path, mtime, page, width)."""

    def __init__(self, max_bytes: int = 64 * 1024 * 1024):
        self.max_bytes = max_bytes
        self._items: "OrderedDict[tuple, tuple[int, int, bytes]]" = OrderedDict()
        self._size = 0

    def get(self, key: tuple):
        v = self._items.get(key)
        if v is not None:
            self._items.move_to_end(key)
        return v

    def put(self, key: tuple, value: tuple[int, int, bytes]) -> None:
        old = self._items.pop(key, None)
        if old:
            self._size -= len(old[2])
        self._items[key] = value
        self._size += len(value[2])
        while self._size > self.max_bytes and self._items:
            _, (_, _, data) = self._items.popitem(last=False)
            self._size -= len(data)

    def clear(self) -> None:
        self._items.clear()
        self._size = 0

    def __len__(self) -> int:
        return len(self._items)


def thumbnail_key(path: str, page: int, width: int) -> tuple:
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    return (path, mtime, page, width)


def save_pixmap_as(pix: fitz.Pixmap, path: str, fmt: str, dpi: int, quality: int = 85) -> None:
    """Save a pixmap as JPG/PNG/TIFF using Pillow, atomically."""
    fmt = fmt.upper()
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    try:
        def _w(tmp: str) -> None:
            if fmt in ("JPG", "JPEG"):
                img.save(tmp, "JPEG", quality=int(quality), optimize=True, dpi=(dpi, dpi))
            elif fmt == "PNG":
                img.save(tmp, "PNG", dpi=(dpi, dpi), compress_level=6)
            elif fmt in ("TIFF", "TIF"):
                img.save(tmp, "TIFF", compression="tiff_lzw", dpi=(dpi, dpi))
            else:
                raise ProcessingError(f"Unsupported image format: {fmt}")
        atomic_write(path, _w)
    finally:
        img.close()


@dataclass
class ExportResult:
    files: list[str]
    pages_exported: int


def export_images(
    pdfs: Sequence[str],
    out_dir: str,
    fmt: str = "PNG",
    dpi: int = 150,
    quality: int = 85,
    page_text: Optional[str] = None,
    passwords: Optional[dict[str, str]] = None,
    ctx: Optional[JobContext] = None,
) -> ExportResult:
    """Export pages of one or more PDFs as images, one page at a time (low memory).

    Output names are '<stem>_page_<NNN>.<ext>'. With several PDFs each gets its own
    sub-folder. Existing files are never overwritten. `page_text` (ranges) applies to
    every PDF; None means all pages.
    """
    ctx = ctx_or_default(ctx)
    passwords = passwords or {}
    fmt = fmt.upper()
    if fmt not in FORMATS:
        raise ProcessingError(f"Unsupported image format: {fmt}")
    ext = {"JPG": ".jpg", "PNG": ".png", "TIFF": ".tif"}[fmt]
    multi = len(pdfs) > 1

    # Plan: resolve the page lists first so progress is accurate.
    plan: list[tuple[str, list[int]]] = []
    for p in pdfs:
        doc = open_pdf(p, passwords.get(p))
        try:
            if page_text and page_text.strip().lower() != "all":
                try:
                    pages = parse_page_ranges(page_text, doc.page_count)
                except ValueError as e:
                    raise ProcessingError(f"{os.path.basename(p)}: {e}") from None
            else:
                pages = list(range(doc.page_count))
        finally:
            doc.close()
        plan.append((p, pages))
    total = sum(len(pg) for _, pg in plan)

    files: list[str] = []
    done = 0
    for path, pages in plan:
        stem = os.path.splitext(os.path.basename(path))[0]
        target = os.path.join(out_dir, safe_filename(stem)) if multi else out_dir
        os.makedirs(target, exist_ok=True)
        width = max(3, len(str(max(pages) + 1)))
        doc = open_pdf(path, passwords.get(path))
        try:
            for pno in pages:
                ctx.report(done, total, f"{stem}: page {pno + 1}")
                pix = render_pixmap(doc[pno], dpi)
                try:
                    out = unique_path(os.path.join(target, f"{safe_filename(stem)}_page_{pno + 1:0{width}d}{ext}"))
                    save_pixmap_as(pix, out, fmt, dpi, quality)
                    files.append(out)
                finally:
                    pix = None  # release the page bitmap immediately
                done += 1
        finally:
            doc.close()
    ctx.report(total, total, "Done")
    return ExportResult(files, done)
