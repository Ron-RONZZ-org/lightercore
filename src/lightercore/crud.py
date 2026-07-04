"""CRUD service base class — generic create/read/update/delete with UUID
prefix matching, soft-delete, and FTS hooks.

Usage::

    from lightercore.crud import CRUDService

    class MyService(CRUDService):
        def __init__(self, db):
            super().__init__(db, table="my_entities", trash_table="my_entities_trash")
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from lightercore.db import LighterbirdDB


def now() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


class CRUDService:
    """Generic CRUD service with UUID primary keys and soft-delete support."""

    def __init__(
        self,
        db: LighterbirdDB,
        table: str,
        trash_table: str | None = None,
        pk_column: str = "uuid",
    ) -> None:
        self.db = db
        self.table = table
        self._trash_table = trash_table
        self._pk_column = pk_column

    # ── Hooks (override in subclass) ───────────────────────────────────

    def _post_create(self, data: dict[str, Any]) -> None:
        """Called after successful create."""

    def _post_update(self, pk: str, old_data: dict[str, Any] | None, new_data: dict[str, Any]) -> None:
        """Called after successful update."""

    def _post_delete(self, pk: str, data: dict[str, Any] | None) -> None:
        """Called after successful delete."""

    # ── Read ───────────────────────────────────────────────────────────

    def list(
        self,
        order_by: str | None = None,
        direction: str = "DESC",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List entries, optionally ordered and limited."""
        if order_by is None:
            order_by = self._pk_column
        return self.db.execute(
            f"SELECT * FROM {self.table} ORDER BY {order_by} {direction} LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def get(self, pk: str) -> dict[str, Any] | None:
        """Get a single entry by primary key (supports prefix matching via LIKE)."""
        return self.db.execute_one(
            f"SELECT * FROM {self.table} WHERE {self._pk_column} LIKE ? COLLATE NOCASE",
            (f"{pk}%",),
        )

    def find_by_pk_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        """Find entries whose PK starts with the given prefix."""
        if not prefix:
            return []
        return self.db.execute(
            f"SELECT * FROM {self.table} WHERE {self._pk_column} LIKE ? "
            f"ORDER BY created_at DESC LIMIT ?",
            (f"{prefix}%", limit),
        )

    def count(self) -> int:
        """Return the number of entries in the table."""
        row = self.db.execute_one(f"SELECT COUNT(*) AS cnt FROM {self.table}")
        return row["cnt"] if row else 0

    def search(
        self,
        field: str,
        query: str,
        case_sensitive: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search entries by field containing a substring (LIKE)."""
        if case_sensitive:
            sql = f"SELECT * FROM {self.table} WHERE {field} LIKE ? LIMIT ?"
        else:
            sql = f"SELECT * FROM {self.table} WHERE LOWER({field}) LIKE LOWER(?) COLLATE NOCASE LIMIT ?"
        return self.db.execute(sql, (f"%{query}%", limit))

    # ── Write ──────────────────────────────────────────────────────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new entry with auto-generated UUID and timestamps.

        *data* is copied so the caller's dict is not mutated.
        """
        ts = now()
        data = dict(data)
        data.setdefault(self._pk_column, str(uuid.uuid4()))
        data.setdefault("created_at", ts)
        data["updated_at"] = ts

        columns = list(data.keys())
        placeholders = ", ".join(["?"] * len(columns))
        values = [data[k] for k in columns]

        with self.db.transaction() as conn:
            conn.execute(
                f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )

        self._post_create(data)
        return data

    def update(self, pk: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update an entry, preserving creation timestamp.

        Supports UUID prefix matching via LIKE.
        """
        old_data = self.get(pk)
        if not old_data:
            return None

        ts = now()
        data = dict(data)
        data["updated_at"] = ts

        columns = [k for k in data.keys()]
        set_clauses = [f"{k} = ?" for k in columns]
        values = [data[k] for k in columns] + [f"{pk}%"]

        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE {self.table} SET {', '.join(set_clauses)} WHERE {self._pk_column} LIKE ?",
                values,
            )

        self._post_update(pk, old_data, data)
        return self.get(pk)

    def delete(self, pk: str, soft: bool = True) -> bool:
        """Delete an entry.

        Args:
            pk: Primary key value (supports prefix matching).
            soft: If True and a trash table is configured, move to trash.
                  If False, permanent delete.
        """
        old_data = self.get(pk)
        if not old_data:
            return False

        if soft and self._trash_table:
            self._move_to_trash(pk)
        else:
            with self.db.transaction() as conn:
                conn.execute(
                    f"DELETE FROM {self.table} WHERE {self._pk_column} LIKE ?",
                    (f"{pk}%",),
                )

        self._post_delete(pk, old_data)
        return True

    # ── Trash management ───────────────────────────────────────────────

    def _move_to_trash(self, pk: str) -> None:
        """Move entry to trash table."""
        entry = self.get(pk)
        if not entry:
            return
        trash = dict(entry)
        trash["deleted_at"] = now()
        columns = list(trash.keys())
        placeholders = ", ".join(["?"] * len(columns))
        values = [trash[k] for k in columns]
        with self.db.transaction() as conn:
            conn.execute(
                f"INSERT INTO {self._trash_table} ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
            conn.execute(
                f"DELETE FROM {self.table} WHERE {self._pk_column} LIKE ?",
                (f"{pk}%",),
            )

    def list_trash(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """List soft-deleted entries."""
        if not self._trash_table:
            return []
        return self.db.execute(
            f"SELECT * FROM {self._trash_table} ORDER BY deleted_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def restore_from_trash(self, pk: str) -> dict[str, Any] | None:
        """Restore a soft-deleted entry.

        Returns the restored entry, or None if not found in trash.
        """
        if not self._trash_table:
            return None
        entry = self.db.execute_one(
            f"SELECT * FROM {self._trash_table} WHERE {self._pk_column} LIKE ?",
            (f"{pk}%",),
        )
        if not entry:
            return None
        restored = dict(entry)
        restored.pop("deleted_at", None)

        with self.db.transaction() as conn:
            conn.execute(
                f"DELETE FROM {self._trash_table} WHERE {self._pk_column} LIKE ?",
                (f"{pk}%",),
            )
            columns = list(restored.keys())
            values = [restored[k] for k in columns]
            placeholders = ", ".join(["?"] * len(columns))
            conn.execute(
                f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )

        return restored
