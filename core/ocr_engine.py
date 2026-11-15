"""Phase 3 (Optional Module) - Tesseract OCR engine:
recognize scanned documents, generate searchable PDFs, extract text from scans,
support English + installed language packs, and batch OCR."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import io
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional, Sequence

import fitz
from PIL import Image

from core.common import JobContext, ProcessingError, ctx_or_default
from utils.file_utils import atomic_write, safe_filename, unique_path
from utils.validators import open_pdf, parse_page_ranges

COMMON_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
)


def find_tesseract(custom_path: str = "") -> Optional[str]:
    """Locate the Tesseract executable on Windows or PATH."""
    if custom_path and os.path.isfile(custom_path):
        return custom_path
    which = shutil.which("tesseract")
    if which:
        return which
    for p in COMMON_TESSERACT_PATHS:
        if os.path.isfile(p):
            return p
    return None


def available_languages(custom_path: str = "") -> list[str]:
    """Return installed Tesseract language codes (always includes 'eng' as default option)."""
    exe = find_tesseract(custom_path)
    if not exe:
        return ["eng"]
    try:
        proc = subprocess.run(
            [exe, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        langs = [
            line.strip()
            for line in (proc.stdout + "\n" + proc.stderr).splitlines()
            if line.strip() and not line.lower().startswith("list of") and " " not in line.strip()
        ]
        if "osd" in langs:
            langs.remove("osd")
        return langs or ["eng"]
    except Exception:
        return ["eng"]


@dataclass
class OcrResult:
    outputs: list[str]
    pages_processed: int
    extracted_preview: str = ""


def _require_pytesseract(tesseract_exe: Optional[str]):
    if not tesseract_exe:
        raise ProcessingError(
            "Tesseract OCR was not found on this computer.\n\n"
            "Install Tesseract OCR (e.g. from https://github.com/UB-Mannheim/tesseract/wiki) "
            "or select your tesseract.exe path in the OCR options panel."
        )
    try:
        import pytesseract
    except ImportError:
        raise ProcessingError("The optional 'pytesseract' Python package is not installed.") from None
    pytesseract.pytesseract.tesseract_cmd = tesseract_exe
    return pytesseract


def run_ocr(
    pdfs: Sequence[str],
    out_dir: str,
    mode: str = "searchable_pdf",
    lang: str = "eng",
    dpi: int = 200,
    page_text: Optional[str] = None,
    skip_pages_with_text: bool = False,
    tesseract_path: str = "",
    passwords: Optional[dict[str, str]] = None,
    ctx: Optional[JobContext] = None,
) -> OcrResult:
    """Run OCR on one or more PDF files (page-by-page to keep memory low).

    mode:
      'searchable_pdf' - generates a PDF with an invisible searchable text layer over each page
      'extract_text'   - writes recognized text to a UTF-8 .txt file per input PDF
    """
    ctx = ctx_or_default(ctx)
    passwords = passwords or {}
    if not pdfs:
        raise ProcessingError("Add at least one PDF file for OCR.")
    exe = find_tesseract(tesseract_path)
    pytesseract = _require_pytesseract(exe)

    os.makedirs(out_dir, exist_ok=True)
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

    total_pages = sum(len(pg) for _, pg in plan)
    done = 0
    outputs: list[str] = []
    preview_snippets: list[str] = []
    scale = dpi / 72.0

    for src, pages in plan:
        stem = safe_filename(os.path.splitext(os.path.basename(src))[0])
        doc = open_pdf(src, passwords.get(src))
        try:
            if mode == "searchable_pdf":
                out_pdf_doc = fitz.open()
                try:
                    for pno in pages:
                        ctx.report(done, total_pages, f"OCR ({lang}) on {stem} - page {pno + 1}")
                        page = doc[pno]
                        existing_txt = page.get_text("text").strip()
                        if skip_pages_with_text and len(existing_txt) > 20:
                            out_pdf_doc.insert_pdf(doc, from_page=pno, to_page=pno)
                        else:
                            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                            pix = None
                            try:
                                pdf_bytes = pytesseract.image_to_pdf_or_hocr(img, lang=lang, extension="pdf")
                                page_doc = fitz.open("pdf", pdf_bytes)
                                try:
                                    out_pdf_doc.insert_pdf(page_doc)
                                finally:
                                    page_doc.close()
                            finally:
                                img.close()
                        done += 1
                    dst = unique_path(os.path.join(out_dir, f"{stem}_ocr.pdf"))
                    atomic_write(dst, lambda tmp: out_pdf_doc.save(tmp, garbage=3, deflate=True))
                    outputs.append(dst)
                finally:
                    out_pdf_doc.close()
            elif mode == "extract_text":
                text_parts: list[str] = []
                for pno in pages:
                    ctx.report(done, total_pages, f"OCR text ({lang}) on {stem} - page {pno + 1}")
                    page = doc[pno]
                    existing_txt = page.get_text("text").strip()
                    if skip_pages_with_text and len(existing_txt) > 20:
                        txt = existing_txt
                    else:
                        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                        pix = None
                        try:
                            txt = pytesseract.image_to_string(img, lang=lang).strip()
                        finally:
                            img.close()
                    text_parts.append(f"=== Page {pno + 1} ===\n{txt}\n")
                    if len(preview_snippets) < 3 and txt:
                        preview_snippets.append(txt[:300])
                    done += 1
                dst = unique_path(os.path.join(out_dir, f"{stem}_ocr.txt"))
                full_txt = "\n".join(text_parts)
                atomic_write(dst, lambda tmp, data=full_txt: open(tmp, "w", encoding="utf-8").write(data))
                outputs.append(dst)
            else:
                raise ProcessingError(f"Unknown OCR mode: {mode}")
        finally:
            doc.close()

    ctx.report(total_pages, total_pages, "Done")
    return OcrResult(outputs=outputs, pages_processed=done, extracted_preview="\n---\n".join(preview_snippets))
