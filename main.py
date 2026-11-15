"""PDF Master - entry point."""
from __future__ import annotations

import os
import subprocess
import sys


def _ensure_venv() -> None:
    """If launched with a global Python that lacks PySide6, automatically re-launch
    using the project's .venv interpreter when present."""
    if getattr(sys, "frozen", False):
        return
    try:
        import PySide6  # noqa: F401
        import fitz  # noqa: F401
    except ImportError:
        root = os.path.dirname(os.path.abspath(__file__))
        venv_py = os.path.join(root, ".venv", "Scripts", "python.exe")
        if os.path.isfile(venv_py) and os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(venv_py):
            raise SystemExit(subprocess.call([venv_py, *sys.argv]))


_ensure_venv()


def _resource_dir() -> str:
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def main(start_tool: str | None = None) -> int:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PDFMaster.OfflineToolkit.1.0")
        except Exception:
            pass

    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app.main_window import MainWindow
    from app.settings import Settings
    from utils.logger import get_logger

    log = get_logger()

    def excepthook(exc_type, exc, tb):
        log.error("Uncaught exception", exc_info=(exc_type, exc, tb))
        QMessageBox.critical(None, "PDF Master", f"An unexpected error occurred:\n{exc_type.__name__}: {exc}\n\n"
                                                 "Details were written to the log file.")

    sys.excepthook = excepthook
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Master")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    res_icons = os.path.join(_resource_dir(), "resources", "icons")
    app_icon = QIcon()
    for fname in ("app.ico", "app.png"):
        fpath = os.path.join(res_icons, fname)
        if os.path.exists(fpath):
            app_icon.addFile(fpath)
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    win = MainWindow(Settings())
    if not app_icon.isNull():
        win.setWindowIcon(app_icon)
    if start_tool:
        if start_tool.startswith(("cat:", "dashboard", "recent", "settings", "about")):
            win.navigate(start_tool)
        else:
            win.open_tool(start_tool)
    win.show()
    # Open a PDF passed on the command line (e.g. "Open with")
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".pdf") and os.path.isfile(arg):
            win.open_viewer(os.path.abspath(arg))
            break
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
