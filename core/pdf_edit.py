"""Phase 2 - PDF Editing engine: page numbers, headers/footers, watermarks,
text/image insertion, highlight/underline, shapes/annotations, cropping, metadata."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import datetime
import io
import math
from typing import Optional, Sequence

import fitz
from PIL import Image

from core.common import JobContext, ProcessingError, ctx_or_default
from utils.file_utils import atomic_write
from utils.validators import check_image_file, open_pdf, parse_page_ranges

MM = 72.0 / 25.4

NAMED_COLORS: dict[str, tuple[float, float, float]] = {
    "Black": (0.12, 0.12, 0.12),
    "Dark Gray": (0.35, 0.35, 0.35),
    "Red": (0.85, 0.15, 0.15),
    "Blue": (0.12, 0.35, 0.82),
    "Green": (0.10, 0.58, 0.28),
    "Yellow": (0.98, 0.88, 0.18),
    "Orange": (0.95, 0.50, 0.10),
}


def _resolve_pages(doc: fitz.Document, page_text: Optional[str]) -> list[int]:
    if not page_text or page_text.strip().lower() == "all":
        return list(range(doc.page_count))
    try:
        return parse_page_ranges(page_text, doc.page_count)
    except ValueError as e:
        raise ProcessingError(str(e)) from None


def _save_doc(doc: fitz.Document, output: str) -> str:
    atomic_write(output, lambda tmp: doc.save(tmp, garbage=3, deflate=True))
    return output


# ---------------------------------------------------------------------------
# 1. Page Numbers
# ---------------------------------------------------------------------------
def add_page_numbers(
    src: str,
    output: str,
    position: str = "bottom-center",
    fmt: str = "Page {n} of {total}",
    start_page: int = 1,
    start_number: int = 1,
    fontsize: float = 10.5,
    margin_mm: float = 10.0,
    color_name: str = "Dark Gray",
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    """Stamp page numbers onto `src` and write to `output`."""
    ctx = ctx_or_default(ctx)
    doc = open_pdf(src, password)
    try:
        total = doc.page_count
        if start_page < 1 or start_page > total:
            raise ProcessingError(f"Start page must be between 1 and {total}.")
        margin = max(8.0, margin_mm * MM)
        color = NAMED_COLORS.get(color_name, (0.25, 0.25, 0.25))
        for i in range(start_page - 1, total):
            ctx.report(i - (start_page - 1), total - (start_page - 1), f"Numbering page {i + 1}")
            page = doc[i]
            r = page.rect
            num = start_number + (i - (start_page - 1))
            label = fmt.replace("{n}", str(num)).replace("{page}", str(num)).replace("{total}", str(total))
            tw = fitz.get_text_length(label, fontname="helv", fontsize=fontsize)
            if "top" in position:
                y = r.y0 + margin + fontsize
            else:
                y = r.y1 - margin
            if "left" in position:
                x = r.x0 + margin
            elif "right" in position:
                x = r.x1 - margin - tw
            else:
                x = r.x0 + (r.width - tw) / 2.0
            page.insert_text(fitz.Point(x, y), label, fontname="helv", fontsize=fontsize, color=color, overlay=True)
        ctx.report(total, total, "Saving")
        return _save_doc(doc, output)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# 2. Headers & Footers
# ---------------------------------------------------------------------------
def add_header_footer(
    src: str,
    output: str,
    header_left: str = "",
    header_center: str = "",
    header_right: str = "",
    footer_left: str = "",
    footer_center: str = "",
    footer_right: str = "",
    fontsize: float = 10.0,
    margin_mm: float = 10.0,
    color_name: str = "Dark Gray",
    page_text: Optional[str] = None,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    """Add headers and/or footers to selected pages. Supports {page}, {total}, {date}."""
    ctx = ctx_or_default(ctx)
    if not any(s.strip() for s in (header_left, header_center, header_right, footer_left, footer_center, footer_right)):
        raise ProcessingError("Enter at least one header or footer text field.")
    doc = open_pdf(src, password)
    try:
        pages = _resolve_pages(doc, page_text)
        total = doc.page_count
        margin = max(8.0, margin_mm * MM)
        color = NAMED_COLORS.get(color_name, (0.25, 0.25, 0.25))
        today = datetime.date.today().isoformat()

        def _expand(tpl: str, pno: int) -> str:
            return (
                tpl.replace("{page}", str(pno))
                .replace("{n}", str(pno))
                .replace("{total}", str(total))
                .replace("{date}", today)
            )

        for idx, pno in enumerate(pages):
            ctx.report(idx, len(pages), f"Applying header/footer to page {pno + 1}")
            page = doc[pno]
            r = page.rect
            hy = r.y0 + margin + fontsize
            fy = r.y1 - margin
            for text, y, align in (
                (header_left, hy, "left"),
                (header_center, hy, "center"),
                (header_right, hy, "right"),
                (footer_left, fy, "left"),
                (footer_center, fy, "center"),
                (footer_right, fy, "right"),
            ):
                if not text.strip():
                    continue
                s = _expand(text.strip(), pno + 1)
                tw = fitz.get_text_length(s, fontname="helv", fontsize=fontsize)
                if align == "left":
                    x = r.x0 + margin
                elif align == "right":
                    x = r.x1 - margin - tw
                else:
                    x = r.x0 + (r.width - tw) / 2.0
                page.insert_text(fitz.Point(x, y), s, fontname="helv", fontsize=fontsize, color=color, overlay=True)
        ctx.report(len(pages), len(pages), "Saving")
        return _save_doc(doc, output)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# 3. Text & Image Watermarks
# ---------------------------------------------------------------------------
def add_text_watermark(
    src: str,
    output: str,
    text: str,
    fontsize: float = 48.0,
    angle: float = 45.0,
    opacity: float = 0.25,
    color_name: str = "Red",
    tiled: bool = False,
    underlay: bool = False,
    page_text: Optional[str] = None,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    """Stamp a semi-transparent text watermark (diagonal or horizontal, single or tiled)."""
    ctx = ctx_or_default(ctx)
    text = (text or "").strip()
    if not text:
        raise ProcessingError("Watermark text cannot be empty.")
    opacity = max(0.05, min(1.0, float(opacity)))
    color = NAMED_COLORS.get(color_name, (0.85, 0.15, 0.15))
    doc = open_pdf(src, password)
    try:
        pages = _resolve_pages(doc, page_text)
        tw = fitz.get_text_length(text, fontname="helv", fontsize=fontsize)
        for idx, pno in enumerate(pages):
            ctx.report(idx, len(pages), f"Watermarking page {pno + 1}")
            page = doc[pno]
            r = page.rect
            centers: list[tuple[float, float]] = []
            if tiled:
                step_x = max(tw * 1.35, 180.0)
                step_y = max(fontsize * 3.2, 140.0)
                y = r.y0 + step_y * 0.5
                while y < r.y1:
                    x = r.x0 + step_x * 0.5
                    while x < r.x1:
                        centers.append((x, y))
                        x += step_x
                    y += step_y
            else:
                centers.append((r.x0 + r.width / 2.0, r.y0 + r.height / 2.0))
            for cx, cy in centers:
                pivot = fitz.Point(cx, cy)
                mat = fitz.Matrix(1, 1).prerotate(angle)
                pt = fitz.Point(cx - tw / 2.0, cy + fontsize / 3.0)
                page.insert_text(
                    pt,
                    text,
                    fontname="helv",
                    fontsize=fontsize,
                    color=color,
                    fill_opacity=opacity,
                    stroke_opacity=opacity,
                    morph=(pivot, mat),
                    overlay=not underlay,
                )
        ctx.report(len(pages), len(pages), "Saving")
        return _save_doc(doc, output)
    finally:
        doc.close()


def add_image_watermark(
    src: str,
    output: str,
    image_path: str,
    scale: float = 0.35,
    opacity: float = 0.35,
    position: str = "center",
    underlay: bool = False,
    page_text: Optional[str] = None,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    """Stamp an image watermark with adjustable scale, opacity, and placement."""
    ctx = ctx_or_default(ctx)
    check_image_file(image_path)
    scale = max(0.05, min(1.0, float(scale)))
    opacity = max(0.05, min(1.0, float(opacity)))
    with Image.open(image_path) as im:
        rgba = im.convert("RGBA")
        r_ch, g_ch, b_ch, a_ch = rgba.split()
        a_ch = a_ch.point(lambda p: int(p * opacity))
        rgba = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))
        img_w, img_h = rgba.size
        buf = io.BytesIO()
        rgba.save(buf, "PNG")
        png_bytes = buf.getvalue()

    doc = open_pdf(src, password)
    try:
        pages = _resolve_pages(doc, page_text)
        margin = 24.0
        for idx, pno in enumerate(pages):
            ctx.report(idx, len(pages), f"Applying image watermark to page {pno + 1}")
            page = doc[pno]
            pr = page.rect
            target_w = pr.width * scale
            target_h = target_w * (img_h / max(1, img_w))
            if "left" in position:
                x0 = pr.x0 + margin
            elif "right" in position:
                x0 = pr.x1 - margin - target_w
            else:
                x0 = pr.x0 + (pr.width - target_w) / 2.0
            if "top" in position:
                y0 = pr.y0 + margin
            elif "bottom" in position:
                y0 = pr.y1 - margin - target_h
            else:
                y0 = pr.y0 + (pr.height - target_h) / 2.0
            rect = fitz.Rect(x0, y0, x0 + target_w, y0 + target_h)
            page.insert_image(rect, stream=png_bytes, overlay=not underlay)
        ctx.report(len(pages), len(pages), "Saving")
        return _save_doc(doc, output)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# 4. Annotate & Add Content (Text, Images, Highlight, Underline, Shapes, Ink)
# ---------------------------------------------------------------------------
def annotate_pdf(
    src: str,
    output: str,
    mode: str,
    *,
    text: str = "",
    search_text: str = "",
    image_path: str = "",
    shape_kind: str = "rect",
    x_mm: float = 25.0,
    y_mm: float = 25.0,
    width_mm: float = 80.0,
    height_mm: float = 35.0,
    fontsize: float = 12.0,
    color_name: str = "Red",
    stroke_width: float = 2.0,
    page_text: Optional[str] = None,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> tuple[str, int]:
    """Add text, image, highlight, underline, shape, or freehand drawing to pages.
    Returns (output_path, count_of_items_added)."""
    ctx = ctx_or_default(ctx)
    color = NAMED_COLORS.get(color_name, (0.85, 0.15, 0.15))
    doc = open_pdf(src, password)
    try:
        pages = _resolve_pages(doc, page_text)
        x0 = x_mm * MM
        y0 = y_mm * MM
        w = max(10.0, width_mm * MM)
        h = max(10.0, height_mm * MM)
        box = fitz.Rect(x0, y0, x0 + w, y0 + h)
        count = 0

        if mode == "add_image":
            if not image_path:
                raise ProcessingError("Select an image file to insert.")
            check_image_file(image_path)
        elif mode == "add_text":
            if not text.strip():
                raise ProcessingError("Enter the text you want to add.")
        elif mode in ("highlight", "underline"):
            if not search_text.strip():
                raise ProcessingError("Enter the text to search and mark.")

        for idx, pno in enumerate(pages):
            ctx.report(idx, len(pages), f"Editing page {pno + 1}")
            page = doc[pno]
            if mode == "add_text":
                page.insert_textbox(box, text, fontsize=fontsize, fontname="helv", color=color, overlay=True)
                count += 1
            elif mode == "add_image":
                page.insert_image(box, filename=image_path, keep_proportion=True, overlay=True)
                count += 1
            elif mode in ("highlight", "underline"):
                quads = page.search_for(search_text.strip(), quads=True)
                for q in quads:
                    annot = page.add_highlight_annot(q) if mode == "highlight" else page.add_underline_annot(q)
                    annot.set_colors(stroke=color)
                    annot.update()
                    count += 1
            elif mode == "shape":
                if shape_kind == "circle":
                    annot = page.add_circle_annot(box)
                elif shape_kind == "line":
                    annot = page.add_line_annot(box.tl, box.br)
                else:
                    annot = page.add_rect_annot(box)
                annot.set_colors(stroke=color)
                annot.set_border(width=max(0.5, float(stroke_width)))
                annot.update()
                count += 1
            elif mode == "freehand":
                # Smooth signature/wave or underlined flourish inside `box`, plus optional note
                pts = [
                    (box.x0 + box.width * t / 20.0,
                     box.y0 + box.height * (0.5 + 0.35 * math.sin(t * 0.6)))
                    for t in range(21)
                ]
                annot = page.add_ink_annot([pts])
                annot.set_colors(stroke=color)
                annot.set_border(width=max(1.0, float(stroke_width)))
                if text.strip():
                    annot.set_info(content=text.strip(), title="PDF Master")
                annot.update()
                count += 1
            else:
                raise ProcessingError(f"Unknown edit mode: {mode}")

        if mode in ("highlight", "underline") and count == 0:
            raise ProcessingError(f"No occurrences of '{search_text.strip()}' were found on the selected pages.")
        ctx.report(len(pages), len(pages), "Saving")
        _save_doc(doc, output)
        return output, count
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# 5. Crop Pages
# ---------------------------------------------------------------------------
def crop_pdf(
    src: str,
    output: str,
    top_mm: float = 0.0,
    bottom_mm: float = 0.0,
    left_mm: float = 0.0,
    right_mm: float = 0.0,
    page_text: Optional[str] = None,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    """Crop margins (in mm) from selected or all pages."""
    ctx = ctx_or_default(ctx)
    if all(v <= 0 for v in (top_mm, bottom_mm, left_mm, right_mm)):
        raise ProcessingError("Specify at least one positive crop margin (top, bottom, left, or right).")
    doc = open_pdf(src, password)
    try:
        pages = _resolve_pages(doc, page_text)
        t_pt, b_pt, l_pt, r_pt = top_mm * MM, bottom_mm * MM, left_mm * MM, right_mm * MM
        for idx, pno in enumerate(pages):
            ctx.report(idx, len(pages), f"Cropping page {pno + 1}")
            page = doc[pno]
            mb = page.cropbox
            new_box = fitz.Rect(mb.x0 + l_pt, mb.y0 + t_pt, mb.x1 - r_pt, mb.y1 - b_pt)
            if new_box.width < 36 or new_box.height < 36:
                raise ProcessingError(f"Crop margins are too large for page {pno + 1}.")
            page.set_cropbox(new_box)
        ctx.report(len(pages), len(pages), "Saving")
        return _save_doc(doc, output)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# 6. Edit PDF Metadata
# ---------------------------------------------------------------------------
def read_metadata(src: str, password: Optional[str] = None) -> dict[str, str]:
    doc = open_pdf(src, password)
    try:
        md = doc.metadata or {}
        return {k: (md.get(k) or "") for k in ("title", "author", "subject", "keywords", "creator", "producer")}
    finally:
        doc.close()


def edit_metadata(
    src: str,
    output: str,
    metadata: dict[str, str],
    clear_all: bool = False,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    ctx = ctx_or_default(ctx)
    doc = open_pdf(src, password)
    try:
        ctx.report(0, 1, "Updating metadata")
        if clear_all:
            doc.set_metadata({})
            try:
                doc.del_xml_metadata()
            except Exception:
                pass
        else:
            clean = {k: str(v).strip() for k, v in metadata.items()
                     if k in ("title", "author", "subject", "keywords", "creator", "producer")}
            doc.set_metadata(clean)
        ctx.report(1, 1, "Saving")
        return _save_doc(doc, output)
    finally:
        doc.close()
