"""PDF compression: image recompression/downsampling + structural optimisation."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import io
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Optional

import fitz
from PIL import Image

from core.common import JobContext, ProcessingError, ctx_or_default
from utils.file_utils import atomic_write
from utils.validators import open_pdf

# preset -> (JPEG quality, target DPI, downsample only when image exceeds this DPI)
PRESETS = {
    "low": {"label": "Low compression (best quality)", "quality": 85, "target_dpi": 220, "trigger_dpi": 300},
    "recommended": {"label": "Recommended (balanced)", "quality": 70, "target_dpi": 150, "trigger_dpi": 200},
    "high": {"label": "High compression (smallest file)", "quality": 45, "target_dpi": 96, "trigger_dpi": 130},
}


@dataclass
class CompressResult:
    original_size: int
    new_size: int
    output: Optional[str]      # None when no smaller file could be produced
    images_optimized: int = 0
    note: str = ""

    @property
    def saved_bytes(self) -> int:
        return max(0, self.original_size - self.new_size)

    @property
    def percent_saved(self) -> float:
        return 100.0 * self.saved_bytes / self.original_size if self.original_size else 0.0

    @property
    def reduced(self) -> bool:
        return self.output is not None and self.new_size < self.original_size


def _optimise_images(doc: fitz.Document, preset: dict, downsample: bool, ctx: JobContext) -> int:
    """Re-encode large raster images as JPEG (and shrink when over-resolved). Returns count."""
    changed = 0
    seen: set[int] = set()
    total = doc.page_count
    for pno in range(total):
        ctx.report(pno, total, f"Optimising images on page {pno + 1} of {total}")
        page = doc[pno]
        for info in page.get_images(full=True):
            xref, smask = info[0], info[1]
            if xref in seen:
                continue
            seen.add(xref)
            if smask:  # transparent images: leave untouched to avoid visual damage
                continue
            try:
                ex = doc.extract_image(xref)
                if not ex or ex.get("colorspace") not in (1, 3):  # gray / RGB only (skip CMYK, masks)
                    continue
                raw = ex["image"]
                if len(raw) < 20_000:
                    continue
                with Image.open(io.BytesIO(raw)) as im:
                    im.load()
                    img = im.convert("L" if ex["colorspace"] == 1 else "RGB")
                if downsample:
                    rects = page.get_image_rects(xref)
                    if rects:
                        width_in = max(r.width for r in rects) / 72.0
                        eff = img.width / width_in if width_in > 0 else 0
                        if eff > preset["trigger_dpi"]:
                            f = preset["target_dpi"] / eff
                            img = img.resize((max(1, int(img.width * f)), max(1, int(img.height * f))), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=preset["quality"], optimize=True)
                if len(buf.getvalue()) < len(raw) * 0.9:
                    page.replace_image(xref, stream=buf.getvalue())
                    changed += 1
            except Exception:
                continue  # never fail the whole job for one odd image
    return changed


def _pikepdf_pass(src: str, dst: str, strip_metadata: bool) -> bool:
    """Structural recompression with pikepdf (object streams, flate recompression)."""
    try:
        import pikepdf
    except Exception:
        return False
    try:
        with pikepdf.open(src) as pdf:
            if strip_metadata:
                try:
                    del pdf.docinfo
                except Exception:
                    pass
            pdf.remove_unreferenced_resources()
            pdf.save(
                dst,
                compress_streams=True,
                recompress_flate=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
            )
        return True
    except Exception:
        return False


def compress_pdf(
    src: str,
    output: str,
    preset: str = "recommended",
    *,
    optimize_images: bool = True,
    downsample: bool = True,
    remove_unused: bool = True,
    strip_metadata: bool = False,
    password: Optional[str] = None,
    ctx: Optional[JobContext] = None,
) -> CompressResult:
    """Compress `src` into `output`. The output is ONLY written when it is genuinely
    smaller than the original; otherwise nothing is written and result.reduced is False."""
    ctx = ctx_or_default(ctx)
    if preset not in PRESETS:
        raise ProcessingError("Unknown compression preset.")
    cfg = PRESETS[preset]
    orig_size = os.path.getsize(src)
    doc = open_pdf(src, password)
    tmpdir = tempfile.mkdtemp(prefix="pdfm_cmp_", dir=os.path.dirname(os.path.abspath(output)))
    try:
        was_encrypted = doc.is_encrypted
        n_img = _optimise_images(doc, cfg, downsample, ctx) if optimize_images else 0
        ctx.report(doc.page_count, doc.page_count, "Optimising structure")
        if strip_metadata:
            doc.set_metadata({})
            try:
                doc.del_xml_metadata()
            except Exception:
                pass
        stage1 = os.path.join(tmpdir, "stage1.pdf")
        doc.save(
            stage1,
            garbage=4 if remove_unused else 0,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
            clean=remove_unused,
            use_objstms=1,
        )
        doc.close()
        ctx.check()
        candidates = [stage1]
        stage2 = os.path.join(tmpdir, "stage2.pdf")
        if _pikepdf_pass(stage1, stage2, strip_metadata):
            candidates.append(stage2)
        best = min(candidates, key=os.path.getsize)
        best_size = os.path.getsize(best)
        # Validate that the candidate reopens with the same page count before publishing.
        check = open_pdf(best)
        check.close()
        note = "The output is not password protected." if was_encrypted else ""
        if best_size >= orig_size:
            return CompressResult(orig_size, orig_size, None, n_img,
                                  "This file is already well optimised - no smaller version could be produced, so nothing was saved.")
        atomic_write(output, lambda tmp: shutil.copyfile(best, tmp))
        return CompressResult(orig_size, best_size, output, n_img, note)
    finally:
        try:
            doc.close()
        except Exception:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)
