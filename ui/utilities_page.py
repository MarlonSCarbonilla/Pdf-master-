"""Phase 2 - PDF Utilities UI pages:
Repair PDF, Remove Blank Pages, Flatten PDF, Grayscale PDF, Extract Text,
Extract Embedded Images, Compare PDFs, Batch Rename PDFs."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.pdf_utilities import (
    CompareResult,
    batch_rename_pdfs,
    compare_pdfs,
    convert_to_grayscale,
    extract_embedded_images,
    extract_text_to_file,
    flatten_pdf,
    remove_blank_pages,
    repair_pdf,
)
from ui.components.file_list import FilePanel
from ui.components.tool_page import ToolPage
from ui.components.widgets import hint, labeled


class RepairPdfPage(ToolPage):
    TOOL_ID = "repair"
    TITLE = "Repair PDF"
    DESC = "Recover readable pages and rebuild corrupted cross-reference tables or streams where possible."
    START_TEXT = "Repair PDF"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf_raw", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("Optional password if encrypted")
        layout.addWidget(labeled("Password:", self.pw))
        layout.addWidget(hint("Attempts page-by-page salvage and structural stream reconstruction."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_repaired.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        out = self.output_file(".pdf", [src])
        return repair_pdf, dict(src=src, output=out, password=self.pw.text() or None)

    def result_paths(self, result):
        return [result[0]]

    def describe_result(self, result) -> str:
        path, pages = result
        return f"Recovered {pages} readable page(s) → {os.path.basename(path)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class RemoveBlankPagesPage(ToolPage):
    TOOL_ID = "remove_blank"
    TITLE = "Remove Blank Pages"
    DESC = "Automatically detect and delete empty or near-white pages from a PDF."
    START_TEXT = "Remove blank pages"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.sens = QComboBox()
        self.sens.addItems(["Strict (pure white only)", "Balanced (recommended)", "Aggressive (light scan noise)"])
        self.sens.setCurrentIndex(1)
        layout.addWidget(labeled("Detection:", self.sens))
        layout.addWidget(hint("Pages containing any selectable text are never treated as blank."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_no_blanks.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        out = self.output_file(".pdf", [src])
        thresh = [0.999, 0.995, 0.985][self.sens.currentIndex()]
        return remove_blank_pages, dict(
            src=src, output=out, sensitivity=thresh, password=self.panel.passwords.get(src),
        )

    def result_paths(self, result):
        return [result[0]]

    def describe_result(self, result) -> str:
        path, removed, kept = result
        if not removed:
            return f"ℹ No blank pages were detected; saved all {kept} page(s) to {os.path.basename(path)}."
        return f"Removed {len(removed)} blank page(s) ({', '.join(map(str, removed[:10]))}); kept {kept} page(s)."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class FlattenPdfPage(ToolPage):
    TOOL_ID = "flatten"
    TITLE = "Flatten PDF"
    DESC = "Merge annotations, stamps and interactive form fields permanently into page content."
    START_TEXT = "Flatten PDF"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.c_annots = QCheckBox("Flatten annotations & markups")
        self.c_annots.setChecked(True)
        self.c_forms = QCheckBox("Flatten interactive form fields")
        self.c_forms.setChecked(True)
        layout.addWidget(self.c_annots)
        layout.addWidget(self.c_forms)
        layout.addWidget(hint("Flattening prevents recipients from editing or moving annotations and form values."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_flattened.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        if not self.c_annots.isChecked() and not self.c_forms.isChecked():
            raise ValueError("Check at least one item to flatten.")
        out = self.output_file(".pdf", [src])
        return flatten_pdf, dict(
            src=src, output=out,
            flatten_annots=self.c_annots.isChecked(),
            flatten_widgets=self.c_forms.isChecked(),
            password=self.panel.passwords.get(src),
        )

    def describe_result(self, result) -> str:
        return f"Flattened PDF saved as {os.path.basename(result)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class GrayscalePdfPage(ToolPage):
    TOOL_ID = "grayscale"
    TITLE = "Convert PDF to Grayscale"
    DESC = "Convert color PDFs to black-and-white / grayscale for printing and archiving."
    START_TEXT = "Convert to grayscale"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.keep_vec = QCheckBox("Preserve selectable text and vectors (recommended)")
        self.keep_vec.setChecked(True)
        layout.addWidget(self.keep_vec)
        self.dpi = QComboBox()
        self.dpi.addItems(["150", "200", "300"])
        layout.addWidget(labeled("Raster DPI (if unchecked):", self.dpi))
        layout.addWidget(hint("Preserving text keeps fonts sharp and searchable while converting images and RGB colors to grayscale."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_grayscale.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        out = self.output_file(".pdf", [src])
        return convert_to_grayscale, dict(
            src=src, output=out,
            preserve_text=self.keep_vec.isChecked(),
            dpi=int(self.dpi.currentText()),
            password=self.panel.passwords.get(src),
        )

    def describe_result(self, result) -> str:
        return f"Grayscale PDF saved as {os.path.basename(result)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class ExtractTextPage(ToolPage):
    TOOL_ID = "extract_text"
    TITLE = "Extract Text"
    DESC = "Export selectable text from all or chosen PDF pages into a clean UTF-8 .txt file."
    START_TEXT = "Extract text"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("all (or e.g. 1-5, 8)")
        layout.addWidget(labeled("Pages:", self.pages))
        self.headers = QCheckBox("Include '=== Page N ===' separators")
        self.headers.setChecked(True)
        layout.addWidget(self.headers)
        layout.addWidget(hint("For scanned PDFs without selectable text, use OCR Tools instead."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_text.txt")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        out = self.output_file(".txt", [src])
        return extract_text_to_file, dict(
            src=src, output_txt=out,
            page_text=self.pages.text().strip() or None,
            include_page_headers=self.headers.isChecked(),
            password=self.panel.passwords.get(src),
        )

    def result_paths(self, result):
        return [result[0]]

    def describe_result(self, result) -> str:
        path, pages, chars = result
        return f"Extracted {chars:,} character(s) from {pages} page(s) → {os.path.basename(path)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class ExtractImagesPage(ToolPage):
    TOOL_ID = "extract_images"
    TITLE = "Extract Embedded Images"
    DESC = "Save all embedded photos and graphics from a PDF in their original resolution."
    START_TEXT = "Extract images"
    OUTPUT_IS_DIR = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("all (or e.g. 1-3, 5)")
        layout.addWidget(labeled("Pages:", self.pages))
        self.min_dim = QSpinBox()
        self.min_dim.setRange(1, 500)
        self.min_dim.setValue(16)
        self.min_dim.setSuffix(" px")
        layout.addWidget(labeled("Min size:", self.min_dim))
        layout.addWidget(hint("Skips tiny 1×1 spacer bitmaps smaller than the minimum pixel size."))

    def _on_file(self) -> None:
        self.default_dir_from(self.panel.first_path())

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        self._check_folder()
        return extract_embedded_images, dict(
            src=src, out_dir=self.out_dir(),
            page_text=self.pages.text().strip() or None,
            min_dimension=self.min_dim.value(),
            password=self.panel.passwords.get(src),
        )

    def result_paths(self, result):
        return list(result)

    def describe_result(self, result) -> str:
        return f"Extracted {len(result)} embedded image(s) to {os.path.dirname(result[0])}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class ComparePdfsPage(ToolPage):
    TOOL_ID = "compare"
    TITLE = "Compare Two PDFs"
    DESC = "Compare two PDF documents side-by-side (both text and visual pixel changes) and generate a highlighted diff report PDF."
    START_TEXT = "Compare PDFs"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=False)
        self.panel.changed.connect(self._on_files)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        layout.addWidget(hint(
            "• Add exactly two PDF files (Document A and Document B).\n"
            "• Generates a landscape comparison report PDF showing Document A, Document B, "
            "red-highlighted visual differences, and unified text diffs for every page."
        ))

    def _on_files(self) -> None:
        first = self.panel.first_path()
        if first:
            self.default_dir_from(first)
            if self.name_edit and not self.name_edit.text():
                self.name_edit.setText("comparison_report.pdf")

    def prepare(self):
        files = self.panel.paths()
        if len(files) != 2:
            raise ValueError("Select exactly two PDF files to compare (Document A and Document B).")
        out = self.output_file(".pdf", files)
        return compare_pdfs, dict(
            pdf_a=files[0],
            pdf_b=files[1],
            output_report_pdf=out,
            password_a=self.panel.passwords.get(files[0]),
            password_b=self.panel.passwords.get(files[1]),
        )

    def result_paths(self, result: CompareResult):
        return [result.report_pdf]

    def describe_result(self, result: CompareResult) -> str:
        return f"{result.summary} Report: {os.path.basename(result.report_pdf)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class BatchRenamePage(ToolPage):
    TOOL_ID = "batch_rename"
    TITLE = "Batch Rename PDFs"
    DESC = "Copy and rename multiple PDF files using numbering patterns, page counts, dates, or find & replace."
    START_TEXT = "Rename batch"
    OUTPUT_IS_DIR = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=False)
        self.panel.changed.connect(self._on_files)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.pattern = QLineEdit("{num:03d}_{name}")
        layout.addWidget(labeled("Name pattern:", self.pattern))
        self.start_num = QSpinBox()
        self.start_num.setRange(1, 999999)
        self.start_num.setValue(1)
        layout.addWidget(labeled("Start number:", self.start_num))
        self.find_txt = QLineEdit()
        self.find_txt.setPlaceholderText("Optional text to find")
        layout.addWidget(labeled("Find in name:", self.find_txt))
        self.repl_txt = QLineEdit()
        self.repl_txt.setPlaceholderText("Replacement")
        layout.addWidget(labeled("Replace with:", self.repl_txt))
        layout.addWidget(hint(
            "Placeholders:\n"
            "• {num} or {num:03d} - sequence number\n"
            "• {name} - original file name\n"
            "• {pages} - page count\n"
            "• {date} - YYYY-MM-DD\n"
            "Originals are preserved; renamed copies are written to the output folder."
        ))

    def _on_files(self) -> None:
        self.default_dir_from(self.panel.first_path())

    def prepare(self):
        files = self.panel.paths()
        if not files:
            raise ValueError("Add at least one PDF file to rename.")
        self._check_folder()
        return batch_rename_pdfs, dict(
            inputs=files,
            out_dir=self.out_dir(),
            pattern=self.pattern.text().strip() or "{num:03d}_{name}",
            start_num=self.start_num.value(),
            find_text=self.find_txt.text(),
            replace_text=self.repl_txt.text(),
            passwords=dict(self.panel.passwords),
        )

    def result_paths(self, result):
        return list(result)

    def describe_result(self, result) -> str:
        return f"Created {len(result)} renamed PDF file(s) in {os.path.dirname(result[0])}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main(start_tool='repair'))
