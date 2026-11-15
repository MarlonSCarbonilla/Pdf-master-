"""Page-level restructuring: reorder, duplicate, delete, rotate."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

from typing import Optional, Sequence

import fitz

from core.common import JobContext, ProcessingError, ctx_or_default
from utils.file_utils import atomic_write
from utils.validators import open_pdf, parse_page_ranges

# A plan entry: (source page index, extra clockwise rotation in degrees: 0/90/180/270)
PlanEntry = tuple[int, int]


def rebuild_pdf(
    src: str,
    output: str,
    plan: Sequence[PlanEntry],
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    """Create `output` from the page plan. A page may appear several times (duplicate)
    or not at all (deleted)."""
    ctx = ctx_or_default(ctx)
    if not plan:
        raise ProcessingError("The result would contain no pages. Keep at least one page.")
    doc = open_pdf(src, password)
    new = fitz.open()
    try:
        n = doc.page_count
        for idx, rot in plan:
            if not 0 <= idx < n or rot % 90:
                raise ProcessingError("Invalid page plan.")
        total = len(plan)
        i = 0
        while i < total:
            idx, rot = plan[i]
            j = i
            # group contiguous ascending pages having the same rotation
            while j + 1 < total and plan[j + 1][0] == plan[j][0] + 1 and plan[j + 1][1] == rot:
                j += 1
            ctx.report(i, total, f"Processing page {i + 1} of {total}")
            start = new.page_count
            new.insert_pdf(doc, from_page=plan[i][0], to_page=plan[j][0])
            if rot % 360:
                for k, src_idx in enumerate(range(plan[i][0], plan[j][0] + 1)):
                    pg = new[start + k]
                    pg.set_rotation((doc[src_idx].rotation + rot) % 360)
            i = j + 1
        ctx.report(total, total, "Saving")
        atomic_write(output, lambda tmp: new.save(tmp, garbage=3, deflate=True))
    finally:
        new.close()
        doc.close()
    return output


def _page_count(src: str, password: Optional[str]) -> int:
    d = open_pdf(src, password)
    try:
        return d.page_count
    finally:
        d.close()


def remove_pages(src: str, output: str, page_text: str, password: Optional[str] = None,
                 ctx: Optional[JobContext] = None) -> str:
    n = _page_count(src, password)
    try:
        gone = set(parse_page_ranges(page_text, n))
    except ValueError as e:
        raise ProcessingError(str(e)) from None
    if len(gone) >= n:
        raise ProcessingError("You cannot remove all pages of the document.")
    plan = [(i, 0) for i in range(n) if i not in gone]
    return rebuild_pdf(src, output, plan, password, ctx)


def rotate_pdf(src: str, output: str, angle: int, page_text: Optional[str] = None,
               password: Optional[str] = None, ctx: Optional[JobContext] = None) -> str:
    """Rotate pages clockwise by 90/180/270. `page_text` None/'all' rotates every page."""
    if angle not in (90, 180, 270):
        raise ProcessingError("Rotation must be 90, 180 or 270 degrees.")
    n = _page_count(src, password)
    if not page_text or page_text.strip().lower() == "all":
        sel = set(range(n))
    else:
        try:
            sel = set(parse_page_ranges(page_text, n))
        except ValueError as e:
            raise ProcessingError(str(e)) from None
    plan = [(i, angle if i in sel else 0) for i in range(n)]
    return rebuild_pdf(src, output, plan, password, ctx)
