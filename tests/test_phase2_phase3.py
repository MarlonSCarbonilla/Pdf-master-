"""Tests for Phase 2 (PDF Editing, Security, Utilities) and Phase 3 (Office Conversion & OCR)."""
from __future__ import annotations

import os

import fitz
import pytest

from core.common import ProcessingError
from core.ocr_engine import find_tesseract, run_ocr
from core.office_convert import office_to_pdf, pdf_to_docx, pdf_to_pptx, pdf_to_xlsx
from core.pdf_edit import (
    add_header_footer,
    add_image_watermark,
    add_page_numbers,
    add_text_watermark,
    annotate_pdf,
    crop_pdf,
    edit_metadata,
    read_metadata,
)
from core.pdf_security import protect_pdf, redact_pdf, sign_pdf, unlock_pdf
from core.pdf_utilities import (
    batch_rename_pdfs,
    compare_pdfs,
    convert_to_grayscale,
    extract_embedded_images,
    extract_text_to_file,
    flatten_pdf,
    remove_blank_pages,
    repair_pdf,
)


# ---------------------------------------------------------------------------
# Phase 2A: PDF Editing
# ---------------------------------------------------------------------------
def test_page_numbers_and_headers_footers(samples, out):
    numbered = str(out / "num.pdf")
    add_page_numbers(samples["multi"], numbered, position="bottom-right", fmt="Page {n} of {total}", start_page=2, start_number=1)
    d = fitz.open(numbered)
    assert "Page 1 of 10" not in d[0].get_text()
    assert "Page 1 of 10" in d[1].get_text()
    assert "Page 9 of 10" in d[9].get_text()
    d.close()

    hf = str(out / "hf.pdf")
    add_header_footer(samples["multi2"], hf, header_left="CONFIDENTIAL", footer_right="P.{page}/{total}", page_text="1-2")
    d = fitz.open(hf)
    assert "CONFIDENTIAL" in d[0].get_text() and "P.1/4" in d[0].get_text()
    assert "CONFIDENTIAL" not in d[2].get_text()
    d.close()


def test_text_and_image_watermarks(samples, out):
    wm_txt = str(out / "wm_txt.pdf")
    add_text_watermark(samples["multi2"], wm_txt, "DRAFT COPY", angle=45, opacity=0.3, tiled=True)
    d = fitz.open(wm_txt)
    assert "DRAFT COPY" in d[0].get_text()
    d.close()

    wm_img = str(out / "wm_img.pdf")
    add_image_watermark(samples["single"], wm_img, samples["b.png"], scale=0.3, opacity=0.4, position="bottom-right")
    d = fitz.open(wm_img)
    assert len(d[0].get_images()) >= 1
    d.close()


def test_annotate_all_modes(samples, out):
    p1 = str(out / "ann_text.pdf")
    _, c = annotate_pdf(samples["single"], p1, "add_text", text="Inserted Note", x_mm=20, y_mm=20)
    assert c == 1 and "Inserted Note" in fitz.open(p1)[0].get_text()

    p2 = str(out / "ann_img.pdf")
    _, c = annotate_pdf(samples["single"], p2, "add_image", image_path=samples["a.jpg"])
    assert c == 1 and len(fitz.open(p2)[0].get_images()) == 1

    p3 = str(out / "ann_hl.pdf")
    _, c = annotate_pdf(samples["multi2"], p3, "highlight", search_text="Other page")
    assert c == 4

    p4 = str(out / "ann_ul.pdf")
    _, c = annotate_pdf(samples["multi2"], p4, "underline", search_text="page 2")
    assert c == 1

    p5 = str(out / "ann_shape.pdf")
    _, c = annotate_pdf(samples["single"], p5, "shape", shape_kind="circle")
    assert c == 1 and len(list(fitz.open(p5)[0].annots())) == 1

    p6 = str(out / "ann_ink.pdf")
    _, c = annotate_pdf(samples["single"], p6, "freehand", text="My note")
    assert c == 1 and len(list(fitz.open(p6)[0].annots())) == 1


def test_crop_and_metadata(samples, out):
    cropped = str(out / "crop.pdf")
    crop_pdf(samples["single"], cropped, top_mm=15, bottom_mm=15, left_mm=10, right_mm=10)
    d = fitz.open(cropped)
    assert d[0].cropbox.width < 595 and d[0].cropbox.height < 842
    d.close()

    meta = str(out / "meta.pdf")
    edit_metadata(samples["single"], meta, {"title": "My Report", "author": "Alice", "keywords": "pdf,offline"})
    md = read_metadata(meta)
    assert md["title"] == "My Report" and md["author"] == "Alice"

    cleared = str(out / "meta_clear.pdf")
    edit_metadata(meta, cleared, {}, clear_all=True)
    assert read_metadata(cleared)["title"] == ""


# ---------------------------------------------------------------------------
# Phase 2B: PDF Security
# ---------------------------------------------------------------------------
def test_protect_and_unlock_pdf(samples, out):
    enc = str(out / "enc.pdf")
    protect_pdf(samples["multi2"], enc, user_password="user123", owner_password="owner456", allow_print=True, allow_copy=False)
    d = fitz.open(enc)
    assert d.needs_pass
    assert not d.authenticate("wrong")
    assert d.authenticate("user123")
    d.close()

    with pytest.raises(ProcessingError):
        unlock_pdf(enc, str(out / "bad_un.pdf"), password="wrong")

    dec = str(out / "dec.pdf")
    unlock_pdf(enc, dec, password="user123")
    d2 = fitz.open(dec)
    assert not d2.needs_pass and d2.page_count == 4
    d2.close()


