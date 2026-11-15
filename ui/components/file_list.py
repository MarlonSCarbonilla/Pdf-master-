"""File queue widgets: drag & drop, browse, remove, reorder, validation."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    import main as _main_bootstrap  # noqa: F401

import os
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout, QWidget)

from core.common import ProcessingError
from ui.components import dialogs
from utils.file_utils import human_size
from utils.validators import IMAGE_EXTS, check_image_file, has_pdf_header, probe_pdf

PDF_FILTER = "PDF files (*.pdf)"
IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)"
OFFICE_EXTS = {".docx", ".xlsx", ".pptx"}
OFFICE_FILTER = "Office documents (*.docx *.xlsx *.pptx)"


class FileList(QListWidget):
    """List of validated files. Accepts drops from Explorer; items can be reordered by drag."""

    changed = Signal()

    def __init__(self, kind: str = "pdf", single: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.kind = kind
        self.single = single
        self.passwords: dict[str, str] = {}
        self.setSelectionMode(QAbstractItemView.SingleSelection if single else QAbstractItemView.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setDragEnabled(not single)
        self.setDragDropMode(QAbstractItemView.NoDragDrop if single else QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setAlternatingRowColors(False)
        self.setMinimumHeight(140)
        self.model().rowsMoved.connect(lambda *_: self.changed.emit())

    # ---- data ----
    def paths(self) -> list[str]:
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    def selected_paths(self) -> list[str]:
        return [i.data(Qt.UserRole) for i in self.selectedItems()]

    def first_path(self) -> Optional[str]:
        return self.item(0).data(Qt.UserRole) if self.count() else None

    def page_counts(self) -> dict[str, int]:
        return {self.item(i).data(Qt.UserRole): self.item(i).data(Qt.UserRole + 1) for i in range(self.count())}

    # ---- adding ----
    def _accepted_ext(self, path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        if self.kind in ("pdf", "pdf_raw"):
            return ext == ".pdf"
        if self.kind == "office":
            return ext in OFFICE_EXTS
        return ext in IMAGE_EXTS

    def add_paths(self, paths: list[str]) -> None:
        expanded: list[str] = []
        for p in paths:
            if os.path.isdir(p):
                expanded += [os.path.join(p, f) for f in sorted(os.listdir(p)) if self._accepted_ext(f)]
            else:
                expanded.append(p)
        problems: list[str] = []
        existing = set(self.paths())
        for p in expanded:
            p = os.path.abspath(p)
            name = os.path.basename(p)
            if p in existing:
                continue
            if not self._accepted_ext(p):
                problems.append(f"{name}: unsupported file type.")
                continue
            try:
                if self.kind == "pdf":
                    pages, locked = probe_pdf(p)
                    if locked:
                        pw = self._unlock(p)
                        if pw is None:
                            problems.append(f"{name}: password not provided.")
                            continue
                        from utils.validators import open_pdf
                        d = open_pdf(p, pw)
                        pages = d.page_count
                        d.close()
                        self.passwords[p] = pw
                    sub = f"{pages} page{'s' if pages != 1 else ''}"
                elif self.kind == "pdf_raw":
                    if not os.path.isfile(p) or os.path.getsize(p) == 0 or not has_pdf_header(p):
                        raise ProcessingError(f"'{name}' is not a PDF file.")
                    pages, sub = 0, "PDF file"
                elif self.kind == "office":
                    import zipfile
                    if not os.path.isfile(p) or not zipfile.is_zipfile(p):
                        raise ProcessingError(f"'{name}' is not a valid Office (.docx/.xlsx/.pptx) file.")
                    pages, sub = 1, os.path.splitext(name)[1].upper().lstrip(".") + " document"
                else:
                    check_image_file(p)
                    pages, sub = 1, "image"
            except ProcessingError as e:
                problems.append(str(e))
                continue
            if self.single:
                self.clear()
                existing.clear()
            it = QListWidgetItem(f"{name}\n{sub} · {human_size(os.path.getsize(p))}")
            it.setData(Qt.UserRole, p)
            it.setData(Qt.UserRole + 1, pages)
            it.setToolTip(p)
            self.addItem(it)
            existing.add(p)
        if problems:
            dialogs.warn(self.window(), "Some files were skipped", "\n".join(problems[:12]))
        self.changed.emit()

    def _unlock(self, path: str) -> Optional[str]:
        from utils.validators import open_pdf
        wrong = False
        for _ in range(3):
            pw = dialogs.ask_password(self.window(), path, wrong)
            if pw is None:
                return None
            try:
                open_pdf(path, pw).close()
                return pw
            except ProcessingError:
                wrong = True
        return None

    def remove_selected(self) -> None:
        for it in self.selectedItems():
            self.passwords.pop(it.data(Qt.UserRole), None)
            self.takeItem(self.row(it))
        self.changed.emit()

    def clear_all(self) -> None:
        self.clear()
        self.passwords.clear()
        self.changed.emit()

    def move_selected(self, delta: int) -> None:
        rows = sorted(self.row(i) for i in self.selectedItems())
        if not rows:
            return
        if delta < 0 and rows[0] == 0 or delta > 0 and rows[-1] == self.count() - 1:
            return
        for r in (rows if delta < 0 else reversed(rows)):
            it = self.takeItem(r)
            self.insertItem(r + delta, it)
            it.setSelected(True)
        self.changed.emit()

    # ---- drag & drop from outside ----
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            self.add_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
            e.acceptProposedAction()
        else:
            super().dropEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.remove_selected()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.count() == 0:
            p = QPainter(self.viewport())
            p.setPen(self.palette().mid().color())
            what = {"pdf": "PDF files", "pdf_raw": "PDF files", "office": "Word / Excel / PowerPoint files"}.get(self.kind, "images")
            p.drawText(self.viewport().rect(), Qt.AlignCenter,
                       f"Drag & drop {what} here\nor click “Browse files”")


class FilePanel(QWidget):
    """FileList + Browse / Remove / Clear / Move buttons."""

    changed = Signal()

    def __init__(self, kind: str = "pdf", single: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.kind, self.single = kind, single
        self.list = FileList(kind, single)
        self.list.changed.connect(self.changed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.btn_browse = QPushButton("Browse file…" if single else "Browse files…")
        self.btn_browse.setObjectName("primary")
        self.btn_browse.clicked.connect(self.browse)
        row.addWidget(self.btn_browse)
        self.btn_remove = QPushButton("Remove selected")
        self.btn_remove.clicked.connect(self.list.remove_selected)
        row.addWidget(self.btn_remove)
        if not single:
            for text, d in (("▲ Up", -1), ("▼ Down", 1)):
                b = QPushButton(text)
                b.clicked.connect(lambda _=False, d=d: self.list.move_selected(d))
                row.addWidget(b)
        row.addStretch(1)
        clear = QPushButton("Clear list")
        clear.clicked.connect(self.list.clear_all)
        row.addWidget(clear)
        lay.addLayout(row)

    def browse(self) -> None:
        if self.kind in ("pdf", "pdf_raw"):
            flt, title = PDF_FILTER, "Select PDF"
        elif self.kind == "office":
            flt, title = OFFICE_FILTER, "Select Office document"
        else:
            flt, title = IMAGE_FILTER, "Select images"
        if self.single:
            f, _ = QFileDialog.getOpenFileName(self, title, "", flt)
            files = [f] if f else []
        else:
            files, _ = QFileDialog.getOpenFileNames(self, title, "", flt)
        if files:
            self.list.add_paths(files)

    # delegates
    def paths(self) -> list[str]:
        return self.list.paths()

    def first_path(self) -> Optional[str]:
        return self.list.first_path()

    @property
    def passwords(self) -> dict[str, str]:
        return self.list.passwords

    def set_enabled_editing(self, on: bool) -> None:
        self.setEnabled(on)


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main())
