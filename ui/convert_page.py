"""Convert pages: PDF -> images and images -> PDF."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os

import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QRadioButton,
                               QSlider, QSpinBox, QVBoxLayout, QWidget, QFrame)

from core.image_to_pdf import images_to_pdf
from core.common import ProcessingError
from utils.file_utils import check_disk_space
from core.pdf_render import DPI_CHOICES, FORMATS, export_images, render_pixmap
from ui.components.file_list import FilePanel
from ui.components.tool_page import ToolPage
from ui.components.widgets import hint, labeled
from utils.validators import open_pdf, parse_page_ranges
from workers.conversion_worker import ConversionWorker


class PdfToImagePage(ToolPage):
    TOOL_ID = "pdf2img"
    TITLE = "PDF to Image"
    DESC = "Convert PDF pages to JPG, PNG or TIFF. Pages are rendered one at a time to keep memory low."
    START_TEXT = "Convert to images"
    OUTPUT_IS_DIR = True
    WORKER_CLASS = ConversionWorker

    def build_input(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = FilePanel("pdf", single=False)
        self.panel.changed.connect(self._on_files)
        self.panel.list.itemSelectionChanged.connect(self._refresh_preview)
        lay.addWidget(self.panel, 3)
        pv = QFrame()
        pv.setObjectName("card")
        pl = QVBoxLayout(pv)
        pl.addWidget(QLabel("Preview"))
        self.preview = QLabel("Select a file to preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(220, 260)
        pl.addWidget(self.preview, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Page:"))
        self.prev_page = QSpinBox()
        self.prev_page.setMinimum(1)
        self.prev_page.valueChanged.connect(self._refresh_preview)
        row.addWidget(self.prev_page)
        row.addStretch(1)
        pl.addLayout(row)
        self.size_lbl = hint("")
        pl.addWidget(self.size_lbl)
        lay.addWidget(pv, 2)
        return w

    def build_options(self, layout: QVBoxLayout) -> None:
        self.fmt = QComboBox()
        self.fmt.addItems(FORMATS)
        self.fmt.setCurrentText(self.settings.get("image_format"))
        self.fmt.currentTextChanged.connect(self._fmt_changed)
        layout.addWidget(labeled("Format:", self.fmt))
        self.dpi = QComboBox()
        self.dpi.addItems([f"{d} DPI" for d in DPI_CHOICES])
        self.dpi.setCurrentText(f"{self.settings.get('image_dpi')} DPI")
        self.dpi.currentIndexChanged.connect(self._refresh_preview)
        layout.addWidget(labeled("Resolution:", self.dpi))
        self.qlabel = QLabel("JPG quality: 85")
        self.quality = QSlider(Qt.Horizontal)
        self.quality.setRange(10, 100)
        self.quality.setValue(85)
        self.quality.valueChanged.connect(lambda v: self.qlabel.setText(f"JPG quality: {v}"))
        layout.addWidget(self.qlabel)
        layout.addWidget(self.quality)
        self.r_all = QRadioButton("All pages")
        self.r_sel = QRadioButton("Selected pages")
        self.r_all.setChecked(True)
        layout.addWidget(self.r_all)
        layout.addWidget(self.r_sel)
        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText("e.g. 1-3, 5")
        self.pages_edit.textEdited.connect(lambda _: self.r_sel.setChecked(True))
        layout.addWidget(self.pages_edit)
        layout.addWidget(hint("With several PDFs, each gets its own sub-folder. Files are named with page numbers; "
                              "existing images are never overwritten."))
        self._fmt_changed(self.fmt.currentText())

    def apply_preset(self, **kw) -> None:
        if "format" in kw:
            self.fmt.setCurrentText(kw["format"])

    def _fmt_changed(self, f: str) -> None:
        jpg = f == "JPG"
        self.quality.setVisible(jpg)
        self.qlabel.setVisible(jpg)

    def _current_dpi(self) -> int:
        return DPI_CHOICES[self.dpi.currentIndex()]

    def _on_files(self) -> None:
        first = self.panel.first_path()
        self.default_dir_from(first)
        if first and not self.panel.list.selectedItems():
            self.panel.list.setCurrentRow(0)
        self._refresh_preview()

    def _refresh_preview(self, *_) -> None:
        sel = self.panel.list.selected_paths()
        path = sel[0] if sel else self.panel.first_path()
        if not path:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Select a file to preview")
            self.size_lbl.setText("")
            return
        try:
            doc = open_pdf(path, self.panel.passwords.get(path))
        except Exception:
            self.preview.setText("Preview not available")
            return
        try:
            n = doc.page_count
            self.prev_page.setMaximum(n)
            pno = min(self.prev_page.value(), n) - 1
            page = doc[pno]
            dpi = self._current_dpi()
            w_px, h_px = int(page.rect.width * dpi / 72), int(page.rect.height * dpi / 72)
            self.size_lbl.setText(f"Output size: {w_px} × {h_px} px (preview is scaled down)")
            pix = render_pixmap(page, 60)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            self.preview.setPixmap(QPixmap.fromImage(img).scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        finally:
            doc.close()

    def prepare(self):
        files = self.panel.paths()
        if not files:
            raise ValueError("Add at least one PDF file.")
        self._check_folder()
        page_text = None
        if self.r_sel.isChecked():
            page_text = self.pages_edit.text().strip()
            if not page_text:
                raise ValueError("Enter the pages to export, or choose 'All pages'.")
            for p in files:  # validate against each document up-front
                d = open_pdf(p, self.panel.passwords.get(p))
                try:
                    parse_page_ranges(page_text, d.page_count)
                except ValueError as e:
                    raise ValueError(f"{os.path.basename(p)}: {e}") from None
                finally:
                    d.close()
        dpi = self._current_dpi()
        # rough disk estimate: 1 MB per page at 150 dpi scaled by dpi^2
        pages = sum(self.panel.list.page_counts().values())
        try:
            check_disk_space(self.out_dir(), int(pages * 0.5e6 * (dpi / 150) ** 2))
        except ProcessingError as e:
            raise ValueError(str(e)) from None
        return export_images, dict(pdfs=files, out_dir=self.out_dir(), fmt=self.fmt.currentText(), dpi=dpi,
                                   quality=self.quality.value(), page_text=page_text,
                                   passwords=dict(self.panel.passwords))

    def result_paths(self, result):
        return [os.path.dirname(result.files[0])] if result.files else []

    def describe_result(self, result) -> str:
        return f"Exported {result.pages_exported} image(s) to {os.path.dirname(result.files[0])}."

    def reset_options(self) -> None:
        self.fmt.setCurrentText(self.settings.get("image_format"))
        self.dpi.setCurrentText(f"{self.settings.get('image_dpi')} DPI")
        self.quality.setValue(85)
        self.r_all.setChecked(True)
        self.pages_edit.clear()

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class ImageToPdfPage(ToolPage):
    TOOL_ID = "img2pdf"
    TITLE = "Image to PDF"
    DESC = "Combine JPG, PNG, BMP and TIFF images into one PDF. Drag to reorder."
    START_TEXT = "Create PDF"
    NEEDS_FILENAME = True
    WORKER_CLASS = ConversionWorker

    def build_input(self) -> QWidget:
        self.panel = FilePanel("image", single=False)
        self.panel.changed.connect(self._on_files)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.size = QComboBox()
        self.size.addItems(["A4", "Letter", "Legal", "Original image size"])
        self.size.currentIndexChanged.connect(self._size_changed)
        layout.addWidget(labeled("Page size:", self.size))
        self.orient = QComboBox()
        self.orient.addItems(["Auto (match image)", "Portrait", "Landscape"])
        layout.addWidget(labeled("Orientation:", self.orient))
        self.fit = QComboBox()
        self.fit.addItems(["Fit to page (keep aspect ratio)", "Stretch to page", "Original size (shrink if too big)"])
        layout.addWidget(self.fit)
        self.margin = QDoubleSpinBox()
        self.margin.setRange(0, 100)
        self.margin.setValue(10)
        self.margin.setSuffix(" mm")
        layout.addWidget(labeled("Margin:", self.margin))
        layout.addWidget(hint("All images are combined into a single PDF, one image per page, in list order. "
                              "Multi-page TIFFs add every frame."))

    def apply_preset(self, **kw) -> None:
        pass

    def _size_changed(self) -> None:
        self.orient.setEnabled(self.size.currentIndex() != 3)

    def _on_files(self) -> None:
        first = self.panel.first_path()
        if first and self.name_edit and not self.name_edit.text():
            self.name_edit.setText("images.pdf")
        self.default_dir_from(first)

    def prepare(self):
        files = self.panel.paths()
        if not files:
            raise ValueError("Add at least one image.")
        out = self.output_file(".pdf", files)
        self.check_space(files, 1.2)
        size = ["A4", "Letter", "Legal", "Original"][self.size.currentIndex()]
        orient = ["auto", "portrait", "landscape"][self.orient.currentIndex()]
        fit = ["fit", "stretch", "original"][self.fit.currentIndex()]
        return images_to_pdf, dict(images=files, output=out, page_size=size, orientation=orient,
                                   margin_mm=self.margin.value(), fit=fit)

    def describe_result(self, result) -> str:
        d = fitz.open(result)
        n = d.page_count
        d.close()
        return f"Created {os.path.basename(result)} with {n} page(s)."

    def reset_options(self) -> None:
        self.size.setCurrentIndex(0)
        self.orient.setCurrentIndex(0)
        self.fit.setCurrentIndex(0)
        self.margin.setValue(10)

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class PdfToWordPage(ToolPage):
    TOOL_ID = "pdf2docx"
    TITLE = "PDF to Word (.docx)"
    DESC = "Convert a PDF into an editable Word document preserving headings, font styling, tables, and embedded images."
    START_TEXT = "Convert to Word"
    NEEDS_FILENAME = True
    WORKER_CLASS = ConversionWorker

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.inc_img = QCheckBox("Include embedded images")
        self.inc_img.setChecked(True)
        layout.addWidget(self.inc_img)
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("all (or e.g. 1-5)")
        layout.addWidget(labeled("Pages:", self.pages))
        layout.addWidget(hint(
            "Limitation note: Complex multi-column layouts are linearized in reading order, "
            "nonstandard embedded fonts map to standard Word fonts, and scanned image-only pages "
            "are inserted as images unless OCR is run first."
        ))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + ".docx")

    def prepare(self):
        from core.office_convert import pdf_to_docx

        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        out = self.output_file(".docx", [src])
        return pdf_to_docx, dict(
            src=src,
            output=out,
            include_images=self.inc_img.isChecked(),
            page_text=self.pages.text().strip() or None,
            password=self.panel.passwords.get(src),
        )

    def result_paths(self, result):
        return [result.output]

    def describe_result(self, result) -> str:
        msg = f"Saved Word document {os.path.basename(result.output)} ({result.pages_or_items} page(s))."
        return f"{msg} {result.note}" if result.note else msg

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class PdfToExcelPage(ToolPage):
    TOOL_ID = "pdf2xlsx"
    TITLE = "PDF to Excel (.xlsx)"
    DESC = "Extract tables and structured columnar data from PDF pages into an Excel workbook."
    START_TEXT = "Convert to Excel"
    NEEDS_FILENAME = True
    WORKER_CLASS = ConversionWorker

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("all (or e.g. 1-3)")
        layout.addWidget(labeled("Pages:", self.pages))
        layout.addWidget(hint(
            "Each detected table is exported to its own worksheet tab. "
            "If a page has no ruled borders, rows are reconstructed from word alignment."
        ))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + ".xlsx")

    def prepare(self):
        from core.office_convert import pdf_to_xlsx

        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        out = self.output_file(".xlsx", [src])
        return pdf_to_xlsx, dict(
            src=src,
            output=out,
            page_text=self.pages.text().strip() or None,
            password=self.panel.passwords.get(src),
        )

    def result_paths(self, result):
        return [result.output]

    def describe_result(self, result) -> str:
        msg = f"Saved Excel workbook {os.path.basename(result.output)}."
        return f"{msg} {result.note}" if result.note else msg

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class PdfToPptxPage(ToolPage):
    TOOL_ID = "pdf2pptx"
    TITLE = "PDF to PowerPoint (.pptx)"
    DESC = "Convert PDF pages into a PowerPoint presentation (one slide per page, plus selectable text in speaker notes)."
    START_TEXT = "Convert to PowerPoint"
    NEEDS_FILENAME = True
    WORKER_CLASS = ConversionWorker

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.dpi = QComboBox()
        self.dpi.addItems(["150", "200", "300"])
        layout.addWidget(labeled("Slide DPI:", self.dpi))
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("all (or e.g. 1-10)")
        layout.addWidget(labeled("Pages:", self.pages))
        layout.addWidget(hint("Matches the PDF page aspect ratio and places page text into slide notes."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + ".pptx")

    def prepare(self):
        from core.office_convert import pdf_to_pptx

        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        out = self.output_file(".pptx", [src])
        return pdf_to_pptx, dict(
            src=src,
            output=out,
            dpi=int(self.dpi.currentText()),
            page_text=self.pages.text().strip() or None,
            password=self.panel.passwords.get(src),
        )

    def result_paths(self, result):
        return [result.output]

    def describe_result(self, result) -> str:
        return f"Saved presentation {os.path.basename(result.output)} ({result.pages_or_items} slide(s))."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class OfficeToPdfPage(ToolPage):
    TOOL_ID = "office2pdf"
    TITLE = "Office to PDF (Word / Excel / PowerPoint)"
    DESC = "Convert .docx, .xlsx and .pptx documents to PDF offline (uses LibreOffice headless mode when installed, with a built-in pure-Python fallback)."
    START_TEXT = "Convert to PDF"
    NEEDS_FILENAME = True
    WORKER_CLASS = ConversionWorker

    def build_input(self) -> QWidget:
        self.panel = FilePanel("office", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        from core.office_convert import find_libreoffice

        lo = find_libreoffice()
        self.lo_edit = QLineEdit(lo or "")
        self.lo_edit.setPlaceholderText("Optional: path to soffice.exe (LibreOffice)")
        layout.addWidget(labeled("LibreOffice:", self.lo_edit))
        if lo:
            layout.addWidget(hint(f"✔ LibreOffice detected at:\n{lo}"))
        else:
            layout.addWidget(hint(
                "ℹ LibreOffice was not found on PATH; conversions will use the built-in offline Python renderer. "
                "Install LibreOffice for 100% native Office layout rendering."
            ))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + ".pdf")

    def prepare(self):
        from core.office_convert import office_to_pdf

        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a Word (.docx), Excel (.xlsx), or PowerPoint (.pptx) file first.")
        out = self.output_file(".pdf", [src])
        return office_to_pdf, dict(
            src=src,
            output=out,
            libreoffice_path=self.lo_edit.text().strip(),
        )

    def result_paths(self, result):
        return [result.output]

    def describe_result(self, result) -> str:
        return f"Created {os.path.basename(result.output)} ({result.pages_or_items} page(s)). {result.note}"

    def clear_input(self) -> None:
        self.panel.list.clear_all()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main(start_tool='pdf2img'))
