if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

"""Conversion jobs (PDF <-> image). Same machinery as ProcessingWorker; kept as its own
module so Phase 3 office/OCR conversion workers have an obvious home."""
from workers.processing_worker import ProcessingWorker


class ConversionWorker(ProcessingWorker):
    """Worker used by the conversion pages."""
