"""SQLite database wrapper with WAL mode and per-thread connection caching.

Merges the richer query methods from lighterbird's DB layer
(init_schema, table_exists, get_pragma_table_info, WAL checkpoint,
auto-commit, auto-mkdir) with semantika's backup() method using
SQLite online backup API.

Usage::

    from lightercore.db import LighterDB

    db = LighterDB(path)
    db.init_schema({"items": "CREATE TABLE items (uuid TEXT PRIMARY KEY, name TEXT)"})
    result = db.execute("SELECT * FROM items WHERE uuid LIKE ?", ("abc%",))
"""

from __future__ import annotations

import collections.abc
import sqlite3
import threading
import weakref
from pathlib import Path
from typing import Any


class LighterDB:
    """Thread-safe SQLite database with WAL mode and per-thread connections.

    Connections are cached per-thread via ``threading.local``.
    Each thread gets its own ``sqlite3.Connection``, avoiding the
    ``ProgrammingError: SQLite objects created in a thread can only be
    used in that same thread`` error.

    Within a single thread, the connection is lazily created on first use
    and reused for subsequent queries.

    Connections are automatically closed via ``weakref.finalize`` when
    the ``LighterDB`` instance is garbage-collected.  This prevents
    ``ResourceWarning: unclosed database`` in long-running processes
    and test suites.  For connections that live on a different thread
    (where the finalizer cannot reach them), the per-thread cache is
    reclaimed when that thread terminates.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        after_connect: collections.abc.Callable[[sqlite3.Connection], None] | None = None,
    ) -> None:
        """Initialize the database.

        Args:
            path: Path to the SQLite database file.
            after_connect: Optional callback invoked on each new SQLite
                connection (e.g. to load extensions like sqlite-vec).
                Called once per thread since connections are cached per thread.
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._after_connect = after_connect
        self._local = threading.local()
        weakref.finalize(self, LighterDB.close, self)

    # ── Connection management ──────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create a per-thread connection with WAL mode."""
        conn = getattr(self._local, "_conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA wal_autocheckpoint=100")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.row_factory = sqlite3.Row
            if self._after_connect:
                self._after_connect(conn)
            self._local._conn = conn
        return conn

    def close(self) -> None:
        """Checkpoint WAL and close the calling thread's connection."""
        conn = getattr(self._local, "_conn", None)
        if conn is not None:
            try:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            self._local._conn = None

    # ── Query helpers ──────────────────────────────────────────────────

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Execute SQL and return results as dicts. Auto-commits."""
        conn = self._get_conn()
        cursor = conn.execute(sql, params or ())
        rows = cursor.fetchall()
        conn.commit()
        return [dict(r) for r in rows]

    def execute_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """Execute SQL and return first result, or None."""
        results = self.execute(sql, params)
        return results[0] if results else None

    def execute_many(self, sql: str, params_list: list[tuple[Any, ...]]) -> None:
        """Execute SQL with multiple parameter sets. Auto-commits."""
        conn = self._get_conn()
        conn.executemany(sql, params_list)
        conn.commit()

    # ── Transactions ───────────────────────────────────────────────────

    def transaction(self):
        """Context manager yielding a connection with auto-commit/rollback."""

        class _TransactionContext:
            def __init__(self, db: LighterDB):
                self.db = db

            def __enter__(self):
                return self.db._get_conn()

            def __exit__(self, exc_type, exc_val, exc_tb):
                conn = self.db._get_conn()
                if exc_type is None:
                    conn.commit()
                else:
                    conn.rollback()

        return _TransactionContext(self)

    # ── Schema helpers ─────────────────────────────────────────────────

    def init_schema(self, schema: dict[str, str]) -> None:
        """Initialize database tables from a schema dict.

        Args:
            schema: Mapping of table_name → CREATE TABLE SQL.
                Tables that already exist are skipped.
        """
        conn = self._get_conn()
        for table, sql in schema.items():
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if cursor.fetchone() is None:
                conn.executescript(sql)
        conn.commit()

    def get_pragma_table_info(self, table: str) -> list[dict[str, Any]]:
        """Return PRAGMA table_info for a table.

        Returns:
            List of column dicts with keys: cid, name, type, notnull, dflt_value, pk.
        """
        return self.execute(f"PRAGMA table_info({table})")

    def table_exists(self, name: str) -> bool:
        """Check if a table exists in the database."""
        return self.execute_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ) is not None

    # ── Migrations ──────────────────────────────────────────────────────

    def migrate(self, migrations: list[tuple[int, str]]) -> None:
        """Apply pending schema migrations in forward-only order.

        Each migration is wrapped in its own transaction so that a
        partially-applied migration (e.g. due to a crash) does not
        leave the database in an inconsistent state.  If a migration
        fails, the transaction is rolled back and the exception is
        re-raised; subsequent migrations are *not* attempted.

        The current schema version is stored in ``PRAGMA user_version``.

        Args:
            migrations: Ordered list of ``(version, sql)`` tuples.
                Version ``1`` should create the initial schema (or be
                the first diff).  Each version must be strictly greater
                than the previous one.

        Raises:
            ValueError: If migrations are not in strictly ascending
                version order or if they start with version ``0``.
            sqlite3.DatabaseError: If a migration SQL statement fails.

        Usage::

            MIGRATIONS = [
                (1, "CREATE TABLE items (uuid TEXT PRIMARY KEY, name TEXT)"),
                (2, "ALTER TABLE items ADD COLUMN description TEXT"),
            ]
            db.migrate(MIGRATIONS)
        """
        if not migrations:
            return

        # Validate ordering
        versions = [v for v, _ in migrations]
        if versions != sorted(set(versions)):
            raise ValueError(
                f"Migrations must be in strictly ascending order "
                f"with no duplicates. Got versions: {versions}"
            )
        if versions[0] < 1:
            raise ValueError(
                f"Migration versions must start at 1 or higher. "
                f"Got version {versions[0]}"
            )

        row = self.execute_one("PRAGMA user_version")
        current = row["user_version"] if row else 0

        for version, sql in migrations:
            if version > current:
                with self.transaction() as conn:
                    conn.executescript(sql)
                    conn.execute(f"PRAGMA user_version = {version}")

    # ── Backup ─────────────────────────────────────────────────────────

    def backup(self, dest_path: str | Path) -> None:
        """Backup the database to *dest_path* using SQLite's online backup API.

        Produces a consistent snapshot even while the database is in use.
        """
        dest = sqlite3.connect(str(dest_path))
        try:
            conn = self._get_conn()
            conn.backup(dest)
        finally:
            dest.close()
