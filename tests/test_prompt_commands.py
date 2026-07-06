"""Tests for lightercore.prompt_commands — file scanner, parser, and expander."""

from __future__ import annotations

from pathlib import Path

import pytest

from lightercore.prompt_commands import (
    PromptCommand,
    expand_prompt_template,
    list_prompt_commands,
    load_prompt_command,
    prompt_command_exists,
)


class TestListPromptCommands:
    """Scanning the commands directory."""

    def test_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        assert list_prompt_commands(commands_dir) == []

    def test_non_existent_dir_returns_empty_list(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"  # does not exist
        assert list_prompt_commands(commands_dir) == []

    def test_skips_non_md_files(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "notes.txt").write_text("# Test", encoding="utf-8")
        assert list_prompt_commands(commands_dir) == []

    def test_skips_dotfiles(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / ".hidden.md").write_text("# Hidden\nprompt", encoding="utf-8")
        assert list_prompt_commands(commands_dir) == []

    def test_skips_file_without_hash_header(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "naked.md").write_text("just text", encoding="utf-8")
        assert list_prompt_commands(commands_dir) == []

    def test_parses_valid_file(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "weekly.md").write_text(
            "# Weekly status report\nCompile report from $1 folder.",
            encoding="utf-8",
        )
        cmds = list_prompt_commands(commands_dir)
        assert len(cmds) == 1
        cmd = cmds[0]
        assert cmd.name == "weekly"
        assert cmd.description == "Weekly status report"
        assert cmd.template == "Compile report from $1 folder."
        assert cmd.path == commands_dir / "weekly.md"
        assert cmd.param_count == 1

    def test_multiple_files_sorted(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "zzz.md").write_text("# Z last\nzzz", encoding="utf-8")
        (commands_dir / "aaa.md").write_text("# A first\naaa", encoding="utf-8")
        cmds = list_prompt_commands(commands_dir)
        assert len(cmds) == 2
        assert cmds[0].name == "aaa"
        assert cmds[1].name == "zzz"

    def test_handles_unicode_error_gracefully(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        path = commands_dir / "bad.md"
        path.write_bytes(b"# \xff\xfe desc\nprompt")
        cmds = list_prompt_commands(commands_dir)
        assert len(cmds) == 0

    def test_multiline_template(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "multi.md").write_text(
            "# Multi-line\nLine one\nLine two\n\nLine three",
            encoding="utf-8",
        )
        cmd = load_prompt_command(commands_dir, "multi")
        assert cmd is not None
        assert cmd.template == "Line one\nLine two\n\nLine three"


class TestLoadPromptCommand:
    """Loading single commands by name."""

    def test_load_by_name(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "test.md").write_text("# My command\nprompt body", encoding="utf-8")
        cmd = load_prompt_command(commands_dir, "test")
        assert cmd is not None
        assert cmd.name == "test"
        assert cmd.description == "My command"
        assert cmd.template == "prompt body"

    def test_case_insensitive(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "MyCmd.md").write_text("# Case test\nbody", encoding="utf-8")
        cmd = load_prompt_command(commands_dir, "mycmd")
        assert cmd is not None
        assert cmd.name == "MyCmd"

    def test_not_found_returns_none(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        assert load_prompt_command(commands_dir, "nonexistent") is None

    def test_non_existent_dir_returns_none(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        assert load_prompt_command(commands_dir, "anything") is None


class TestExpandPromptTemplate:
    """Template expansion with positional args."""

    def test_single_arg(self) -> None:
        result = expand_prompt_template("Hello $1!", ["World"])
        assert result == "Hello World!"

    def test_multiple_args(self) -> None:
        result = expand_prompt_template(
            "$1 emails from $2 folder", ["10", "INBOX"]
        )
        assert result == "10 emails from INBOX folder"

    def test_unused_placeholder_left_as_is(self) -> None:
        result = expand_prompt_template("$1 and $2", ["only"])
        assert result == "only and $2"

    def test_no_args(self) -> None:
        result = expand_prompt_template("Static prompt", [])
        assert result == "Static prompt"

    def test_no_placeholders(self) -> None:
        result = expand_prompt_template("No placeholders", ["ignored"])
        assert result == "No placeholders"

    def test_dollar_arguments_catch_all(self) -> None:
        result = expand_prompt_template(
            "Write about $ARGUMENTS", ["cats", "and", "dogs"]
        )
        assert result == "Write about cats and dogs"

    def test_mixed_positional_and_arguments(self) -> None:
        result = expand_prompt_template(
            "$1 folder: $ARGUMENTS", ["INBOX", "summarize", "recent"]
        )
        # $ARGUMENTS gets ALL args (including those already matched by $N)
        assert result == "INBOX folder: INBOX summarize recent"

    def test_dollar_arguments_with_no_args(self) -> None:
        result = expand_prompt_template("Tell me $ARGUMENTS", [])
        assert result == "Tell me "

    def test_repeated_placeholder(self) -> None:
        result = expand_prompt_template("$1, $1, $1", ["echo"])
        assert result == "echo, echo, echo"


class TestPromptCommandExists:
    """Existence check helper."""

    def test_exists(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "test.md").write_text("# Exists\nbody", encoding="utf-8")
        assert prompt_command_exists(commands_dir, "test") is True

    def test_not_exists(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        assert prompt_command_exists(commands_dir, "test") is False

    def test_not_exists_non_existent_dir(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        assert prompt_command_exists(commands_dir, "test") is False


class TestPromptCommandDataclass:
    """PromptCommand dataclass behavior."""

    def test_fields(self) -> None:
        cmd = PromptCommand(
            name="test",
            description="A test",
            template="template body",
            path=Path("/tmp/test.md"),
            param_count=2,
        )
        assert cmd.name == "test"
        assert cmd.description == "A test"
        assert cmd.template == "template body"
        assert cmd.path == Path("/tmp/test.md")
        assert cmd.param_count == 2

    def test_default_param_count_zero(self) -> None:
        cmd = PromptCommand(
            name="test",
            description="A test",
            template="no params",
            path=Path("/tmp/test.md"),
        )
        assert cmd.param_count == 0
