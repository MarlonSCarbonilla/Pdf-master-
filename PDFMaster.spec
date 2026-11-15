# PyInstaller spec - one-folder build. Run via build.ps1
# Excludes Qt modules / packages the app never uses to keep the distribution small.
block_cipher = None

EXCLUDES = [
    "tkinter", "unittest", "pydoc", "test", "pytest", "setuptools", "pip", "numpy",
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore", "PySide6.QtSql",
    "PySide6.QtMultimedia", "PySide6.QtSvg", "PySide6.QtOpenGL", "PySide6.Qt3DCore", "PySide6.QtDesigner",
    "PySide6.QtPdf", "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtCharts",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=[
        ("resources/icons/app.ico", "resources/icons"),
        ("resources/icons/app.png", "resources/icons"),
        ("resources/icons/app.svg", "resources/icons"),
    ],
    hiddenimports=[
        # tool pages are imported lazily via importlib, so list them explicitly
        "ui.merge_page", "ui.split_page", "ui.organize_page", "ui.pages_page", "ui.convert_page",
        "ui.compress_page", "ui.viewer_page", "ui.dashboard",
        "ui.edit_page", "ui.security_page", "ui.utilities_page", "ui.ocr_page",
        "ui.components.page_canvas",
        "core.history_db", "sqlite3",
        "core.pdf_edit", "core.pdf_security", "core.pdf_utilities",
        "core.ocr_engine", "core.office_convert",
        "docx", "openpyxl", "pptx", "pytesseract",
        "PySide6.QtPrintSupport",
    ],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="PDFMaster",
    console=False,
    icon="resources/icons/app.ico",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PDFMaster")
