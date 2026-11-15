"""Background job runner. Every long operation runs in a QThread; the GUI never blocks."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import os
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from core.common import JobContext, OperationCancelled, ProcessingError
from utils.logger import get_logger

log = get_logger()

# Practical limit for simultaneous jobs on ordinary office PCs (dual core, 4 GB RAM).
MAX_JOBS = max(1, min(2, (os.cpu_count() or 2) // 2))
_active = 0


def can_start_job() -> bool:
    return _active < MAX_JOBS


class ProcessingWorker(QThread):
    """Runs `fn(*args, ctx=JobContext, **kwargs)` off the GUI thread."""

    progress = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn: Callable[..., Any], kwargs: dict[str, Any], parent=None):
        super().__init__(parent)
        self._fn = fn
        self._kwargs = kwargs
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        global _active
        _active += 1
        ctx = JobContext(lambda d, t, m: self.progress.emit(d, t, m), lambda: self._cancel)
        try:
            result = self._fn(ctx=ctx, **self._kwargs)
        except OperationCancelled:
            self.cancelled.emit()
        except ProcessingError as e:
            self.failed.emit(str(e))
        except MemoryError:
            self.failed.emit("Not enough memory for this operation. Try a lower resolution or a smaller file.")
        except PermissionError as e:
            self.failed.emit(f"Permission denied while writing a file. Check the output folder.\n({e.filename})")
        except OSError as e:
            self.failed.emit(f"A file error occurred: {e.strerror or e}")
        except Exception as e:  # unexpected: log the traceback, show a short message
            log.exception("Unhandled error in worker")
            self.failed.emit(f"An unexpected error occurred: {type(e).__name__}: {e}")
        else:
            self.succeeded.emit(result)
        finally:
            _active -= 1
