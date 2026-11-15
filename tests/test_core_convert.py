import os
import time

import fitz
import pytest
from PIL import Image

from core.common import JobContext, OperationCancelled, ProcessingError
from core.image_to_pdf import images_to_pdf
from core.pdf_compress import compress_pdf
from core.pdf_render import ThumbnailCache, export_images, render_thumbnail


# ---------- render / export ----------
def test_export_png_jpg_tiff(samples, out):
    for fmt, ext in [("PNG", ".png"), ("JPG", ".jpg"), ("TIFF", ".tif")]:
        d = out / fmt
        r = export_images([samples["multi"]], str(d), fmt, 72)
        assert r.pages_exported == 10 and len(r.files) == 10
        assert all(f.endswith(ext) for f in r.files)
        assert os.path.basename(r.files[0]).endswith("_page_001" + ext)
        with Image.open(r.files[0]) as im:
            assert im.size == (595, 842)


def test_export_300_and_600_dpi(samples, out):
    for dpi in (300, 600):
        r = export_images([samples["single"]], str(out / str(dpi)), "PNG", dpi)
        with Image.open(r.files[0]) as im:
            assert abs(im.width - 595 * dpi / 72) <= 1
            assert round(im.info["dpi"][0]) == dpi


def test_export_selected_pages_and_jpg_quality(samples, out):
    r = export_images([samples["images"]], str(out / "hi"), "JPG", 72, quality=95, page_text="1,3")
    r2 = export_images([samples["images"]], str(out / "lo"), "JPG", 72, quality=20, page_text="1,3")
    assert [os.path.basename(f).split("_")[-1] for f in r.files] == ["001.jpg", "003.jpg"]
    assert os.path.getsize(r2.files[0]) < os.path.getsize(r.files[0])


def test_export_batch_subfolders(samples, out):
    r = export_images([samples["multi2"], samples["single"]], str(out), "PNG", 72)
    assert r.pages_exported == 5
    assert os.path.isdir(out / "multi2") and os.path.isdir(out / "single")


def test_export_content_correct(samples, out):
    r = export_images([samples["scanned"]], str(out), "PNG", 100)
    assert len(r.files) == 2


def test_export_cancel(samples, out):
    n = {"c": 0}

    def cancel():
        n["c"] += 1
        return n["c"] > 3
    with pytest.raises(OperationCancelled):
        export_images([samples["large"]], str(out), "PNG", 72, ctx=JobContext(is_cancelled=cancel))
    assert len(os.listdir(out)) <= 4


def test_export_locked(samples, out):
    with pytest.raises(ProcessingError):
        export_images([samples["locked"]], str(out), "PNG", 72)
    r = export_images([samples["locked"]], str(out), "PNG", 72, passwords={samples["locked"]: "secret"})
    assert len(r.files) == 4


def test_large_doc_export_is_page_by_page(samples, out):
    import tracemalloc
    tracemalloc.start()
    export_images([samples["large"]], str(out), "JPG", 100, page_text="1-60")
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 60 * 1024 * 1024  # Python-side peak stays small (no accumulation)


def test_thumbnail_cache_bounded(samples):
    cache = ThumbnailCache(max_bytes=200_000)
    doc = fitz.open(samples["large"])
    for i in range(50):
        cache.put(("k", i), render_thumbnail(doc[i], 100))
    assert len(cache) < 50 and cache._size <= 200_000
    doc.close()


# ---------- image -> pdf ----------
def test_images_to_pdf_all_formats(samples, out):
    imgs = [samples[k] for k in ("a.jpg", "b.png", "c.bmp", "d.tiff", "e.jpeg")]
    o = str(out / "i.pdf")
    images_to_pdf(imgs, o, "A4", "auto", 10, "fit")
    d = fitz.open(o)
    assert d.page_count == 5
    assert all(len(d[i].get_images()) == 1 for i in range(5))
    assert d[0].rect.width > d[0].rect.height      # landscape image -> landscape page
    assert d[4].rect.width < d[4].rect.height      # portrait
    r = d[0].get_image_rects(d[0].get_images()[0][0])[0]
    assert abs((r.width / r.height) - (800 / 600)) < 0.01   # aspect preserved
    assert r.x0 >= 10 * 72 / 25.4 - 0.5                      # margin respected


def test_images_to_pdf_sizes_and_orientation(samples, out):
    for size, (w, h) in [("A4", (595.28, 841.89)), ("Letter", (612, 792)), ("Legal", (612, 1008))]:
        o = str(out / f"{size}.pdf")
        images_to_pdf([samples["a.jpg"]], o, size, "portrait", 0, "fit")
        d = fitz.open(o)
        assert abs(d[0].rect.width - w) < 1 and abs(d[0].rect.height - h) < 1
        o2 = str(out / f"{size}L.pdf")
        images_to_pdf([samples["a.jpg"]], o2, size, "landscape", 0, "fit")
        d = fitz.open(o2)
        assert d[0].rect.width > d[0].rect.height


def test_images_to_pdf_original_size(samples, out):
    o = str(out / "orig.pdf")
    images_to_pdf([samples["a.jpg"]], o, "Original", "auto", 0, "fit")
    d = fitz.open(o)
    assert abs(d[0].rect.width - 800 / 96 * 72) < 1.5


def test_images_to_pdf_rejects_fake(samples, out):
    with pytest.raises(ProcessingError) as e:
        images_to_pdf([samples["a.jpg"], samples["fake.png"]], str(out / "x.pdf"))
    assert "fake.png" in str(e.value)
    assert not (out / "x.pdf").exists()


# ---------- compress ----------
def test_compress_presets(samples, out):
    orig = os.path.getsize(samples["images"])
    sizes = {}
    for p in ("low", "recommended", "high"):
        o = str(out / f"{p}.pdf")
        r = compress_pdf(samples["images"], o, p)
        assert r.original_size == orig
        assert r.reduced and r.new_size == os.path.getsize(o) < orig
        assert 0 < r.percent_saved < 100
        d = fitz.open(o)
        assert d.page_count == 3 and "Images page 2" in d[1].get_text()   # text preserved
        sizes[p] = r.new_size
    assert sizes["high"] < sizes["recommended"] <= sizes["low"] or sizes["high"] < sizes["low"]


def test_compress_never_claims_when_larger(samples, out):
    # Invariant: a file is only published (and "reduced") if it is really smaller.
    # Re-compressing an already compressed file must hit the "nothing to gain" path.
    first = str(out / "first.pdf")
    compress_pdf(samples["images"], first, "high")
    for i, src in enumerate([samples["single"], first, first]):
        o = str(out / f"again{i}.pdf")
        r = compress_pdf(src, o, "high")
        if r.reduced:
            assert os.path.getsize(o) < os.path.getsize(src)
        else:
            assert r.output is None and not os.path.exists(o)
            assert r.saved_bytes == 0 and r.percent_saved == 0
    # second pass of an already-optimised file: must not be reported as reduced unless smaller
    r = compress_pdf(first, str(out / "third.pdf"), "high")
    third = out / "third.pdf"
    assert r.reduced == third.exists()


def test_compress_text_doc_keeps_text(samples, out):
    o = str(out / "t.pdf")
    r = compress_pdf(samples["large"], o, "recommended")
    if r.reduced:
        assert fitz.open(o).page_count == 400


def test_compress_cancel(samples, out):
    with pytest.raises(OperationCancelled):
        compress_pdf(samples["images"], str(out / "c.pdf"), ctx=JobContext(is_cancelled=lambda: True))
    assert os.listdir(out) == []
