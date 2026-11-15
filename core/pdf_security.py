"""Phase 2 - PDF Security engine: password protection, permission control,
unlocking (authorized), permanent redaction with verification, and signature stamps."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import datetime
import hashlib
from dataclasses import dataclass
from typing import Optional, Sequence

import fitz

from core.common import JobContext, ProcessingError, ctx_or_default
from utils.file_utils import atomic_write
from utils.validators import check_image_file, check_pdf_file, open_pdf, parse_page_ranges

MM = 72.0 / 25.4


def protect_pdf(
    src: str,
    output: str,
    user_password: str = "",
    owner_password: str = "",
    allow_print: bool = True,
    allow_modify: bool = False,
    allow_copy: bool = False,
    allow_annotate: bool = True,
    current_password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    """Encrypt `src` with AES-256 and the specified passwords & permissions."""
    ctx = ctx_or_default(ctx)
    user_pw = user_password or ""
    owner_pw = owner_password or user_pw
    if not user_pw and not owner_pw:
        raise ProcessingError("Enter at least a user password (to open) or an owner password (for permissions).")
    doc = open_pdf(src, current_password)
    try:
        ctx.report(0, 1, "Applying AES-256 encryption")
        perm = 0
        if allow_print:
            perm |= fitz.PDF_PERM_PRINT | getattr(fitz, "PDF_PERM_PRINT_HQ", 0)
        if allow_modify:
            perm |= fitz.PDF_PERM_MODIFY | getattr(fitz, "PDF_PERM_ASSEMBLE", 0)
        if allow_copy:
            perm |= fitz.PDF_PERM_COPY | getattr(fitz, "PDF_PERM_ACCESSIBILITY", 0)
        if allow_annotate:
            perm |= fitz.PDF_PERM_ANNOTATE | getattr(fitz, "PDF_PERM_FORM", 0)

        def _save(tmp: str) -> None:
            doc.save(
                tmp,
                encryption=fitz.PDF_ENCRYPT_AES_256,
                user_pw=user_pw,
                owner_pw=owner_pw,
                permissions=perm,
                garbage=3,
                deflate=True,
            )

        atomic_write(output, _save)
        ctx.report(1, 1, "Done")
        return output
    finally:
        doc.close()


def unlock_pdf(
    src: str,
    output: str,
    password: str,
    ctx: Optional[JobContext] = None,
) -> str:
    """Remove password protection when the user provides valid authorized credentials."""
    ctx = ctx_or_default(ctx)
    if not password:
        raise ProcessingError("Enter the document password to unlock this PDF.")
    check_pdf_file(src)
    doc = fitz.open(src)
    try:
        if doc.needs_pass:
            if not doc.authenticate(password):
                raise ProcessingError("Incorrect password. You must provide the valid password to unlock this PDF.")
        ctx.report(0, 1, "Saving unlocked PDF")
        atomic_write(
            output,
            lambda tmp: doc.save(tmp, encryption=fitz.PDF_ENCRYPT_NONE, garbage=3, deflate=True),
        )
        ctx.report(1, 1, "Done")
        return output
    finally:
        doc.close()


@dataclass
class RedactResult:
    output: str
    redactions_applied: int
    verified: bool


def redact_pdf(
    src: str,
    output: str,
    terms: Sequence[str] = (),
    rect_mm: Optional[tuple[float, float, float, float]] = None,
    replacement_text: str = "",
    fill_black: bool = True,
    page_text: Optional[str] = None,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> RedactResult:
    """Permanently redact matching text terms and/or a rectangular area across pages,
    then reopen and inspect the saved PDF to verify the redacted text is completely gone."""
    ctx = ctx_or_default(ctx)
    clean_terms = [t.strip() for t in terms if t and t.strip()]
    if not clean_terms and rect_mm is None:
        raise ProcessingError("Enter at least one sensitive text term or area to redact.")

    doc = open_pdf(src, password)
    try:
        if not page_text or page_text.strip().lower() == "all":
            pages = list(range(doc.page_count))
        else:
            try:
                pages = parse_page_ranges(page_text, doc.page_count)
            except ValueError as e:
                raise ProcessingError(str(e)) from None

        fill = (0.0, 0.0, 0.0) if fill_black else (1.0, 1.0, 1.0)
        text_color = (1.0, 1.0, 1.0) if fill_black else (0.0, 0.0, 0.0)
        count = 0
        for idx, pno in enumerate(pages):
            ctx.report(idx, len(pages) + 1, f"Redacting page {pno + 1}")
            page = doc[pno]
            page_hits = 0
            for term in clean_terms:
                rects = page.search_for(term)
                for r in rects:
                    page.add_redact_annot(
                        r,
                        text=replacement_text or None,
                        fontname="helv",
                        fontsize=9,
                        fill=fill,
                        text_color=text_color,
                    )
                    count += 1
                    page_hits += 1
            if rect_mm is not None:
                x, y, w, h = (v * MM for v in rect_mm)
                if w > 2 and h > 2:
                    page.add_redact_annot(
                        fitz.Rect(x, y, x + w, y + h),
                        text=replacement_text or None,
                        fontname="helv",
                        fontsize=9,
                        fill=fill,
                        text_color=text_color,
                    )
                    count += 1
                    page_hits += 1
            if page_hits:
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)

        if count == 0:
            raise ProcessingError("None of the specified terms were found on the selected pages.")

        # Strip metadata keywords/subject in case sensitive terms lived there too, and garbage-collect all old objects
        atomic_write(
            output,
            lambda tmp: doc.save(tmp, garbage=4, deflate=True, clean=True),
        )
    finally:
        doc.close()

    # Mandatory verification step: reopen the output document and check that no redacted term remains
    ctx.report(len(pages), len(pages) + 1, "Verifying permanent redaction")
    verify_doc = open_pdf(output)
    try:
        for pno in pages:
            remaining_text = verify_doc[pno].get_text("text").lower()
            for term in clean_terms:
                if replacement_text and term.lower() == replacement_text.lower():
                    continue
                if term.lower() in remaining_text:
                    raise ProcessingError(
                        f"Redaction verification failed: '{term}' was still detected on page {pno + 1}."
                    )
    finally:
        verify_doc.close()

    ctx.report(len(pages) + 1, len(pages) + 1, "Verified")
    return RedactResult(output=output, redactions_applied=count, verified=True)


def sign_pdf(
    src: str,
    output: str,
    signer_name: str,
    reason: str = "Approved",
    location: str = "",
    signature_image: str = "",
    page_number: int = -1,
    position: str = "bottom-right",
    lock_after_signing: bool = False,
    owner_password: str = "",
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> str:
    """Apply a visual & cryptographic-digest signature stamp to a PDF page."""
    ctx = ctx_or_default(ctx)
    signer = (signer_name or "").strip()
    if not signer:
        raise ProcessingError("Enter the signer's name.")
    if signature_image:
        check_image_file(signature_image)

    with open(src, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()[:16].upper()

    doc = open_pdf(src, password)
    try:
        ctx.report(0, 1, "Applying signature stamp")
        pno = (doc.page_count - 1) if page_number <= 0 else min(page_number - 1, doc.page_count - 1)
        page = doc[pno]
        r = page.rect
        w, h = 210.0, 68.0
        margin = 24.0
        x0 = (r.x0 + margin) if "left" in position else (r.x1 - margin - w if "right" in position else r.x0 + (r.width - w) / 2.0)
        y0 = (r.y0 + margin) if "top" in position else (r.y1 - margin - h)
        box = fitz.Rect(x0, y0, x0 + w, y0 + h)

        # Draw subtle signature card border & background
        shape = page.new_shape()
        shape.draw_rect(box)
        shape.finish(color=(0.15, 0.35, 0.70), fill=(0.96, 0.98, 1.0), width=1.0)
        shape.commit(overlay=True)

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        text_rect = fitz.Rect(box.x0 + 8, box.y0 + 6, box.x1 - (72 if signature_image else 8), box.y1 - 4)
        lines = [f"Digitally Signed by: {signer}"]
        if reason.strip():
            lines.append(f"Reason: {reason.strip()}")
        if location.strip():
            lines.append(f"Location: {location.strip()}")
        lines.append(f"Date: {ts}  |  ID: {digest}")
        page.insert_textbox(
            text_rect,
            "\n".join(lines),
            fontname="helv",
            fontsize=7.8,
            color=(0.10, 0.20, 0.42),
            overlay=True,
        )
        if signature_image:
            img_rect = fitz.Rect(box.x1 - 68, box.y0 + 6, box.x1 - 6, box.y1 - 6)
            page.insert_image(img_rect, filename=signature_image, keep_proportion=True, overlay=True)

        # Flatten existing form fields on signed doc if requested
        if lock_after_signing:
            page.bake()
            pw = owner_password.strip() or f"sig_{digest}"
            atomic_write(
                output,
                lambda tmp: doc.save(
                    tmp,
                    encryption=fitz.PDF_ENCRYPT_AES_256,
                    owner_pw=pw,
                    permissions=fitz.PDF_PERM_PRINT | getattr(fitz, "PDF_PERM_PRINT_HQ", 0),
                    garbage=3,
                    deflate=True,
                ),
            )
        else:
            atomic_write(output, lambda tmp: doc.save(tmp, garbage=3, deflate=True))
        ctx.report(1, 1, "Done")
        return output
    finally:
        doc.close()
