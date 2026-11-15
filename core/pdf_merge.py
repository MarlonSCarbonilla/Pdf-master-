"""Merge several PDFs into one."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os
from typing import Mapping, Optional, Sequence

import fitz

from core.common import JobContext, ProcessingError, ctx_or_default
from utils.file_utils import atomic_write
from utils.validators import open_pdf


def merge_pdfs(
    inputs: Sequence[str],
    output: str,
    passwords: Optional[Mapping[str, str]] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    """Merge `inputs` (in order) into `output`. Files are validated first so a bad
    file is reported before any work is done. Returns the output path."""
    ctx = ctx_or_default(ctx)
    passwords = passwords or {}
    if len(inputs) < 2:
        raise ProcessingError("Add at least two PDF files to merge.")

    # 1) Validate everything up-front and collect all problems at once.
    problems: list[str] = []
    for p in inputs:
        try:
            open_pdf(p, passwords.get(p)).close()
        except ProcessingError as e:
            problems.append(str(e))
    if problems:
        raise ProcessingError("Cannot merge, problems found:\n- " + "\n- ".join(problems))

    # 2) Merge one source at a time (only one source document open at once).
    out = fitz.open()
    try:
        total = len(inputs)
        for i, p in enumerate(inputs):
            ctx.report(i, total, f"Merging {os.path.basename(p)}")
            src = open_pdf(p, passwords.get(p))
            try:
                out.insert_pdf(src)
            finally:
                src.close()
        ctx.report(total, total, "Saving merged file")

        def _save(tmp: str) -> None:
            out.save(tmp, garbage=3, deflate=True)

        atomic_write(output, _save)
    finally:
        out.close()
    return output
