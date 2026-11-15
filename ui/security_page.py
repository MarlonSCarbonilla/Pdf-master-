"""Phase 2 - PDF Security UI pages:
Protect PDF (password & permissions), Unlock PDF, Redact PDF (with verification), Sign PDF."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.pdf_security import RedactResult, protect_pdf, redact_pdf, sign_pdf, unlock_pdf
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


class ProtectPage(ToolPage):
    TOOL_ID = "protect"
    TITLE = "Protect PDF"
    DESC = "Encrypt a PDF with AES-256 password protection and configure document permissions."
    START_TEXT = "Protect PDF"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.user_pw = QLineEdit()
        self.user_pw.setEchoMode(QLineEdit.Password)
        self.user_pw.setPlaceholderText("Required to open document")
        layout.addWidget(labeled("User password:", self.user_pw))

        self.user_pw2 = QLineEdit()
        self.user_pw2.setEchoMode(QLineEdit.Password)
        self.user_pw2.setPlaceholderText("Confirm user password")
        layout.addWidget(labeled("Confirm:", self.user_pw2))

        self.owner_pw = QLineEdit()
        self.owner_pw.setEchoMode(QLineEdit.Password)
        self.owner_pw.setPlaceholderText("Optional: permissions password")
        layout.addWidget(labeled("Owner password:", self.owner_pw))

        layout.addWidget(QLabel("Allowed permissions:"))
        self.p_print = QCheckBox("Allow printing")
        self.p_print.setChecked(True)
        self.p_copy = QCheckBox("Allow copying text and graphics")
        self.p_modify = QCheckBox("Allow modifying document")
        self.p_annot = QCheckBox("Allow annotations and form filling")
        self.p_annot.setChecked(True)
        for c in (self.p_print, self.p_copy, self.p_modify, self.p_annot):
            layout.addWidget(c)
        layout.addWidget(hint("Uses strong 256-bit AES encryption. Keep your password safe; it cannot be recovered if lost."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_protected.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        upw = self.user_pw.text()
        opw = self.owner_pw.text()
        if not upw and not opw:
            raise ValueError("Enter a user password or an owner password.")
        if upw and upw != self.user_pw2.text():
            raise ValueError("User password confirmation does not match.")
        out = self.output_file(".pdf", [src])
        return protect_pdf, dict(
            src=src,
            output=out,
            user_password=upw,
            owner_password=opw,
            allow_print=self.p_print.isChecked(),
            allow_modify=self.p_modify.isChecked(),
            allow_copy=self.p_copy.isChecked(),
            allow_annotate=self.p_annot.isChecked(),
            current_password=self.panel.passwords.get(src),
        )

    def describe_result(self, result) -> str:
        return f"Encrypted PDF saved as {os.path.basename(result)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()
        self.user_pw.clear()
        self.user_pw2.clear()
        self.owner_pw.clear()


class UnlockPage(ToolPage):
    TOOL_ID = "unlock"
    TITLE = "Unlock PDF"
    DESC = "Remove password protection from a PDF when you have the authorized password."
    START_TEXT = "Unlock PDF"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf_raw", single=True)
        self.panel.changed.connect(self._on_file)
        return self.panel

    def build_options(self, layout: QVBoxLayout) -> None:
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("Enter current PDF password")
        layout.addWidget(labeled("Password:", self.pw))
        layout.addWidget(hint("You must know the document's valid password to remove its encryption."))

    def _on_file(self) -> None:
        p = self.panel.first_path()
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_unlocked.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a password-protected PDF file first.")
        pw = self.pw.text() or self.panel.passwords.get(src, "")
        if not pw:
            raise ValueError("Enter the PDF password to unlock the file.")
        out = self.output_file(".pdf", [src])
        return unlock_pdf, dict(src=src, output=out, password=pw)

    def describe_result(self, result) -> str:
        return f"Unlocked PDF saved as {os.path.basename(result)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()
        self.pw.clear()


class RedactPage(ToolPage):
    TOOL_ID = "redact"
    TITLE = "Redact Sensitive Content"
    DESC = "Permanently destroy sensitive text and underlying image pixels, then verify removal by re-inspecting the saved PDF."
    START_TEXT = "Redact permanently"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.preview_card = PagePreviewCard(interactive_rect=True)
        self.preview_card.rect_selected.connect(self._on_rect_dragged)
        self.panel.changed.connect(self._on_file)
        return _with_preview(self.panel, self.preview_card)

    def build_options(self, layout: QVBoxLayout) -> None:
        layout.addWidget(QLabel("Sensitive words/phrases (comma or line separated):"))
        self.terms = QLineEdit()
        self.terms.setPlaceholderText("e.g. SSN, John Doe, Account 12345")
        layout.addWidget(self.terms)
        self.repl = QLineEdit()
        self.repl.setPlaceholderText("Optional overlay label (e.g. [REDACTED])")
        layout.addWidget(labeled("Overlay text:", self.repl))
        self.fill_black = QCheckBox("Black redaction bars (uncheck for white)")
        self.fill_black.setChecked(True)
        layout.addWidget(self.fill_black)

        self.use_rect = QCheckBox("Also redact rectangular region (mm)")
        layout.addWidget(self.use_rect)
        self.rx = QDoubleSpinBox(); self.rx.setRange(0, 500); self.rx.setValue(20); self.rx.setSuffix(" mm")
        self.ry = QDoubleSpinBox(); self.ry.setRange(0, 500); self.ry.setValue(20); self.ry.setSuffix(" mm")
        self.rw = QDoubleSpinBox(); self.rw.setRange(0, 500); self.rw.setValue(60); self.rw.setSuffix(" mm")
        self.rh = QDoubleSpinBox(); self.rh.setRange(0, 500); self.rh.setValue(20); self.rh.setSuffix(" mm")
        for l, w in (("Area X:", self.rx), ("Area Y:", self.ry), ("Area W:", self.rw), ("Area H:", self.rh)):
            w.valueChanged.connect(self._sync_rect_to_preview)
            layout.addWidget(labeled(l, w))

        self.pages = QLineEdit()
        self.pages.setPlaceholderText("all (or e.g. 1-3, 5)")
        layout.addWidget(labeled("Pages:", self.pages))
        layout.addWidget(hint("Drag on the page preview to select a region, or enter words above. After saving, PDF Master reopens the output file and verifies removal."))

    def _on_rect_dragged(self, x: float, y: float, w: float, h: float) -> None:
        self.use_rect.setChecked(True)
        for sb, val in ((self.rx, x), (self.ry, y), (self.rw, w), (self.rh, h)):
            sb.blockSignals(True)
            sb.setValue(val)
            sb.blockSignals(False)

    def _sync_rect_to_preview(self) -> None:
        if hasattr(self, "preview_card"):
            self.preview_card.canvas.set_box_mm(self.rx.value(), self.ry.value(), self.rw.value(), self.rh.value())

    def _on_file(self) -> None:
        p = self.panel.first_path()
        self.preview_card.set_document(p, self.panel.passwords.get(p) if p else None)
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_redacted.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        raw_terms = [t.strip() for t in self.terms.text().replace(";", ",").split(",") if t.strip()]
        rect = (self.rx.value(), self.ry.value(), self.rw.value(), self.rh.value()) if self.use_rect.isChecked() else None
        if not raw_terms and rect is None:
            raise ValueError("Enter at least one word/phrase to redact or enable rectangular region redaction.")
        out = self.output_file(".pdf", [src])
        return redact_pdf, dict(
            src=src,
            output=out,
            terms=raw_terms,
            rect_mm=rect,
            replacement_text=self.repl.text().strip(),
            fill_black=self.fill_black.isChecked(),
            page_text=self.pages.text().strip() or None,
            password=self.panel.passwords.get(src),
        )

    def result_paths(self, result: RedactResult):
        return [result.output]

    def describe_result(self, result: RedactResult) -> str:
        return (
            f"Permanently applied {result.redactions_applied} redaction(s) and verified removal "
            f"→ {os.path.basename(result.output)}."
        )

    def clear_input(self) -> None:
        self.panel.list.clear_all()
        self.terms.clear()


class SignPage(ToolPage):
    TOOL_ID = "sign"
    TITLE = "Sign PDF"
    DESC = "Stamp a visible signature block with signer details, SHA-256 document digest, optional handwritten image, and optional lock."
    START_TEXT = "Sign PDF"
    NEEDS_FILENAME = True

    def build_input(self) -> QWidget:
        self.panel = FilePanel("pdf", single=True)
        self.preview_card = PagePreviewCard()
        self.panel.changed.connect(self._on_file)
        return _with_preview(self.panel, self.preview_card)

    def build_options(self, layout: QVBoxLayout) -> None:
        self.signer = QLineEdit()
        self.signer.setPlaceholderText("Full name of signer")
        layout.addWidget(labeled("Signer name:", self.signer))
        self.reason = QLineEdit("Approved")
        layout.addWidget(labeled("Reason:", self.reason))
        self.loc = QLineEdit()
        self.loc.setPlaceholderText("Optional city / office")
        layout.addWidget(labeled("Location:", self.loc))

        row = QHBoxLayout()
        self.sig_img = QLineEdit()
        self.sig_img.setPlaceholderText("Optional signature image…")
        b = QPushButton("Browse…")
        b.clicked.connect(self._browse_img)
        row.addWidget(self.sig_img, 1)
        row.addWidget(b)
        layout.addLayout(row)

        self.page_num = QSpinBox()
        self.page_num.setRange(0, 99999)
        self.page_num.setValue(0)
        self.page_num.setSpecialValueText("Last page")
        layout.addWidget(labeled("Page:", self.page_num))
        self.pos = QComboBox()
        self.pos.addItems(["bottom-right", "bottom-left", "bottom-center", "top-right", "top-left"])
        layout.addWidget(labeled("Position:", self.pos))
        self.lock = QCheckBox("Flatten and lock against modifications")
        layout.addWidget(self.lock)

    def _browse_img(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Select signature image", "", IMAGE_FILTER)
        if f:
            self.sig_img.setText(f)

    def _on_file(self) -> None:
        p = self.panel.first_path()
        self.preview_card.set_document(p, self.panel.passwords.get(p) if p else None)
        if p:
            self.default_dir_from(p)
            if self.name_edit:
                self.name_edit.setText(os.path.splitext(os.path.basename(p))[0] + "_signed.pdf")

    def prepare(self):
        src = self.panel.first_path()
        if not src:
            raise ValueError("Select a PDF file first.")
        if not self.signer.text().strip():
            raise ValueError("Enter the signer's name.")
        out = self.output_file(".pdf", [src])
        pno = -1 if self.page_num.value() == 0 else self.page_num.value()
        return sign_pdf, dict(
            src=src,
            output=out,
            signer_name=self.signer.text().strip(),
            reason=self.reason.text().strip(),
            location=self.loc.text().strip(),
            signature_image=self.sig_img.text().strip(),
            page_number=pno,
            position=self.pos.currentText(),
            lock_after_signing=self.lock.isChecked(),
            password=self.panel.passwords.get(src),
        )

    def describe_result(self, result) -> str:
        return f"Signed PDF saved as {os.path.basename(result)}."

    def clear_input(self) -> None:
        self.panel.list.clear_all()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main(start_tool='protect'))
