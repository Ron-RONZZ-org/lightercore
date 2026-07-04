"""SQLite database wrapper — WAL mode, per-thread connections, connection pooling.

Usage::

    from lightercore.db import LighterbirdDB

    db = LighterbirdDB(path)
    for row in db.execute("SELECT * FROM t"):
        ...
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any


class LighterbirdDB:
    """Thread-safe SQLite database with WAL mode and connection caching.

    Each thread gets its own connection (``threading.local``).  WAL mode
    is enabled on the first connection automatically.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        self._local = threading.local()

    # ── Connection management ──────────────────────────────────────────

    @property
    def _conn(self) -> sqlite3.Connection:
        """Get or create a per-thread connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._path, timeout=10.0)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def close(self) -> None:
        """Close the per-thread connection (if open)."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    # ── Query helpers ──────────────────────────────────────────────────

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Execute a query and return all rows as dicts."""
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def execute_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """Execute a query and return the first row as a dict, or ``None``."""
        cur = self._conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None

    def execute_many(self, sql: str, seq: list[tuple[Any, ...]]) -> None:
        """Execute a parameterised statement for every item in *seq*."""
        self._conn.executemany(sql, seq)
        self._conn.commit()

    # ── Transactions ───────────────────────────────────────────────────

    @property
    def in_transaction(self) -> bool:
        return self._conn.in_transaction

    def transaction(self) -> _Transaction:
        """Return a context manager for an explicit transaction.

        Auto-commits on success, rolls back on exception.
        """
        return _Transaction(self._conn)

    def begin(self) -> None:
        if not self.in_transaction:
            self._conn.execute("BEGIN")

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()


class _Transaction:
    """Context manager for explicit transaction control."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        self._conn.execute("BEGIN")
        return self._conn

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
