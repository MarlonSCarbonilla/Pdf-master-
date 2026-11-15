"""Phase 3 (Optional Module) - OCR Tools UI page:
Searchable PDF generation, scanned text extraction, language pack selection, and batch OCR."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from core.ocr_engine import OcrResult, available_languages, find_tesseract, run_ocr
from ui.components.file_list import FilePanel
from ui.components.tool_page import ToolPage
from ui.components.widgets import hint, labeled
from workers.conversion_worker import ConversionWorker


class OcrPage(ToolPage):
    TOOL_ID = "ocr"
    TITLE = "OCR PDF (Recognize Scanned Text)"
    DESC = "Turn scanned PDFs into searchable documents or extract recognized text using Tesseract OCR (supports batch processing)."
    START_TEXT = "Run OCR"
    OUTPUT_IS_DIR = True
    WORKER_CLASS = ConversionWorker

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=False)
        self.panel.changed.connect(self._on_files)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.r_pdf = QRadioButton("Create searchable PDF(s)")
        self.r_txt = QRadioButton("Extract text to .txt file(s)")
        self.r_pdf.setChecked(True)
        layout.addWidget(self.r_pdf)
        layout.addWidget(self.r_txt)

        self.lang = QComboBox()
        self.lang.setEditable(True)
        self.dpi = QComboBox()
        self.dpi.addItems(["150", "200", "300"])
        self.dpi.setCurrentText("200")
        layout.addWidget(labeled("Language:", self.lang))
        layout.addWidget(labeled("Scan DPI:", self.dpi))

        self.pages = QLineEdit()
        self.pages.setPlaceholderText("all (or e.g. 1-5)")
        layout.addWidget(labeled("Pages:", self.pages))
        self.skip_existing = QCheckBox("Skip pages that already have selectable text")
        self.skip_existing.setChecked(True)
        layout.addWidget(self.skip_existing)

        layout.addWidget(QLabel("Tesseract executable (auto-detected if installed):"))
        row = QHBoxLayout()
        self.tess_edit = QLineEdit(find_tesseract() or "")
        self.tess_edit.setPlaceholderText("C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
        self.tess_edit.textChanged.connect(self._refresh_langs)
        b = QPushButton("Browse…")
        b.clicked.connect(self._browse_tess)
        row.addWidget(self.tess_edit, 1)
        row.addWidget(b)
        layout.addLayout(row)
        self.tess_status = hint("")
        layout.addWidget(self.tess_status)
        self._refresh_langs()

    def _browse_tess(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Locate tesseract.exe", "", "Executable (*.exe)")
        if f:
            self.tess_edit.setText(f)

    def _refresh_langs(self) -> None:
        exe = find_tesseract(self.tess_edit.text().strip())
        langs = available_languages(exe or "")
        cur = self.lang.currentText() or "eng"
        self.lang.blockSignals(True)
        self.lang.clear()
        self.lang.addItems(langs)
        self.lang.setCurrentText(cur if cur in langs else langs[0])
        self.lang.blockSignals(False)
        if exe:
            self.tess_status.setText(f"✔ Tesseract ready ({len(langs)} language pack(s): {', '.join(langs[:6])}).")
        else:
            self.tess_status.setText(
                "ℹ Tesseract OCR binary not detected yet. Install Tesseract OCR or browse to tesseract.exe above."
            )

    def _on_files(self) -> None:
        self.default_dir_from(self.panel.first_path())

    def prepare(self):
        files = self.panel.paths()
        if not files:
            raise ValueError("Add at least one PDF file for OCR.")
        self._check_folder()
        mode = "searchable_pdf" if self.r_pdf.isChecked() else "extract_text"
        return run_ocr, dict(
            pdfs=files,
            out_dir=self.out_dir(),
            mode=mode,
            lang=(self.lang.currentText() or "eng").strip(),
            dpi=int(self.dpi.currentText()),
            page_text=self.pages.text().strip() or None,
            skip_pages_with_text=self.skip_existing.isChecked(),
            tesseract_path=self.tess_edit.text().strip(),
            passwords=dict(self.panel.passwords),
        )

    def result_paths(self, result: OcrResult):
        return list(result.outputs)

    def describe_result(self, result: OcrResult) -> str:
        return f"OCR processed {result.pages_processed} page(s) → {len(result.outputs)} output file(s)."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main(start_tool='ocr'))
