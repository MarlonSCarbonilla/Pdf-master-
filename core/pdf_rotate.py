if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

"""Rotate PDF pages (thin public wrapper over pdf_organize)."""
from core.pdf_organize import rotate_pdf  # noqa: F401
