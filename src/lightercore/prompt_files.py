"""Prompt file registry — track, compare, and reset shipped prompt files.

Each app (lighterbird, semantika) defines its own list of shipped prompt files
with their default content.  This module provides a shared manager to:

- List all prompt files with their modification status.
- Read current content from disk.
- Compare file content against the shipped default.
- Reset a file to its shipped default.
- Save edited content atomically.

Usage::

    from pathlib import Path
    from lightercore.prompt_files import PromptFile, PromptFilesManager

    DEFAULTS = [
        PromptFile("system-prompt", "system_prompt.md", "...", "system"),
        PromptFile("agents", "AGENTS.md", "...", "system"),
        PromptFile("template", "commands/template.md", "...", "command"),
    ]

    mgr = PromptFilesManager(Path("~/.config/myapp"), DEFAULTS)

    for pf in mgr.list_all():
        print(pf["name"], pf["is_modified"])

    content = mgr.get_content("system-prompt")
    mgr.reset("agents")          #  writes default, returns it
    mgr.save("template", "new content")  #  atomic write
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PromptFile:
    """Descriptor for a single shipped prompt file.

    Attributes:
        name: Unique logical name (e.g. ``"system-prompt"``, ``"template/turn1"``).
        relative_path: Path relative to the config directory
            (e.g. ``"system_prompt.md"``, ``"commands/_template_turns/turn1.md"``).
        default_content: The shipped default text for this prompt.
        category: Semantic group — ``"system"``, ``"agents"``, ``"command"``,
            ``"turn"``, etc.
    """

    name: str
    relative_path: str
    default_content: str
    category: str = ""


# ── Normalisation ─────────────────────────────────────────────────────────────


def _normalise(text: str) -> str:
    """Normalise prompt text for comparison purposes.

    Strips leading/trailing whitespace and normalises line endings so that
    files written on different platforms compare correctly.
    """
    return text.strip().replace("\r\n", "\n").replace("\r", "\n")


# ── Manager ───────────────────────────────────────────────────────────────────


class PromptFilesManager:
    """Manages a collection of shipped prompt files on disk.

    Args:
        config_dir: The app's config directory (e.g. ``config_dir()``).
        defaults: List of :class:`PromptFile` descriptors shipped with the app.
    """

    def __init__(
        self,
        config_dir: Path,
        defaults: list[PromptFile],
    ) -> None:
        self._config_dir = config_dir
        self._defaults_by_name: dict[str, PromptFile] = {}
        for pf in defaults:
            self._defaults_by_name[pf.name] = pf

    def list_all(self) -> list[dict[str, Any]]:
        """Return metadata for all registered prompt files.

        Each entry contains:
            ``name``, ``path``, ``relative_path``, ``category``,
            ``exists`` (bool), ``is_modified`` (bool, False if !exists).
        """
        result: list[dict[str, Any]] = []
        for pf in self._defaults_by_name.values():
            full_path = self._config_dir / pf.relative_path
            exists = full_path.is_file()
            modified = self._is_modified(pf) if exists else False
            result.append({
                "name": pf.name,
                "path": str(full_path),
                "relative_path": pf.relative_path,
                "category": pf.category,
                "exists": exists,
                "is_modified": modified,
            })
        return result

    def get_content(self, name: str) -> str | None:
        """Read a prompt file's current content from disk.

        Returns ``None`` if the file doesn't exist or can't be read.
        """
        pf = self._resolve(name)
        if pf is None:
            return None
        full_path = self._config_dir / pf.relative_path
        try:
            if full_path.is_file():
                return full_path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Failed to read prompt file: %s", full_path)
        return None

    def is_modified(self, name: str) -> bool | None:
        """Check whether a prompt file differs from its shipped default.

        Returns:
            ``True`` if modified, ``False`` if identical, ``None`` if the
            file doesn't exist or the name is unknown.
        """
        pf = self._resolve(name)
        if pf is None:
            return None
        full_path = self._config_dir / pf.relative_path
        if not full_path.is_file():
            return None
        return self._is_modified(pf)

    def reset(self, name: str) -> str | None:
        """Reset a prompt file to its shipped default.

        Creates the file (and parent directories) if it doesn't exist.
        Uses an atomic write (temp + rename) to avoid corruption.

        Returns:
            The default content string, or ``None`` if the name is unknown.
        """
        pf = self._resolve(name)
        if pf is None:
            return None
        full_path = self._config_dir / pf.relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = full_path.with_suffix(f"{full_path.suffix}.tmp")
        try:
            tmp.write_text(pf.default_content, encoding="utf-8")
            tmp.rename(full_path)
        except OSError as e:
            logger.error("Failed to reset prompt file %s: %s", full_path, e)
            return None
        logger.info("Reset prompt file '%s' to default", name)
        return pf.default_content

    def save(self, name: str, content: str) -> bool:
        """Save (create or overwrite) a prompt file with atomic write.

        Args:
            name: The prompt file's logical name.
            content: New content to write.

        Returns:
            ``True`` on success, ``False`` if the name is unknown or write fails.
        """
        pf = self._resolve(name)
        if pf is None:
            return False
        full_path = self._config_dir / pf.relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = full_path.with_suffix(f"{full_path.suffix}.tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.rename(full_path)
        except OSError as e:
            logger.error("Failed to save prompt file %s: %s", full_path, e)
            return False
        logger.info("Saved prompt file '%s' (%d chars)", name, len(content))
        return True

    def modified_count(self) -> int:
        """Count how many registered prompt files are modified from default."""
        count = 0
        for pf in self._defaults_by_name.values():
            full_path = self._config_dir / pf.relative_path
            if full_path.is_file() and self._is_modified(pf):
                count += 1
        return count

    def list_modified(self) -> list[str]:
        """Return names of all prompt files that differ from their defaults."""
        result: list[str] = []
        for pf in self._defaults_by_name.values():
            full_path = self._config_dir / pf.relative_path
            if full_path.is_file() and self._is_modified(pf):
                result.append(pf.name)
        return result

    def reset_all(self) -> list[dict[str, str | bool]]:
        """Reset all registered prompt files to their defaults.

        Returns:
            List of ``{"name": str, "success": bool}`` dicts.
        """
        results: list[dict[str, str | bool]] = []
        for name in self._defaults_by_name:
            content = self.reset(name)
            results.append({"name": name, "success": content is not None})
        return results

    def get_default(self, name: str) -> str | None:
        """Return the shipped default content for a prompt file by name.

        Returns ``None`` if the name is not registered.
        """
        pf = self._resolve(name)
        return pf.default_content if pf is not None else None

    # ── Internal helpers ──────────────────────────────────────────────────

    def _resolve(self, name: str) -> PromptFile | None:
        """Look up a :class:`PromptFile` by name (case-insensitive)."""
        if not name:
            return None
        lower = name.lower()
        for pf in self._defaults_by_name.values():
            if pf.name.lower() == lower:
                return pf
        return None

    def _is_modified(self, pf: PromptFile) -> bool:
        """Compare file on disk against shipped default."""
        full_path = self._config_dir / pf.relative_path
        try:
            content = full_path.read_text(encoding="utf-8")
        except OSError:
            return False
        return _normalise(content) != _normalise(pf.default_content)


__all__ = [
    "PromptFile",
    "PromptFilesManager",
]
