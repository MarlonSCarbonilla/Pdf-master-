"""Generates the sample PDFs required by the test plan."""
from __future__ import annotations

import io
import os
import sys

import fitz
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_pdf(path, pages=1, size=(595, 842), label="Doc", rotate_every=None):
    doc = fitz.open()
    for i in range(pages):
        w, h = size if not callable(size) else size(i)
        p = doc.new_page(width=w, height=h)
        p.insert_text((72, 100), f"{label} page {i + 1}", fontsize=24)
    doc.save(str(path))
    doc.close()
    return str(path)


def page_texts(path, password=None):
    d = fitz.open(path)
    if d.needs_pass:
        d.authenticate(password)
    out = [d[i].get_text().strip() for i in range(d.page_count)]
    d.close()
    return out


def noisy_image(w=1600, h=1200, seed=1):
    import random

    rnd = random.Random(seed)
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for _ in range(400):
        x, y = rnd.randrange(w), rnd.randrange(h)
        d.ellipse((x, y, x + rnd.randrange(10, 120), y + rnd.randrange(10, 120)),
                  fill=(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
    return im


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    d = tmp_path_factory.mktemp("samples")
    s = {}
    s["single"] = make_pdf(d / "single.pdf", 1, label="Single")
    s["multi"] = make_pdf(d / "multi.pdf", 10, label="Multi")
    s["multi2"] = make_pdf(d / "multi2.pdf", 4, label="Other")
    s["large"] = make_pdf(d / "large.pdf", 400, label="Large")
    s["sizes"] = make_pdf(d / "sizes.pdf", 4, size=lambda i: [(595, 842), (842, 595), (612, 792), (300, 400)][i], label="Sizes")

    # image-containing PDF (photos as PNG so they are compressible)
    doc = fitz.open()
    for i in range(3):
        p = doc.new_page()
        buf = io.BytesIO()
        noisy_image(2400, 1800, seed=i).save(buf, "PNG")
        p.insert_image(fitz.Rect(36, 36, 559, 430), stream=buf.getvalue())
        p.insert_text((72, 500), f"Images page {i + 1}", fontsize=20)
    doc.save(str(d / "images.pdf"))
    doc.close()
    s["images"] = str(d / "images.pdf")

    # "scanned": image-only pages, no text layer
    doc = fitz.open()
    for i in range(2):
        p = doc.new_page()
        im = Image.new("L", (1240, 1754), 255)
        ImageDraw.Draw(im).text((100, 100), f"scan {i}", fill=0)
        buf = io.BytesIO()
        im.save(buf, "JPEG")
        p.insert_image(p.rect, stream=buf.getvalue())
    doc.save(str(d / "scanned.pdf"))
    doc.close()
    s["scanned"] = str(d / "scanned.pdf")

    # password protected
    doc = fitz.open(s["multi2"])
    doc.save(str(d / "locked.pdf"), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    doc.close()
    s["locked"] = str(d / "locked.pdf")

    # damaged / unsupported
    data = open(s["multi"], "rb").read()
    (d / "truncated.pdf").write_bytes(data[: len(data) // 3])
    (d / "garbage.pdf").write_bytes(os.urandom(2048))
    (d / "notapdf.pdf").write_text("hello this is plain text")
    (d / "empty.pdf").write_bytes(b"")
    s["truncated"], s["garbage"] = str(d / "truncated.pdf"), str(d / "garbage.pdf")
    s["notapdf"], s["empty"] = str(d / "notapdf.pdf"), str(d / "empty.pdf")

    # images for image->pdf
    for name, fmt, mode in [("a.jpg", "JPEG", "RGB"), ("b.png", "PNG", "RGBA"), ("c.bmp", "BMP", "RGB"),
                            ("d.tiff", "TIFF", "RGB"), ("e.jpeg", "JPEG", "RGB")]:
        im = noisy_image(800 if name != "e.jpeg" else 600, 600 if name != "e.jpeg" else 900, seed=7).convert(mode)
        im.save(d / name, fmt)
        s[name] = str(d / name)
    (d / "fake.png").write_text("not an image")
    s["fake.png"] = str(d / "fake.png")
    s["dir"] = d
    return s


@pytest.fixture
def out(tmp_path):
    return tmp_path
