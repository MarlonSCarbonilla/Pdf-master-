"""Input validation: files, PDF readability, page ranges."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os
from typing import Optional

import fitz  # PyMuPDF

from core.common import PasswordRequired, ProcessingError

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def parse_page_ranges(text: str, page_count: int, *, dedupe: bool = True) -> list[int]:
    """Parse '1-3, 5, 8-' into 0-based page indexes (order preserved).

    Supports 'N', 'A-B', 'A-' (to the end), '-B' (from the start) and 'all'.
    Raises ValueError with a readable message on bad input.
    """
    text = (text or "").strip().lower()
    if not text:
        raise ValueError("Please enter page numbers, e.g. 1-3, 5, 8-10.")
    if text == "all":
        return list(range(page_count))
    result: list[int] = []
    seen: set[int] = set()
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = (s.strip() for s in part.split("-", 1))
                start = int(a) if a else 1
                end = int(b) if b else page_count
            else:
                start = end = int(part)
        except ValueError:
            raise ValueError(f"'{part}' is not a valid page number or range.") from None
        if start < 1 or end < 1 or start > page_count or end > page_count:
            raise ValueError(f"'{part}' is outside the document (1-{page_count}).")
        if start > end:
            raise ValueError(f"Range '{part}' is reversed (start is greater than end).")
        for i in range(start - 1, end):
            if dedupe and i in seen:
                continue
            seen.add(i)
            result.append(i)
    if not result:
        raise ValueError("No pages selected.")
    return result


def parse_range_groups(text: str, page_count: int) -> list[list[int]]:
    """Like parse_page_ranges but keeps each comma-separated item as its own group."""
    groups: list[list[int]] = []
    for part in (text or "").replace(";", ",").split(","):
        if part.strip():
            groups.append(parse_page_ranges(part, page_count, dedupe=False))
    if not groups:
        raise ValueError("Please enter page ranges, e.g. 1-3, 4-6, 9.")
    return groups


def format_ranges(indexes: list[int]) -> str:
    """0-based sorted indexes -> '1-3, 5'."""
    idx = sorted(set(indexes))
    parts: list[str] = []
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and idx[j + 1] == idx[j] + 1:
            j += 1
        parts.append(str(idx[i] + 1) if i == j else f"{idx[i] + 1}-{idx[j] + 1}")
        i = j + 1
    return ", ".join(parts)


def has_pdf_header(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return b"%PDF-" in f.read(1024)
    except OSError:
        return False


def check_pdf_file(path: str) -> None:
    """Cheap validation: exists, is a file, has a PDF header. Raises ProcessingError."""
    name = os.path.basename(path)
    if not os.path.isfile(path):
        raise ProcessingError(f"File not found: {name}")
    if os.path.getsize(path) == 0:
        raise ProcessingError(f"'{name}' is empty.")
    if not has_pdf_header(path):
        raise ProcessingError(f"'{name}' is not a valid PDF file (wrong file format).")


def open_pdf(path: str, password: Optional[str] = None) -> fitz.Document:
    """Open a PDF, raising ProcessingError/PasswordRequired with friendly messages."""
    check_pdf_file(path)
    name = os.path.basename(path)
    try:
        doc = fitz.open(path)
    except Exception:
        raise ProcessingError(f"'{name}' could not be opened. The file is damaged or unsupported.") from None
    try:
        if not doc.is_pdf:
            raise ProcessingError(f"'{name}' is not a PDF document.")
        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                if password:
                    raise ProcessingError(f"Wrong password for '{name}'.")
                raise PasswordRequired(path)
        if doc.page_count == 0:
            raise ProcessingError(f"'{name}' contains no readable pages (damaged file?).")
    except BaseException:
        doc.close()
        raise
    return doc


def probe_pdf(path: str) -> tuple[int, bool]:
    """Return (page_count, needs_password). page_count is 0 when locked. May raise ProcessingError."""
    check_pdf_file(path)
    try:
        doc = fitz.open(path)
    except Exception:
        raise ProcessingError(f"'{os.path.basename(path)}' is damaged or unsupported.") from None
    try:
        if not doc.is_pdf:
            raise ProcessingError(f"'{os.path.basename(path)}' is not a PDF document.")
        if doc.needs_pass:
            return 0, True
        if doc.page_count == 0:
            raise ProcessingError(f"'{os.path.basename(path)}' has no readable pages.")
        return doc.page_count, False
    finally:
        doc.close()


def check_image_file(path: str) -> None:
    """Verify extension and actual image content (Pillow)."""
    from PIL import Image

    name = os.path.basename(path)
    if not os.path.isfile(path):
        raise ProcessingError(f"File not found: {name}")
    if os.path.splitext(path)[1].lower() not in IMAGE_EXTS:
        raise ProcessingError(f"'{name}' has an unsupported image extension.")
    try:
        with Image.open(path) as im:
            im.verify()
    except Exception:
        raise ProcessingError(f"'{name}' is damaged or not a real image.") from None
