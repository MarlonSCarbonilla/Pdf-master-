"""Remove pages / Extract pages / Rotate PDF - thumbnail selection + range text."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os

from PySide6.QtWidgets import (QButtonGroup, QLabel, QLineEdit, QRadioButton, QVBoxLayout, QWidget)

from core.pdf_organize import remove_pages, rotate_pdf
from core.pdf_split import extract_pages
from ui.components.file_list import FilePanel
from ui.components.thumbnails import ThumbnailGrid
from ui.components.tool_page import ToolPage
from ui.components.widgets import hint
from utils.validators import format_ranges, parse_page_ranges


class PageSelectPage(ToolPage):
    NEEDS_FILENAME = True
    SUFFIX = "_edited"

    def build_input(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = FilePanel("pdf", single=True)
        self.panel.setMaximumHeight(190)
        self.panel.list.setMinimumHeight(60)
        self.panel.changed.connect(self._on_file)
        lay.addWidget(self.panel)
        self.grid = ThumbnailGrid(movable=False)
        self.grid.itemSelectionChanged.connect(self._grid_selected)
        lay.addWidget(self.grid, 1)
        return w

    def build_options(self, layout: QVBoxLayout) -> None:
        self.count_lbl = hint("No file selected.")
        layout.addWidget(self.count_lbl)
        layout.addWidget(QLabel("Pages (numbers or ranges):"))
        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText("e.g. 1-3, 5, 8-10")
        self.pages_edit.textEdited.connect(self._text_edited)
        layout.addWidget(self.pages_edit)
        layout.addWidget(hint("Click thumbnails to select pages, or type page numbers - both stay in sync."))
        self.summary = hint("")
        layout.addWidget(self.summary)
        self.build_extra(layout)

    def build_extra(self, layout: QVBoxLayout) -> None:
        pass

    # ---- state ----
    def page_count(self) -> int:
        p = self.panel.first_path()
        return self.panel.list.page_counts()[p] if p else 0

    def _on_file(self) -> None:
        p = self.panel.first_path()
        n = self.page_count()
        self.grid.load(p, n, self.panel.passwords.get(p) if p else None) if p else self.grid.load(None)
        self.pages_edit.clear()
        self.count_lbl.setText(f"Document has {n} pages." if p else "No file selected.")
        if p and self.name_edit:
            self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + self.SUFFIX + ".pdf")
        self.default_dir_from(p)
        self._update_summary()

    def _grid_selected(self) -> None:
        if getattr(self, "_syncing", False):
            return
        self.pages_edit.setText(format_ranges(self.grid.selected_source_pages()))
        self._update_summary()

    def _text_edited(self, text: str) -> None:
        try:
            pages = parse_page_ranges(text, self.page_count())
            self._syncing = True
            try:
                self.grid.select_source_pages(pages)
            finally:
                self._syncing = False
        except ValueError:
            pass
        self._update_summary()

    def selected_text(self) -> str:
        return self.pages_edit.text().strip()

    def _update_summary(self) -> None:
        txt = self.selected_text()
        if not txt or not self.page_count():
            self.summary.setText("")
            return
        try:
            n = len(parse_page_ranges(txt, self.page_count()))
        except ValueError as e:
            self.summary.setText(f"⚠ {e}")
            return
        self.summary.setText(self.describe_selection(n))

    def describe_selection(self, n: int) -> str:
        return f"{n} page(s) selected."

    def require_source(self) -> str:
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        return src

    def require_pages(self) -> str:
        txt = self.selected_text()
        try:
            parse_page_ranges(txt, self.page_count())
        except ValueError as e:
            raise ValueError(str(e)) from None
        return txt

    def clear_input(self) -> None:
        self.panel.list.clear_all()
        self.pages_edit.clear()

    def shutdown(self) -> None:
        self.grid.stop_loading()
        super().shutdown()


class RemovePagesPage(PageSelectPage):
    TOOL_ID = "remove"
    TITLE = "Remove Pages"
    DESC = "Select the pages you want to delete. A new PDF without them is saved."
    START_TEXT = "Remove pages"
    SUFFIX = "_removed"

    def describe_selection(self, n: int) -> str:
        left = self.page_count() - n
        return f"{n} page(s) will be removed → the result will have {left} page(s)."

    def prepare(self):
        src = self.require_source()
        txt = self.require_pages()
        out = self.output_file(".pdf", [src])
        self.check_space([src], 1.5)
        return remove_pages, dict(src=src, output=out, page_text=txt, password=self.panel.passwords.get(src))

    def describe_result(self, result) -> str:
        return f"Saved {os.path.basename(result)} without the selected pages."


class ExtractPagesPage(PageSelectPage):
    TOOL_ID = "extract"
    TITLE = "Extract Pages"
    DESC = "Pick pages or ranges and export them as a separate PDF."
    START_TEXT = "Extract pages"
    SUFFIX = "_extracted"

    def describe_selection(self, n: int) -> str:
        return f"{n} page(s) will be exported, in the order you typed them."

    def prepare(self):
        src = self.require_source()
        txt = self.require_pages()
        out = self.output_file(".pdf", [src])
        self.check_space([src], 1.0)
        return extract_pages, dict(src=src, output=out, page_text=txt, password=self.panel.passwords.get(src))

    def describe_result(self, result) -> str:
        return f"Extracted pages saved to {os.path.basename(result)}."


class RotatePdfPage(PageSelectPage):
    TOOL_ID = "rotate"
    TITLE = "Rotate PDF"
    DESC = "Rotate all pages, or only selected ones, by 90, 180 or 270 degrees."
    START_TEXT = "Rotate PDF"
    SUFFIX = "_rotated"

    def build_extra(self, layout: QVBoxLayout) -> None:
        layout.addWidget(QLabel("Rotation (clockwise):"))
        self.angles = {}
        grp = QButtonGroup(self)
        for a in (90, 180, 270):
            r = QRadioButton(f"{a}°")
            grp.addButton(r)
            layout.addWidget(r)
            self.angles[a] = r
        self.angles[90].setChecked(True)
        layout.addWidget(QLabel("Apply to:"))
        self.r_all = QRadioButton("All pages")
        self.r_sel = QRadioButton("Selected pages / ranges")
        self.r_all.setChecked(True)
        g2 = QButtonGroup(self)
        for r in (self.r_all, self.r_sel):
            g2.addButton(r)
            layout.addWidget(r)

    def describe_selection(self, n: int) -> str:
        return f"{n} page(s) selected."

    def prepare(self):
        src = self.require_source()
        angle = next(a for a, r in self.angles.items() if r.isChecked())
        if self.r_sel.isChecked():
            txt = self.require_pages()
        else:
            txt = None
        out = self.output_file(".pdf", [src])
        self.check_space([src], 1.5)
        return rotate_pdf, dict(src=src, output=out, angle=angle, page_text=txt, password=self.panel.passwords.get(src))

    def describe_result(self, result) -> str:
        return f"Rotated PDF saved as {os.path.basename(result)}."

    def reset_options(self) -> None:
        self.angles[90].setChecked(True)
        self.r_all.setChecked(True)
        self.pages_edit.clear()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main(start_tool='remove'))
