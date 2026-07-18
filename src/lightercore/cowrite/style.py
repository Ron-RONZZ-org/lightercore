"""Generic co-writing style cascade loading mechanism.

The app provides:
- ``config_dir``: where the style files live (a ``Path`` or string).
- Optional ``form_type_to_domain`` mapping (``form_type`` \u2192 domain slug).
- Optional ``defaults`` dict (``"general"`` + domain slugs \u2192 default content).

This module handles: reading, lazy-seeding, and cascading.

**Cascade order**: general file (\u2192 auto-seed) → domain file (\u2192 auto-seed).

Example::

    from lightercore.cowrite.style import load_cowrite_style
    from lightercore.paths import config_dir

    style = load_cowrite_style(
        config_dir=config_dir(),
        form_type="node-add-concept",
        form_type_to_domain={"node-add-concept": "node"},
        defaults={
            "general": "# General writing rules\\n...",
            "node": "# Node writing rules\\n...",
        },
    )
"""

from __future__ import annotations

from pathlib import Path

_COWRITE_GENERAL_FILENAME = "cowrite_style.md"
_COWRITE_DOMAIN_PREFIX = "cowrite_style_"
_COWRITE_DOMAIN_SUFFIX = ".md"


def cowrite_style_path(config_dir: str | Path) -> str:
    """Return the path to the general co-writing style file.

    Args:
        config_dir: The application's config directory.

    Returns:
        Absolute path to the general style file as a string.
    """
    return str(Path(config_dir) / _COWRITE_GENERAL_FILENAME)


def cowrite_style_domain_path(config_dir: str | Path, domain: str) -> str:
    """Return the path to a domain-specific co-writing style file.

    Args:
        config_dir: The application's config directory.
        domain: Domain slug (``"node"``, ``"predicate"``, ``"triple"``, etc.).

    Returns:
        Absolute path to the domain style file as a string.
    """
    return str(
        Path(config_dir) / f"{_COWRITE_DOMAIN_PREFIX}{domain}{_COWRITE_DOMAIN_SUFFIX}"
    )


def _lazy_seed(path: Path, default: str) -> None:
    """Write *default* to *path* if the file doesn't exist or is empty.

    Args:
        path: File path to write.
        default: Default content to write if the file is missing/empty.
    """
    try:
        if path.is_file():
            try:
                if path.read_text(encoding="utf-8").strip():
                    return
            except OSError:
                pass
    except OSError:
        pass
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(default, encoding="utf-8")
    except OSError:
        pass


def _read_file(path: Path) -> str | None:
    """Read and return *path* content, or ``None`` if missing/empty.

    Args:
        path: File path to read.

    Returns:
        Strip content string, or ``None`` if the file doesn't exist,
        is empty, or cannot be read.
    """
    try:
        content = path.read_text(encoding="utf-8").strip()
        return content if content else None
    except OSError:
        return None


def load_cowrite_style(
    config_dir: str | Path,
    form_type: str | None = None,
    form_type_to_domain: dict[str, str] | None = None,
    defaults: dict[str, str] | None = None,
) -> str | None:
    """Load the co-writing style guide (general + per-domain cascade).

    **Cascade order** (both optional):
    1. Load general ``cowrite_style.md`` (auto-seeded from
       ``defaults.get("general")`` on first access).
    2. If *form_type* is provided, resolve the domain slug via
       *form_type_to_domain*, load the domain-specific file
       (auto-seeded from ``defaults.get(domain)`` on first access),
       and append it under a ``## Domain-specific Guide`` heading.

    Args:
        config_dir: The application's config directory.
        form_type: Form type string (e.g. ``"node-add-concept"``,
            ``"triple-add"``). If ``None``, only the general file is loaded.
        form_type_to_domain: Mapping of form_type → domain slug
            (e.g. ``{"node-add-concept": "node"}``).
        defaults: Dict mapping ``"general"`` or domain slugs to default
            content strings.  Used to seed files that don't exist yet.

    Returns:
        The combined style guide string, or ``None`` if nothing is
        available (general file missing/empty and no domain file).
    """
    cfg = Path(config_dir)
    parts: list[str] = []
    defaults = defaults or {}

    # 1. General file — lazy seed on first access
    general_path = cfg / _COWRITE_GENERAL_FILENAME
    general = _read_file(general_path)
    if general is None and "general" in defaults:
        _lazy_seed(general_path, defaults["general"])
        general = _read_file(general_path)
    if general:
        parts.append(general)

    # 2. Domain-specific file (if form_type resolves to a known domain)
    domain = (form_type_to_domain or {}).get(form_type) if form_type else None
    if domain:
        domain_path = cfg / f"{_COWRITE_DOMAIN_PREFIX}{domain}{_COWRITE_DOMAIN_SUFFIX}"
        domain_content = _read_file(domain_path)
        if domain_content is None and domain in defaults:
            _lazy_seed(domain_path, defaults[domain])
            domain_content = _read_file(domain_path)
        if domain_content:
            parts.append("## Domain-specific Guide\n\n" + domain_content)

    return "\n\n".join(parts) if parts else None
