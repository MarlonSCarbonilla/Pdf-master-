from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os

from PySide6.QtWidgets import QButtonGroup, QCheckBox, QFrame, QLabel, QRadioButton, QVBoxLayout, QWidget

from core.pdf_compress import PRESETS, CompressResult, compress_pdf
from ui.components.file_list import FilePanel
from ui.components.tool_page import ToolPage
from ui.components.widgets import hint
from utils.file_utils import human_size


class CompressPage(ToolPage):
    TOOL_ID = "compress"
    TITLE = "Compress PDF"
    DESC = "Reduce PDF file size by optimising images and removing unused data. Text and vectors stay sharp."
    START_TEXT = "Compress PDF"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = FilePanel("pdf", single=True)
        self.panel.changed.connect(self._on_file)
        lay.addWidget(self.panel, 1)
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        self.result_title = QLabel("Result")
        self.result_title.setObjectName("h2")
        cl.addWidget(self.result_title)
        self.result_lbl = QLabel("Choose a file and start compression to see the exact savings here.")
        self.result_lbl.setWordWrap(True)
        cl.addWidget(self.result_lbl)
        lay.addWidget(card)
        return w

    def build_options(self, layout: QVBoxLayout) -> None:
        self.presets: dict[str, QRadioButton] = {}
        grp = QButtonGroup(self)
        for key, cfg in PRESETS.items():
            r = QRadioButton(cfg["label"])
            grp.addButton(r)
            layout.addWidget(r)
            self.presets[key] = r
        self.presets[self.settings.get("compression_preset")].setChecked(True)
        self.c_images = QCheckBox("Optimise embedded images")
        self.c_down = QCheckBox("Downsample high-resolution images")
        self.c_unused = QCheckBox("Remove unused objects")
        self.c_meta = QCheckBox("Strip document metadata")
        for c in (self.c_images, self.c_down, self.c_unused):
            c.setChecked(True)
            layout.addWidget(c)
        layout.addWidget(self.c_meta)
        layout.addWidget(hint("Text and vector graphics are never rasterised. If the file cannot be made smaller, "
                              "nothing is saved and you are told so."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_compressed.pdf")
            self.result_lbl.setText(f"Original size: {human_size(os.path.getsize(p))}")
        else:
            self.result_lbl.setText("Choose a file and start compression to see the exact savings here.")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        out = self.output_file(".pdf", [src])
        self.check_space([src], 2.5)  # temp stages + output
        preset = next(k for k, r in self.presets.items() if r.isChecked())
        self.result_lbl.setText("Compressing…")
        return compress_pdf, dict(src=src, output=out, preset=preset, optimize_images=self.c_images.isChecked(),
                                  downsample=self.c_down.isChecked(), remove_unused=self.c_unused.isChecked(),
                                  strip_metadata=self.c_meta.isChecked(), password=self.panel.passwords.get(src))

    def result_paths(self, result: CompressResult):
        return [result.output] if result.output else []

    def describe_result(self, r: CompressResult) -> str:
        if not r.reduced:
            self.result_lbl.setText(f"Original size: {human_size(r.original_size)}\n\n{r.note}")
            return "ℹ No reduction possible - the original is already well optimised (no file was written)."
        self.result_lbl.setText(
            f"Original size:    {human_size(r.original_size)}\n"
            f"Compressed size:  {human_size(r.new_size)}\n"
            f"Size reduction:   {human_size(r.saved_bytes)}\n"
            f"Saved:            {r.percent_saved:.1f}%\n"
            f"Images optimised: {r.images_optimized}" + (f"\n{r.note}" if r.note else ""))
        return f"Compressed: {r.percent_saved:.1f}% smaller ({human_size(r.original_size)} → {human_size(r.new_size)})."

    def _on_failed(self, msg: str) -> None:
        self._on_file()
        super()._on_failed(msg)

    def reset_options(self) -> None:
        self.presets[self.settings.get("compression_preset")].setChecked(True)
        for c in (self.c_images, self.c_down, self.c_unused):
            c.setChecked(True)
        self.c_meta.setChecked(False)

    def clear_input(self) -> None:
        self.panel.list.clear_all()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main(start_tool='compress'))
