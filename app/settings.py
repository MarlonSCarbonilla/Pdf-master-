"""Application settings (JSON) + SQLite file history (%APPDATA%/PDFMaster/history.db)."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import json
import os
from typing import Any, Optional

from core.history_db import HistoryDB, HistoryEntry
from utils.logger import data_dir

DEFAULTS: dict[str, Any] = {
    "theme": "light",               # light | dark
    "output_dir": "",               # empty = ask / same folder as source
    "image_format": "PNG",          # JPG | PNG | TIFF
    "image_dpi": 150,
    "compression_preset": "recommended",
    "recent": [],                   # newest first (mirrored from SQLite history.db)
    "tool_usage": {},               # tool id -> count (for "frequently used")
}
MAX_RECENT = 30


class Settings:
    def __init__(self, path: str | None = None, db_path: str | None = None):
        self.path = path or os.path.join(data_dir(), "settings.json")
        resolved_db = db_path or os.path.join(os.path.dirname(os.path.abspath(self.path)), "history.db")
        self.history_db = HistoryDB(resolved_db)
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.load()
        self._sync_recent_from_db()

    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    if k in DEFAULTS and type(v) is type(DEFAULTS[k]):
                        self.data[k] = v
        except (OSError, ValueError):
            pass  # first run or corrupt file -> defaults

    def _sync_recent_from_db(self) -> None:
        # Migrate any legacy JSON recent paths into SQLite if SQLite is empty
        if self.data.get("recent") and self.history_db.count() == 0:
            for p in reversed(self.data["recent"]):
                if isinstance(p, str) and p.strip():
                    self.history_db.record_file(p, action="Opened")
        self.data["recent"] = self.history_db.list_paths(limit=MAX_RECENT, existing_only=False)

    def save(self) -> None:
        tmp = self.path + ".tmp"
        try:
            parent = os.path.dirname(os.path.abspath(self.path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def get(self, key: str) -> Any:
        if key == "recent":
            self.data["recent"] = self.history_db.list_paths(limit=MAX_RECENT, existing_only=False)
        return self.data.get(key, DEFAULTS[key])

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

    # ---- SQLite file history ----
    def add_recent(
        self,
        path: str,
        action: str = "Opened",
        page_count: Optional[int] = None,
    ) -> None:
        self.history_db.record_file(path, action=action, page_count=page_count)
        self.data["recent"] = self.history_db.list_paths(limit=MAX_RECENT, existing_only=False)
        self.save()

    def remove_recent(self, path: str) -> None:
        self.history_db.remove_file(path)
        self.data["recent"] = self.history_db.list_paths(limit=MAX_RECENT, existing_only=False)
        self.save()

    def recent_existing(self, limit: int = MAX_RECENT) -> list[str]:
        return self.history_db.list_paths(limit=limit, existing_only=True)

    def recent_entries(
        self,
        limit: int = MAX_RECENT,
        existing_only: bool = True,
        search: str = "",
        action_filter: str = "",
    ) -> list[HistoryEntry]:
        return self.history_db.list_entries(
            limit=limit,
            existing_only=existing_only,
            search=search,
            action_filter=action_filter,
        )

    def clear_history(self) -> None:
        self.history_db.clear()
        self.data["recent"] = []
        self.save()

    def bump_tool(self, tool_id: str) -> None:
        usage = dict(self.data["tool_usage"])
        usage[tool_id] = usage.get(tool_id, 0) + 1
        self.data["tool_usage"] = usage
        self.save()

    def reset(self) -> None:
        keep_recent = self.history_db.list_paths(limit=MAX_RECENT, existing_only=False)
        self.data = dict(DEFAULTS)
        self.data["recent"] = keep_recent
        self.save()


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main())
