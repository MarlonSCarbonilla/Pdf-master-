"""Generate the sample PDF, Image, and Office files in ./samples for manual and automated testing."""
from __future__ import annotations

import io
import os
import random
import sys

import fitz
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _noisy_image(w: int = 1200, h: int = 900, seed: int = 1) -> Image.Image:
    rnd = random.Random(seed)
    im = Image.new("RGB", (w, h), (245, 247, 250))
    d = ImageDraw.Draw(im)
    for _ in range(180):
        x, y = rnd.randrange(w), rnd.randrange(h)
        d.ellipse(
            (x, y, x + rnd.randrange(15, 110), y + rnd.randrange(15, 110)),
            fill=(rnd.randrange(40, 240), rnd.randrange(40, 240), rnd.randrange(40, 240)),
        )
    return im


def generate_all(out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    created: list[str] = []

    # 1. Single-page PDF
    p_single = os.path.join(out_dir, "01_single_page.pdf")
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text((72, 90), "PDF Master - Sample Single-Page Document", fontsize=20)
    pg.insert_text((72, 135), "This document is used to test single-page operations, metadata, watermarks, and signing.", fontsize=11)
    doc.save(p_single); doc.close()
    created.append(p_single)

    # 2. Multi-page PDF (with headings, body text, and a blank page for blank-page detection)
    p_multi = os.path.join(out_dir, "02_multi_page_10p.pdf")
    doc = fitz.open()
    for i in range(10):
        pg = doc.new_page()
        pg.insert_text((72, 90), f"Chapter {i + 1}: Multi-Page Sample", fontsize=18)
        pg.insert_text((72, 130), f"This is page {i + 1} of 10. Sensitive token: Account-98765.", fontsize=11)
    doc.save(p_multi); doc.close()
    created.append(p_multi)

    # 3. Large 400-page PDF
    p_large = os.path.join(out_dir, "03_large_400_pages.pdf")
    doc = fitz.open()
    for i in range(400):
        pg = doc.new_page()
        pg.insert_text((72, 100), f"Large Document - Page {i + 1} of 400", fontsize=16)
    doc.save(p_large, garbage=3, deflate=True); doc.close()
    created.append(p_large)

    # 4. Scanned document (image-only pages, no selectable text layer)
    p_scan = os.path.join(out_dir, "04_scanned_document.pdf")
    doc = fitz.open()
    for i in range(2):
        pg = doc.new_page()
        im = Image.new("RGB", (1240, 1754), (255, 255, 255))
        draw = ImageDraw.Draw(im)
        draw.text((120, 160), f"SCANNED INVOICE PAGE {i + 1} - TOTAL USD 450.00", fill=(10, 10, 10))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        pg.insert_image(pg.rect, stream=buf.getvalue())
    doc.save(p_scan); doc.close()
    created.append(p_scan)

    # 5. Password-protected PDF (password: secret)
    p_locked = os.path.join(out_dir, "05_password_protected_pw_secret.pdf")
    doc = fitz.open(p_multi)
    doc.save(p_locked, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    doc.close()
    created.append(p_locked)

    # 6. Document containing embedded images and a bordered table (great for Compress & PDF-to-Excel/Word)
    p_images = os.path.join(out_dir, "06_images_and_table.pdf")
    doc = fitz.open()
    for i in range(3):
        pg = doc.new_page()
        pg.insert_text((50, 50), f"Visual & Table Report - Page {i + 1}", fontsize=16)
        buf = io.BytesIO()
        _noisy_image(1600, 1000, seed=i + 10).save(buf, "PNG")
        pg.insert_image(fitz.Rect(50, 75, 545, 360), stream=buf.getvalue())
        # Draw a 4x3 bordered table for table extraction testing
        y_top = 400
        row_h = 28
        cols = [50, 210, 380, 545]
        rows_data = [
            ["Item", "Department", "Amount"],
            [f"Service {i + 1}A", "Engineering", "$1,200"],
            [f"Service {i + 1}B", "Operations", "$850"],
            ["Total", "All", "$2,050"],
        ]
        shape = pg.new_shape()
        for r_idx, r_vals in enumerate(rows_data):
            y0 = y_top + r_idx * row_h
            y1 = y0 + row_h
            for c_idx, val in enumerate(r_vals):
                x0, x1 = cols[c_idx], cols[c_idx + 1]
                shape.draw_rect(fitz.Rect(x0, y0, x1, y1))
                pg.insert_text((x0 + 8, y0 + 18), val, fontsize=10.5)
        shape.finish(color=(0.2, 0.2, 0.2), width=1.0)
        shape.commit()
    doc.save(p_images); doc.close()
    created.append(p_images)

    # 7. Mixed page sizes (A4 portrait, A4 landscape, Letter, Custom small)
    p_sizes = os.path.join(out_dir, "07_mixed_page_sizes.pdf")
    doc = fitz.open()
    for idx, (w, h, label) in enumerate([
        (595, 842, "A4 Portrait"),
        (842, 595, "A4 Landscape"),
        (612, 792, "US Letter"),
        (420, 595, "A5 Portrait"),
    ]):
        pg = doc.new_page(width=w, height=h)
        pg.insert_text((48, 80), f"Page {idx + 1}: {label} ({w}x{h} pt)", fontsize=15)
    doc.save(p_sizes); doc.close()
    created.append(p_sizes)

    # 8. Damaged / truncated PDF
    p_damaged = os.path.join(out_dir, "08_damaged_truncated.pdf")
    raw = open(p_multi, "rb").read()
    with open(p_damaged, "wb") as f:
        f.write(raw[: len(raw) // 2])
    created.append(p_damaged)

    # Sample images for Image-to-PDF and Watermarking
    for name, fmt in (("sample_photo_1.jpg", "JPEG"), ("sample_badge_2.png", "PNG")):
        ip = os.path.join(out_dir, name)
        _noisy_image(800, 600, seed=42 if fmt == "JPEG" else 99).save(ip, fmt)
        created.append(ip)

    return created


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = os.path.join(root, "samples")
    files = generate_all(target)
    print(f"Generated {len(files)} sample files in {target}")
