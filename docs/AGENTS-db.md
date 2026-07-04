# AGENTS-db.md — Database Module

## Summary
Thread-safe SQLite3 wrapper with WAL mode, per-thread connection caching, and explicit transaction support.

## Key Classes
- **`LighterbirdDB(path)`** — main database handle. Use `execute()`, `execute_one()`, `transaction()`.

## Constraints
- WAL mode enabled automatically on first connection.
- Foreign keys enabled on first connection.
- Each Python thread gets its own `sqlite3.Connection` (via `threading.local()`).
- The connection is created lazily on first query.

## Safety
- `_Transaction` context manager auto-commits on success, rolls back on exception.
- `close()` clears the thread-local connection — safe to call multiple times.