def test_redact_permanent_and_verified(samples, out):
    red = str(out / "redacted.pdf")
    res = redact_pdf(samples["multi2"], red, terms=["Other page 2", "Other page 4"], replacement_text="[REDACTED]")
    assert res.verified and res.redactions_applied == 2
    d = fitz.open(red)
    assert "Other page 2" not in d[1].get_text()
    assert "Other page 4" not in d[3].get_text()
    assert "Other page 1" in d[0].get_text()
    d.close()


def test_sign_pdf(samples, out):
    signed = str(out / "signed.pdf")
    sign_pdf(samples["single"], signed, signer_name="Jane Smith", reason="Final Approval", location="London", signature_image=samples["b.png"])
    d = fitz.open(signed)
    txt = d[0].get_text()
    assert "Jane Smith" in txt and "Final Approval" in txt
    d.close()


# ---------------------------------------------------------------------------
# Phase 2C: PDF Utilities
# ---------------------------------------------------------------------------
def test_repair_remove_blank_flatten_grayscale(samples, out):
    rep, n = repair_pdf(samples["multi2"], str(out / "repaired.pdf"))
    assert n == 4 and os.path.exists(rep)

    # Create a doc with a blank page in the middle
    with_blank = str(out / "with_blank.pdf")
    doc = fitz.open()
    p1 = doc.new_page(); p1.insert_text((72, 100), "Page One")
    doc.new_page()  # blank page 2
    p3 = doc.new_page(); p3.insert_text((72, 100), "Page Three")
    doc.save(with_blank); doc.close()

    cleaned, removed, kept = remove_blank_pages(with_blank, str(out / "no_blank.pdf"))
    assert removed == [2] and kept == 2 and fitz.open(cleaned).page_count == 2

    # Flatten
    ann_file = str(out / "with_annot.pdf")
    annotate_pdf(samples["single"], ann_file, "shape", shape_kind="rect")
    flat = str(out / "flat.pdf")
    flatten_pdf(ann_file, flat)
    assert len(list(fitz.open(flat)[0].annots())) == 0

    # Grayscale
    gray = str(out / "gray.pdf")
    convert_to_grayscale(samples["images"], gray, preserve_text=True)
    d = fitz.open(gray)
    assert d.page_count == 3 and "Images page 1" in d[0].get_text()
    d.close()


def test_extract_text_and_images_and_compare_and_rename(samples, out):
    txt_out, pages, chars = extract_text_to_file(samples["multi2"], str(out / "extracted.txt"))
    assert pages == 4 and chars > 20 and "Other page 3" in open(txt_out, encoding="utf-8").read()

    imgs = extract_embedded_images(samples["images"], str(out / "ext_imgs"))
    assert len(imgs) == 3

    cmp_res = compare_pdfs(samples["multi2"], samples["single"], str(out / "diff_report.pdf"))
    assert cmp_res.pages_compared == 4 and cmp_res.pages_with_text_diff >= 1
    assert fitz.open(cmp_res.report_pdf).page_count == 4

    renamed = batch_rename_pdfs(
        [samples["single"], samples["multi2"]],
        str(out / "renamed"),
        pattern="Doc_{num:02d}_{name}_{pages}p",
        start_num=5,
    )
    assert len(renamed) == 2
    assert os.path.basename(renamed[0]) == "Doc_05_single_1p.pdf"
    assert os.path.basename(renamed[1]) == "Doc_06_multi2_4p.pdf"


# ---------------------------------------------------------------------------
# Phase 3: Office Conversions (PDF <-> DOCX / XLSX / PPTX)
# ---------------------------------------------------------------------------
def test_pdf_to_office_and_back(samples, out):
    docx_out = str(out / "conv.docx")
    r_docx = pdf_to_docx(samples["multi2"], docx_out)
    assert os.path.isfile(r_docx.output) and r_docx.pages_or_items == 4

    xlsx_out = str(out / "conv.xlsx")
    r_xlsx = pdf_to_xlsx(samples["multi2"], xlsx_out)
    assert os.path.isfile(r_xlsx.output) and r_xlsx.pages_or_items >= 1

    pptx_out = str(out / "conv.pptx")
    r_pptx = pdf_to_pptx(samples["multi2"], pptx_out, dpi=100)
    assert os.path.isfile(r_pptx.output) and r_pptx.pages_or_items == 4

    # Convert DOCX, XLSX, PPTX back to PDF
    for ext, src_office in (("docx", docx_out), ("xlsx", xlsx_out), ("pptx", pptx_out)):
        pdf_back = str(out / f"from_{ext}.pdf")
        res = office_to_pdf(src_office, pdf_back)
        assert os.path.isfile(res.output) and fitz.open(res.output).page_count >= 1


def test_ocr_scanned_pdf(samples, out):
    if not find_tesseract():
        pytest.skip("Tesseract OCR not installed")
    res_pdf = run_ocr([samples["scanned"]], str(out), mode="searchable_pdf", lang="eng", dpi=150)
    assert res_pdf.pages_processed == 2 and len(res_pdf.outputs) == 1
    ocr_pdf = res_pdf.outputs[0]
    assert os.path.isfile(ocr_pdf)
    d = fitz.open(ocr_pdf)
    assert d.page_count == 2
    assert len(d[0].get_text().strip()) > 0
    d.close()

    res_txt = run_ocr([samples["scanned"]], str(out), mode="extract_text", lang="eng", dpi=150)
    assert res_txt.pages_processed == 2 and len(res_txt.outputs) == 1
    assert os.path.isfile(res_txt.outputs[0]) and len(res_txt.extracted_preview) > 0


