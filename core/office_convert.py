"""Phase 3 (Optional Module) - Office document conversions:
PDF -> DOCX, PDF -> XLSX, PDF -> PPTX, and DOCX / XLSX / PPTX -> PDF."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import io
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

import fitz

from core.common import JobContext, ProcessingError, ctx_or_default
from utils.file_utils import atomic_write
from utils.validators import open_pdf, parse_page_ranges

OFFICE_EXTS = {".docx", ".xlsx", ".pptx"}

COMMON_LIBREOFFICE_PATHS = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\LibreOffice\program\soffice.exe"),
)


def find_libreoffice(custom_path: str = "") -> Optional[str]:
    if custom_path and os.path.isfile(custom_path):
        return custom_path
    for name in ("soffice", "libreoffice"):
        which = shutil.which(name)
        if which:
            return which
    for p in COMMON_LIBREOFFICE_PATHS:
        if os.path.isfile(p):
            return p
    return None


@dataclass
class OfficeConvertResult:
    output: str
    pages_or_items: int
    note: str = ""


# ---------------------------------------------------------------------------
# 1. PDF -> Word (.docx)
# ---------------------------------------------------------------------------
def pdf_to_docx(
    src: str,
    output: str,
    include_images: bool = True,
    page_text: Optional[str] = None,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> OfficeConvertResult:
    """Convert a PDF to a Word (.docx) document while preserving headings, bold/italic,
    tables, and embedded images as much as reasonably possible."""
    ctx = ctx_or_default(ctx)
    try:
        import docx
        from docx.shared import Inches, Pt, RGBColor
    except ImportError:
        raise ProcessingError("The optional 'python-docx' library is not installed.") from None

    pdf = open_pdf(src, password)
    try:
        if page_text and page_text.strip().lower() != "all":
            try:
                pages = parse_page_ranges(page_text, pdf.page_count)
            except ValueError as e:
                raise ProcessingError(str(e)) from None
        else:
            pages = list(range(pdf.page_count))

        word = docx.Document()
        scanned_pages = 0
        multi_col_pages = 0

        for idx, pno in enumerate(pages):
            ctx.report(idx, len(pages), f"Converting page {pno + 1} to Word")
            page = pdf[pno]
            text_raw = page.get_text("text").strip()

            # Scanned page (no selectable text): embed rendered page image so content isn't lost
            if not text_raw:
                scanned_pages += 1
                pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
                word.add_picture(io.BytesIO(pix.tobytes("png")), width=Inches(6.0))
                if idx < len(pages) - 1:
                    word.add_page_break()
                continue

            # Extract tables first and remember their bounding boxes
            table_rects: list[fitz.Rect] = []
            extracted_tables: list[tuple[float, list[list[str]]]] = []
            try:
                tf = page.find_tables()
                for tab in tf.tables:
                    t_rect = fitz.Rect(tab.bbox)
                    rows = tab.extract()
                    if rows and any(any(cell for cell in r) for r in rows):
                        table_rects.append(t_rect)
                        extracted_tables.append((t_rect.y0, [[str(c or "").strip() for c in r] for r in rows]))
            except Exception:
                pass

            # Collect text blocks and images sorted vertically by y0
            items: list[tuple[float, str, object]] = []
            for y0, rows in extracted_tables:
                items.append((y0, "table", rows))

            pdict = page.get_text("dict")
            text_x0s: list[float] = []
            for blk in pdict.get("blocks", []):
                b_rect = fitz.Rect(blk.get("bbox", (0, 0, 0, 0)))
                if any(b_rect.intersects(tr) for tr in table_rects):
                    continue
                if blk.get("type") == 0:
                    text_x0s.append(round(b_rect.x0, -1))
                    items.append((b_rect.y0, "text", blk))
                elif blk.get("type") == 1 and include_images and blk.get("image"):
                    items.append((b_rect.y0, "image", (b_rect, blk.get("image"))))

            if len(set(text_x0s)) >= 3:
                multi_col_pages += 1

            items.sort(key=lambda t: t[0])

            for _, kind, payload in items:
                if kind == "table":
                    rows = payload  # type: ignore[assignment]
                    ncols = max(len(r) for r in rows)
                    if ncols > 0:
                        t = word.add_table(rows=len(rows), cols=ncols)
                        t.style = "Table Grid"
                        for r_i, r_vals in enumerate(rows):
                            for c_i, val in enumerate(r_vals):
                                t.cell(r_i, c_i).text = val
                elif kind == "image":
                    b_rect, img_bytes = payload  # type: ignore[misc]
                    try:
                        w_in = max(0.8, min(6.0, b_rect.width / 72.0))
                        word.add_picture(io.BytesIO(img_bytes), width=Inches(w_in))
                    except Exception:
                        pass
                elif kind == "text":
                    blk = payload  # type: ignore[assignment]
                    lines = blk.get("lines", [])
                    if not lines:
                        continue
                    first_spans = lines[0].get("spans", [])
                    max_sz = max((sp.get("size", 11.0) for ln in lines for sp in ln.get("spans", [])), default=11.0)
                    full_block_txt = " ".join(
                        "".join(sp.get("text", "") for sp in ln.get("spans", [])) for ln in lines
                    ).strip()
                    if not full_block_txt:
                        continue
                    if max_sz >= 18 and len(full_block_txt) < 120:
                        word.add_heading(full_block_txt, level=1)
                    elif max_sz >= 14 and len(full_block_txt) < 140:
                        word.add_heading(full_block_txt, level=2)
                    else:
                        para = word.add_paragraph()
                        for l_i, ln in enumerate(lines):
                            if l_i > 0:
                                para.add_run(" ")
                            for sp in ln.get("spans", []):
                                txt = sp.get("text", "")
                                if not txt:
                                    continue
                                run = para.add_run(txt)
                                sz = sp.get("size", 11.0)
                                run.font.size = Pt(max(7.0, min(36.0, round(sz, 1))))
                                flags = int(sp.get("flags", 0))
                                font_low = (sp.get("font") or "").lower()
                                if (flags & 16) or "bold" in font_low:
                                    run.bold = True
                                if (flags & 2) or "italic" in font_low or "oblique" in font_low:
                                    run.italic = True
                                col_int = int(sp.get("color", 0))
                                if col_int:
                                    r_c = (col_int >> 16) & 255
                                    g_c = (col_int >> 8) & 255
                                    b_c = col_int & 255
                                    run.font.color.rgb = RGBColor(r_c, g_c, b_c)

            if idx < len(pages) - 1:
                word.add_page_break()

        notes: list[str] = []
        if scanned_pages:
            notes.append(f"{scanned_pages} scanned page(s) had no selectable text and were inserted as page images (use OCR first for editable text).")
        if multi_col_pages:
            notes.append(f"{multi_col_pages} page(s) contained complex multi-column positioning; paragraphs were linearized in reading order.")

        ctx.report(len(pages), len(pages), "Saving Word document")
        atomic_write(output, lambda tmp: word.save(tmp))
        return OfficeConvertResult(output=output, pages_or_items=len(pages), note=" ".join(notes))
    finally:
        pdf.close()


# ---------------------------------------------------------------------------
# 2. PDF -> Excel (.xlsx)
# ---------------------------------------------------------------------------
def pdf_to_xlsx(
    src: str,
    output: str,
    page_text: Optional[str] = None,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> OfficeConvertResult:
    """Extract tables (or structured columnar rows) from a PDF into an Excel (.xlsx) workbook."""
    ctx = ctx_or_default(ctx)
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise ProcessingError("The optional 'openpyxl' library is not installed.") from None

    pdf = open_pdf(src, password)
    try:
        if page_text and page_text.strip().lower() != "all":
            try:
                pages = parse_page_ranges(page_text, pdf.page_count)
            except ValueError as e:
                raise ProcessingError(str(e)) from None
        else:
            pages = list(range(pdf.page_count))

        wb = openpyxl.Workbook()
        default_ws = wb.active
        tables_found = 0
        fallback_pages = 0
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="D93831")

        def _style_sheet(ws) -> None:
            for col in ws.columns:
                max_len = max((len(str(cell.value or "")) for cell in col), default=8)
                col_letter = get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = max(10, min(50, max_len + 3))

        for idx, pno in enumerate(pages):
            ctx.report(idx, len(pages), f"Extracting tables from page {pno + 1}")
            page = pdf[pno]
            page_tables: list[list[list[str]]] = []
            try:
                tf = page.find_tables()
                for tab in tf.tables:
                    rows = tab.extract()
                    if rows and any(any(c for c in r) for r in rows):
                        page_tables.append([[str(c or "").strip() for c in r] for r in rows])
            except Exception:
                pass

            if page_tables:
                for t_idx, rows in enumerate(page_tables, start=1):
                    tables_found += 1
                    title = f"P{pno + 1}_Table{t_idx}"
                    ws = wb.create_sheet(title=title[:31])
                    for r_i, r_vals in enumerate(rows, start=1):
                        ws.append(r_vals)
                        if r_i == 1:
                            for cell in ws[1]:
                                cell.font = header_font
                                cell.fill = header_fill
                                cell.alignment = Alignment(vertical="center")
                    _style_sheet(ws)
            else:
                # Fallback: group words by vertical line (y) and sort horizontally (x)
                words = page.get_text("words")
                if words:
                    fallback_pages += 1
                    ws = wb.create_sheet(title=f"Page_{pno + 1}"[:31])
                    rows_by_y: dict[int, list[tuple[float, str]]] = {}
                    for x0, y0, _x1, _y1, wtext, *_ in words:
                        bucket = int(round(y0 / 6.0) * 6)
                        rows_by_y.setdefault(bucket, []).append((x0, wtext))
                    for y_key in sorted(rows_by_y):
                        line_words = [w for _, w in sorted(rows_by_y[y_key], key=lambda t: t[0])]
                        # Split into columns when separated by multi-space or tabs, or keep as columns
                        ws.append(line_words)
                    _style_sheet(ws)

        if len(wb.sheetnames) > 1 and default_ws in wb.worksheets:
            wb.remove(default_ws)
        else:
            default_ws.title = "Empty"
            default_ws.append(["No extractable tables or text were found in this PDF."])

        note = ""
        if tables_found == 0 and fallback_pages > 0:
            note = (
                f"No bordered tables were detected; extracted {fallback_pages} page(s) using row/column word alignment. "
                "Complex borderless layouts may require manual column adjustment."
            )
        elif tables_found == 0:
            note = "This PDF appears to be scanned or contains no extractable text tables."

        ctx.report(len(pages), len(pages), "Saving Excel workbook")
        atomic_write(output, lambda tmp: wb.save(tmp))
        return OfficeConvertResult(output=output, pages_or_items=max(tables_found, fallback_pages), note=note)
    finally:
        pdf.close()


# ---------------------------------------------------------------------------
# 3. PDF -> PowerPoint (.pptx)
# ---------------------------------------------------------------------------
def pdf_to_pptx(
    src: str,
    output: str,
    dpi: int = 150,
    page_text: Optional[str] = None,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> OfficeConvertResult:
    """Convert PDF pages into a PowerPoint (.pptx) presentation (one slide per page,
    preserving exact visual layout plus speaker notes with the page's selectable text)."""
    ctx = ctx_or_default(ctx)
    try:
        import pptx
        from pptx.util import Inches
    except ImportError:
        raise ProcessingError("The optional 'python-pptx' library is not installed.") from None

    pdf = open_pdf(src, password)
    try:
        if page_text and page_text.strip().lower() != "all":
            try:
                pages = parse_page_ranges(page_text, pdf.page_count)
            except ValueError as e:
                raise ProcessingError(str(e)) from None
        else:
            pages = list(range(pdf.page_count))

        prs = pptx.Presentation()
        first_rect = pdf[pages[0]].rect
        prs.slide_width = Inches(first_rect.width / 72.0)
        prs.slide_height = Inches(first_rect.height / 72.0)
        blank_layout = prs.slide_layouts[6]
        scale = dpi / 72.0

        for idx, pno in enumerate(pages):
            ctx.report(idx, len(pages), f"Creating slide {idx + 1} of {len(pages)}")
            page = pdf[pno]
            slide = prs.slides.add_slide(blank_layout)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            slide.shapes.add_picture(
                io.BytesIO(pix.tobytes("png")),
                0,
                0,
                width=prs.slide_width,
                height=prs.slide_height,
            )
            pix = None
            txt = page.get_text("text").strip()
            if txt:
                slide.notes_slide.notes_text_frame.text = txt

        ctx.report(len(pages), len(pages), "Saving PowerPoint presentation")
        atomic_write(output, lambda tmp: prs.save(tmp))
        return OfficeConvertResult(output=output, pages_or_items=len(pages))
    finally:
        pdf.close()


# ---------------------------------------------------------------------------
# 4. Office (DOCX / XLSX / PPTX) -> PDF
# ---------------------------------------------------------------------------
def _libreoffice_to_pdf(src: str, output: str, soffice: str) -> bool:
    """Run LibreOffice in headless mode with a temporary profile to convert `src` to `output`."""
    tmpdir = tempfile.mkdtemp(prefix="pdfm_lo_")
    try:
        profile_url = "file:///" + os.path.join(tmpdir, "profile").replace("\\", "/")
        cmd = [
            soffice,
            f"-env:UserInstallation={profile_url}",
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--convert-to",
            "pdf",
            "--outdir",
            tmpdir,
            os.path.abspath(src),
        ]
        subprocess.run(
            cmd,
            capture_output=True,
            timeout=120,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        stem = os.path.splitext(os.path.basename(src))[0]
        cand = os.path.join(tmpdir, stem + ".pdf")
        if not os.path.isfile(cand):
            pdfs = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.lower().endswith(".pdf")]
            cand = pdfs[0] if pdfs else ""
        if cand and os.path.isfile(cand) and os.path.getsize(cand) > 0:
            atomic_write(output, lambda tmp: shutil.copyfile(cand, tmp))
            return True
        return False
    except Exception:
        return False
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _docx_to_pdf_fallback(src: str, output: str, ctx: JobContext) -> int:
    """Pure-Python offline DOCX -> PDF renderer when LibreOffice is not installed."""
    import docx

    d = docx.Document(src)
    blocks: list[tuple[str, float, bool]] = []
    for p in d.paragraphs:
        txt = p.text.strip()
        if not txt:
            blocks.append(("", 6.0, False))
            continue
        style_name = (p.style.name if p.style else "").lower()
        if "heading 1" in style_name or "title" in style_name:
            blocks.append((txt, 16.0, True))
        elif "heading" in style_name:
            blocks.append((txt, 13.0, True))
        else:
            bold = any(bool(r.bold) for r in p.runs) and all(bool(r.bold) for r in p.runs if r.text.strip())
            blocks.append((txt, 11.0, bold))
    for tab in d.tables:
        for row in tab.rows:
            line = "  |  ".join(c.text.strip().replace("\n", " ") for c in row.cells)
            if line.strip():
                blocks.append((line, 9.5, False))
        blocks.append(("", 6.0, False))

    return _render_text_blocks_to_pdf(blocks, output, ctx)


def _xlsx_to_pdf_fallback(src: str, output: str, ctx: JobContext) -> int:
    """Pure-Python offline XLSX -> PDF renderer when LibreOffice is not installed."""
    import openpyxl

    wb = openpyxl.load_workbook(src, data_only=True)
    blocks: list[tuple[str, float, bool]] = []
    for name in wb.sheetnames:
        ws = wb[name]
        blocks.append((f"Sheet: {name}", 14.0, True))
        for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            vals = [str(v) if v is not None else "" for v in row]
            if any(vals):
                blocks.append(("   |   ".join(vals), 9.5, r_idx == 1))
        blocks.append(("", 10.0, False))
    wb.close()
    return _render_text_blocks_to_pdf(blocks, output, ctx, landscape=True)


def _pptx_to_pdf_fallback(src: str, output: str, ctx: JobContext) -> int:
    """Pure-Python offline PPTX -> PDF renderer when LibreOffice is not installed."""
    import pptx

    prs = pptx.Presentation(src)
    pdf = fitz.open()
    try:
        sw = float(prs.slide_width or 9144000) / 914400.0 * 72.0
        sh = float(prs.slide_height or 6858000) / 914400.0 * 72.0
        total = max(1, len(prs.slides))
        for idx, slide in enumerate(prs.slides):
            ctx.report(idx, total, f"Rendering slide {idx + 1}")
            page = pdf.new_page(width=sw, height=sh)
            for shape in slide.shapes:
                x0 = float(getattr(shape, "left", 0)) / 914400.0 * 72.0
                y0 = float(getattr(shape, "top", 0)) / 914400.0 * 72.0
                w = max(20.0, float(getattr(shape, "width", 1800000)) / 914400.0 * 72.0)
                h = max(20.0, float(getattr(shape, "height", 900000)) / 914400.0 * 72.0)
                rect = fitz.Rect(x0, y0, x0 + w, y0 + h)
                if getattr(shape, "shape_type", None) == 13 and hasattr(shape, "image"):
                    try:
                        page.insert_image(rect, stream=shape.image.blob, keep_proportion=True)
                        continue
                    except Exception:
                        pass
                if getattr(shape, "has_text_frame", False):
                    txt = shape.text_frame.text.strip()
                    if txt:
                        page.insert_textbox(rect, txt, fontsize=14, fontname="helv")
        if pdf.page_count == 0:
            pdf.new_page(width=sw, height=sh)
        atomic_write(output, lambda tmp: pdf.save(tmp, garbage=3, deflate=True))
        return pdf.page_count
    finally:
        pdf.close()


def _render_text_blocks_to_pdf(
    blocks: list[tuple[str, float, bool]],
    output: str,
    ctx: JobContext,
    landscape: bool = False,
) -> int:
    pdf = fitz.open()
    try:
        pw, ph = (841.89, 595.28) if landscape else (595.28, 841.89)
        margin = 42.0
        avail_w = pw - 2 * margin
        page = pdf.new_page(width=pw, height=ph)
        y = margin
        total = max(1, len(blocks))
        for idx, (text, fsize, bold) in enumerate(blocks):
            if idx % 25 == 0:
                ctx.report(idx, total, "Formatting document pages")
            if not text:
                y += fsize
                continue
            fontname = "hebo" if bold else "helv"
            est_lines = max(1, int(fitz.get_text_length(text, fontname=fontname, fontsize=fsize) / avail_w) + 1)
            box_h = max(fsize * 1.45, est_lines * fsize * 1.38 + 4)
            if y + box_h > ph - margin:
                page = pdf.new_page(width=pw, height=ph)
                y = margin
            rect = fitz.Rect(margin, y, pw - margin, min(ph - margin, y + box_h + fsize))
            page.insert_textbox(rect, text, fontsize=fsize, fontname=fontname)
            y += box_h
        atomic_write(output, lambda tmp: pdf.save(tmp, garbage=3, deflate=True))
        return pdf.page_count
    finally:
        pdf.close()


def office_to_pdf(
    src: str,
    output: str,
    libreoffice_path: str = "",
    ctx: Optional[JobContext] = None,
) -> OfficeConvertResult:
    """Convert DOCX, XLSX or PPTX to PDF using LibreOffice headless mode when installed,
    or the built-in offline Python converter as a fallback."""
    ctx = ctx_or_default(ctx)
    if not os.path.isfile(src):
        raise ProcessingError(f"File not found: {os.path.basename(src)}")
    ext = os.path.splitext(src)[1].lower()
    if ext not in OFFICE_EXTS:
        raise ProcessingError(f"Unsupported Office file format '{ext}'. Supported: .docx, .xlsx, .pptx.")

    ctx.report(0, 2, f"Converting {os.path.basename(src)} to PDF")
    soffice = find_libreoffice(libreoffice_path)
    if soffice and _libreoffice_to_pdf(src, output, soffice):
        doc = open_pdf(output)
        try:
            n = doc.page_count
        finally:
            doc.close()
        ctx.report(2, 2, "Done")
        return OfficeConvertResult(output=output, pages_or_items=n, note="Converted using LibreOffice headless engine.")

    # Pure-Python fallback so DOCX/XLSX/PPTX -> PDF works offline even without LibreOffice installed
    try:
        if ext == ".docx":
            pages = _docx_to_pdf_fallback(src, output, ctx)
        elif ext == ".xlsx":
            pages = _xlsx_to_pdf_fallback(src, output, ctx)
        else:
            pages = _pptx_to_pdf_fallback(src, output, ctx)
    except Exception as e:
        raise ProcessingError(f"Could not convert '{os.path.basename(src)}': {e}") from None

    ctx.report(2, 2, "Done")
    return OfficeConvertResult(
        output=output,
        pages_or_items=pages,
        note="Converted using built-in offline engine (install LibreOffice for full native Office layout rendering).",
    )
