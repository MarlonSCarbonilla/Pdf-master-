"""Generate resources/icons/app.ico, app.png, and app.svg via tools.generate_app_icon."""
from __future__ import annotations

import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

from tools.generate_app_icon import generate_icons

if __name__ == "__main__":
    generate_icons()
