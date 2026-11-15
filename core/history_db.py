"""SQLite-backed file & operation history store (%APPDATA%/PDFMaster/history.db)."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import contextlib
import datetime
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

from utils.logger import data_dir

MAX_HISTORY_ROWS = 200


@dataclass(frozen=True)
class HistoryEntry:
    file_path: str
    file_name: str
    action: str
    file_size: int
    page_count: int
    last_opened_at: str
    open_count: int


@dataclass(frozen=True)
class OperationEntry:
    id: int
    tool_id: str
    output_path: str
    summary: str
    created_at: str


class HistoryDB:
    """Lightweight offline SQLite store for recent files and tool operations."""

    _last_ns: int = 0

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(data_dir(), "history.db")
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_schema()

    @classmethod
    def _next_ns(cls) -> int:
        ns = time.time_ns()
        if ns <= cls._last_ns:
            ns = cls._last_ns + 1
        cls._last_ns = ns
        return ns

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS file_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL UNIQUE,
                    file_name TEXT NOT NULL,
                    action TEXT NOT NULL DEFAULT 'Opened',
                    file_size INTEGER NOT NULL DEFAULT 0,
                    page_count INTEGER NOT NULL DEFAULT 0,
                    last_opened_at TEXT NOT NULL,
                    updated_ns INTEGER NOT NULL DEFAULT 0,
                    open_count INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_file_history_last_opened
                    ON file_history (updated_ns DESC, id DESC);

                CREATE TABLE IF NOT EXISTS operation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_id TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_operation_history_created
                    ON operation_history (created_at DESC, id DESC);
                """
            )

    @staticmethod
    def _now_iso() -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _probe_pdf_pages(path: str) -> int:
        if not path.lower().endswith(".pdf") or not os.path.isfile(path):
            return 0
        try:
            import fitz

            with fitz.open(path) as doc:
                if not doc.needs_pass:
                    return doc.page_count
        except Exception:
            pass
        return 0

    def record_file(
        self,
        path: str,
        action: str = "Opened",
        page_count: Optional[int] = None,
    ) -> None:
        """Insert or update a file entry in SQLite history."""
        norm_path = os.path.abspath(path)
        name = os.path.basename(norm_path) or norm_path
        size = os.path.getsize(norm_path) if os.path.isfile(norm_path) else 0
        pages = page_count if page_count is not None else self._probe_pdf_pages(norm_path)
        now = self._now_iso()
        now_ns = self._next_ns()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO file_history (
                    file_path, file_name, action, file_size, page_count, last_opened_at, updated_ns, open_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(file_path) DO UPDATE SET
                    file_name = excluded.file_name,
                    action = excluded.action,
                    file_size = CASE WHEN excluded.file_size > 0 THEN excluded.file_size ELSE file_history.file_size END,
                    page_count = CASE WHEN excluded.page_count > 0 THEN excluded.page_count ELSE file_history.page_count END,
                    last_opened_at = excluded.last_opened_at,
                    updated_ns = excluded.updated_ns,
                    open_count = file_history.open_count + 1
                """,
                (norm_path, name, action or "Opened", size, pages, now, now_ns),
            )
            # Keep table bounded
            conn.execute(
                """
                DELETE FROM file_history
                WHERE id NOT IN (
                    SELECT id FROM file_history
                    ORDER BY updated_ns DESC, id DESC
                    LIMIT ?
                )
                """,
                (MAX_HISTORY_ROWS,),
            )

    def record_operation(self, tool_id: str, output_path: str, summary: str = "") -> None:
        """Record a completed tool operation in SQLite."""
        now = self._now_iso()
        norm_out = os.path.abspath(output_path) if output_path else ""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO operation_history (tool_id, output_path, summary, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (tool_id, norm_out, summary, now),
            )
            conn.execute(
                """
                DELETE FROM operation_history
                WHERE id NOT IN (
                    SELECT id FROM operation_history
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                )
                """,
                (MAX_HISTORY_ROWS,),
            )

    def list_entries(
        self,
        limit: int = 50,
        existing_only: bool = True,
        search: str = "",
        action_filter: str = "",
    ) -> list[HistoryEntry]:
        """Query recent file entries ordered from newest to oldest."""
        clauses: list[str] = []
        params: list[object] = []
        if search.strip():
            q = f"%{search.strip()}%"
            clauses.append("(file_name LIKE ? OR file_path LIKE ? OR action LIKE ?)")
            params.extend([q, q, q])
        if action_filter.strip() and action_filter.strip().lower() != "all":
            clauses.append("action = ?")
            params.append(action_filter.strip())

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            SELECT file_path, file_name, action, file_size, page_count, last_opened_at, open_count
            FROM file_history
            {where_sql}
            ORDER BY updated_ns DESC, id DESC
        """
        out: list[HistoryEntry] = []
        with self._connect() as conn:
            for row in conn.execute(sql, params):
                fp = row["file_path"]
                if existing_only and not os.path.exists(fp):
                    continue
                size = os.path.getsize(fp) if os.path.isfile(fp) else row["file_size"]
                out.append(
                    HistoryEntry(
                        file_path=fp,
                        file_name=row["file_name"],
                        action=row["action"],
                        file_size=size,
                        page_count=row["page_count"],
                        last_opened_at=row["last_opened_at"],
                        open_count=row["open_count"],
                    )
                )
                if len(out) >= limit:
                    break
        return out

    def list_paths(self, limit: int = 30, existing_only: bool = True) -> list[str]:
        return [e.file_path for e in self.list_entries(limit=limit, existing_only=existing_only)]

    def distinct_actions(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT action FROM file_history ORDER BY action ASC").fetchall()
            return [r["action"] for r in rows if r["action"]]

    def list_operations(self, limit: int = 50) -> list[OperationEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, tool_id, output_path, summary, created_at
                FROM operation_history
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                OperationEntry(
                    id=r["id"],
                    tool_id=r["tool_id"],
                    output_path=r["output_path"],
                    summary=r["summary"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def remove_file(self, path: str) -> None:
        norm_path = os.path.abspath(path)
        with self._connect() as conn:
            conn.execute("DELETE FROM file_history WHERE file_path = ? OR file_path = ?", (norm_path, path))

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM file_history")
            conn.execute("DELETE FROM operation_history")

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM file_history").fetchone()
            return int(row["n"]) if row else 0

    def export_csv(self, csv_path: str) -> int:
        """Export SQLite file history records to a UTF-8 CSV file."""
        import csv

        entries = self.list_entries(limit=MAX_HISTORY_ROWS, existing_only=False)
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["File Name", "Full Path", "Action", "Size (Bytes)", "Pages", "Last Opened", "Open Count"])
            for e in entries:
                writer.writerow([
                    e.file_name,
                    e.file_path,
                    e.action,
                    e.file_size,
                    e.page_count,
                    e.last_opened_at,
                    e.open_count,
                ])
        return len(entries)

