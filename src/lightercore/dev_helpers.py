"""Dev server helpers shared across lighterbird, semantika, and related projects.

Provides infrastructure for CLI argument parsing, data directory management,
seed-file discovery, mutual exclusivity validation, and cleanup.

**No web framework dependency.**  This module only uses the stdlib — projects
that use it add their own ``import uvicorn`` + ``uvicorn.run()`` call.

Usage::

    from lightercore.dev_helpers import (
        find_dot_dev,
        find_dot_prod,
        is_seeded,
        setup_data_dir,
        standard_dev_parser,
        validate_seed_sources,
        cleanup_data_dir,
    )

Typical project ``dev_main()``::

    def dev_main() -> None:
        parser = standard_dev_parser("MyApp dev server", default_port=8000)
        parser.add_argument("--my-flag", ...)  # project-specific extras
        args = parser.parse_args()

        validate_seed_sources(args)

        root_dir, data_dir, config_dir, is_temp = setup_data_dir(
            args.data_dir, app_name="myapp",
        )

        if args.seed_from is not None:
            ...  # restore from archive
        elif args.seed is not None:
            if not is_seeded(data_dir):
                seed_data_dir(data_dir, find_dot_dev(...))
        elif args.prod is not None:
            if not is_seeded(data_dir):
                seed_data_dir(data_dir, find_dot_prod(...))

        import uvicorn
        try:
            uvicorn.run(...)
        finally:
            cleanup_data_dir(root_dir, is_temp, args.keep_data)
"""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path


# ── Env var prefix mapping ────────────────────────────────────────────────

_APP_ENV_PREFIXES: dict[str, str] = {
    "lighterbird": "LIGHTERBIRD",
    "semantika": "SEMANTIKA",
    "lightercore": "LIGHTERCORE",
}


def _app_env_prefix(app_name: str) -> str:
    """Return the environment variable prefix for a given app name.

    Args:
        app_name: Lowercase app name, e.g. ``"lighterbird"`` or ``"semantika"``.

    Returns:
        Uppercase prefix, e.g. ``"LIGHTERBIRD"`` or ``"SEMANTIKA"``.

    Raises:
        ValueError: If *app_name* is not recognised.
    """
    prefix = _APP_ENV_PREFIXES.get(app_name)
    if prefix is None:
        raise ValueError(
            f"Unknown app name {app_name!r}. "
            f"Supported: {', '.join(sorted(_APP_ENV_PREFIXES))}"
        )
    return prefix


# ── Seed file discovery ───────────────────────────────────────────────────


def find_dot_dev(script_path: str | Path) -> Path | None:
    """Find the ``.dev`` file by walking up from the given *script_path*.

    The script is expected to live at ``<project_root>/src/<pkg>/scripts/dev_cli.py``
    (or a similar depth), and ``.dev`` is at the project root.

    Args:
        script_path: Path to the calling script (typically ``__file__``).

    Returns:
        Absolute path to ``.dev`` if found, else ``None``.
    """
    project_root = _resolve_project_root(script_path)
    candidate = project_root / ".dev"
    return candidate if candidate.exists() else None


def find_dot_prod(script_path: str | Path) -> Path | None:
    """Find the ``.prod`` file by walking up from the given *script_path*.

    Args:
        script_path: Path to the calling script (typically ``__file__``).

    Returns:
        Absolute path to ``.prod`` if found, else ``None``.
    """
    project_root = _resolve_project_root(script_path)
    candidate = project_root / ".prod"
    return candidate if candidate.exists() else None


