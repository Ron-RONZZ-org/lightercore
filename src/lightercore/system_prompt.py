"""Editable system prompt management.

Provides a file-based system prompt that users can customise by editing
a Markdown file in their config directory.  On first access (when no file
exists) a shipped default is automatically seeded so the user always has
something to start from.

Usage::

    from pathlib import Path
    from lightercore.system_prompt import SystemPromptManager

    mgr = SystemPromptManager(Path("~/.config/myapp"))
    prompt = mgr.load("Default prompt text...")
"""

from __future__ import annotations

from pathlib import Path


class SystemPromptManager:
    """File-based system prompt with auto-seed on first access.

    Args:
        directory: Path to the config directory (should already exist).
        filename: Name of the prompt file (default ``"system_prompt.md"``).
    """

    def __init__(self, directory: Path, filename: str = "system_prompt.md") -> None:
        self._directory = directory
        self._filename = filename

    def path(self) -> Path:
        """Return the full path to the prompt file."""
        return self._directory / self._filename

    def load(self, default: str) -> str:
        """Load the system prompt, auto-seeding the default on first run.

        Resolution order:
        1. If the file exists and is non-empty → return its content.
        2. Otherwise, write *default* to the file and return *default*.

        Args:
            default: The default prompt content (shipped with the app).

        Returns:
            The system prompt string.
        """
        path = self.path()

        try:
            if path.exists():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    return content
        except OSError:
            pass

        # Auto-seed on first run
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(default, encoding="utf-8")
        except OSError:
            pass
        return default

    def reload(self, default: str) -> str:
        """Force-reload the prompt, ignoring any cached state.

        Args:
            default: Fallback prompt content.

        Returns:
            The (reloaded) system prompt string.
        """
        return self.load(default)


__all__ = ["SystemPromptManager"]
