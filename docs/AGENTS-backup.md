# AGENTS-backup.md — Backup Module

## Summary
Multi-strategy backup/restore system using 7z archives with SHA-256 integrity verification and external directory sync.

## Key Concepts
- **Strategy** — a named backup configuration (retention, schedule, target). Stored in `~/.config/lighterbird/backup.json`.
- **Auto-discovery** — `get_backup_targets()` scans `data_dir()/*.db` and `config_dir()/*.md` — no registration needed.
- **7z archives** — per-strategy archives bundle all DBs + config. Uses LZMA2 compression.
- **Single-DB backup** — `backup_database()` uses SQLite's online backup API for consistent single-file snapshots.

## Key Functions
- `backup_all_strategies()` — backup all DBs with every enabled strategy
- `list_backups()` — list all available backups, newest first
- `restore_latest(target_dir)` — restore newest backup per stem
- `export_data(output_dir)` — create portable 7z with manifest
- `import_data(arc_path)` — import from exported 7z with SHA-256 verification
- `add_strategy()`, `update_strategy()`, `remove_strategy()` — manage strategies
- `prune_old_backups()` — enforce retention limits

## Constraints
- Requires `py7zr` (LZMA2 compression). Falls back to `.db` snapshots for single-DB tools.
- External sync (`target != "local"`) is best-effort — failures are logged, not raised.
- SHA-256 verification is performed on every copy — mismatches raise `OSError`.
