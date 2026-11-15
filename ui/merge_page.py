from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os

from PySide6.QtWidgets import QVBoxLayout, QWidget

from core.pdf_merge import merge_pdfs
from ui.components.file_list import FilePanel
from ui.components.tool_page import ToolPage
from ui.components.widgets import hint


class MergePage(ToolPage):
    TOOL_ID = "merge"
    TITLE = "Merge PDF"
    DESC = "Combine several PDF files into a single document, in the order shown."
    START_TEXT = "Merge PDFs"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=False)
        self.panel.changed.connect(self._on_files)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        layout.addWidget(hint("• Add or drop two or more PDFs.\n• Drag items in the list (or use Up/Down) to change the order.\n"
                              "• Password-protected files ask for their password when added.\n"
                              "• Your original files are never modified."))
        self.total = hint("")
        layout.addWidget(self.total)

    def _on_files(self) -> None:
        counts = self.panel.list.page_counts()
        self.total.setText(f"{len(counts)} file(s), {sum(counts.values())} pages in total." if counts else "")
        if self.name_edit and not self.name_edit.text():
            self.name_edit.setText("merged.pdf")
        first = self.panel.first_path()
        self.default_dir_from(first)

    def prepare(self):
        files = self.panel.paths()
        if len(files) < 2:
            raise ValueError("Add at least two PDF files to merge.")
        out = self.output_file(".pdf", files)
        self.check_space(files, 1.2)
        return merge_pdfs, dict(inputs=files, output=out, passwords=dict(self.panel.passwords))

    def describe_result(self, result) -> str:
        import fitz
        d = fitz.open(result)
        n = d.page_count
        d.close()
        return f"Merged into {os.path.basename(result)} ({n} pages)."

    def clear_input(self) -> None:
        self.panel.list.clear_all()
        self.total.setText("")


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main(start_tool='merge'))