def _resolve_project_root(script_path: str | Path) -> Path:
    """Walk up from *script_path* until we find a ``pyproject.toml`` (or root).

    Fallback: go up 4 levels from ``<pkg>/scripts/dev_cli.py``.
    """
    path = Path(script_path).resolve()
    # Walk up looking for pyproject.toml
    for parent in [path] + list(path.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: walk up 4 levels from typical script location
    # src/<pkg>/scripts/dev_cli.py  ->  project root
    return path.parent.parent.parent.parent


# ── Seeding detection ─────────────────────────────────────────────────────


def is_seeded(data_dir: Path) -> bool:
    """Check if *data_dir* already has content (i.e. was seeded before).

    Returns ``True`` if the directory exists and is non-empty.
    """
    if not data_dir.is_dir():
        return False
    return any(data_dir.iterdir())


# ── Data directory setup ──────────────────────────────────────────────────


def _ephemeral_root(app_name: str) -> tuple[Path, bool]:
    """Create an ephemeral temp directory for a dev server session."""
    root = Path(tempfile.mkdtemp(prefix=f"{app_name}-dev-"))
    return root, True


def setup_data_dir(
    data_dir_arg: str | None,
    app_name: str,
) -> tuple[Path, Path, Path, bool]:
    """Resolve and prepare the data directory for a dev server.

    Two modes:

    * **Persistent** (``data_dir_arg`` is given) — use the specified path
      as the data directory directly.  Created if missing.  Never cleaned
      up automatically.  The returned ``config_dir`` is a default suggestion
      (``<data-dir>/config``) but is **not** created — config is the
      caller's responsibility (typically via ``--local-config``).
    * **Ephemeral** (``data_dir_arg`` is ``None``) — create a temporary
      directory via ``tempfile.mkdtemp``, with ``data/`` and ``config/``
      subdirectories inside.  Cleaned up on exit unless ``--keep-data``
      is passed.

    Sets the following environment variables (where ``PREFIX`` is derived
    from *app_name*, e.g. ``LIGHTERBIRD`` or ``SEMANTIKA``):

    * ``<PREFIX>_DATA_DIR`` — always set
    * ``<PREFIX>_CONFIG_DIR`` — set **only** in ephemeral mode (temp dir);
      in persistent mode the caller is responsible for config.
    * ``<PREFIX>_CACHE_DIR``
    * ``<PREFIX>_STATE_DIR``

    Args:
        data_dir_arg: Value of ``--data-dir`` (or ``None`` for temp dir).
        app_name: Application name (e.g. ``"lighterbird"``, ``"semantika"``).

    Returns:
        Tuple of ``(root_dir, data_dir, config_dir, is_temp)``.

    Raises:
        ValueError: If *app_name* is not recognised.
    """
    prefix = _app_env_prefix(app_name)

    if data_dir_arg is not None:
        # ── Persistent mode: caller-supplied data dir ─────────────────
        root_dir = Path(data_dir_arg).expanduser().resolve()
        root_dir.mkdir(parents=True, exist_ok=True)
        is_temp = False
        data_dir = root_dir
        config_dir = root_dir / "config"  # suggestion only — NOT created
    else:
        # ── Ephemeral mode: temp dir with data/ and config/ siblings ─
        root_dir, is_temp = _ephemeral_root(app_name)
        data_dir = root_dir / "data"
        config_dir = root_dir / "config"
        data_dir.mkdir(parents=True, exist_ok=True)
        config_dir.mkdir(parents=True, exist_ok=True)
        os.environ[f"{prefix}_CONFIG_DIR"] = str(config_dir)

    # Set env vars BEFORE any app-level imports resolve paths
    os.environ[f"{prefix}_DATA_DIR"] = str(data_dir)
    os.environ[f"{prefix}_CACHE_DIR"] = str(root_dir / "cache")
    os.environ[f"{prefix}_STATE_DIR"] = str(root_dir / "state")

    return root_dir, data_dir, config_dir, is_temp


# ── Argument parser ───────────────────────────────────────────────────────


def standard_dev_parser(
    description: str,
    default_port: int,
) -> argparse.ArgumentParser:
    """Return an ``ArgumentParser`` pre-loaded with standard dev-server flags.

    The returned parser can be extended with project-specific arguments
    before calling ``parse_args()``.

    Standard flags:

    * ``--seed`` (optional path to ``.dev``, or auto-discover)
    * ``--prod`` (optional path to ``.prod``, or auto-discover)
    * ``--seed-from ARCHIVE_PATH`` (restore from backup archive)
    * ``--data-dir DIR`` (persistent data directory)
    * ``--port PORT``
    * ``--keep-data`` (preserve temp dir on exit)
    * ``--quiet`` (suppress info output)

    Args:
        description: Description for ``--help``.
        default_port: Port to bind when ``--port`` is not given.

    Returns:
        Configured ``ArgumentParser``.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--seed",
        nargs="?",
        const="auto",
        default=None,
        metavar="DOT_DEV_PATH",
        help="Seed from .dev file (default: auto-discover from project root)",
    )
    parser.add_argument(
        "--prod",
        nargs="?",
        const="auto",
        default=None,
        metavar="DOT_PROD_PATH",
        help="Seed from .prod file (default: auto-discover from project root). "
        "Mutually exclusive with --seed and --seed-from.",
    )
    parser.add_argument(
        "--seed-from",
        type=str,
        default=None,
        metavar="ARCHIVE_PATH",
        help="Restore seed from a .7z backup archive (mutually exclusive "
        "with --seed and --prod)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        metavar="DIR",
        help="Persistent data directory (replaces ephemeral temp dir). "
        "Data survives restarts; seeding runs only when the dir is empty.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Port to bind (default: {default_port})",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="Do not clean up the temp data directory on exit",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational output (errors still displayed)",
    )
    return parser


# ── Validation ────────────────────────────────────────────────────────────


def validate_seed_sources(args: argparse.Namespace) -> None:
    """Validate mutual exclusivity of seed-source flags.

    Checks that at most one of ``--seed``, ``--prod``, ``--seed-from``
    was provided.  Prints an error message and calls ``SystemExit`` if
    more than one is set.

    Args:
        args: Parsed arguments (must have ``seed``, ``prod``, ``seed_from``).

    Raises:
        SystemExit: If two or more seed sources are specified.
    """
    enabled: list[str] = []
    for name in ("seed", "prod", "seed_from"):
        if getattr(args, name, None) is not None:
            enabled.append(name.replace("_", "-"))
    if len(enabled) > 1:
        print(
            f"ERROR: --{enabled[0]}, --{enabled[1]} "
            "are mutually exclusive. Use only one."
        )
        raise SystemExit(1)


# ── Cleanup ───────────────────────────────────────────────────────────────


def cleanup_data_dir(
    root_dir: Path,
    is_temp: bool,
    keep_data: bool,
    *,
    quiet: bool = False,
    log_prefix: str = "[dev]",
) -> None:
    """Clean up the data directory after the server stops.

    * **Persistent dir** (``is_temp=False``): logs the path, never deletes.
    * **Temp dir** (``is_temp=True``) with ``keep_data=True``: logs the path.
    * **Temp dir** with ``keep_data=False``: removes the tree via
      ``shutil.rmtree``.

    Args:
        root_dir: Root directory (returned by ``setup_data_dir``).
        is_temp: Whether this is an ephemeral temp directory.
        keep_data: Whether to preserve data.
        quiet: Suppress informational output.
        log_prefix: Prefix for log messages (e.g. ``"[myapp-dev]"``).
    """
    if not is_temp:
        if not quiet:
            print(f"{log_prefix} Data preserved at: {root_dir}")
        return

    if keep_data:
        if not quiet:
            print(f"{log_prefix} Data preserved at: {root_dir}")
    else:
        if not quiet:
            print(f"{log_prefix} Cleaning up: {root_dir}")
        shutil.rmtree(root_dir, ignore_errors=True)
