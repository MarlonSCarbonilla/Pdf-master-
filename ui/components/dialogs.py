"""Small dialog helpers."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    import main as _main_bootstrap  # noqa: F401

import os
from typing import Optional

from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget


def ask_password(parent: QWidget, path: str, wrong: bool = False) -> Optional[str]:
    msg = f"'{os.path.basename(path)}' is password protected.\nEnter the password to open it:"
    if wrong:
        msg = "Wrong password. Try again.\n\n" + msg
    text, ok = QInputDialog.getText(parent, "Password required", msg, QLineEdit.Password)
    return text if ok and text else None


def confirm_overwrite(parent: QWidget, path: str) -> bool:
    r = QMessageBox.question(
        parent, "File already exists",
        f"'{os.path.basename(path)}' already exists in that folder.\nDo you want to replace it?",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    return r == QMessageBox.Yes


def warn(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def error(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


def info(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main())
