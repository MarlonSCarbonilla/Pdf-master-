"""Phase 2 - PDF Utilities engine: repair, remove blank pages, flatten annotations/forms,
grayscale conversion, extract text, extract embedded images, compare two PDFs, batch rename."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import datetime
import difflib
import io
import os
import re
import shutil
from dataclasses import dataclass
from typing import Optional, Sequence

import fitz
from PIL import Image, ImageChops, ImageStat

from core.common import JobContext, ProcessingError, ctx_or_default
from core.rust_accel import is_buffer_blank, rgb_to_grayscale_bytes, visual_diff_rgb
from utils.file_utils import atomic_write, safe_filename, unique_path
from utils.validators import has_pdf_header, open_pdf, parse_page_ranges


# ---------------------------------------------------------------------------
# 1. Repair PDF
# ---------------------------------------------------------------------------
def repair_pdf(
    src: str,
    output: str,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> tuple[str, int]:
    """Attempt to repair a damaged/corrupted PDF using PyMuPDF + pikepdf stream recovery.
    Returns (output_path, recovered_page_count)."""
    ctx = ctx_or_default(ctx)
    if not os.path.isfile(src) or os.path.getsize(src) == 0:
        raise ProcessingError("The file does not exist or is empty.")
    if not has_pdf_header(src):
        raise ProcessingError(f"'{os.path.basename(src)}' does not contain a PDF header and cannot be repaired.")

    ctx.report(0, 2, "Inspecting and rebuilding PDF structure")
    recovered_pages = 0
    # Try PyMuPDF page-by-page salvage first
    try:
        doc = fitz.open(src)
        if doc.needs_pass and password:
            doc.authenticate(password)
        rebuilt = fitz.open()
        try:
            for i in range(doc.page_count):
                try:
                    rebuilt.insert_pdf(doc, from_page=i, to_page=i)
                    recovered_pages += 1
                except Exception:
                    continue
            if recovered_pages > 0:
                atomic_write(
                    output,
                    lambda tmp: rebuilt.save(tmp, garbage=4, deflate=True, clean=True),
                )
        finally:
            rebuilt.close()
            doc.close()
    except Exception:
        recovered_pages = 0

    # If PyMuPDF salvage failed, try pikepdf structural open/save
    if recovered_pages == 0:
        try:
            import pikepdf

            with pikepdf.open(src, password=password or "") as pdf:
                recovered_pages = len(pdf.pages)
                if recovered_pages > 0:
                    atomic_write(output, lambda tmp: pdf.save(tmp, compress_streams=True))
        except Exception:
            pass

    if recovered_pages == 0 or not os.path.exists(output):
        raise ProcessingError(f"'{os.path.basename(src)}' is too severely damaged to recover any readable pages.")

    ctx.report(2, 2, "Done")
    return output, recovered_pages


# ---------------------------------------------------------------------------
# 2. Remove Blank Pages
# ---------------------------------------------------------------------------
def _is_page_blank(page: fitz.Page, threshold: float = 0.998) -> bool:
    """Return True if a page has no text and renders as almost pure white (Rust-accelerated)."""
    if page.get_text("text").strip():
        return False
    pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), colorspace=fitz.csGRAY, alpha=False)
    return is_buffer_blank(pix.samples, white_threshold=245, max_dark_ratio=max(0.0005, 1.0 - threshold))


def remove_blank_pages(
    src: str,
    output: str,
    sensitivity: float = 0.995,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> tuple[str, list[int], int]:
    """Detect and remove blank/near-blank pages.
    Returns (output_path, removed_1based_pages, kept_page_count)."""
    ctx = ctx_or_default(ctx)
    doc = open_pdf(src, password)
    try:
        total = doc.page_count
        keep: list[int] = []
        removed: list[int] = []
        for i in range(total):
            ctx.report(i, total, f"Checking page {i + 1} of {total}")
            if _is_page_blank(doc[i], threshold=sensitivity):
                removed.append(i + 1)
            else:
                keep.append(i)
        if not keep:
            raise ProcessingError("Every page in this document appears blank. Cannot remove all pages.")
        new_doc = fitz.open()
        try:
            for i in keep:
                new_doc.insert_pdf(doc, from_page=i, to_page=i)
            atomic_write(output, lambda tmp: new_doc.save(tmp, garbage=3, deflate=True))
        finally:
            new_doc.close()
        ctx.report(total, total, "Done")
        return output, removed, len(keep)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# 3. Flatten Annotations & Form Fields
# ---------------------------------------------------------------------------
def flatten_pdf(
    src: str,
    output: str,
    flatten_annots: bool = True,
    flatten_widgets: bool = True,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    """Bake annotations and/or interactive form fields permanently into page content."""
    ctx = ctx_or_default(ctx)
    doc = open_pdf(src, password)
    try:
        ctx.report(0, 2, "Flattening annotations and form elements")
        doc.bake(annots=flatten_annots, widgets=flatten_widgets)
        ctx.report(1, 2, "Saving flattened PDF")
        atomic_write(output, lambda tmp: doc.save(tmp, garbage=3, deflate=True))
        ctx.report(2, 2, "Done")
        return output
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# 4. Convert to Grayscale
# ---------------------------------------------------------------------------
def _rgb_stream_to_gray(stream: bytes) -> bytes:
    """Convert RGB color operators (r g b rg / RG) in a PDF content stream to DeviceGray (g / G)."""
    def _conv(m: re.Match) -> bytes:
        try:
            r, g, b = float(m.group(1)), float(m.group(2)), float(m.group(3))
            op = m.group(4)
            lum = max(0.0, min(1.0, 0.299 * r + 0.587 * g + 0.114 * b))
            new_op = b"g" if op == b"rg" else b"G"
            return f"{lum:.3f} ".encode("ascii") + new_op
        except Exception:
            return m.group(0)

    pattern = re.compile(rb"(\d*\.?\d+)\s+(\d*\.?\d+)\s+(\d*\.?\d+)\s+(rg|RG)\b")
    return pattern.sub(_conv, stream)


def convert_to_grayscale(
    src: str,
    output: str,
    preserve_text: bool = True,
    dpi: int = 150,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    """Convert a PDF to grayscale.
    When `preserve_text=True` (default), embedded images and RGB stream operators are
    converted to grayscale while keeping selectable text and vector paths sharp.
    When `preserve_text=False`, each page is rendered as an 8-bit grayscale bitmap."""
    ctx = ctx_or_default(ctx)
    doc = open_pdf(src, password)
    try:
        total = doc.page_count
        if preserve_text:
            seen_xrefs: set[int] = set()
            for pno in range(total):
                ctx.report(pno, total, f"Converting page {pno + 1} of {total} to grayscale")
                page = doc[pno]
                page.clean_contents()
                for cx in page.get_contents():
                    raw_s = doc.xref_stream(cx)
                    if raw_s:
                        doc.update_stream(cx, _rgb_stream_to_gray(raw_s))
                for info in page.get_images(full=True):
                    xref = info[0]
                    if xref in seen_xrefs:
                        continue
                    seen_xrefs.add(xref)
                    try:
                        ex = doc.extract_image(xref)
                        if not ex or ex.get("colorspace") == 1:
                            continue
                        with Image.open(io.BytesIO(ex["image"])) as im:
                            rgb_im = im.convert("RGB")
                            w, h = rgb_im.size
                            gray_bytes = rgb_to_grayscale_bytes(rgb_im.tobytes(), w * h)
                            gray = Image.frombytes("L", (w, h), gray_bytes)
                            buf = io.BytesIO()
                            gray.save(buf, "PNG")
                        page.replace_image(xref, stream=buf.getvalue())
                    except Exception:
                        continue
            ctx.report(total, total, "Saving")
            atomic_write(output, lambda tmp: doc.save(tmp, garbage=3, deflate=True))
            return output
        else:
            out_doc = fitz.open()
            try:
                scale = dpi / 72.0
                for pno in range(total):
                    ctx.report(pno, total, f"Rendering grayscale page {pno + 1} of {total}")
                    page = doc[pno]
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False)
                    new_p = out_doc.new_page(width=page.rect.width, height=page.rect.height)
                    new_p.insert_image(new_p.rect, stream=pix.tobytes("png"))
                    pix = None
                ctx.report(total, total, "Saving")
                atomic_write(output, lambda tmp: out_doc.save(tmp, garbage=3, deflate=True))
                return output
            finally:
                out_doc.close()
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# 5. Extract Text
# ---------------------------------------------------------------------------
def extract_text_to_file(
    src: str,
    output_txt: str,
    page_text: Optional[str] = None,
    include_page_headers: bool = True,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> tuple[str, int, int]:
    """Extract selectable text from `src` into a UTF-8 `.txt` file.
    Returns (output_txt_path, pages_processed, total_characters)."""
    ctx = ctx_or_default(ctx)
    doc = open_pdf(src, password)
    try:
        if not page_text or page_text.strip().lower() == "all":
            pages = list(range(doc.page_count))
        else:
            try:
                pages = parse_page_ranges(page_text, doc.page_count)
            except ValueError as e:
                raise ProcessingError(str(e)) from None

        chunks: list[str] = []
        chars = 0
        for idx, pno in enumerate(pages):
            ctx.report(idx, len(pages), f"Extracting text from page {pno + 1}")
            txt = doc[pno].get_text("text").strip()
            chars += len(txt)
            if include_page_headers:
                chunks.append(f"=== Page {pno + 1} ===\n{txt}\n")
            else:
                chunks.append(txt + "\n")

        full_text = "\n".join(chunks)

        def _write(tmp: str) -> None:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(full_text)

        atomic_write(output_txt, _write)
        ctx.report(len(pages), len(pages), "Done")
        return output_txt, len(pages), chars
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# 6. Extract Embedded Images
# ---------------------------------------------------------------------------
def extract_embedded_images(
    src: str,
    out_dir: str,
    page_text: Optional[str] = None,
    min_dimension: int = 16,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> list[str]:
    """Extract all unique embedded raster images from `src` into `out_dir`."""
    ctx = ctx_or_default(ctx)
    doc = open_pdf(src, password)
    try:
        if not page_text or page_text.strip().lower() == "all":
            pages = list(range(doc.page_count))
        else:
            try:
                pages = parse_page_ranges(page_text, doc.page_count)
            except ValueError as e:
                raise ProcessingError(str(e)) from None

        os.makedirs(out_dir, exist_ok=True)
        stem = safe_filename(os.path.splitext(os.path.basename(src))[0])
        seen: set[int] = set()
        saved: list[str] = []
        for idx, pno in enumerate(pages):
            ctx.report(idx, len(pages), f"Scanning page {pno + 1} for images")
            for img_idx, info in enumerate(doc[pno].get_images(full=True), start=1):
                xref = info[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    ex = doc.extract_image(xref)
                    if not ex:
                        continue
                    w, h = ex.get("width", 0), ex.get("height", 0)
                    if w < min_dimension or h < min_dimension:
                        continue
                    ext = (ex.get("ext") or "png").lower()
                    raw = ex["image"]
                    if ext not in ("png", "jpg", "jpeg", "tif", "tiff", "bmp"):
                        with Image.open(io.BytesIO(raw)) as im:
                            buf = io.BytesIO()
                            im.convert("RGB").save(buf, "PNG")
                            raw = buf.getvalue()
                            ext = "png"
                    fname = f"{stem}_p{pno + 1:03d}_img{img_idx:02d}.{ext}"
                    out_path = unique_path(os.path.join(out_dir, fname))
                    atomic_write(out_path, lambda tmp, data=raw: open(tmp, "wb").write(data))
                    saved.append(out_path)
                except Exception:
                    continue
        if not saved:
            raise ProcessingError("No embedded images were found on the selected pages.")
        ctx.report(len(pages), len(pages), "Done")
        return saved
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# 7. Compare Two PDFs
# ---------------------------------------------------------------------------
@dataclass
class CompareResult:
    report_pdf: str
    pages_compared: int
    pages_with_text_diff: int
    pages_with_visual_diff: int
    summary: str


def compare_pdfs(
    pdf_a: str,
    pdf_b: str,
    output_report_pdf: str,
    password_a: Optional[str] = None,
    password_b: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> CompareResult:
    """Compare two PDFs page by page (both text and visual appearance) and write a
    visual + textual comparison report PDF."""
    ctx = ctx_or_default(ctx)
    doc_a = open_pdf(pdf_a, password_a)
    doc_b = open_pdf(pdf_b, password_b)
    report = fitz.open()
    try:
        max_pages = max(doc_a.page_count, doc_b.page_count)
        text_diffs = 0
        visual_diffs = 0
        diff_lines_summary: list[str] = [
            f"Document A: {os.path.basename(pdf_a)} ({doc_a.page_count} pages)",
            f"Document B: {os.path.basename(pdf_b)} ({doc_b.page_count} pages)",
            "",
        ]

        scale = 96.0 / 72.0
        for i in range(max_pages):
            ctx.report(i, max_pages, f"Comparing page {i + 1} of {max_pages}")
            has_a = i < doc_a.page_count
            has_b = i < doc_b.page_count
            txt_a = doc_a[i].get_text("text").splitlines() if has_a else []
            txt_b = doc_b[i].get_text("text").splitlines() if has_b else []
            diff = list(difflib.unified_diff(txt_a, txt_b, lineterm="", n=1))
            if diff:
                text_diffs += 1
                diff_lines_summary.append(f"Page {i + 1}: text differs ({len(diff)} diff lines)")

            # Visual comparison page (landscape summary showing A, B, and Red-highlighted diff)
            rp = report.new_page(width=842, height=595)
            rp.insert_text((28, 30), f"Comparison - Page {i + 1} of {max_pages}", fontsize=14, fontname="helv")

            if has_a and has_b:
                pa = doc_a[i].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                pb = doc_b[i].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                im_a = Image.frombytes("RGB", (pa.width, pa.height), pa.samples)
                im_b = Image.frombytes("RGB", (pb.width, pb.height), pb.samples)
                if im_a.size != im_b.size:
                    im_b_resized = im_b.resize(im_a.size, Image.LANCZOS)
                else:
                    im_b_resized = im_b
                pixel_count = im_a.width * im_a.height
                diff_bytes, changed_px = visual_diff_rgb(
                    im_a.tobytes(),
                    im_b_resized.tobytes(),
                    pixel_count,
                    threshold=18,
                )
                is_vdiff = (changed_px / max(1, pixel_count)) > 0.002 or im_a.size != im_b.size
                if is_vdiff:
                    visual_diffs += 1
                overlay = Image.frombytes("RGB", im_a.size, diff_bytes)

                for col_idx, (label, img_obj) in enumerate((("Document A", im_a), ("Document B", im_b), ("Differences (Red)", overlay))):
                    x0 = 28 + col_idx * 265
                    rp.insert_text((x0, 52), label, fontsize=10, fontname="helv")
                    buf = io.BytesIO()
                    img_obj.save(buf, "PNG")
                    rp.insert_image(fitz.Rect(x0, 60, x0 + 250, 430), stream=buf.getvalue(), keep_proportion=True)
                im_a.close()
                im_b.close()
                overlay.close()
            else:
                visual_diffs += 1
                missing = "Document B (missing page)" if has_a else "Document A (missing page)"
                rp.insert_text((28, 80), f"Only present in one document - missing in {missing}.", fontsize=11, color=(0.8, 0.1, 0.1))

            # Show text diff snippet at the bottom of the report page
            snippet = "\n".join(diff[:10]) if diff else "No text differences on this page."
            rp.insert_textbox(fitz.Rect(28, 445, 814, 575), snippet, fontsize=8.5, fontname="cour")

        summary_str = (
            f"Compared {max_pages} page(s): {text_diffs} page(s) with text changes, "
            f"{visual_diffs} page(s) with visual changes."
        )
        atomic_write(output_report_pdf, lambda tmp: report.save(tmp, garbage=3, deflate=True))
        ctx.report(max_pages, max_pages, "Done")
        return CompareResult(
            report_pdf=output_report_pdf,
            pages_compared=max_pages,
            pages_with_text_diff=text_diffs,
            pages_with_visual_diff=visual_diffs,
            summary=summary_str,
        )
    finally:
        report.close()
        doc_a.close()
        doc_b.close()


# ---------------------------------------------------------------------------
# 8. Batch Rename Output Files
# ---------------------------------------------------------------------------
def batch_rename_pdfs(
    inputs: Sequence[str],
    out_dir: str,
    pattern: str = "{num:03d}_{name}",
    start_num: int = 1,
    find_text: str = "",
    replace_text: str = "",
    passwords: Optional[dict[str, str]] = None,
    ctx: Optional[JobContext] = None,
) -> list[str]:
    """Copy a batch of PDFs into `out_dir` with newly formatted names.
    Supported placeholders: {num}, {num:03d}, {name}, {pages}, {date}."""
    ctx = ctx_or_default(ctx)
    passwords = passwords or {}
    if not inputs:
        raise ProcessingError("Add at least one PDF file to rename.")
    pattern = (pattern or "{num:03d}_{name}").strip()
    os.makedirs(out_dir, exist_ok=True)
    today = datetime.date.today().isoformat()
    results: list[str] = []

    for idx, src in enumerate(inputs):
        ctx.report(idx, len(inputs), f"Processing {os.path.basename(src)}")
        doc = open_pdf(src, passwords.get(src))
        try:
            pages = doc.page_count
        finally:
            doc.close()
        stem = os.path.splitext(os.path.basename(src))[0]
        if find_text:
            stem = stem.replace(find_text, replace_text)
        num = start_num + idx
        try:
            rendered = pattern.format(num=num, name=stem, original=stem, pages=pages, date=today)
        except Exception:
            rendered = f"{num:03d}_{stem}"
        clean = safe_filename(rendered)
        if not clean.lower().endswith(".pdf"):
            clean += ".pdf"
        dst = unique_path(os.path.join(out_dir, clean))
        atomic_write(dst, lambda tmp, s=src: shutil.copyfile(s, tmp))
        results.append(dst)

    ctx.report(len(inputs), len(inputs), "Done")
    return results
