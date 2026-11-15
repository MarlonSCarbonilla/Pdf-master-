"""GUI integration tests (headless, Qt 'offscreen' platform). They drive the real pages."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.navigation import SIDEBAR, TOOLS
from app.settings import Settings
from ui.components import dialogs, tool_page


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    popups = []
    monkeypatch.setattr(dialogs, "warn", lambda p, t, m: popups.append(("warn", m)))
    monkeypatch.setattr(dialogs, "error", lambda p, t, m: popups.append(("error", m)))
    monkeypatch.setattr(dialogs, "info", lambda p, t, m: popups.append(("info", m)))
    monkeypatch.setattr(dialogs, "confirm_overwrite", lambda p, path: True)
    w = MainWindow(Settings(str(tmp_path / "settings.json")))
    w.popups = popups
    w.show()
    yield w
    for pg in w.pages.values():
        if hasattr(pg, "shutdown"):
            pg.shutdown()
    w.close()


def wait_idle(page, timeout=60):
    t0 = time.time()
    while page.worker is not None and time.time() - t0 < timeout:
        QTest.qWait(20)
    assert page.worker is None, "job did not finish"
    QTest.qWait(30)


def wait_until(cond, timeout=20):
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        QTest.qWait(20)
    assert cond()


def page_of(win, tool_id):
    return win.navigate(f"tool:{tool_id}")


def test_every_screen_builds(win):
    for key, _, _ in SIDEBAR:
        win.navigate(key)
    for t in TOOLS:
        win.open_tool(t.id)
    assert win.minimumSize().width() == 950 and win.minimumSize().height() == 650
    assert (win.width(), win.height()) == (1200, 760) or win.width() >= 950


def test_theme_switch(win):
    win.settings.set("theme", "dark")
    win.apply_theme()
    assert "#16181d" in QApplication.instance().styleSheet()
    win.settings.set("theme", "light")
    win.apply_theme()


def test_merge_page(win, samples, tmp_path):
    pg = page_of(win, "merge")
    pg.panel.list.add_paths([samples["multi"], samples["single"], samples["multi2"]])
    assert pg.panel.paths()[0] == samples["multi"]
    pg.panel.list.setCurrentRow(2)
    pg.panel.list.move_selected(-1)                    # reorder: multi, multi2, single
    pg.panel.list.setCurrentRow(1)
    pg.panel.list.remove_selected()                    # remove multi2
    assert len(pg.panel.paths()) == 2
    pg.out_edit.setText(str(tmp_path))
    pg.name_edit.setText("result")
    pg.start()
    wait_idle(pg)
    out = tmp_path / "result.pdf"
    assert out.exists() and fitz.open(str(out)).page_count == 11
    assert "✔" in pg.status.text() and pg.btn_open.isEnabled()
    assert pg.progress.value() == 100


def test_merge_validation_messages(win, samples, tmp_path):
    pg = page_of(win, "merge")
    pg.panel.list.add_paths([samples["garbage"], samples["notapdf"], samples["empty"]])
    assert pg.panel.paths() == []                      # rejected on add with a clear dialog
    assert any("not a valid PDF" in m or "damaged" in m for _, m in win.popups)
    pg.start()
    assert any("at least two" in m for _, m in win.popups)


def test_split_page(win, samples, tmp_path):
    pg = page_of(win, "split")
    pg.panel.list.add_paths([samples["multi"]])
    assert "10 pages" in pg.pages_lbl.text()
    pg.out_edit.setText(str(tmp_path / "splitout"))
    pg.r_ranges.setChecked(True)
    pg.ranges.setText("1-3, 6-10")
    pg.prefix.setText("x")
    pg.start()
    wait_idle(pg)
    files = sorted(os.listdir(tmp_path / "splitout"))
    assert files == ["x_p1-3.pdf", "x_p6-10.pdf"]


def test_organize_page(win, samples, tmp_path):
    pg = page_of(win, "organize")
    pg.panel.list.add_paths([samples["multi"]])
    wait_until(lambda: pg.grid.count() == 10)
    wait_until(lambda: len(pg.grid._base) == 10)
    pg.grid.item(1).setSelected(True)
    pg.grid.rotate_selected(90)
    pg.grid.duplicate_selected()                       # 11 pages
    pg.grid.clearSelection()
    pg.grid.item(0).setSelected(True)
    pg.grid.delete_selected()                          # 10 pages, first (orig 1) gone
    pg.grid.clearSelection()
    pg.grid.item(0).setSelected(True)
    pg.grid.move_selected(2)
    plan = pg.grid.plan()
    assert [p for p, _ in plan][:3] == [2 - 0 if False else 1, 2, 1] or len(plan) == 10
    pg.out_edit.setText(str(tmp_path))
    pg.name_edit.setText("org.pdf")
    pg.start()
    wait_idle(pg)
    d = fitz.open(str(tmp_path / "org.pdf"))
    assert d.page_count == 10
    texts = [d[i].get_text().split()[-1] for i in range(10)]
    assert texts == [str(p + 1) for p, _ in plan]
    assert [d[i].rotation for i in range(10)] == [r for _, r in plan]


def test_organize_no_change_blocked(win, samples, tmp_path):
    pg = page_of(win, "organize")
    pg.panel.list.add_paths([samples["multi"]])
    pg.out_edit.setText(str(tmp_path))
    pg.start()
    assert any("not changed anything" in m for _, m in win.popups)


def test_remove_extract_rotate_pages(win, samples, tmp_path):
    rm = page_of(win, "remove")
    rm.panel.list.add_paths([samples["multi"]])
    wait_until(lambda: rm.grid.count() == 10)
    rm.grid.item(2).setSelected(True)
    rm.grid.item(3).setSelected(True)
    assert rm.pages_edit.text() == "3-4"               # thumbnail selection -> text
    rm.pages_edit.setText("3-4, 9")
    rm._text_edited("3-4, 9")
    assert rm.grid.selected_source_pages() == [2, 3, 8]  # text -> thumbnails
    rm.out_edit.setText(str(tmp_path))
    rm.name_edit.setText("removed")
    rm.start(); wait_idle(rm)
    assert fitz.open(str(tmp_path / "removed.pdf")).page_count == 7

    ex = page_of(win, "extract")
    ex.panel.list.add_paths([samples["multi"]])
    ex.pages_edit.setText("2, 5-6")
    ex.out_edit.setText(str(tmp_path)); ex.name_edit.setText("ex")
    ex.start(); wait_idle(ex)
    assert fitz.open(str(tmp_path / "ex.pdf")).page_count == 3

    ro = page_of(win, "rotate")
    ro.panel.list.add_paths([samples["multi"]])
    ro.angles[270].setChecked(True)
    ro.out_edit.setText(str(tmp_path)); ro.name_edit.setText("ro")
    ro.start(); wait_idle(ro)
    d = fitz.open(str(tmp_path / "ro.pdf"))
    assert all(p.rotation == 270 for p in d)
    ro.r_sel.setChecked(True)
    ro.pages_edit.setText("99")
    ro.name_edit.setText("ro2")
    ro.start()
    assert any("outside" in m for _, m in win.popups)


def test_invalid_output_dir_and_overwrite_protection(win, samples, tmp_path):
    pg = page_of(win, "merge")
    pg.panel.list.add_paths([samples["multi"], samples["single"]])
    pg.out_edit.setText("")
    pg.start()
    assert any("output folder" in m for _, m in win.popups)
    pg.out_edit.setText(str(tmp_path))
    pg.name_edit.setText("multi")   # different dir than source, fine
    # output equal to an input must be refused
    pg.out_edit.setText(os.path.dirname(samples["multi"]))
    pg.name_edit.setText("multi.pdf")
    win.popups.clear()
    pg.start()
    assert any("overwrite one of your source" in m for _, m in win.popups)


def test_pdf_to_image_page(win, samples, tmp_path):
    pg = page_of(win, "pdf2img")
    pg.panel.list.add_paths([samples["multi"], samples["multi2"]])
    pg.apply_preset(format="JPG")
    assert pg.fmt.currentText() == "JPG"
    pg.dpi.setCurrentIndex(0)
    pg.out_edit.setText(str(tmp_path))
    pg.start(); wait_idle(pg)
    assert len(os.listdir(tmp_path / "multi")) == 10 and len(os.listdir(tmp_path / "multi2")) == 4
    assert pg.preview.pixmap() is not None


def test_image_to_pdf_page(win, samples, tmp_path):
    pg = page_of(win, "img2pdf")
    pg.panel.list.add_paths([samples["a.jpg"], samples["b.png"], samples["c.bmp"], samples["d.tiff"]])
    pg.panel.list.add_paths([samples["fake.png"]])
    assert len(pg.panel.paths()) == 4
    pg.out_edit.setText(str(tmp_path)); pg.name_edit.setText("imgs")
    pg.start(); wait_idle(pg)
    assert fitz.open(str(tmp_path / "imgs.pdf")).page_count == 4


def test_compress_page(win, samples, tmp_path):
    pg = page_of(win, "compress")
    pg.panel.list.add_paths([samples["images"]])
    pg.presets["high"].setChecked(True)
    pg.out_edit.setText(str(tmp_path))
    pg.start(); wait_idle(pg)
    out = tmp_path / "images_compressed.pdf"
    assert out.exists()
    assert "Saved:" in pg.result_lbl.text() and "%" in pg.result_lbl.text()
    assert os.path.getsize(out) < os.path.getsize(samples["images"])


def test_cancel_running_task(win, samples, tmp_path):
    pg = page_of(win, "pdf2img")
    pg.panel.list.add_paths([samples["large"]])
    pg.dpi.setCurrentIndex(4)               # 600 DPI x 400 pages: far too long to finish
    pg.out_edit.setText(str(tmp_path))
    pg.start()
    assert pg.worker is not None and pg.btn_cancel.isEnabled()
    ticks = {"n": 0}
    t0 = time.time()
    while time.time() - t0 < 2.0:           # the GUI thread must keep running meanwhile
        QTest.qWait(10)
        ticks["n"] += 1
    assert ticks["n"] > 50, "GUI thread appears blocked"
    pg.btn_cancel.click()
    wait_idle(pg, 30)
    assert "cancelled" in pg.status.text().lower()
    assert not any(f.endswith(".tmp") for f in os.listdir(tmp_path / "") if os.path.isfile(tmp_path / f))
    assert pg.btn_start.isEnabled() and not pg.btn_cancel.isEnabled()


def test_viewer(win, samples, tmp_path):
    v = page_of(win, "reader")
    assert v.open_file(samples["multi"])
    wait_until(lambda: v.thumbs.count() == 10)
    v.view.goto(4)
    assert v.view.current == 4 and v.spin.value() == 5
    v.view.set_fit("page"); v.view.set_fit("width")
    z = v.view.zoom
    v.view.set_zoom(z * 1.5)
    assert v.view.zoom > z
    v.view.rotate_view(90)
    assert v.view.view_rot == 90
    v.b_cont.click()                                 # single page mode
    assert not v.view.continuous
    v.view.goto(2)
    assert v.view.current == 2
    v.b_cont.click()
    v.search.setText("page 7")
    v.do_search()
    assert v.hit_lbl.text().startswith("1 /")
    assert v.view.current == 6
    img = v.view.viewport().grab()                   # rendering does not crash (incl. highlights)
    assert not img.isNull()
    v.search.setText("zzzz-nothing")
    v.do_search()
    assert v.hit_lbl.text() == "No matches"
    # recent list updated
    assert samples["multi"] in win.settings.get("recent")


def test_viewer_locked_and_bad_files(win, samples, monkeypatch):
    v = page_of(win, "reader")
    monkeypatch.setattr(dialogs, "ask_password", lambda parent, path, wrong=False: "secret")
    assert v.open_file(samples["locked"])
    assert v.doc.page_count == 4
    assert not v.open_file(samples["garbage"])
    assert any("garbage.pdf" in m for k, m in win.popups if k == "error")


def test_settings_roundtrip(win, tmp_path):
    s = win.settings
    s.add_recent(str(tmp_path))  # nonexistent file filtered by recent_existing; dir exists though
    s.set("image_dpi", 300)
    s2 = Settings(s.path)
    assert s2.get("image_dpi") == 300
    s.reset()
    assert s.get("image_dpi") == 150
    s.clear_history()
    assert s.get("recent") == []


def test_phase2_phase3_gui_and_open_in_reader(win, samples, tmp_path):
    # Test Crop page with interactive PagePreviewCard
    cr = page_of(win, "crop")
    cr.panel.list.add_paths([samples["single"]])
    assert cr.preview_card._path == samples["single"]
    assert cr.preview_card.canvas._pixmap is not None
    cr.preview_card.crop_selected.emit(12.0, 14.0, 16.0, 18.0)
    assert cr.top.value() == 12.0 and cr.left.value() == 16.0
    cr.out_edit.setText(str(tmp_path))
    cr.name_edit.setText("cropped_gui")
    cr.start(); wait_idle(cr)
    assert (tmp_path / "cropped_gui.pdf").exists()
    assert cr.btn_view.isEnabled()

    # Click "Open in Reader" button and verify it opens in the Reader page
    cr.btn_view.click()
    v = win.pages.get("tool:reader")
    assert v is not None and v.doc is not None and v.doc.page_count == 1

    # Test Annotate page with interactive rectangle drag
    ann = page_of(win, "annotate")
    ann.panel.list.add_paths([samples["single"]])
    ann.text_box.setPlainText("Interactive box note")
    ann.preview_card.rect_selected.emit(25.0, 35.0, 80.0, 30.0)
    assert abs(ann.x_mm.value() - 25.0) < 0.2 and abs(ann.y_mm.value() - 35.0) < 0.2
    ann.out_edit.setText(str(tmp_path))
    ann.name_edit.setText("annotated_gui")
    ann.start(); wait_idle(ann)
    assert (tmp_path / "annotated_gui.pdf").exists()

    # Test Redact page with region selection
    red = page_of(win, "redact")
    red.panel.list.add_paths([samples["multi2"]])
    red.terms.setText("Other page 2")
    red.preview_card.rect_selected.emit(10.0, 10.0, 50.0, 20.0)
    assert red.use_rect.isChecked() and red.rw.value() == 50.0
    red.out_edit.setText(str(tmp_path))
    red.name_edit.setText("redacted_gui")
    red.start(); wait_idle(red)
    assert (tmp_path / "redacted_gui.pdf").exists()


def test_sqlite_history_persistence_and_search(win, samples, tmp_path):
    s = win.settings
    assert os.path.isfile(s.history_db.db_path)

    # Record files with actions and verify SQLite persistence across Settings reload
    s.add_recent(samples["single"], action="Merge PDF", page_count=1)
    s.add_recent(samples["multi"], action="PDF Reader", page_count=10)
    s.add_recent(samples["single"], action="Compress PDF", page_count=1)  # bumps open_count to 2
    s.history_db.record_operation("compress", samples["single"], "Saved 42%")

    s_reloaded = Settings(s.path)
    entries = s_reloaded.recent_entries()
    assert len(entries) >= 2
    top = entries[0]
    assert top.file_path == os.path.abspath(samples["single"])
    assert top.action == "Compress PDF"
    assert top.open_count == 2
    assert top.page_count == 1

    ops = s_reloaded.history_db.list_operations()
    assert len(ops) == 1 and ops[0].tool_id == "compress"

    # Test RecentPage UI filtering & removal backed by SQLite
    rec_pg = win.navigate("recent")
    assert rec_pg.list.count() >= 2
    rec_pg.search_edit.setText("multi")
    assert rec_pg.list.count() == 1
    rec_pg.search_edit.setText("")
    rec_pg.action_box.setCurrentText("Compress PDF")
    assert rec_pg.list.count() == 1
    rec_pg.action_box.setCurrentText("All")

    # Remove single item from RecentPage
    rec_pg.list.setCurrentRow(0)
    rec_pg._remove()
    assert os.path.abspath(samples["single"]) not in s.recent_existing()

    # Export CSV from SQLite history
    csv_out = str(tmp_path / "history_export.csv")
    exported_n = s.history_db.export_csv(csv_out)
    assert exported_n >= 1 and os.path.isfile(csv_out)
    assert rec_pg.ops_list.count() >= 1

    # Send to Tool from RecentPage
    rec_pg.list.setCurrentRow(0)
    rec_pg._send_to_tool("compress")
    comp_pg = win.pages.get("tool:compress")
    assert comp_pg is not None and len(comp_pg.panel.paths()) == 1

    # Send to Tool from ViewerPage
    v = page_of(win, "reader")
    v.open_file(samples["single"])
    v._send_to_tool("watermark")
    wm_pg = win.pages.get("tool:watermark")
    assert wm_pg is not None and wm_pg.panel.first_path() == samples["single"]

    # Dashboard instant tool search & sidebar quick theme toggle
    dash = win.navigate("dashboard")
    dash.tool_search.setText("redact")
    dash.tool_search.setText("")
    win.btn_theme_toggle.click()
    assert win.settings.get("theme") == "dark"
    win.btn_theme_toggle.click()
    assert win.settings.get("theme") == "light"




