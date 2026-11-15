"""Base class shared by every processing page: input, options, output, progress, cancel."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    import main as _main_bootstrap  # noqa: F401

import os
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from app.settings import Settings
from core.file_manager import open_folder
from ui.components import dialogs
from ui.components.icons import icon
from utils.file_utils import check_disk_space, ensure_output_dir, safe_filename
from core.common import ProcessingError
from workers.processing_worker import ProcessingWorker, can_start_job


class UserAbort(Exception):
    """Raised by prepare() when the user declined something (e.g. overwrite)."""


class ToolPage(QWidget):
    back_requested = Signal()
    open_in_viewer = Signal(str)

    TOOL_ID = ""
    TITLE = "Tool"
    DESC = ""
    ICON = "doc"
    START_TEXT = "Start"
    NEEDS_FILENAME = False       # show a "file name" field next to the output folder
    OUTPUT_IS_DIR = False        # True when results are many files written into the folder
    WORKER_CLASS = ProcessingWorker

    def __init__(self, settings: Settings, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.settings = settings
        self.worker: Optional[ProcessingWorker] = None
        self.last_output: Optional[str] = None
        self._build()

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(12)

        head = QHBoxLayout()
        back = QPushButton(" Back")
        back.setIcon(icon("back", "#6b7280", 18))
        back.setObjectName("link")
        back.clicked.connect(self.back_requested)
        head.addWidget(back)
        head.addStretch(1)
        root.addLayout(head)

        title = QLabel(self.TITLE)
        title.setObjectName("h1")
        desc = QLabel(self.DESC)
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(desc)

        body = QHBoxLayout()
        body.setSpacing(16)
        self.input_widget = self.build_input()
        body.addWidget(self.input_widget, 3)
        opts = QFrame()
        opts.setObjectName("card")
        ol = QVBoxLayout(opts)
        ol.setContentsMargins(16, 14, 16, 14)
        h = QLabel("Options")
        h.setObjectName("h2")
        ol.addWidget(h)
        self.build_options(ol)
        ol.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(opts)
        sc.setFixedWidth(330)
        sc.setFrameShape(QFrame.NoFrame)
        body.addWidget(sc, 0)
        root.addLayout(body, 1)

        foot = QFrame()
        foot.setObjectName("card")
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(16, 12, 16, 12)
        row = QHBoxLayout()
        row.addWidget(QLabel("Output folder:"))
        self.out_edit = QLineEdit(self.settings.get("output_dir"))
        self.out_edit.setPlaceholderText("Choose where to save the result…")
        row.addWidget(self.out_edit, 1)
        b = QPushButton("Browse…")
        b.clicked.connect(self._browse_out)
        row.addWidget(b)
        self.name_edit: Optional[QLineEdit] = None
        if self.NEEDS_FILENAME:
            row.addWidget(QLabel("File name:"))
            self.name_edit = QLineEdit()
            self.name_edit.setFixedWidth(230)
            row.addWidget(self.name_edit)
        fl.addLayout(row)

        prow = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        prow.addWidget(self.progress, 1)
        fl.addLayout(prow)
        self.status = QLabel("Ready.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        fl.addWidget(self.status)

        btns = QHBoxLayout()
        self.btn_clear = QPushButton("Clear settings")
        self.btn_clear.clicked.connect(self._clear_all)
        btns.addWidget(self.btn_clear)
        btns.addStretch(1)
        self.btn_view = QPushButton("Open in Reader")
        self.btn_view.setIcon(icon("reader", "#6b7280", 18))
        self.btn_view.setEnabled(False)
        self.btn_view.clicked.connect(self._view_output)
        btns.addWidget(self.btn_view)
        self.btn_open = QPushButton("Open output folder")
        self.btn_open.setIcon(icon("open", "#6b7280", 18))
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._open_output)
        btns.addWidget(self.btn_open)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        btns.addWidget(self.btn_cancel)
        self.btn_start = QPushButton(self.START_TEXT)
        self.btn_start.setObjectName("primary")
        self.btn_start.clicked.connect(self.start)
        btns.addWidget(self.btn_start)
        fl.addLayout(btns)
        root.addWidget(foot)

    # ------------------------------------------------------------------ hooks
    def build_input(self) -> QWidget:  # pragma: no cover - overridden
        return QWidget()

    def build_options(self, layout: QVBoxLayout) -> None:
        pass

    def prepare(self) -> tuple[Callable[..., Any], dict[str, Any]]:
        """Validate the UI state and return (engine function, kwargs). Raise ValueError for user mistakes."""
        raise NotImplementedError

    def describe_result(self, result: Any) -> str:
        return "Done."

    def result_paths(self, result: Any) -> list[str]:
        """Output files to add to recent history / for 'open folder'."""
        return [result] if isinstance(result, str) else []

    def reset_options(self) -> None:
        pass

    def clear_input(self) -> None:
        pass

    def apply_preset(self, **kw: Any) -> None:
        if "file" in kw:
            self.load_file(kw["file"])

    def load_file(self, path: str) -> None:
        """Pre-load a file into this tool page's FilePanel when sent from Reader or Recent Files."""
        if not path or not os.path.isfile(path):
            return
        panel = getattr(self, "panel", None)
        if panel is not None and hasattr(panel, "list"):
            if getattr(panel.list, "single", False):
                panel.list.clear_all()
            panel.list.add_paths([path])

    # ------------------------------------------------------------------ helpers
    def out_dir(self) -> str:
        return self.out_edit.text().strip()

    def default_dir_from(self, source: Optional[str]) -> None:
        """If no output folder is set, suggest the source's folder."""
        if source and not self.out_edit.text().strip():
            self.out_edit.setText(os.path.dirname(source))

    def output_file(self, ext: str = ".pdf", inputs: tuple[str, ...] | list[str] = ()) -> str:
        """Resolve folder + file name for single-file outputs; never replaces an input,
        and asks before overwriting any other existing file."""
        folder = self.out_dir()
        name = safe_filename((self.name_edit.text() if self.name_edit else "output").strip())
        if not name.lower().endswith(ext):
            name += ext
        self._check_folder()
        path = os.path.join(folder, name)
        norm = lambda p: os.path.normcase(os.path.abspath(p))  # noqa: E731
        if any(norm(path) == norm(i) for i in inputs):
            raise ValueError("The output file would overwrite one of your source files.\n"
                             "Please choose a different file name or output folder.")
        if os.path.exists(path) and not dialogs.confirm_overwrite(self, path):
            raise UserAbort()
        return path

    def _check_folder(self) -> None:
        try:
            ensure_output_dir(self.out_dir())
        except ProcessingError as e:
            raise ValueError(str(e)) from None

    def check_space(self, sources: list[str], factor: float = 1.5) -> None:
        try:
            size = sum(os.path.getsize(p) for p in sources if os.path.exists(p))
            check_disk_space(self.out_dir(), int(size * factor))
        except ProcessingError as e:
            raise ValueError(str(e)) from None

    def set_status(self, text: str, kind: str = "muted") -> None:
        self.status.setObjectName(kind)
        self.status.setStyleSheet("")  # force re-polish for the new object name
        self.style().unpolish(self.status)
        self.style().polish(self.status)
        self.status.setText(text)

    # ------------------------------------------------------------------ actions
    def _browse_out(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Select output folder", self.out_dir() or "")
        if d:
            self.out_edit.setText(d)

    def _clear_all(self) -> None:
        if self.worker:
            return
        self.clear_input()
        self.reset_options()
        self.out_edit.setText(self.settings.get("output_dir"))
        if self.name_edit:
            self.name_edit.clear()
        self.progress.setValue(0)
        self.btn_open.setEnabled(False)
        self.btn_view.setEnabled(False)
        self.last_output = None
        self.set_status("Ready.")

    def _view_output(self) -> None:
        if self.last_output and os.path.isfile(self.last_output) and self.last_output.lower().endswith(".pdf"):
            self.open_in_viewer.emit(self.last_output)

    def _open_output(self) -> None:
        target = self.last_output or self.out_dir()
        if target:
            open_folder(target, select_file=bool(self.last_output and os.path.isfile(self.last_output)))

    def set_busy(self, busy: bool) -> None:
        self.btn_start.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)
        self.btn_clear.setEnabled(not busy)
        self.input_widget.setEnabled(not busy)

    def start(self) -> None:
        if self.worker is not None:
            return
        if not can_start_job():
            dialogs.info(self, "Please wait", "Another operation is still running. Wait for it to finish first.")
            return
        try:
            fn, kwargs = self.prepare()
        except UserAbort:
            return
        except ValueError as e:
            dialogs.warn(self, self.TITLE, str(e))
            return
        self.progress.setValue(0)
        self.btn_open.setEnabled(False)
        self.btn_view.setEnabled(False)
        self.set_status("Starting…")
        self.set_busy(True)
        self.worker = self.WORKER_CLASS(fn, kwargs, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.succeeded.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.finished.connect(self._cleanup)
        self.worker.start()
        if self.TOOL_ID:
            self.settings.bump_tool(self.TOOL_ID)

    def _cancel(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self.set_status("Cancelling…")

    def _on_progress(self, done: int, total: int, msg: str) -> None:
        self.progress.setValue(int(100 * done / total) if total else 0)
        if msg:
            self.set_status(msg)

    def _on_done(self, result: Any) -> None:
        self.progress.setValue(100)
        paths = self.result_paths(result)
        for p in paths[:5]:
            if os.path.isfile(p):
                self.settings.add_recent(p, action=self.TITLE)
        self.last_output = paths[0] if paths else self.out_dir()
        self.btn_open.setEnabled(True)
        self.btn_view.setEnabled(
            bool(self.last_output and os.path.isfile(self.last_output) and self.last_output.lower().endswith(".pdf"))
        )
        msg = self.describe_result(result)
        if self.TOOL_ID:
            self.settings.history_db.record_operation(self.TOOL_ID, self.last_output or "", msg)
        neutral = msg[:1] in ("ℹ", "⚠")
        self.set_status(msg if neutral else "✔ " + msg, "muted" if neutral else "ok")

    def _on_failed(self, msg: str) -> None:
        self.progress.setValue(0)
        self.set_status("✖ " + msg.splitlines()[0], "err")
        dialogs.error(self, "Operation failed", msg)

    def _on_cancelled(self) -> None:
        self.progress.setValue(0)
        self.set_status("Operation cancelled. No output file was kept.", "muted")

    def _cleanup(self) -> None:
        if self.worker:
            self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)

    def is_busy(self) -> bool:
        return self.worker is not None

    def shutdown(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.worker.wait(5000)


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main())
