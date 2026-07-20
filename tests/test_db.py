"""Tests for LighterDB — the SQLite database wrapper."""

from __future__ import annotations

import sqlite3

import pytest

from lightercore.db import LighterDB


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path):
    """Fresh in-memory LighterDB for each test."""
    test_db = LighterDB(tmp_path / "test.db")
    yield test_db


# ── migrate() tests ───────────────────────────────────────────────────


def test_migrate_applies_pending_migrations(db):
    """Migrations in ascending order are applied sequentially."""
    db.migrate([
        (1, "CREATE TABLE t1 (id INTEGER PRIMARY KEY)"),
        (2, "CREATE TABLE t2 (id INTEGER PRIMARY KEY)"),
    ])

    assert db.table_exists("t1")
    assert db.table_exists("t2")


def test_migrate_applies_partial_range(db):
    """Starting from version 2 skips version 1 if already applied."""
    db.migrate([
        (1, "CREATE TABLE t1 (id INTEGER PRIMARY KEY)"),
    ])
    db.migrate([
        (2, "CREATE TABLE t2 (id INTEGER PRIMARY KEY)"),
    ])
    assert db.table_exists("t1")
    assert db.table_exists("t2")


def test_migrate_idempotent(db):
    """Running migrate() twice on an up-to-date DB does nothing."""
    db.migrate([
        (1, "CREATE TABLE t1 (id INTEGER PRIMARY KEY)"),
    ])
    db.migrate([
        (1, "CREATE TABLE t1 (id INTEGER PRIMARY KEY)"),
    ])
    # No crash = pass


def test_migrate_skips_already_applied(db):
    """Only pending migrations (version > current) are applied."""
    db.migrate([
        (1, "CREATE TABLE t1 (id INTEGER PRIMARY KEY)"),
    ])

    applied_versions = []

    # Monkey-patch execute to track which migrations run
    orig_execute = db.execute

    def tracking_execute(sql, params=()):
        if sql.startswith("PRAGMA user_version"):
            pass
        applied_versions.append(sql)
        return orig_execute(sql, params)

    db.execute = tracking_execute

    db.migrate([
        (1, "CREATE TABLE t1 (id INTEGER PRIMARY KEY)"),
        (2, "CREATE TABLE t2 (id INTEGER PRIMARY KEY)"),
    ])

    # Migration 1 should NOT have run again; migration 2 should have
    assert db.table_exists("t2")


def test_migrate_rejects_out_of_order(db):
    """Non-ascending versions raise ValueError."""
    with pytest.raises(ValueError, match="strictly ascending"):
        db.migrate([
            (2, "CREATE TABLE t2 (id INTEGER PRIMARY KEY)"),
            (1, "CREATE TABLE t1 (id INTEGER PRIMARY KEY)"),
        ])


def test_migrate_rejects_duplicate_versions(db):
    """Duplicate versions raise ValueError."""
    with pytest.raises(ValueError, match="strictly ascending|duplicates"):
        db.migrate([
            (1, "CREATE TABLE t1 (id INTEGER PRIMARY KEY)"),
            (1, "CREATE TABLE t1_dup (id INTEGER PRIMARY KEY)"),
        ])


def test_migrate_rejects_version_zero(db):
    """Version 0 is not allowed (PRAGMA user_version defaults to 0)."""
    with pytest.raises(ValueError, match="start at 1"):
        db.migrate([
            (0, "CREATE TABLE t0 (id INTEGER PRIMARY KEY)"),
        ])


def test_migrate_empty_list_is_noop(db):
    """Empty migration list is a no-op."""
    db.migrate([])  # No crash = pass


def test_migrate_rolls_back_on_failure(db):
    """A failed migration rolls back and does not update user_version."""
    # Apply version 1 successfully
    db.migrate([
        (1, "CREATE TABLE good (id INTEGER PRIMARY KEY)"),
    ])

    # Version 2 is invalid SQL → should fail and roll back
    with pytest.raises(sqlite3.DatabaseError):
        db.migrate([
            (2, "CREATEEEE TABLE bad (id INTEGER PRIMARY KEY)"),  # typo: CREATEEEE
        ])

    # PRAGMA user_version should still be 1
    row = db.execute_one("PRAGMA user_version")
    assert row["user_version"] == 1


def test_migrate_pragma_user_version_updated(db):
    """PRAGMA user_version reflects the highest applied version."""
    db.migrate([
        (1, "CREATE TABLE t1 (id INTEGER PRIMARY KEY)"),
        (2, "CREATE TABLE t2 (id INTEGER PRIMARY KEY)"),
    ])

    row = db.execute_one("PRAGMA user_version")
    assert row["user_version"] == 2


def test_migrate_works_with_init_schema(db):
    """migrate() works alongside init_schema() for hybrid setups."""
    schema = {
        "items": "CREATE TABLE items (uuid TEXT PRIMARY KEY, name TEXT)",
    }
    db.init_schema(schema)
    assert db.table_exists("items")

    # Now apply a migration that adds a column
    db.migrate([
        (1, "ALTER TABLE items ADD COLUMN description TEXT DEFAULT ''"),
    ])

    info = db.get_pragma_table_info("items")
    cols = [c["name"] for c in info]
    assert "description" in cols
