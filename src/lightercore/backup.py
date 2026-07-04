"""Timestamped, checksum-verified backups for lightercore-based applications.

Supports:

- Multi-strategy backup configurations (scheduled, retention, external targets)
- ``.7z`` archives bundling all databases + optional config files
- SQLite online backup API for consistent snapshots
- Export/import with SHA-256 manifest integrity verification
- External directory sync (Nextcloud, Dropbox, rsync, etc.)

Usage::

    from lightercore.backup import (
        backup_all_strategies,
        list_backups,
        restore_latest,
        export_data,
        import_data,
    )
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import time
import zipfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import py7zr

from lightercore.paths import config_dir, data_dir

# ── Defaults ──────────────────────────────────────────────────────────────

_BACKUP_SUBDIR = ".backups"
_CONFIG_FILENAME = "backup.json"
_CONFIG_VERSION = 3
_DEFAULT_MAX_COPIES = 10


# ── Dataclasses ────────────────────────────────────────────────────────────


class BackupTarget:
    """A single file that should be backed up (or restored/exported).

    Attributes:
        path:     Absolute filesystem path.
        category: ``"data"`` (restore to ``data_dir``) or ``"config"``.
        module:   Module name (e.g. ``"email"``, ``"graph"``).
        label:    Human-readable description (e.g. ``"Email database"``).
    """

    def __init__(
        self,
        path: Path,
        category: str = "data",
        module: str = "",
        label: str = "",
    ) -> None:
        self.path = path
        self.category = category
        self.module = module
        self.label = label

    def __repr__(self) -> str:
        return f"BackupTarget({self.path.name}, category={self.category})"


class BackupStrategy:
    """A named backup policy.

    Attributes:
        id: Unique kebab-case identifier (e.g. ``"daily"``, ``"hourly"``).
        label: Human-readable name for display.
        interval_minutes: How often to auto-backup in minutes.
            0 means on-demand (only via ``!backup now``).
        max_copies: Maximum number of backups to keep per database stem.
        target: ``"local"`` (default backup dir) or an absolute path to
            an external/synced directory.
        enabled: Whether this strategy is active.
        last_backup_at: ISO-8601 timestamp of the last successful backup,
            or empty string if never backed up.
    """

    def __init__(
        self,
        id: str,
        label: str = "",
        interval_minutes: int = 0,
        max_copies: int = _DEFAULT_MAX_COPIES,
        target: str = "local",
        enabled: bool = True,
        last_backup_at: str = "",
    ) -> None:
        self.id = id
        self.label = label or id
        self.interval_minutes = interval_minutes
        self.max_copies = max_copies
        self.target = target
        self.enabled = enabled
        self.last_backup_at = last_backup_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "max_copies": self.max_copies,
            "target": self.target,
            "last_backup_at": self.last_backup_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BackupStrategy:
        return cls(
            id=d.get("id", ""),
            label=d.get("label", ""),
            interval_minutes=d.get("interval_minutes", 0),
            max_copies=d.get("max_copies", _DEFAULT_MAX_COPIES),
            target=d.get("target", "local"),
            enabled=d.get("enabled", True),
            last_backup_at=d.get("last_backup_at", ""),
        )


def resolve_target_path(strategy: dict[str, Any]) -> str:
    """Resolve a strategy's target to an absolute path.

    ``"local"`` is resolved to the default backup directory.
    """
    target = strategy.get("target", "local")
    if target == "local" or not target:
        return str(_backup_dir())
    return str(Path(target).expanduser().resolve())


def get_strategy(strategy_id: str) -> dict[str, Any] | None:
    """Return a single strategy dict by id, or ``None``."""
    for s in list_strategies():
        if s["id"] == strategy_id:
            return s
    return None


# ── Internal helpers ──────────────────────────────────────────────────────


def _backup_dir() -> Path:
    """Return the backup directory (created on first access)."""
    bd = data_dir() / _BACKUP_SUBDIR
    bd.mkdir(parents=True, exist_ok=True)
    return bd


def _config_path() -> Path:
    """Return the backup config file path."""
    return config_dir() / _CONFIG_FILENAME


def _timestamp() -> str:
    """Return a sortable ISO-like timestamp (microsecond precision).

    Format: ``YYYYMMDDTHHMMSSuuuuuu`` — no colons, spaces, or dots,
    so it is safe for filenames.
    """
    nsec = time.time_ns()
    usec = (nsec // 1000) % 1_000_000
    return time.strftime("%Y%m%dT%H%M%S", time.gmtime(nsec / 1_000_000_000)) + f"{usec:06d}"


def _sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    h = sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _copy_with_verify(src: Path, dst: Path) -> None:
    """Copy *src* to *dst* and verify SHA-256 matches."""
    shutil.copy2(str(src), str(dst))
    src_sha = _sha256(src)
    dst_sha = _sha256(dst)
    if src_sha != dst_sha:
        dst.unlink(missing_ok=True)
        raise OSError(
            f"Checksum mismatch after copy: {src.name} "
            f"(expected {src_sha[:12]}, got {dst_sha[:12]})"
        )


def _checkpoint_db(db_path: Path) -> None:
    """Force-checkpoint the WAL into the main database file.

    Opens a temporary SQLite connection in WAL mode and runs
    ``wal_checkpoint(TRUNCATE)`` to flush all pending WAL data
    to the main ``.db`` file before it is backed up.
    """
    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except sqlite3.Error:
        pass  # best-effort


def _checkpoint_known_dbs(db_dir: Path | None = None) -> None:
    """Checkpoint all discovered databases before backup.

    Flushes WAL → main DB for every ``.db`` file found in *db_dir*.
    """
    for db_path in _known_db_paths(db_dir):
        _checkpoint_db(db_path)


# ── DB discovery ───────────────────────────────────────────────────────────


def get_backup_targets(
    *,
    db_dir: Path | None = None,
    cfg_dir: Path | None = None,
    category: str | None = None,
) -> list[BackupTarget]:
    """Auto-discover files to back up by scanning directories.

    Discovery strategy:

    1. Scan ``db_dir/*.db`` — any SQLite database is included.
    2. Scan ``cfg_dir/*.md`` — Markdown config files are included.

    This means a new module that places ``<module>.db`` in the data
    directory is *automatically* backed up — no registration needed.

    Args:
        db_dir: Database directory (defaults to ``data_dir()``).
        cfg_dir: Config directory (defaults to ``config_dir()``).
        category: If set, filter to only ``"data"`` or ``"config"``.

    Returns:
        Deduplicated list of :class:`BackupTarget` sorted by path.
    """
    dd = db_dir or data_dir()
    cd = cfg_dir or config_dir()
    targets: list[BackupTarget] = []
    seen: set[Path] = set()

    if dd.is_dir():
        for p in sorted(dd.glob("*.db")):
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                targets.append(BackupTarget(
                    path=p,
                    category="data",
                    module=p.stem,
                    label=f"{p.stem} database",
                ))

    if cd.is_dir():
        for p in sorted(cd.glob("*.md")):
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                targets.append(BackupTarget(
                    path=p,
                    category="config",
                    module=p.stem,
                    label=f"{p.stem} config",
                ))

    if category:
        targets = [t for t in targets if t.category == category]
    return targets


def _known_db_paths(db_dir: Path | None = None) -> list[Path]:
    """Return paths to all discovered database files."""
    return [t.path for t in get_backup_targets(db_dir=db_dir, category="data")]


def _known_config_files(cfg_dir: Path | None = None) -> list[Path]:
    """Return paths to all discovered config files."""
    return [t.path for t in get_backup_targets(cfg_dir=cfg_dir, category="config")]


# ── Strategy config ────────────────────────────────────────────────────────


def _load_raw_config() -> dict[str, Any]:
    """Load the backup config JSON, returning an empty dict on failure."""
    cfg_path = _config_path()
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_raw_config(cfg: dict[str, Any]) -> None:
    """Write the backup config JSON."""
    cfg_path = _config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _migrate_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Migrate older config formats to the current strategy-based format."""
    # Strip unknown top-level keys, keeping only allowed ones
    allowed = {"version", "strategies", "external_dir", "retention",
               "interval_minutes", "last_backup_at"}
    cleaned = {k: v for k, v in raw.items() if k in allowed}

    # v1: flat config with optional external_dir
    if "strategies" not in cleaned:
        ext_dir = cleaned.get("external_dir", "")
        retention = cleaned.get("retention", _DEFAULT_MAX_COPIES)
        cleaned["strategies"] = [
            {
                "id": "default",
                "label": "Default",
                "enabled": True,
                "interval_minutes": cleaned.get("interval_minutes", 0),
                "max_copies": int(retention),
                "target": ext_dir if ext_dir else "local",
            }
        ]
        # Preserve last_backup_at if it exists
        if cleaned.get("last_backup_at"):
            cleaned["strategies"][0]["last_backup_at"] = cleaned["last_backup_at"]
        cleaned.pop("external_dir", None)
        cleaned.pop("interval_minutes", None)
        cleaned.pop("last_backup_at", None)
        cleaned.pop("retention", None)
    cleaned.setdefault("version", _CONFIG_VERSION)
    return cleaned


def list_strategies() -> list[dict[str, Any]]:
    """Return the list of configured backup strategies.

    Returns a default strategy if no config exists.
    """
    raw = _load_raw_config()
    if not raw:
        return [{"id": "default", "label": "Default", "enabled": True,
                 "interval_minutes": 0, "max_copies": _DEFAULT_MAX_COPIES,
                 "target": "local", "last_backup_at": ""}]
    raw = _migrate_config(raw)
    return raw.get("strategies", [])


def load_config() -> dict[str, Any]:
    """Load the full backup config, migrating if needed.

    Returns a dict with ``"version"`` and ``"strategies"`` keys.
    """
    raw = _load_raw_config()
    if not raw:
        return {
            "version": _CONFIG_VERSION,
            "strategies": list_strategies(),
        }
    return _migrate_config(raw)


def save_config(cfg: dict[str, Any]) -> None:
    """Validate and persist the backup config."""
    seen_ids: set[str] = set()
    for s in cfg.get("strategies", []):
        # Validate strategy ID: lowercase, kebab-case
        sid = s.get("id", "")
        if not re.match(r"^[a-z][a-z0-9-]*$", sid):
            raise ValueError(
                f"Strategy ID must match [a-z][a-z0-9-]* (got {sid!r})"
            )
        if sid in seen_ids:
            raise ValueError(f"Duplicate strategy ID: {sid}")
        seen_ids.add(sid)
        # Validate max_copies
        mc = s.get("max_copies", _DEFAULT_MAX_COPIES)
        if not isinstance(mc, int) or mc < 1:
            try:
                mc = int(mc)
            except (ValueError, TypeError):
                raise ValueError(
                    f"max_copies must be a positive integer (got {mc!r})"
                )
            s["max_copies"] = mc
        s.setdefault("enabled", True)
        s.setdefault("max_copies", _DEFAULT_MAX_COPIES)
        s.setdefault("target", "local")
    _save_raw_config(cfg)


def add_strategy(
    strategy_id_or_obj: str | BackupStrategy,
    *,
    label: str = "",
    interval_minutes: int = 0,
    max_copies: int = _DEFAULT_MAX_COPIES,
    target: str = "local",
    enabled: bool = True,
) -> dict[str, Any]:
    """Add a new backup strategy.

    Accepts either a ``BackupStrategy`` object or keyword arguments.
    """
    cfg = load_config()
    if isinstance(strategy_id_or_obj, BackupStrategy):
        entry = strategy_id_or_obj.to_dict()
    else:
        strategy_id = strategy_id_or_obj
        if any(s["id"] == strategy_id for s in cfg["strategies"]):
            raise ValueError(f"Strategy '{strategy_id}' already exists")
        entry = {
            "id": strategy_id,
            "label": label or strategy_id,
            "enabled": enabled,
            "interval_minutes": interval_minutes,
            "max_copies": max_copies,
            "target": target,
        }
    if any(s["id"] == entry["id"] for s in cfg["strategies"]):
        raise ValueError(f"Strategy '{entry['id']}' already exists")
    cfg["strategies"].append(entry)
    save_config(cfg)
    return entry


def update_strategy(
    strategy_id: str,
    *updates_dict: dict[str, Any],
    **updates: Any,
) -> dict[str, Any] | None:
    """Update fields on an existing strategy.

    Accepts either keyword arguments or a single dict (backward-compat).
    """
    # Merge positional dict and keyword args
    all_updates: dict[str, Any] = {}
    if updates_dict:
        all_updates.update(updates_dict[0])
    all_updates.update(updates)

    cfg = load_config()
    for s in cfg["strategies"]:
        if s["id"] == strategy_id:
            for key in ("label", "enabled", "interval_minutes", "max_copies", "target"):
                if key in all_updates:
                    s[key] = all_updates[key]
            save_config(cfg)
            return s
    return None


def remove_strategy(strategy_id: str) -> bool:
    """Remove a strategy by ID. Returns False if not found."""
    cfg = load_config()
    before = len(cfg["strategies"])
    cfg["strategies"] = [s for s in cfg["strategies"] if s["id"] != strategy_id]
    if len(cfg["strategies"]) < before:
        save_config(cfg)
        return True
    return False


# ── 7z archive helpers ────────────────────────────────────────────────────


def _archive_filename(strategy_id: str, ts: str) -> str:
    return f"backup_{strategy_id}_{ts}.7z"


def _create_strategy_archive(
    strategy: dict[str, Any],
    *,
    db_dir: Path | None = None,
    cfg_dir: Path | None = None,
    include_config: bool = True,
) -> Path | None:
    """Create a 7z archive containing all known databases (+ optional config).

    Returns:
        Path to the created archive, or ``None`` if no data files exist.
    """
    for db_path in _known_db_paths(db_dir):
        _checkpoint_db(db_path)

    db_paths = _known_db_paths(db_dir)
    if not db_paths:
        return None

    backup_dir = _backup_dir()
    ts = _timestamp()
    strategy_id = strategy["id"]
    arc_path = backup_dir / _archive_filename(strategy_id, ts)

    files_to_archive: list[tuple[Path, str]] = []
    for dbp in db_paths:
        files_to_archive.append((dbp, dbp.name))
    if include_config:
        for cfp in _known_config_files(cfg_dir):
            files_to_archive.append((cfp, f"config/{cfp.name}"))

    try:
        with py7zr.SevenZipFile(
            arc_path, mode="w", filters=[{"id": py7zr.FILTER_LZMA2}]
        ) as arc:
            for src_path, arc_name in files_to_archive:
                arc.write(src_path, arc_name)
    except Exception as exc:
        arc_path.unlink(missing_ok=True)
        raise OSError(f"Failed to create backup archive: {exc}") from exc

    _copy_to_external(strategy, arc_path)
    _update_last_backup(strategy_id)
    return arc_path


def _extract_archive(arc_path: Path, target_dir: Path) -> list[Path]:
    """Extract a 7z backup archive into *target_dir*.

    Returns:
        List of extracted file paths.
    """
    with py7zr.SevenZipFile(arc_path, mode="r") as arc:
        arc.extractall(path=target_dir)
    arc_names = set()
    with py7zr.SevenZipFile(arc_path, mode="r") as arc:
        arc_names = set(arc.getnames())

    extracted: list[Path] = []
    for f in target_dir.iterdir():
        if f.is_file() and f.name in arc_names:
            extracted.append(f)
    config_dir_path = target_dir / "config"
    if config_dir_path.is_dir():
        for f in config_dir_path.iterdir():
            rel = f"config/{f.name}"
            if rel in arc_names:
                extracted.append(f)
    return extracted


# ── External copy helper ──────────────────────────────────────────────────


def _copy_to_external(strategy: dict[str, Any], arc_path: Path) -> None:
    """Copy the backup archive to the strategy's external target."""
    target = strategy.get("target", "local")
    if target and target != "local":
        try:
            dst_root = Path(target).expanduser().resolve()
            dst_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(arc_path), str(dst_root / arc_path.name))
        except OSError:
            pass  # best-effort


def _update_last_backup(strategy_id: str) -> None:
    """Update the last_backup_at timestamp on a strategy."""
    try:
        cfg = load_config()
        for s in cfg["strategies"]:
            if s["id"] == strategy_id:
                s["last_backup_at"] = datetime.now(timezone.utc).isoformat()
                save_config(cfg)
                break
    except (OSError, ValueError):
        pass


# ── Public API: Backup ─────────────────────────────────────────────────────


def backup_all_strategies(
    *,
    db_dir: Path | None = None,
    cfg_dir: Path | None = None,
) -> list[Path]:
    """Backup all known databases for every enabled strategy.

    Each strategy produces a single 7z archive containing all DBs +
    optional config files.

    Returns:
        List of backup archive paths created.
    """
    strategies = list_strategies()
    if not strategies:
        strategies = [
            {
                "id": "default",
                "label": "Default",
                "enabled": True,
                "max_copies": _DEFAULT_MAX_COPIES,
                "target": "local",
            }
        ]

    created: list[Path] = []
    for strategy in strategies:
        if not strategy.get("enabled", True):
            continue
        result = _create_strategy_archive(strategy, db_dir=db_dir, cfg_dir=cfg_dir)
        if result is not None:
            _prune_archives_for_strategy(
                strategy["id"],
                retention=strategy["max_copies"],
            )
            created.append(result)
    return created


def backup_database(
    db_path: Path,
    *,
    strategy: dict[str, Any] | None = None,
    retention: int | None = None,
) -> Path | None:
    """Create a single-DB backup tagged with a strategy (backward-compatible).

    This is a convenience wrapper for tools that only manage one database
    (e.g. semantika).  Uses the same strategy-based config system but
    produces a single ``.db`` file.

    Args:
        db_path: Path to the source database file.
        strategy: Strategy dict. If ``None``, uses the first enabled
            strategy or a default.
        retention: Override max_copies for this backup. Takes precedence
            over the strategy's ``max_copies`` when set.

    Returns:
        Path to the created backup file, or ``None`` if *db_path* does
        not exist.
    """
    if not db_path.exists():
        return None

    _checkpoint_db(db_path)

    if strategy is None:
        strategies = list_strategies()
        strategy = next(
            (s for s in strategies if s.get("enabled", True)),
            {"id": "default", "max_copies": _DEFAULT_MAX_COPIES, "target": "local"},
        )

    backup_dir = _backup_dir()
    ts = _timestamp()
    strategy_id = strategy["id"]
    stem = db_path.stem
    filename = f"{stem}_{strategy_id}_{ts}.db"
    backup_path = backup_dir / filename

    # Copy with SHA-256 verification (byte-identical)
    _copy_with_verify(db_path, backup_path)

    _copy_to_external(strategy, backup_path)
    # retention=0 means "use default" (backward-compat with lighterbird)
    effective_retention = retention if retention else strategy.get("max_copies", _DEFAULT_MAX_COPIES)
    _prune_for_stem_and_strategy(stem, strategy_id, retention=effective_retention)
    _update_last_backup(strategy_id)

    return backup_path


def backup_all(*, retention: int | None = None) -> list[Path]:
    """Backup all known databases (compatibility wrapper).

    Delegates to :func:`backup_all_strategies` if strategies are configured;
    otherwise creates a single multi-DB archive.
    """
    cfg = load_config()
    if cfg.get("strategies"):
        return backup_all_strategies()
    default = {
        "id": "default",
        "max_copies": retention or _DEFAULT_MAX_COPIES,
        "target": "local",
    }
    arc = _create_strategy_archive(default)
    return [arc] if arc else []


def copy_to_external(
    target_dir: str | Path,
    *,
    backup_paths: list[Path] | None = None,
) -> list[Path]:
    """Copy backup files to an external (e.g. synced) directory.

    This is the "dumb simple" remote backup: point it at a directory
    that happens to be synced by Nextcloud, Dropbox, etc.
    """
    dst_root = Path(target_dir).expanduser().resolve()
    dst_root.mkdir(parents=True, exist_ok=True)

    if backup_paths is None:
        backup_paths = [b["path"] for b in list_backups()]

    copied: list[Path] = []
    for bp in backup_paths:
        dst = dst_root / bp.name
        shutil.copy2(str(bp), str(dst))
        copied.append(dst)
    return copied


# ── Public API: Test strategy ─────────────────────────────────────────────


def test_strategy(
    strategy: dict[str, Any] | str,
) -> dict[str, bool | str]:
    """Test a backup strategy by verifying the target is writable.

    Args:
        strategy: Strategy dict, or a string ID to look up from config.

    Returns:
        Dict with keys: ``success``, ``message``, and optionally ``error``.
    """
    if isinstance(strategy, str):
        s = get_strategy(strategy)
        if s is None:
            return {"success": False, "message": f"Strategy '{strategy}' not found"}
        strategy = s
    try:
        backup_dir = _backup_dir()
        probe = backup_dir / ".probe"
        probe.write_text("probe", encoding="utf-8")
        probe.unlink()

        target = strategy.get("target", "local")
        if target and target != "local":
            dst_root = Path(target).expanduser().resolve()
            dst_root.mkdir(parents=True, exist_ok=True)
            probe2 = dst_root / ".probe"
            probe2.write_text("probe", encoding="utf-8")
            probe2.unlink()

        return {"success": True, "message": f"Target is writable: {target}"}
    except OSError as e:
        return {
            "success": False,
            "message": f"Target is NOT writable: {target}",
            "error": str(e),
        }


# ── Public API: List / Restore / Prune ─────────────────────────────────────


def list_backups() -> list[dict[str, Any]]:
    """List all available backup files, newest first.

    Returns a list of dicts with keys: ``path``, ``stem``, ``strategy``,
    ``timestamp``, ``size_bytes``, ``modified``.
    """
    bdir = _backup_dir()
    if not bdir.is_dir():
        return []

    # Pattern for "{stem}_{strategy}_{timestamp}.db" (variable-length timestamp)
    pat = re.compile(r"^(.+?)_([a-z][a-z0-9-]*?)_(\d{8}T\d{10,})\.db$")
    # Pattern for "backup_{strategy}_{timestamp}.7z" (archive style)
    arc_pat = re.compile(r"^backup_([a-z][a-z0-9-]*?)_(\d{8}T\d{10,})\.7z$")

    entries: list[dict[str, Any]] = []
    for p in sorted(bdir.iterdir()):
        if p.suffix not in (".db", ".7z"):
            continue
        m = pat.match(p.name)
        if m:
            entries.append({
                "path": p,
                "stem": m.group(1),
                "strategy": m.group(2),
                "timestamp": m.group(3),
                "size_bytes": p.stat().st_size,
                "modified": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
            })
            continue
        m = arc_pat.match(p.name)
        if m:
            entries.append({
                "path": p,
                "stem": "backup",
                "strategy": m.group(1),
                "timestamp": m.group(2),
                "size_bytes": p.stat().st_size,
                "modified": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
            })

    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries


def list_backups_for(stem: str) -> list[dict[str, Any]]:
    """List backups matching a specific stem (e.g. ``"email"``)."""
    return [b for b in list_backups() if b["stem"] == stem]


def _resolve_backup_target_path(backup: dict[str, Any], dst_dir: Path) -> Path:
    stem = backup["stem"]
    if backup["path"].suffix == ".7z":
        return dst_dir / backup["path"].name
    return dst_dir / f"{stem}.db"


def _do_restore(backup_entry: dict[str, Any], dst_dir: Path) -> list[Path]:
    path = backup_entry["path"]
    if path.suffix == ".7z":
        return _extract_archive(path, dst_dir)
    target = _resolve_backup_target_path(backup_entry, dst_dir)
    _copy_with_verify(path, target)
    return [target]


def restore_latest(target_dir: str | Path) -> list[Path]:
    """Restore the newest backup for each known database / archive.

    Args:
        target_dir: Directory to restore files into.

    Returns:
        List of restored file paths.

    Raises:
        FileNotFoundError: If no backups exist.
    """
    backups = list_backups()
    if not backups:
        raise FileNotFoundError("No backups found")

    dst_dir = Path(target_dir).expanduser().resolve()
    dst_dir.mkdir(parents=True, exist_ok=True)

    restored: list[Path] = []
    seen_stems: set[str] = set()
    for b in backups:
        stem = b["stem"]
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        restored.extend(_do_restore(b, dst_dir))
    return restored


def restore_by_timestamp(timestamp_prefix: str, target_dir: str | Path) -> list[Path]:
    """Restore backups matching a timestamp prefix.

    Accepts partial timestamps.
    """
    dst_dir = Path(target_dir).expanduser().resolve()
    dst_dir.mkdir(parents=True, exist_ok=True)

    all_backups = list_backups()
    matches = [b for b in all_backups if b["timestamp"].startswith(timestamp_prefix)]
    if not matches:
        raise FileNotFoundError(f"No backups matching timestamp prefix: {timestamp_prefix}")

    restored: list[Path] = []
    for b in matches:
        restored.extend(_do_restore(b, dst_dir))
    return restored


def prune_old_backups(retention: int | None = None) -> int:
    """Remove old backups beyond the retention limit per (stem, strategy) group.

    Args:
        retention: Max backups per group. If None, uses strategy config.

    Returns:
        Number of files deleted.
    """
    bdir = _backup_dir()
    if not bdir.is_dir():
        return 0

    strategies: dict[str, int] = {}
    for s in list_strategies():
        strategies[s["id"]] = s.get("max_copies", _DEFAULT_MAX_COPIES)

    groups: dict[str, list[Path]] = {}
    for p in bdir.iterdir():
        if p.suffix not in (".db", ".7z"):
            continue
        # Group by stem for .db, or by strategy for .7z
        if p.suffix == ".7z":
            m = re.match(r"^backup_([a-z0-9-]+)_\d{8}T\d{10,}\.7z$", p.name)
            if m:
                groups.setdefault(f"archive:{m.group(1)}", []).append(p)
        else:
            m = re.match(r"^(.+?)_([a-z0-9-]+)_\d{8}T\d{10,}\.db$", p.name)
            if m:
                groups.setdefault(f"{m.group(1)}:{m.group(2)}", []).append(p)

    # Use explicit retention if given, otherwise fall back to per-strategy config
    deleted = 0
    for key, files in groups.items():
        strategy_id = key.split(":")[-1] if ":" in key else "default"
        keep = retention if retention is not None else strategies.get(strategy_id, _DEFAULT_MAX_COPIES)
        files.sort(reverse=True)
        for p in files[keep:]:
            try:
                p.unlink()
                deleted += 1
            except OSError:
                pass
    return deleted


prune_backups = prune_old_backups
"""Alias for :func:`prune_old_backups` (backward-compatible name)."""


def _prune_archives_for_strategy(strategy_id: str, *, retention: int) -> int:
    """Prune old 7z archives for a given strategy."""
    bdir = _backup_dir()
    if not bdir.is_dir():
        return 0
    prefix = f"backup_{strategy_id}_"
    files = sorted(
        [p for p in bdir.iterdir() if p.suffix == ".7z" and p.stem.startswith(prefix)],
        reverse=True,
    )
    deleted = 0
    for p in files[retention:]:
        try:
            p.unlink()
            deleted += 1
        except OSError:
            pass
    return deleted


def _prune_for_stem_and_strategy(
    stem: str,
    strategy_id: str,
    *,
    retention: int,
) -> int:
    """Prune old single-DB backups for a given (stem, strategy)."""
    bdir = _backup_dir()
    if not bdir.is_dir():
        return 0
    prefix = f"{stem}_{strategy_id}_"
    files = sorted(
        [p for p in bdir.iterdir() if p.suffix == ".db" and p.stem.startswith(prefix)],
        reverse=True,
    )
    deleted = 0
    for p in files[retention:]:
        try:
            p.unlink()
            deleted += 1
        except OSError:
            pass
    return deleted


# ── Public API: Export / Import ────────────────────────────────────────────


def export_data(
    output_dir: str | Path,
    *,
    db_dir: Path | None = None,
    cfg_dir: Path | None = None,
) -> Path:
    """Export all DB files + config files to a portable 7z archive.

    Creates a timestamped archive with manifest and SHA-256 checksums.

    Returns:
        Path to the created archive.
    """
    dd = db_dir or data_dir()
    cd = cfg_dir or config_dir()
    dst_root = Path(output_dir).expanduser().resolve()
    dst_root.mkdir(parents=True, exist_ok=True)

    for db_path in _known_db_paths(dd):
        _checkpoint_db(db_path)

    ts = _timestamp()
    arc_path = dst_root / f"export-{ts}.7z"

    manifest: dict[str, Any] = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": {},
    }

    files_to_export: list[tuple[Path, str]] = []
    for db_path in _known_db_paths(dd):
        files_to_export.append((db_path, db_path.name))
        manifest["files"][db_path.name] = {
            "size": db_path.stat().st_size,
            "sha256": _sha256(db_path),
        }
    for cfg_path in _known_config_files(cd):
        rel = f"config/{cfg_path.name}"
        files_to_export.append((cfg_path, rel))
        manifest["files"][rel] = {
            "size": cfg_path.stat().st_size,
            "sha256": _sha256(cfg_path),
        }

    try:
        with py7zr.SevenZipFile(
            arc_path, mode="w", filters=[{"id": py7zr.FILTER_LZMA2}]
        ) as arc:
            # Write manifest as in-memory entry
            import io
            manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
            arc.writef(io.BytesIO(manifest_bytes), "manifest.json")
            for src_path, arc_name in files_to_export:
                arc.write(src_path, arc_name)
    except Exception as exc:
        arc_path.unlink(missing_ok=True)
        raise OSError(f"Failed to create export archive: {exc}") from exc

    return arc_path


def import_data(
    arc_path: str | Path,
    *,
    db_dir: Path | None = None,
    cfg_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Import data from a previously exported 7z archive.

    Args:
        arc_path: Path to an export ``.7z`` archive.
        force: If True, overwrite existing files without checking.
        db_dir: Target database directory (defaults to ``data_dir()``).
        cfg_dir: Target config directory (defaults to ``config_dir()``).

    Returns:
        Dict with keys: ``imported``, ``skipped``, ``errors``.
    """
    src = Path(arc_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Export archive not found: {arc_path}")

    dst_data = db_dir or data_dir()
    dst_config = cfg_dir or config_dir()

    result: dict[str, Any] = {"imported": [], "skipped": [], "errors": []}

    import tempfile

    with tempfile.TemporaryDirectory(prefix="lightercore-import-") as tmp:
        tmp_path = Path(tmp)

        with py7zr.SevenZipFile(src, mode="r") as arc:
            arc.extractall(path=tmp)

        # Read manifest from extracted files
        manifest_path = tmp_path / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("Export archive missing manifest.json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(f"Invalid manifest.json: {e}") from e

        for rel_path_str, file_info in manifest.get("files", {}).items():
            src_file = tmp_path / rel_path_str
            if not src_file.exists():
                result["errors"].append(f"{rel_path_str} (not found in archive)")
                continue

            expected_sha = file_info.get("sha256", "")
            if expected_sha:
                actual_sha = _sha256(src_file)
                if actual_sha != expected_sha:
                    result["errors"].append(
                        f"{rel_path_str} (SHA-256 mismatch)"
                    )
                    if not force:
                        continue

            if rel_path_str.startswith("config/"):
                rel_suffix = rel_path_str[len("config/"):]
                dst_file = dst_config / rel_suffix
            else:
                dst_file = dst_data / rel_path_str

            if dst_file.exists() and not force:
                try:
                    if _sha256(dst_file) == _sha256(src_file):
                        result["skipped"].append(rel_path_str)
                        continue
                except OSError:
                    pass
                result["skipped"].append(
                    f"{rel_path_str} (exists; use --force to overwrite)"
                )
                continue

            try:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                _copy_with_verify(src_file, dst_file)
                result["imported"].append(rel_path_str)
            except OSError as e:
                result["errors"].append(f"{rel_path_str} ({e})")

    return result


# ── Public API: test strategy ──────────────────────────────────────────────


def verify_strategy_target(strategy: dict[str, Any] | str) -> dict[str, bool | str]:
    """Alias for :func:`test_strategy`."""
    return test_strategy(strategy)


__all__ = [
    "BackupStrategy",
    "BackupTarget",
    "add_strategy",
    "backup_all",
    "backup_all_strategies",
    "backup_database",
    "copy_to_external",
    "export_data",
    "get_backup_targets",
    "get_strategy",
    "import_data",
    "list_backups",
    "list_backups_for",
    "list_strategies",
    "load_config",
    "prune_backups",
    "prune_old_backups",
    "remove_strategy",
    "resolve_target_path",
    "restore_by_timestamp",
    "restore_latest",
    "save_config",
    "test_strategy",
    "update_strategy",
    "verify_strategy_target",
]

def _backup_filename(stem: str, strategy_id: str, ts: str, suffix: str = ".db") -> str:
    """Build a backup filename from components."""
    return f"{stem}_{strategy_id}_{ts}{suffix}"
