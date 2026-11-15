import os

import fitz
import pytest

from core.common import JobContext, OperationCancelled, PasswordRequired, ProcessingError
from core.pdf_merge import merge_pdfs
from core.pdf_organize import rebuild_pdf, remove_pages, rotate_pdf
from core.pdf_split import extract_pages, split_pdf
from tests.conftest import page_texts
from utils.validators import format_ranges, parse_page_ranges


def pc(path):
    d = fitz.open(path)
    n = d.page_count
    d.close()
    return n


# ---------- merge ----------
def test_merge_order_and_content(samples, out):
    o = str(out / "m.pdf")
    merge_pdfs([samples["multi2"], samples["single"], samples["multi"]], o)
    t = page_texts(o)
    assert len(t) == 4 + 1 + 10
    assert "Other page 1" in t[0] and "Single page 1" in t[4] and "Multi page 10" in t[-1]


def test_merge_reports_bad_files(samples, out):
    with pytest.raises(ProcessingError) as e:
        merge_pdfs([samples["multi"], samples["garbage"], samples["notapdf"], samples["empty"]], str(out / "x.pdf"))
    msg = str(e.value)
    assert "garbage.pdf" in msg and "notapdf.pdf" in msg and "empty.pdf" in msg
    assert not (out / "x.pdf").exists()


def test_merge_locked_needs_password(samples, out):
    with pytest.raises(ProcessingError):
        merge_pdfs([samples["multi"], samples["locked"]], str(out / "x.pdf"))
    o = str(out / "ok.pdf")
    merge_pdfs([samples["multi"], samples["locked"]], o, passwords={samples["locked"]: "secret"})
    assert pc(o) == 14


def test_merge_cancel_leaves_no_output(samples, out):
    o = out / "c.pdf"
    ctx = JobContext(is_cancelled=lambda: True)
    with pytest.raises(OperationCancelled):
        merge_pdfs([samples["multi"], samples["multi2"]], str(o), ctx=ctx)
    assert not o.exists()
    assert [f for f in os.listdir(out) if f.endswith(".tmp")] == []


# ---------- ranges ----------
def test_ranges():
    assert parse_page_ranges("1-3, 5, 8-", 10) == [0, 1, 2, 4, 7, 8, 9]
    assert parse_page_ranges("-2", 10) == [0, 1]
    assert parse_page_ranges("all", 3) == [0, 1, 2]
    assert format_ranges([0, 1, 2, 4]) == "1-3, 5"
    for bad in ["", "0", "11", "3-1", "a", "1-99"]:
        with pytest.raises(ValueError):
            parse_page_ranges(bad, 10)


# ---------- split ----------
def test_split_each_page(samples, out):
    files = split_pdf(samples["multi"], str(out), "pages")
    assert len(files) == 10 and all(pc(f) == 1 for f in files)
    assert "Multi page 3" in page_texts(files[2])[0]


def test_split_ranges(samples, out):
    files = split_pdf(samples["multi"], str(out), "ranges", ranges="1-3, 5, 7-10", prefix="part")
    assert [pc(f) for f in files] == [3, 1, 4]
    assert os.path.basename(files[0]).startswith("part_")
    assert "Multi page 7" in page_texts(files[2])[0]


def test_split_every_n(samples, out):
    files = split_pdf(samples["multi"], str(out), "every", every_n=4)
    assert [pc(f) for f in files] == [4, 4, 2]


def test_split_invalid_range(samples, out):
    with pytest.raises(ProcessingError):
        split_pdf(samples["multi"], str(out), "ranges", ranges="1-50")


def test_split_never_overwrites(samples, out):
    a = split_pdf(samples["single"], str(out), "pages")
    b = split_pdf(samples["single"], str(out), "pages")
    assert a != b and os.path.exists(a[0]) and os.path.exists(b[0])


def test_extract(samples, out):
    o = str(out / "e.pdf")
    extract_pages(samples["multi"], o, "2-3, 9")
    assert [t.split()[-1] for t in page_texts(o)] == ["2", "3", "9"]


# ---------- organize / remove / rotate ----------
def test_reorder_duplicate_delete(samples, out):
    o = str(out / "r.pdf")
    plan = [(2, 0), (0, 0), (0, 0), (5, 0), (6, 0)]
    rebuild_pdf(samples["multi"], o, plan)
    assert [t.split()[-1] for t in page_texts(o)] == ["3", "1", "1", "6", "7"]


def test_rotate_in_plan(samples, out):
    o = str(out / "r.pdf")
    rebuild_pdf(samples["multi"], o, [(0, 90), (1, 0), (2, 270)])
    d = fitz.open(o)
    assert [d[i].rotation for i in range(3)] == [90, 0, 270]


def test_remove_pages(samples, out):
    o = str(out / "d.pdf")
    remove_pages(samples["multi"], o, "1, 4-6")
    assert [t.split()[-1] for t in page_texts(o)] == ["2", "3", "7", "8", "9", "10"]
    with pytest.raises(ProcessingError):
        remove_pages(samples["multi"], str(out / "z.pdf"), "all")


def test_rotate_selected_and_all(samples, out):
    o = str(out / "rot.pdf")
    rotate_pdf(samples["sizes"], o, 90, "2")
    d = fitz.open(o)
    assert [d[i].rotation for i in range(4)] == [0, 90, 0, 0]
    d.close()
    o2 = str(out / "rot2.pdf")
    rotate_pdf(o, o2, 180, "all")
    d = fitz.open(o2)
    assert [d[i].rotation for i in range(4)] == [180, 270, 180, 180]
    d.close()
    with pytest.raises(ProcessingError):
        rotate_pdf(o, o2, 45)


def test_different_page_sizes_preserved(samples, out):
    o = str(out / "s.pdf")
    merge_pdfs([samples["sizes"], samples["single"]], o)
    d = fitz.open(o)
    assert (round(d[1].rect.width), round(d[1].rect.height)) == (842, 595)
    assert d.page_count == 5
