"""Phase 2 - PDF Editing UI pages:
Page Numbers, Headers & Footers, Watermark (Text/Image), Annotate & Content, Crop Pages, Edit Metadata."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.pdf_edit import (
    NAMED_COLORS,
    add_header_footer,
    add_image_watermark,
    add_page_numbers,
    add_text_watermark,
    annotate_pdf,
    crop_pdf,
    edit_metadata,
    read_metadata,
)
from ui.components.file_list import IMAGE_FILTER, FilePanel
from ui.components.page_canvas import PagePreviewCard
from ui.components.tool_page import ToolPage
from ui.components.widgets import hint, labeled


def _with_preview(panel: FilePanel, preview: PagePreviewCard) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(panel, 3)
    lay.addWidget(preview, 2)
    return w


class PageNumbersPage(ToolPage):
    TOOL_ID = "page_numbers"
    TITLE = "Add Page Numbers"
    DESC = "Stamp customizable page numbers onto your PDF pages."
    START_TEXT = "Add page numbers"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.preview_card = PagePreviewCard()
        self.panel.changed.connect(self._on_file)
        return _with_preview(self.panel, self.preview_card)

    def build_options(self, layout: QVBoxLayout) -> None:
        self.pos = QComboBox()
        self.pos.addItems(["bottom-center", "bottom-right", "bottom-left", "top-center", "top-right", "top-left"])
        layout.addWidget(labeled("Position:", self.pos))
        self.fmt = QComboBox()
        self.fmt.setEditable(True)
        self.fmt.addItems(["Page {n} of {total}", "{n} / {total}", "{n}", "- {n} -"])
        layout.addWidget(labeled("Format:", self.fmt))
        self.start_page = QSpinBox()
        self.start_page.setRange(1, 99999)
        self.start_page.setValue(1)
        layout.addWidget(labeled("Start at page:", self.start_page))
        self.start_num = QSpinBox()
        self.start_num.setRange(1, 99999)
        self.start_num.setValue(1)
        layout.addWidget(labeled("First number:", self.start_num))
        self.fsize = QDoubleSpinBox()
        self.fsize.setRange(6.0, 36.0)
        self.fsize.setValue(10.5)
        self.fsize.setSuffix(" pt")
        layout.addWidget(labeled("Font size:", self.fsize))
        self.margin = QDoubleSpinBox()
        self.margin.setRange(3.0, 50.0)
        self.margin.setValue(10.0)
        self.margin.setSuffix(" mm")
        layout.addWidget(labeled("Margin:", self.margin))
        self.color = QComboBox()
        self.color.addItems(list(NAMED_COLORS.keys()))
        self.color.setCurrentText("Dark Gray")
        layout.addWidget(labeled("Color:", self.color))
        layout.addWidget(hint("Use {n} for the current number and {total} for the total page count."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        self.preview_card.set_document(p, self.panel.passwords.get(p) if p else None)
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_numbered.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        out = self.output_file(".pdf", [src])
        return add_page_numbers, dict(
            src=src,
            output=out,
            position=self.pos.currentText(),
            fmt=self.fmt.currentText(),
            start_page=self.start_page.value(),
            start_number=self.start_num.value(),
            fontsize=self.fsize.value(),
            margin_mm=self.margin.value(),
            color_name=self.color.currentText(),
            password=self.panel.passwords.get(src),
        )

    def describe_result(self, result) -> str:
        return f"Saved numbered PDF as {os.path.basename(result)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class HeaderFooterPage(ToolPage):
    TOOL_ID = "header_footer"
    TITLE = "Headers & Footers"
    DESC = "Add left, center or right headers and footers with dynamic page numbers and dates."
    START_TEXT = "Apply header & footer"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.preview_card = PagePreviewCard()
        self.panel.changed.connect(self._on_file)
        return _with_preview(self.panel, self.preview_card)

    def build_options(self, layout: QVBoxLayout) -> None:
        self.hl = QLineEdit(); self.hl.setPlaceholderText("Left header")
        self.hc = QLineEdit(); self.hc.setPlaceholderText("Center header")
        self.hr = QLineEdit(); self.hr.setPlaceholderText("Right header")
        self.fl = QLineEdit(); self.fl.setPlaceholderText("Left footer")
        self.fc = QLineEdit(); self.fc.setPlaceholderText("Center footer (e.g. Page {page} of {total})")
        self.fr = QLineEdit(); self.fr.setPlaceholderText("Right footer (e.g. {date})")
        for lbl, w in (
            ("Header left:", self.hl), ("Header center:", self.hc), ("Header right:", self.hr),
            ("Footer left:", self.fl), ("Footer center:", self.fc), ("Footer right:", self.fr),
        ):
            layout.addWidget(labeled(lbl, w))
        self.fsize = QDoubleSpinBox(); self.fsize.setRange(6.0, 28.0); self.fsize.setValue(10.0); self.fsize.setSuffix(" pt")
        layout.addWidget(labeled("Font size:", self.fsize))
        self.margin = QDoubleSpinBox(); self.margin.setRange(4.0, 50.0); self.margin.setValue(10.0); self.margin.setSuffix(" mm")
        layout.addWidget(labeled("Margin:", self.margin))
        self.color = QComboBox(); self.color.addItems(list(NAMED_COLORS.keys())); self.color.setCurrentText("Dark Gray")
        layout.addWidget(labeled("Color:", self.color))
        self.pages = QLineEdit(); self.pages.setPlaceholderText("all (or e.g. 1-3, 5)")
        layout.addWidget(labeled("Pages:", self.pages))
        layout.addWidget(hint("Supported placeholders: {page}, {total}, {date}."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        self.preview_card.set_document(p, self.panel.passwords.get(p) if p else None)
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_header_footer.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        if not any(w.text().strip() for w in (self.hl, self.hc, self.hr, self.fl, self.fc, self.fr)):
            raise ValueError("Enter at least one header or footer field.")
        out = self.output_file(".pdf", [src])
        return add_header_footer, dict(
            src=src,
            output=out,
            header_left=self.hl.text(),
            header_center=self.hc.text(),
            header_right=self.hr.text(),
            footer_left=self.fl.text(),
            footer_center=self.fc.text(),
            footer_right=self.fr.text(),
            fontsize=self.fsize.value(),
            margin_mm=self.margin.value(),
            color_name=self.color.currentText(),
            page_text=self.pages.text().strip() or None,
            password=self.panel.passwords.get(src),
        )

    def describe_result(self, result) -> str:
        return f"Headers and footers applied to {os.path.basename(result)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class WatermarkPage(ToolPage):
    TOOL_ID = "watermark"
    TITLE = "Watermark PDF"
    DESC = "Stamp a text or image watermark across your PDF with custom opacity, rotation and placement."
    START_TEXT = "Add watermark"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.preview_card = PagePreviewCard()
        self.panel.changed.connect(self._on_file)
        return _with_preview(self.panel, self.preview_card)

    def build_options(self, layout: QVBoxLayout) -> None:
        self.r_text = QRadioButton("Text watermark")
        self.r_img = QRadioButton("Image watermark")
        self.r_text.setChecked(True)
        self.r_text.toggled.connect(self._toggle_kind)
        layout.addWidget(self.r_text)
        layout.addWidget(self.r_img)

        self.w_text = QWidget()
        tl = QVBoxLayout(self.w_text); tl.setContentsMargins(0, 0, 0, 0)
        self.text_edit = QLineEdit("CONFIDENTIAL")
        tl.addWidget(labeled("Text:", self.text_edit))
        self.fsize = QDoubleSpinBox(); self.fsize.setRange(12.0, 140.0); self.fsize.setValue(48.0); self.fsize.setSuffix(" pt")
        tl.addWidget(labeled("Font size:", self.fsize))
        self.angle = QComboBox(); self.angle.addItems(["45", "-45", "0", "90"])
        tl.addWidget(labeled("Angle (°):", self.angle))
        self.color = QComboBox(); self.color.addItems(list(NAMED_COLORS.keys())); self.color.setCurrentText("Red")
        tl.addWidget(labeled("Color:", self.color))
        self.tiled = QCheckBox("Tile (repeat across page)")
        tl.addWidget(self.tiled)
        layout.addWidget(self.w_text)

        self.w_img = QWidget()
        il = QVBoxLayout(self.w_img); il.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.img_path = QLineEdit(); self.img_path.setPlaceholderText("Watermark image…")
        b_img = QPushButton("Browse…")
        b_img.clicked.connect(self._browse_img)
        row.addWidget(self.img_path, 1); row.addWidget(b_img)
        il.addLayout(row)
        self.img_scale = QSpinBox(); self.img_scale.setRange(10, 90); self.img_scale.setValue(35); self.img_scale.setSuffix(" %")
        il.addWidget(labeled("Width % of page:", self.img_scale))
        self.img_pos = QComboBox(); self.img_pos.addItems(["center", "top-right", "top-left", "bottom-right", "bottom-left"])
        il.addWidget(labeled("Position:", self.img_pos))
        self.w_img.setVisible(False)
        layout.addWidget(self.w_img)

        self.op_lbl = QLabel("Opacity: 25%")
        self.opacity = QSlider(Qt.Horizontal); self.opacity.setRange(5, 100); self.opacity.setValue(25)
        self.opacity.valueChanged.connect(lambda v: self.op_lbl.setText(f"Opacity: {v}%"))
        layout.addWidget(self.op_lbl)
        layout.addWidget(self.opacity)
        self.underlay = QCheckBox("Place behind page content (underlay)")
        layout.addWidget(self.underlay)
        self.pages = QLineEdit(); self.pages.setPlaceholderText("all (or e.g. 1-3, 5)")
        layout.addWidget(labeled("Pages:", self.pages))

    def _toggle_kind(self) -> None:
        is_txt = self.r_text.isChecked()
        self.w_text.setVisible(is_txt)
        self.w_img.setVisible(not is_txt)

    def _browse_img(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Select watermark image", "", IMAGE_FILTER)
        if f:
            self.img_path.setText(f)

    def _on_file(self) -> None:
        p = self.panel.first_path()
        self.preview_card.set_document(p, self.panel.passwords.get(p) if p else None)
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_watermarked.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        out = self.output_file(".pdf", [src])
        pw = self.panel.passwords.get(src)
        pg = self.pages.text().strip() or None
        op = self.opacity.value() / 100.0
        if self.r_text.isChecked():
            txt = self.text_edit.text().strip()
            if not txt:
                raise ValueError("Enter watermark text.")
            return add_text_watermark, dict(
                src=src, output=out, text=txt, fontsize=self.fsize.value(),
                angle=float(self.angle.currentText()), opacity=op, color_name=self.color.currentText(),
                tiled=self.tiled.isChecked(), underlay=self.underlay.isChecked(), page_text=pg, password=pw,
            )
        img = self.img_path.text().strip()
        if not img:
            raise ValueError("Choose a watermark image file.")
        return add_image_watermark, dict(
            src=src, output=out, image_path=img, scale=self.img_scale.value() / 100.0,
            opacity=op, position=self.img_pos.currentText(), underlay=self.underlay.isChecked(),
            page_text=pg, password=pw,
        )

    def describe_result(self, result) -> str:
        return f"Watermarked PDF saved as {os.path.basename(result)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class AnnotatePage(ToolPage):
    TOOL_ID = "annotate"
    TITLE = "Edit & Annotate PDF"
    DESC = "Add text boxes, insert images, highlight or underline text, draw shapes, or add freehand ink annotations."
    START_TEXT = "Apply to PDF"
    NEEDS_FILENAME = True

    MODES = [
        ("Add Text Box", "add_text"),
        ("Insert Image", "add_image"),
        ("Highlight Text", "highlight"),
        ("Underline Text", "underline"),
        ("Add Shape (Rectangle / Circle / Line)", "shape"),
        ("Draw Freehand / Ink Annotation", "freehand"),
    ]

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.preview_card = PagePreviewCard(interactive_rect=True)
        self.preview_card.rect_selected.connect(self._on_rect_dragged)
        self.panel.changed.connect(self._on_file)
        return _with_preview(self.panel, self.preview_card)

    def build_options(self, layout: QVBoxLayout) -> None:
        self.mode_box = QComboBox()
        for label, _ in self.MODES:
            self.mode_box.addItem(label)
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        layout.addWidget(labeled("Action:", self.mode_box))

        self.text_lbl = QLabel("Text content / note:")
        self.text_box = QPlainTextEdit()
        self.text_box.setPlaceholderText("Enter text to insert on the page…")
        self.text_box.setMaximumHeight(75)
        layout.addWidget(self.text_lbl)
        layout.addWidget(self.text_box)

        self.search_w = QWidget()
        sl = QVBoxLayout(self.search_w); sl.setContentsMargins(0, 0, 0, 0)
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Word or phrase to highlight/underline")
        sl.addWidget(labeled("Find text:", self.search_edit))
        layout.addWidget(self.search_w)

        self.img_w = QWidget()
        il = QHBoxLayout(self.img_w); il.setContentsMargins(0, 0, 0, 0)
        self.img_edit = QLineEdit(); self.img_edit.setPlaceholderText("Image to insert…")
        b_img = QPushButton("Browse…")
        b_img.clicked.connect(self._browse_img)
        il.addWidget(self.img_edit, 1); il.addWidget(b_img)
        layout.addWidget(self.img_w)

        self.shape_w = QWidget()
        shl = QVBoxLayout(self.shape_w); shl.setContentsMargins(0, 0, 0, 0)
        self.shape_kind = QComboBox(); self.shape_kind.addItems(["rect", "circle", "line"])
        shl.addWidget(labeled("Shape:", self.shape_kind))
        layout.addWidget(self.shape_w)

        self.geom_w = QWidget()
        gl = QVBoxLayout(self.geom_w); gl.setContentsMargins(0, 0, 0, 0)
        self.x_mm = QDoubleSpinBox(); self.x_mm.setRange(0, 500); self.x_mm.setValue(25); self.x_mm.setSuffix(" mm")
        self.y_mm = QDoubleSpinBox(); self.y_mm.setRange(0, 500); self.y_mm.setValue(25); self.y_mm.setSuffix(" mm")
        self.w_mm = QDoubleSpinBox(); self.w_mm.setRange(10, 500); self.w_mm.setValue(90); self.w_mm.setSuffix(" mm")
        self.h_mm = QDoubleSpinBox(); self.h_mm.setRange(10, 500); self.h_mm.setValue(35); self.h_mm.setSuffix(" mm")
        for sb in (self.x_mm, self.y_mm, self.w_mm, self.h_mm):
            sb.valueChanged.connect(self._sync_box_to_preview)
        gl.addWidget(labeled("X position:", self.x_mm))
        gl.addWidget(labeled("Y position:", self.y_mm))
        gl.addWidget(labeled("Width:", self.w_mm))
        gl.addWidget(labeled("Height:", self.h_mm))
        layout.addWidget(self.geom_w)
        self._sync_box_to_preview()

        self.fsize = QDoubleSpinBox(); self.fsize.setRange(6, 72); self.fsize.setValue(12); self.fsize.setSuffix(" pt")
        layout.addWidget(labeled("Font size:", self.fsize))
        self.color = QComboBox(); self.color.addItems(list(NAMED_COLORS.keys())); self.color.setCurrentText("Red")
        layout.addWidget(labeled("Color:", self.color))
        self.pages = QLineEdit(); self.pages.setPlaceholderText("all (or e.g. 1, 3-5)")
        layout.addWidget(labeled("Pages:", self.pages))
        self._mode_changed()

    def _mode_changed(self) -> None:
        m = self.MODES[self.mode_box.currentIndex()][1]
        self.text_lbl.setVisible(m in ("add_text", "freehand"))
        self.text_box.setVisible(m in ("add_text", "freehand"))
        self.search_w.setVisible(m in ("highlight", "underline"))
        self.img_w.setVisible(m == "add_image")
        self.shape_w.setVisible(m == "shape")
        self.geom_w.setVisible(m in ("add_text", "add_image", "shape", "freehand"))
        if m == "highlight":
            self.color.setCurrentText("Yellow")

    def _browse_img(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Select image", "", IMAGE_FILTER)
        if f:
            self.img_edit.setText(f)

    def _on_rect_dragged(self, x: float, y: float, w: float, h: float) -> None:
        for sb, val in ((self.x_mm, x), (self.y_mm, y), (self.w_mm, max(10.0, w)), (self.h_mm, max(10.0, h))):
            sb.blockSignals(True)
            sb.setValue(val)
            sb.blockSignals(False)

    def _sync_box_to_preview(self) -> None:
        if hasattr(self, "preview_card"):
            self.preview_card.canvas.set_box_mm(self.x_mm.value(), self.y_mm.value(), self.w_mm.value(), self.h_mm.value())

    def _on_file(self) -> None:
        p = self.panel.first_path()
        self.preview_card.set_document(p, self.panel.passwords.get(p) if p else None)
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_annotated.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        m = self.MODES[self.mode_box.currentIndex()][1]
        if m == "add_text" and not self.text_box.toPlainText().strip():
            raise ValueError("Enter the text you want to add.")
        if m in ("highlight", "underline") and not self.search_edit.text().strip():
            raise ValueError("Enter the word or phrase to highlight/underline.")
        if m == "add_image" and not self.img_edit.text().strip():
            raise ValueError("Choose an image file to insert.")
        out = self.output_file(".pdf", [src])
        return annotate_pdf, dict(
            src=src,
            output=out,
            mode=m,
            text=self.text_box.toPlainText(),
            search_text=self.search_edit.text(),
            image_path=self.img_edit.text().strip(),
            shape_kind=self.shape_kind.currentText(),
            x_mm=self.x_mm.value(),
            y_mm=self.y_mm.value(),
            width_mm=self.w_mm.value(),
            height_mm=self.h_mm.value(),
            fontsize=self.fsize.value(),
            color_name=self.color.currentText(),
            page_text=self.pages.text().strip() or None,
            password=self.panel.passwords.get(src),
        )

    def result_paths(self, result):
        return [result[0]]

    def describe_result(self, result) -> str:
        path, count = result
        return f"Applied {count} edit/annotation item(s) → {os.path.basename(path)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class CropPage(ToolPage):
    TOOL_ID = "crop"
    TITLE = "Crop PDF Pages"
    DESC = "Trim top, bottom, left and right margins from all or selected pages."
    START_TEXT = "Crop PDF"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.preview_card = PagePreviewCard(crop_mode=True)
        self.preview_card.crop_selected.connect(self._on_crop_dragged)
        self.panel.changed.connect(self._on_file)
        return _with_preview(self.panel, self.preview_card)

    def build_options(self, layout: QVBoxLayout) -> None:
        self.top = QDoubleSpinBox(); self.top.setRange(0, 200); self.top.setValue(10); self.top.setSuffix(" mm")
        self.bottom = QDoubleSpinBox(); self.bottom.setRange(0, 200); self.bottom.setValue(10); self.bottom.setSuffix(" mm")
        self.left = QDoubleSpinBox(); self.left.setRange(0, 200); self.left.setValue(10); self.left.setSuffix(" mm")
        self.right = QDoubleSpinBox(); self.right.setRange(0, 200); self.right.setValue(10); self.right.setSuffix(" mm")
        for lbl, w in (("Top margin:", self.top), ("Bottom margin:", self.bottom),
                       ("Left margin:", self.left), ("Right margin:", self.right)):
            w.valueChanged.connect(self._sync_crop_to_preview)
            layout.addWidget(labeled(lbl, w))
        self.pages = QLineEdit(); self.pages.setPlaceholderText("all (or e.g. 1-3, 5)")
        layout.addWidget(labeled("Pages:", self.pages))
        layout.addWidget(hint("Drag on the page preview or use the spinboxes to trim margins from each edge."))
        self._sync_crop_to_preview()

    def _on_crop_dragged(self, top: float, bottom: float, left: float, right: float) -> None:
        for sb, val in ((self.top, top), (self.bottom, bottom), (self.left, left), (self.right, right)):
            sb.blockSignals(True)
            sb.setValue(val)
            sb.blockSignals(False)

    def _sync_crop_to_preview(self) -> None:
        if hasattr(self, "preview_card"):
            self.preview_card.canvas.set_crop_mm(self.top.value(), self.bottom.value(), self.left.value(), self.right.value())

    def _on_file(self) -> None:
        p = self.panel.first_path()
        self.preview_card.set_document(p, self.panel.passwords.get(p) if p else None)
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_cropped.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        if all(w.value() <= 0 for w in (self.top, self.bottom, self.left, self.right)):
            raise ValueError("Set at least one positive crop margin.")
        out = self.output_file(".pdf", [src])
        return crop_pdf, dict(
            src=src, output=out,
            top_mm=self.top.value(), bottom_mm=self.bottom.value(),
            left_mm=self.left.value(), right_mm=self.right.value(),
            page_text=self.pages.text().strip() or None,
            password=self.panel.passwords.get(src),
        )

    def describe_result(self, result) -> str:
        return f"Cropped PDF saved as {os.path.basename(result)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


class MetadataPage(ToolPage):
    TOOL_ID = "metadata"
    TITLE = "Edit PDF Metadata"
    DESC = "Inspect, modify or strip document properties (Title, Author, Subject, Keywords, Creator, Producer)."
    START_TEXT = "Save metadata"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.fields: dict[str, QLineEdit] = {}
        for key in ("title", "author", "subject", "keywords", "creator", "producer"):
            e = QLineEdit()
            self.fields[key] = e
            layout.addWidget(labeled(key.capitalize() + ":", e))
        self.clear_chk = QCheckBox("Strip all metadata and XMP properties")
        layout.addWidget(self.clear_chk)
        layout.addWidget(hint("When you select a PDF, its current metadata is loaded automatically."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_metadata.pdf")
            try:
                md = read_metadata(p, self.panel.passwords.get(p))
                for k, e in self.fields.items():
                    e.setText(md.get(k, ""))
            except Exception:
                pass
        else:
            for e in self.fields.values():
                e.clear()

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        out = self.output_file(".pdf", [src])
        md = {k: e.text() for k, e in self.fields.items()}
        return edit_metadata, dict(
            src=src, output=out, metadata=md,
            clear_all=self.clear_chk.isChecked(),
            password=self.panel.passwords.get(src),
        )

    def describe_result(self, result) -> str:
        return f"Saved updated metadata to {os.path.basename(result)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main(start_tool='annotate'))
