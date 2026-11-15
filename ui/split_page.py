from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os

from PySide6.QtWidgets import QButtonGroup, QLineEdit, QRadioButton, QSpinBox, QVBoxLayout, QWidget

from core.pdf_split import split_pdf
from ui.components.file_list import FilePanel
from ui.components.tool_page import ToolPage
from ui.components.widgets import hint, labeled


class SplitPage(ToolPage):
    TOOL_ID = "split"
    TITLE = "Split PDF"
    DESC = "Split one PDF into single pages, custom ranges, or equal parts."
    START_TEXT = "Split PDF"
    OUTPUT_IS_DIR = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.pages_lbl = hint("No file selected.")
        layout.addWidget(self.pages_lbl)
        self.r_pages = QRadioButton("Every page as a separate PDF")
        self.r_ranges = QRadioButton("Custom page ranges")
        self.r_every = QRadioButton("Every N pages")
        self.r_pages.setChecked(True)
        self.group = QButtonGroup(self)
        for r in (self.r_pages, self.r_ranges, self.r_every):
            self.group.addButton(r)
            layout.addWidget(r)
        self.ranges = QLineEdit()
        self.ranges.setPlaceholderText("e.g. 1-3, 5, 7-10")
        layout.addWidget(self.ranges)
        layout.addWidget(hint("Each comma-separated range becomes its own PDF."))
        self.every = QSpinBox()
        self.every.setRange(1, 100000)
        self.every.setValue(2)
        layout.addWidget(labeled("N =", self.every))
        self.prefix = QLineEdit()
        self.prefix.setPlaceholderText("default: original file name")
        layout.addWidget(labeled("Name prefix:", self.prefix))
        layout.addWidget(hint("Output names look like prefix_page_001.pdf. Existing files are never overwritten."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            n = self.panel.list.page_counts()[p]
            self.pages_lbl.setText(f"Document has {n} page{'s' if n != 1 else ''}.")
            self.default_dir_from(p)
        else:
            self.pages_lbl.setText("No file selected.")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        self._check_folder()
        self.check_space([src], 1.5)
        if self.r_ranges.isChecked():
            mode = "ranges"
            if not self.ranges.text().strip():
                raise ValueError("Enter the page ranges to split by, e.g. 1-3, 5, 7-10.")
        elif self.r_every.isChecked():
            mode = "every"
        else:
            mode = "pages"
        return split_pdf, dict(src=src, out_dir=self.out_dir(), mode=mode, ranges=self.ranges.text(),
                               every_n=self.every.value(), prefix=self.prefix.text().strip(),
                               password=self.panel.passwords.get(src))

    def result_paths(self, result):
        return list(result)

    def describe_result(self, result) -> str:
        return f"Created {len(result)} PDF file(s) in {os.path.dirname(result[0])}."

    def reset_options(self) -> None:
        self.r_pages.setChecked(True)
        self.ranges.clear()
        self.every.setValue(2)
        self.prefix.clear()

    def clear_input(self) -> None:
        self.panel.list.clear_all()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main(start_tool='split'))
