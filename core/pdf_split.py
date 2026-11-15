"""Split / extract pages."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os
from typing import Optional, Sequence

import fitz

from core.common import JobContext, ProcessingError, ctx_or_default
from utils.file_utils import atomic_write, safe_filename, unique_path
from utils.validators import open_pdf, parse_page_ranges, parse_range_groups


def write_pages(doc: fitz.Document, pages: Sequence[int], output: str) -> str:
    """Write the given 0-based pages (in the given order) to a new PDF, atomically."""
    new = fitz.open()
    try:
        # Insert contiguous ascending runs in one call (much faster than page by page).
        i = 0
        while i < len(pages):
            j = i
            while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
                j += 1
            new.insert_pdf(doc, from_page=pages[i], to_page=pages[j])
            i = j + 1
        atomic_write(output, lambda tmp: new.save(tmp, garbage=3, deflate=True))
    finally:
        new.close()
    return output


def _name(prefix: str, stem: str, suffix: str) -> str:
    return safe_filename(f"{prefix or stem}_{suffix}") + ".pdf"


def split_pdf(
    src: str,
    out_dir: str,
    mode: str,
    *,
    ranges: str = "",
    every_n: int = 1,
    prefix: str = "",
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> list[str]:
    """Split a PDF.

    mode:
      'pages'  - one file per page
      'ranges' - one file per comma separated range ("1-3, 5, 7-9")
      'every'  - a new file every `every_n` pages
    Existing files are never overwritten (a ' (1)' suffix is added).
    """
    ctx = ctx_or_default(ctx)
    doc = open_pdf(src, password)
    try:
        n = doc.page_count
        stem = os.path.splitext(os.path.basename(src))[0]
        width = len(str(n))
        if mode == "pages":
            groups = [[i] for i in range(n)]
            names = [_name(prefix, stem, f"page_{i + 1:0{width}d}") for i in range(n)]
        elif mode == "every":
            if every_n < 1:
                raise ProcessingError("'Every N pages' must be 1 or more.")
            groups = [list(range(s, min(s + every_n, n))) for s in range(0, n, every_n)]
            names = [_name(prefix, stem, f"part_{k + 1:0{len(str(len(groups)))}d}_p{g[0] + 1}-{g[-1] + 1}") for k, g in enumerate(groups)]
        elif mode == "ranges":
            try:
                groups = parse_range_groups(ranges, n)
            except ValueError as e:
                raise ProcessingError(str(e)) from None
            names = []
            for g in groups:
                lbl = f"p{g[0] + 1}" if len(g) == 1 else f"p{g[0] + 1}-{g[-1] + 1}"
                names.append(_name(prefix, stem, lbl))
        else:
            raise ProcessingError(f"Unknown split mode '{mode}'.")

        os.makedirs(out_dir, exist_ok=True)
        results: list[str] = []
        for k, (g, nm) in enumerate(zip(groups, names)):
            ctx.report(k, len(groups), f"Writing {nm}")
            results.append(write_pages(doc, g, unique_path(os.path.join(out_dir, nm))))
        ctx.report(len(groups), len(groups), "Done")
        return results
    finally:
        doc.close()


def extract_pages(
    src: str,
    output: str,
    page_text: str,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    """Export the selected pages (ranges text) as one separate PDF."""
    ctx = ctx_or_default(ctx)
    doc = open_pdf(src, password)
    try:
        try:
            pages = parse_page_ranges(page_text, doc.page_count)
        except ValueError as e:
            raise ProcessingError(str(e)) from None
        ctx.report(0, 1, "Extracting pages")
        write_pages(doc, pages, output)
        ctx.report(1, 1, "Done")
        return output
    finally:
        doc.close()
