"""XDG-compliant path resolution for lightercore-based applications.

Supports ``LIGHTERCORE_DIR`` environment variable override and sentinel
protection against accidental deletion.

Each consuming application should call ``set_app_name()`` during startup
so that data/config/cache/state directories use the correct app name.
Defaults to ``"unknownlighterapp"`` so that apps that forget to call
``set_app_name()`` get an obvious wrong-directory signal rather than silently
polluting another app's namespace.

Usage::

    from lightercore.paths import data_dir, config_dir, cache_dir, state_dir, ensure_dirs

    ensure_dirs()  # create all standard directories with sentinel protection
    db_path = data_dir() / "app.db"
"""

from __future__ import annotations

import os
from pathlib import Path

_LIGHTERCORE_DIR_ENV = "LIGHTERCORE_DIR"

# App name used for default path fallback (e.g. ~/.local/share/<app_name>).
# Each consuming app should call set_app_name() early during import.
_app_name: str = "unknownlighterapp"


def set_app_name(name: str) -> None:
    """Set the application name used for default XDG directory paths.

    Must be called before the first ``data_dir()`` / ``config_dir()`` /
    ``cache_dir()`` / ``state_dir()`` call to take effect for the default
    fallback (i.e. when no env vars are set).

    Args:
        name: Lowercase app name, e.g. ``"ronzzdoi"`` or ``"semantika"``.
    """
    global _app_name
    _app_name = name


def _sentinel_name() -> str:
    """Return the sentinel filename for the current app name."""
    return f".{_app_name}-protected"


def _base() -> Path | None:
    """Return the base directory from env var, or None.

    Checks (in order): ``LIGHTERCORE_DIR``, ``LIGHTERBIRD_DIR``,
    ``SEMANTIKA_DIR``.
    """
    for var in ("LIGHTERCORE_DIR", "LIGHTERBIRD_DIR", "SEMANTIKA_DIR"):
        val = os.environ.get(var, "").strip()
        if val:
            return Path(val).resolve()
    return None


def data_dir() -> Path:
    """Return the application data directory.

    Default: ``~/.local/share/<app_name>``
    Override: ``LIGHTERCORE_DIR`` → ``$LIGHTERCORE_DIR/data``
    Also: ``LIGHTERBIRD_DATA_DIR`` / ``SEMANTIKA_DATA_DIR`` / ``LIGHTERCORE_DATA_DIR``
    """
    for env in ("LIGHTERCORE_DATA_DIR", "LIGHTERBIRD_DATA_DIR", "SEMANTIKA_DATA_DIR"):
        override = os.environ.get(env)
        if override:
            return Path(override).expanduser().resolve()
    base = _base()
    if base:
        return base / "data"
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser().resolve() / _app_name
    return Path.home() / ".local" / "share" / _app_name


def config_dir() -> Path:
    """Return the application config directory.

    Default: ``~/.config/<app_name>``
    Override: ``LIGHTERCORE_CONFIG_DIR`` / ``LIGHTERBIRD_CONFIG_DIR`` / ``SEMANTIKA_CONFIG_DIR``
    """
    for env in ("LIGHTERCORE_CONFIG_DIR", "LIGHTERBIRD_CONFIG_DIR", "SEMANTIKA_CONFIG_DIR"):
        override = os.environ.get(env)
        if override:
            return Path(override).expanduser().resolve()
    base = _base()
    if base:
        return base / "config"
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser().resolve() / _app_name
    return Path.home() / ".config" / _app_name


def cache_dir() -> Path:
    """Return the application cache directory.

    Default: ``~/.cache/<app_name>``
    Override: ``LIGHTERCORE_CACHE_DIR`` / ``LIGHTERBIRD_CACHE_DIR`` / ``SEMANTIKA_CACHE_DIR``
    """
    for env in ("LIGHTERCORE_CACHE_DIR", "LIGHTERBIRD_CACHE_DIR", "SEMANTIKA_CACHE_DIR"):
        override = os.environ.get(env)
        if override:
            return Path(override).expanduser().resolve()
    base = _base()
    if base:
        return base / "cache"
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser().resolve() / _app_name
    return Path.home() / ".cache" / _app_name


def state_dir() -> Path:
    """Return the application state directory.

    Default: ``~/.local/state/<app_name>``
    Override: ``LIGHTERCORE_STATE_DIR`` / ``LIGHTERBIRD_STATE_DIR`` / ``SEMANTIKA_STATE_DIR``
    """
    for env in ("LIGHTERCORE_STATE_DIR", "LIGHTERBIRD_STATE_DIR", "SEMANTIKA_STATE_DIR"):
        override = os.environ.get(env)
        if override:
            return Path(override).expanduser().resolve()
    base = _base()
    if base:
        return base / "state"
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser().resolve() / _app_name
    return Path.home() / ".local" / "state" / _app_name


# ── Sentinel protection ──────────────────────────────────────────────────


def protect_directory(path: Path) -> Path:
    """Create a ``.lighterbird-protected`` sentinel marker in *path*.

    The marker signals that automated tools should not delete this directory.
    Idempotent.
    """
    path.mkdir(parents=True, exist_ok=True)
    sentinel = path / _sentinel_name()
    if not sentinel.exists():
        sentinel.write_text(
            f"# This directory is protected by lightercore ({_app_name}).\n"
            "# Automated cleanup tools should skip this path.\n",
            encoding="utf-8",
        )
    return path


def is_protected(path: Path) -> bool:
    """Check if *path* (or any ancestor) has a sentinel marker."""
    for parent in [path] + list(path.parents):
        if (parent / _sentinel_name()).exists():
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
