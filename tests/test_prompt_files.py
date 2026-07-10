"""Tests for lightercore.prompt_files — PromptFilesManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from lightercore.prompt_files import PromptFile, PromptFilesManager


@pytest.fixture
def sample_defaults() -> list[PromptFile]:
    return [
        PromptFile("system-prompt", "system_prompt.md", "Default system prompt", "system"),
        PromptFile("agents", "AGENTS.md", "# Style guide\nBe concise.", "system"),
        PromptFile("template/turn1", "commands/_template_turns/turn1.md", "# turn1\nFind predicates.", "turn"),
        PromptFile("template/turn2", "commands/_template_turns/turn2.md", "# turn2\nGenerate YAML.", "turn"),
    ]


@pytest.fixture
def manager(tmp_path: Path, sample_defaults: list[PromptFile]) -> PromptFilesManager:
    return PromptFilesManager(tmp_path, sample_defaults)


class TestPromptFilesManager:
    def test_list_all_initial(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        """All files start as not-existing, not modified."""
        entries = manager.list_all()
        assert len(entries) == 4
        for e in entries:
            assert e["exists"] is False
            assert e["is_modified"] is False
            assert e["category"] in ("system", "turn")

    def test_list_all_after_create(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        """After seeding a file, it shows as exists and unmodified."""
        (tmp_path / "system_prompt.md").write_text("Default system prompt", encoding="utf-8")
        entries = manager.list_all()
        system = next(e for e in entries if e["name"] == "system-prompt")
        assert system["exists"] is True
        assert system["is_modified"] is False

    def test_list_all_modified(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        """A file with different content shows as modified."""
        (tmp_path / "AGENTS.md").write_text("# Custom style\nBe verbose.", encoding="utf-8")
        entries = manager.list_all()
        agents = next(e for e in entries if e["name"] == "agents")
        assert agents["exists"] is True
        assert agents["is_modified"] is True

    def test_get_content_missing(self, manager: PromptFilesManager) -> None:
        """get_content returns None for a non-existent file."""
        assert manager.get_content("system-prompt") is None

    def test_get_content_unknown_name(self, manager: PromptFilesManager) -> None:
        """get_content returns None for an unregistered name."""
        assert manager.get_content("nonexistent") is None

    def test_get_content_found(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        """get_content returns file content when it exists."""
        (tmp_path / "AGENTS.md").write_text("Hello", encoding="utf-8")
        assert manager.get_content("agents") == "Hello"

    def test_get_content_empty_name(self, manager: PromptFilesManager) -> None:
        """get_content returns None for empty name."""
        assert manager.get_content("") is None

    def test_is_modified_unknown(self, manager: PromptFilesManager) -> None:
        assert manager.is_modified("nope") is None

    def test_is_modified_missing(self, manager: PromptFilesManager) -> None:
        assert manager.is_modified("system-prompt") is None

    def test_is_modified_identical(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        (tmp_path / "system_prompt.md").write_text("Default system prompt", encoding="utf-8")
        assert manager.is_modified("system-prompt") is False

    def test_is_modified_different(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        (tmp_path / "system_prompt.md").write_text("Changed", encoding="utf-8")
        assert manager.is_modified("system-prompt") is True

    def test_is_modified_whitespace_insensitive(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        """Trailing whitespace differences should NOT count as modified."""
        (tmp_path / "system_prompt.md").write_text("  Default system prompt  \n", encoding="utf-8")
        assert manager.is_modified("system-prompt") is False

    def test_reset_creates_file(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        """reset() creates the file with default content."""
        content = manager.reset("system-prompt")
        assert content == "Default system prompt"
        file_path = tmp_path / "system_prompt.md"
        assert file_path.exists()
        assert file_path.read_text(encoding="utf-8") == "Default system prompt"

    def test_reset_overwrites_changed_file(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        """reset() restores a modified file to default."""
        (tmp_path / "AGENTS.md").write_text("Custom content", encoding="utf-8")
        content = manager.reset("agents")
        assert content == "# Style guide\nBe concise."
        assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "# Style guide\nBe concise."

    def test_reset_unknown_name(self, manager: PromptFilesManager) -> None:
        assert manager.reset("nonexistent") is None

    def test_save_new_file(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        """Save creates a new file."""
        assert manager.save("template/turn1", "Custom content") is True
        assert (tmp_path / "commands/_template_turns/turn1.md").read_text(encoding="utf-8") == "Custom content"

    def test_save_overwrites(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        """Save overwrites an existing file."""
        (tmp_path / "AGENTS.md").write_text("Old", encoding="utf-8")
        assert manager.save("agents", "New") is True
        assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "New"

    def test_save_unknown_name(self, manager: PromptFilesManager) -> None:
        assert manager.save("nonexistent", "content") is False

    def test_modified_count(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        assert manager.modified_count() == 0
        (tmp_path / "system_prompt.md").write_text("Changed", encoding="utf-8")
        assert manager.modified_count() == 1
        (tmp_path / "AGENTS.md").write_text("Also changed", encoding="utf-8")
        assert manager.modified_count() == 2

    def test_list_modified(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        assert manager.list_modified() == []
        (tmp_path / "system_prompt.md").write_text("Changed", encoding="utf-8")
        assert manager.list_modified() == ["system-prompt"]

    def test_reset_all(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        (tmp_path / "system_prompt.md").write_text("Changed", encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("Changed", encoding="utf-8")
        results = manager.reset_all()
        assert len(results) == 4
        assert all(r["success"] for r in results)
        assert manager.modified_count() == 0

    def test_get_default(self, manager: PromptFilesManager) -> None:
        assert manager.get_default("system-prompt") == "Default system prompt"
        assert manager.get_default("nonexistent") is None

    def test_case_insensitive_name(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        """Name lookups should be case-insensitive."""
        assert manager.get_content("SYSTEM-PROMPT") is None  # doesn't exist yet
        (tmp_path / "system_prompt.md").write_text("Hello", encoding="utf-8")
        assert manager.get_content("SYSTEM-PROMPT") == "Hello"

    def test_relative_path_creation(self, manager: PromptFilesManager, tmp_path: Path) -> None:
        """reset creates parent dirs for nested relative paths."""
        manager.reset("template/turn1")
        turn1_path = tmp_path / "commands/_template_turns/turn1.md"
        assert turn1_path.exists()
        assert "Find predicates" in turn1_path.read_text(encoding="utf-8")
