"""Light / dark themes (Qt style sheets). Red accent for PDF actions."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

LIGHT = {
    "bg": "#f5f6f8", "surface": "#ffffff", "border": "#e2e4e9", "text": "#1f2430", "muted": "#6b7280",
    "accent": "#e5322d", "accent_hover": "#c9231f", "accent_soft": "#fdecec", "side": "#ffffff",
    "hover": "#f0f1f4", "input": "#ffffff", "ok": "#1a8f4c", "err": "#c62828",
}
DARK = {
    "bg": "#16181d", "surface": "#1f2229", "border": "#2e323b", "text": "#e8eaee", "muted": "#9aa1ae",
    "accent": "#ef4a45", "accent_hover": "#ff6560", "accent_soft": "#3a2223", "side": "#1b1e24",
    "hover": "#282c35", "input": "#181b21", "ok": "#4cc47f", "err": "#ff7b72",
}


def palette(dark: bool) -> dict[str, str]:
    return DARK if dark else LIGHT


def stylesheet(dark: bool) -> str:
    c = palette(dark)
    return f"""
* {{ font-family: "Segoe UI", "Segoe UI Variable", sans-serif; font-size: 13px; }}
QWidget {{ color: {c['text']}; }}
QMainWindow, QStackedWidget, #page {{ background: {c['bg']}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
#sidebar {{ background: {c['side']}; border-right: 1px solid {c['border']}; }}
#sidebar QPushButton {{ text-align: left; padding: 10px 14px; border: none; border-radius: 8px;
    color: {c['text']}; background: transparent; margin: 1px 8px; }}
#sidebar QPushButton:hover {{ background: {c['hover']}; }}
#sidebar QPushButton:checked {{ background: {c['accent_soft']}; color: {c['accent']}; font-weight: 600; }}
#brand {{ font-size: 17px; font-weight: 700; padding: 18px 16px 10px 16px; color: {c['text']}; }}
#card, QFrame#card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
#toolcard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; text-align: left; padding: 12px; }}
#toolcard:hover {{ border-color: {c['accent']}; background: {c['accent_soft']}; }}
#h1 {{ font-size: 24px; font-weight: 700; }}
#h2 {{ font-size: 16px; font-weight: 650; }}
#muted {{ color: {c['muted']}; }}
#ok {{ color: {c['ok']}; font-weight: 600; }}
#err {{ color: {c['err']}; font-weight: 600; }}
QPushButton {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 7px 14px; }}
QPushButton:hover {{ background: {c['hover']}; }}
QPushButton:disabled {{ color: {c['muted']}; }}
QPushButton#primary {{ background: {c['accent']}; color: white; border: none; font-weight: 600; padding: 9px 22px; }}
QPushButton#primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#primary:disabled {{ background: {c['border']}; color: {c['muted']}; }}
QPushButton#link {{ border: none; background: transparent; color: {c['accent']}; padding: 4px 6px; }}
QLineEdit, QSpinBox, QComboBox, QDoubleSpinBox, QPlainTextEdit {{ background: {c['input']}; border: 1px solid {c['border']};
    border-radius: 7px; padding: 5px 8px; selection-background-color: {c['accent']}; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {c['accent']}; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; selection-background-color: {c['accent_soft']}; selection-color: {c['text']}; }}
QListWidget {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 4px; outline: 0; }}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; border: 1px solid {c['accent']}; }}
QProgressBar {{ background: {c['border']}; border: none; border-radius: 5px; height: 10px; text-align: center; font-size: 10px; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 5px; }}
QRadioButton, QCheckBox {{ spacing: 8px; }}
QToolBar {{ background: {c['surface']}; border: none; border-bottom: 1px solid {c['border']}; spacing: 4px; padding: 4px; }}
QToolButton {{ border: none; border-radius: 6px; padding: 5px; }}
QToolButton:hover {{ background: {c['hover']}; }}
QToolButton:checked {{ background: {c['accent_soft']}; }}
QScrollBar:vertical {{ background: transparent; width: 12px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 30px; margin: 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; }}
QGroupBox {{ border: 1px solid {c['border']}; border-radius: 10px; margin-top: 12px; padding: 12px 10px 8px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {c['muted']}; }}
QSplitter::handle {{ background: {c['border']}; }}
"""


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main())
