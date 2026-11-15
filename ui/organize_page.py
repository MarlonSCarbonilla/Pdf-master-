from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from core.pdf_organize import rebuild_pdf
from ui.components.file_list import FilePanel
from ui.components.icons import icon
from ui.components.thumbnails import ThumbnailGrid
from ui.components.tool_page import ToolPage
from ui.components.widgets import hint


class OrganizePage(ToolPage):
    TOOL_ID = "organize"
    TITLE = "Organize PDF"
    DESC = "Reorder pages by drag & drop, rotate, duplicate or delete them, then save a new PDF."
    START_TEXT = "Save organized PDF"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = FilePanel("pdf", single=True)
        self.panel.setMaximumHeight(190)
        self.panel.list.setMinimumHeight(60)
        self.panel.changed.connect(self._on_file)
        lay.addWidget(self.panel)

        bar = QHBoxLayout()
        self.grid = ThumbnailGrid(movable=True)
        for name, text, fn in (("rot_left", "Rotate left", lambda: self.grid.rotate_selected(-90)),
                               ("rot_right", "Rotate right", lambda: self.grid.rotate_selected(90)),
                               ("duplicate", "Duplicate", lambda: self.grid.duplicate_selected()),
                               ("remove", "Delete", lambda: self.grid.delete_selected()),
                               ("up", "◀ Earlier", lambda: self.grid.move_selected(-1)),
                               ("down", "Later ▶", lambda: self.grid.move_selected(1))):
            b = QPushButton(text)
            if name not in ("up", "down"):
                b.setIcon(icon(name, "#6b7280", 18))
            b.clicked.connect(lambda _=False, f=fn: f())
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)
        lay.addWidget(self.grid, 1)
        self.grid.plan_changed.connect(self._update_info)
        return w

    def build_options(self, layout: QVBoxLayout) -> None:
        layout.addWidget(hint("• Click a thumbnail to select it (Ctrl/Shift for several).\n"
                              "• Drag pages to a new position to reorder them.\n"
                              "• Use the buttons above to rotate, duplicate or delete the selection.\n"
                              "• Nothing changes in your original file; a new PDF is saved."))
        self.info = hint("")
        layout.addWidget(self.info)

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            n = self.panel.list.page_counts()[p]
            self.grid.load(p, n, self.panel.passwords.get(p))
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_organized.pdf")
            self.default_dir_from(p)
        else:
            self.grid.load(None)
        self._update_info()

    def _update_info(self) -> None:
        p = self.panel.first_path()
        if not p:
            self.info.setText("")
            return
        n = self.panel.list.page_counts()[p]
        self.info.setText(f"Result: {self.grid.count()} page(s) (original had {n}).")

    def _changed(self) -> bool:
        return self.grid.plan() != [(i, 0) for i in range(self.grid.count())]

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        if self.grid.count() == 0:
            raise ValueError("The document has no pages left. Keep at least one page.")
        if not self._changed():
            raise ValueError("You have not changed anything yet. Reorder, rotate, duplicate or delete pages first.")
        out = self.output_file(".pdf", [src])
        self.check_space([src], 1.5)
        return rebuild_pdf, dict(src=src, output=out, plan=self.grid.plan(), password=self.panel.passwords.get(src))

    def describe_result(self, result) -> str:
        return f"Saved {os.path.basename(result)} with {self.grid.count()} pages."

    def clear_input(self) -> None:
        self.panel.list.clear_all()

    def shutdown(self) -> None:
        self.grid.stop_loading()
        super().shutdown()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main(start_tool='organize'))
