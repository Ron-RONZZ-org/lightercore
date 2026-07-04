# AGENTS-paths.md — Paths Module

## Summary
XDG-compliant directory resolution with sentinel-based protection against accidental deletion.

## Key Functions
- `data_dir()`, `config_dir()`, `cache_dir()`, `state_dir()` — resolve standard directories
- `ensure_dirs()` — create + protect all standard dirs
- `protect_directory(path)` — add `.lighterbird-protected` sentinel
- `safe_rmtree(path)` / `safe_unlink(path)` — refuse deletion on protected paths
- `is_protected(path)` — check sentinel up the ancestor chain

## Environment Variables
Resolution order: `LIGHTERCORE_<CATEGORY>_DIR` → `LIGHTERBIRD_<CATEGORY>_DIR` → `SEMANTIKA_<CATEGORY>_DIR` → XDG default. This ensures backward compatibility for both downstream projects.

## Constraints
- Sentinel file is `.lighterbird-protected` (shared across all downstream projects).
- `safe_rmtree` / `safe_unlink` raise `ProtectedPathError` unless `force=True`.
