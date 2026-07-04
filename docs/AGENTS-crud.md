# AGENTS-crud.md — CRUD Module

## Summary
Generic CRUD service base class with UUID primary keys, prefix matching, timestamps, and optional soft-delete via a trash table.

## Key Class
- **`CRUDService(db, table, trash_table=None, pk_column="uuid")`**

## Features
- **Auto-generated UUIDs** — set via `data.setdefault("uuid", ...)` in `create()`.
- **Timestamps** — `created_at` (immutable after create) and `updated_at` (set on create and update).
- **UUID prefix matching** — `get()`, `update()`, `delete()` use `LIKE ?` with `f"{pk}%"`, so users can type short prefixes.
- **Soft-delete** — when `trash_table` is set, `delete(soft=True)` moves entries to the trash table.
- **Hooks** — override `_post_create`, `_post_update`, `_post_delete` for side effects.

## Constraints
- Primary key column defaults to `uuid` — override via `pk_column`.
- Trash table is optional; if not set, `delete(soft=False)` does a permanent delete.
- `search()` uses `LIKE` with `%query%` — not FTS5. Add FTS support at the domain-service level.
