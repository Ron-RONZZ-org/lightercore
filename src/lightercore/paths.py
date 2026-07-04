"""XDG-compliant path resolution for lightercore-based applications.

Supports ``LIGHTERCORE_DIR`` environment variable override and sentinel
protection against accidental deletion.

Usage::

    from lightercore.paths import data_dir, config_dir, cache_dir, state_dir, ensure_dirs

    ensure_dirs()  # create all standard directories with sentinel protection
    db_path = data_dir() / "app.db"
"""

from __future__ import annotations

import os
from pathlib import Path

_LIGHTERCORE_DIR_ENV = "LIGHTERCORE_DIR"
_SENTINEL_NAME = ".lighterbird-protected"


def _base() -> Path | None:
    """Return the base directory from ``LIGHTERCORE_DIR`` env var, or None."""
    val = os.environ.get(_LIGHTERCORE_DIR_ENV, "").strip()
    return Path(val).resolve() if val else None


def _xdg_dir(var: str, default_rel: str) -> Path:
    """Resolve an XDG directory with env override and ``LIGHTERCORE_DIR`` fallback."""
    env_val = os.environ.get(var, "").strip()
    if env_val:
        return Path(env_val).expanduser().resolve()
    base = _base()
    if base:
        return base / default_rel.split("/")[-1]
    return Path.home() / ".local" / default_rel


def data_dir() -> Path:
    """Return the application data directory.

    Default: ``~/.local/share/lighterbird``
    Override: ``LIGHTERCORE_DIR`` → ``$LIGHTERCORE_DIR/data``
    Also: ``LIGHTERBIRD_DATA_DIR`` / ``SEMANTIKA_DATA_DIR`` / ``LIGHTERCORE_DATA_DIR``
    """
    for env in ("LIGHTERCORE_DATA_DIR", "LIGHTERBIRD_DATA_DIR", "SEMANTIKA_DATA_DIR"):
        override = os.environ.get(env)
        if override:
            return Path(override).expanduser().resolve()
    return _xdg_dir("XDG_DATA_HOME", "share/lighterbird")


def config_dir() -> Path:
    """Return the application config directory.

    Default: ``~/.config/lighterbird``
    Override: ``LIGHTERCORE_CONFIG_DIR`` / ``LIGHTERBIRD_CONFIG_DIR`` / ``SEMANTIKA_CONFIG_DIR``
    """
    for env in ("LIGHTERCORE_CONFIG_DIR", "LIGHTERBIRD_CONFIG_DIR", "SEMANTIKA_CONFIG_DIR"):
        override = os.environ.get(env)
        if override:
            return Path(override).expanduser().resolve()
    return _xdg_dir("XDG_CONFIG_HOME", "config/lighterbird")


def cache_dir() -> Path:
    """Return the application cache directory.

    Default: ``~/.cache/lighterbird``
    Override: ``LIGHTERCORE_CACHE_DIR`` / ``LIGHTERBIRD_CACHE_DIR`` / ``SEMANTIKA_CACHE_DIR``
    """
    for env in ("LIGHTERCORE_CACHE_DIR", "LIGHTERBIRD_CACHE_DIR", "SEMANTIKA_CACHE_DIR"):
        override = os.environ.get(env)
        if override:
            return Path(override).expanduser().resolve()
    return _xdg_dir("XDG_CACHE_HOME", "cache/lighterbird")


def state_dir() -> Path:
    """Return the application state directory.

    Default: ``~/.local/state/lighterbird``
    Override: ``LIGHTERCORE_STATE_DIR`` / ``LIGHTERBIRD_STATE_DIR`` / ``SEMANTIKA_STATE_DIR``
    """
    for env in ("LIGHTERCORE_STATE_DIR", "LIGHTERBIRD_STATE_DIR", "SEMANTIKA_STATE_DIR"):
        override = os.environ.get(env)
        if override:
            return Path(override).expanduser().resolve()
    return _xdg_dir("XDG_STATE_HOME", "state/lighterbird")


# ── Sentinel protection ──────────────────────────────────────────────────


def protect_directory(path: Path) -> Path:
    """Create a ``.lighterbird-protected`` sentinel marker in *path*.

    The marker signals that automated tools should not delete this directory.
    Idempotent.
    """
    path.mkdir(parents=True, exist_ok=True)
    sentinel = path / _SENTINEL_NAME
    if not sentinel.exists():
        sentinel.write_text(
            "# This directory is protected by lightercore.\n"
            "# Automated cleanup tools should skip this path.\n",
            encoding="utf-8",
        )
    return path


def is_protected(path: Path) -> bool:
    """Check if *path* (or any ancestor) has a sentinel marker."""
    for parent in [path] + list(path.parents):
        if (parent / _SENTINEL_NAME).exists():
            return True
    return False


def safe_rmtree(path: Path, *, force: bool = False) -> None:
    """Remove a directory tree, refusing if protected.

    Raises:
        ProtectedPathError: If protected and ``force`` is False.
        FileNotFoundError: If path does not exist.
    """
    import shutil

    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not force and is_protected(path):
        from lightercore.exceptions import ProtectedPathError

        raise ProtectedPathError(path, "delete")
    shutil.rmtree(path)


def safe_unlink(path: Path, *, force: bool = False) -> None:
    """Delete a file, refusing if parent is protected.

    Raises:
        ProtectedPathError: If protected and ``force`` is False.
        FileNotFoundError: If path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not force and is_protected(path.parent):
        from lightercore.exceptions import ProtectedPathError

        raise ProtectedPathError(path, "unlink")
    path.unlink()


def ensure_dirs() -> None:
    """Ensure all standard directories exist and are protected."""
    for d in [data_dir(), config_dir(), cache_dir(), state_dir()]:
        protect_directory(d)


def protect_all() -> None:
    """Protect all standard directories. Idempotent."""
    for d in [data_dir(), config_dir(), cache_dir(), state_dir()]:
        protect_directory(d)
