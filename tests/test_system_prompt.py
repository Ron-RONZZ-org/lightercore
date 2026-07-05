"""Tests for lightercore.system_prompt — SystemPromptManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from lightercore.system_prompt import SystemPromptManager


class TestSystemPromptManager:
    def test_load_returns_default_when_no_file(self, tmp_path: Path) -> None:
        mgr = SystemPromptManager(tmp_path)
        prompt = mgr.load("Default prompt")
        assert prompt == "Default prompt"

    def test_load_creates_file_on_first_access(self, tmp_path: Path) -> None:
        mgr = SystemPromptManager(tmp_path)
        mgr.load("Default prompt")
        path = mgr.path()
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "Default prompt"

    def test_load_returns_file_content_when_exists(self, tmp_path: Path) -> None:
        path = tmp_path / "system_prompt.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Custom user prompt", encoding="utf-8")
        mgr = SystemPromptManager(tmp_path)
        prompt = mgr.load("Default prompt")
        assert prompt == "Custom user prompt"
        # File should not have been overwritten
        assert path.read_text(encoding="utf-8") == "Custom user prompt"

    def test_load_skips_empty_file(self, tmp_path: Path) -> None:
        """An empty file triggers auto-seed with default."""
        path = tmp_path / "system_prompt.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("   \n  ", encoding="utf-8")  # whitespace-only
        mgr = SystemPromptManager(tmp_path)
        prompt = mgr.load("Default")
        assert prompt == "Default"

    def test_reload_reloads(self, tmp_path: Path) -> None:
        mgr = SystemPromptManager(tmp_path)
        mgr.load("First")
        path = mgr.path()
        path.write_text("Second", encoding="utf-8")
        assert mgr.reload("Default") == "Second"

    def test_path_property(self, tmp_path: Path) -> None:
        mgr = SystemPromptManager(tmp_path, "my_prompt.txt")
        assert mgr.path() == tmp_path / "my_prompt.txt"

    def test_custom_filename(self, tmp_path: Path) -> None:
        mgr = SystemPromptManager(tmp_path, "custom_prompt.md")
        assert mgr.path().name == "custom_prompt.md"
        mgr.load("Custom file prompt")
        assert (tmp_path / "custom_prompt.md").exists()
