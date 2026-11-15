"""Shared types for the processing engine (no Qt imports here)."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

from dataclasses import dataclass
from typing import Callable, Optional


class ProcessingError(Exception):
    """A user-presentable error (message is safe to show in a dialog)."""


class PasswordRequired(ProcessingError):
    def __init__(self, path: str):
        super().__init__(f"'{path}' is password protected. A password is required.")
        self.path = path


class OperationCancelled(Exception):
    """Raised inside a job when the user cancelled it."""


@dataclass
class JobContext:
    """Progress/cancel channel handed to every long-running engine function."""

    progress: Optional[Callable[[int, int, str], None]] = None
    is_cancelled: Optional[Callable[[], bool]] = None

    def check(self) -> None:
        if self.is_cancelled and self.is_cancelled():
            raise OperationCancelled()

    def report(self, done: int, total: int, message: str = "") -> None:
        self.check()
        if self.progress:
            self.progress(done, total, message)


def ctx_or_default(ctx: Optional[JobContext]) -> JobContext:
    return ctx if ctx is not None else JobContext()
