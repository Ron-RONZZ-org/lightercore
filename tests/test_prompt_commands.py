"""Tests for lightercore.prompt_commands — file scanner, parser, and expander."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lightercore.prompt_commands import (
    PromptCommand,
    build_prompt_messages,
    expand_prompt_template,
    filter_defs_by_domain,
    list_prompt_commands,
    load_prompt_command,
    parse_tool_domains,
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

    def test_last_param_is_greedy(self) -> None:
        # The last $N captures all remaining args (greedy), not just one
        result = expand_prompt_template("$1 and $2", ["only"])
        assert result == "only and "
        # With more args than placeholders, $2 gets the tail
        result = expand_prompt_template("$1 and $2", ["first", "second", "third"])
        assert result == "first and second third"

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


# ── Execution scaffolding ─────────────────────────────────────────────────────


class TestBuildPromptMessages:
    """Message construction from expanded template."""

    def test_builds_system_and_user_messages(self) -> None:
        messages = build_prompt_messages("Do something", lambda: "You are a bot.")
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "You are a bot."}
        assert messages[1] == {"role": "user", "content": "Do something"}

    def test_system_prompt_loader_is_called(self) -> None:
        calls: list[int] = []
        def loader() -> str:
            calls.append(1)
            return "System prompt"
        build_prompt_messages("Hi", loader)
        assert len(calls) == 1


class TestParseToolDomains:
    """Domain restriction parsing."""

    def test_frontmatter_tools_takes_priority(self) -> None:
        domains = parse_tool_domains(
            "# +tools: email, todo\nDo stuff",
            frontmatter_tools=["email", "todo", "calendar"],
        )
        assert domains == {"email", "todo", "calendar"}

    def test_fallback_to_comment_directive(self) -> None:
        domains = parse_tool_domains("# +tools: email, todo\nDo stuff")
        assert domains == {"email", "todo"}

    def test_no_directive_returns_none(self) -> None:
        domains = parse_tool_domains("Just a prompt with no tools directive.")
        assert domains is None

    def test_empty_frontmatter_tools_returns_none(self) -> None:
        domains = parse_tool_domains("Do stuff", frontmatter_tools=[])
        assert domains is None

    def test_comment_directive_case_insensitive(self) -> None:
        domains = parse_tool_domains("# +TOOLS: Email\nDo stuff")
        assert domains == {"email"}

    def test_comment_directive_multiple_spaces(self) -> None:
        domains = parse_tool_domains("#   +tools:   email  ,  todo  \nDo stuff")
        assert domains == {"email", "todo"}

    def test_frontmatter_trumps_comment(self) -> None:
        # When frontmatter tools are present, comment is ignored
        domains = parse_tool_domains(
            "# +tools: todo\nDo stuff",
            frontmatter_tools=["email"],
        )
        assert domains == {"email"}


class TestFilterDefsByDomain:
    """Definition filtering by allowed domain."""

    def make_def(self, path: list[str], desc: str = "", params: list | None = None,
                 flags: list | None = None) -> dict:
        return {"path": path, "description": desc, "params": params or [], "flags": flags or []}

    def test_none_domains_returns_all(self) -> None:
        defs = [self.make_def(["email", "list"]), self.make_def(["todo", "list"])]
        assert filter_defs_by_domain(defs, None) is defs  # same object

    def test_filters_to_single_domain(self) -> None:
        defs = [
            self.make_def(["email", "list"], "List emails"),
            self.make_def(["todo", "list"], "List tasks"),
        ]
        result = filter_defs_by_domain(defs, {"email"})
        assert len(result) == 1
        assert result[0]["path"] == ["email", "list"]

    def test_excludes_bare_group_nodes(self) -> None:
        defs = [
            self.make_def(["email"], "", [], []),  # bare group
            self.make_def(["email", "list"], "List emails"),
        ]
        result = filter_defs_by_domain(defs, {"email"})
        assert len(result) == 1
        assert result[0]["path"] == ["email", "list"]

    def test_empty_allowed_set_returns_empty(self) -> None:
        defs = [self.make_def(["email", "list"])]
        assert filter_defs_by_domain(defs, set()) == []

    def test_keeps_group_with_description(self) -> None:
        defs = [self.make_def(["email"], "Email commands")]
        result = filter_defs_by_domain(defs, {"email"})
        assert len(result) == 1


# ── Full execution pipeline ───────────────────────────────────────────────────


class TestExecutePromptCommand:
    """Unified prompt command execution pipeline."""

    @pytest.fixture
    def commands_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "commands"
        d.mkdir()
        return d

    @pytest.fixture
    def mock_provider(self) -> MagicMock:
        p = MagicMock()
        p.available = True
        return p

    @pytest.fixture
    def mock_definitions_loader(self) -> MagicMock:
        return MagicMock(return_value=[])

    @pytest.fixture
    def mock_tool_loop(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        mock = AsyncMock(return_value="Final answer from LLM.")
        monkeypatch.setattr("lightercore.prompt_commands.run_tool_loop", mock)
        return mock

    async def test_not_found_returns_404(self, commands_dir: Path, mock_provider: MagicMock) -> None:
        from lightercore.prompt_commands import execute_prompt_command

        result = await execute_prompt_command(
            name="nonexistent",
            args=[],
            commands_dir=commands_dir,
            provider=mock_provider,
            system_prompt_loader=lambda: "System prompt",
            definitions_loader=MagicMock(return_value=[]),
            dispatch_fn=MagicMock(),
            get_handler_metadata_fn=MagicMock(return_value=None),
            get_command_level_fn=MagicMock(return_value=None),
        )
        assert result["status_code"] == 404
        assert "nonexistent" in result["detail"]

    async def test_provider_unavailable_returns_status(
        self, commands_dir: Path
    ) -> None:
        from lightercore.prompt_commands import execute_prompt_command

        # Create command file
        (commands_dir / "test.md").write_text("# Test\nDo $1", encoding="utf-8")

        provider = MagicMock()
        provider.available = False

        result = await execute_prompt_command(
            name="test",
            args=["hello"],
            commands_dir=commands_dir,
            provider=provider,
            system_prompt_loader=lambda: "System prompt",
            definitions_loader=MagicMock(return_value=[]),
            dispatch_fn=MagicMock(),
            get_handler_metadata_fn=MagicMock(return_value=None),
            get_command_level_fn=MagicMock(return_value=None),
        )
        assert result["type"] == "status"
        assert "not configured" in result["data"]["message"]

    async def test_successful_execution_returns_chat(
        self, commands_dir: Path, mock_provider: MagicMock, mock_tool_loop: MagicMock
    ) -> None:
        from lightercore.prompt_commands import execute_prompt_command

        (commands_dir / "test.md").write_text("# Test\nDo $1", encoding="utf-8")

        result = await execute_prompt_command(
            name="test",
            args=["hello"],
            commands_dir=commands_dir,
            provider=mock_provider,
            system_prompt_loader=lambda: "System prompt",
            definitions_loader=MagicMock(return_value=[]),
            dispatch_fn=MagicMock(),
            get_handler_metadata_fn=MagicMock(return_value=None),
            get_command_level_fn=MagicMock(return_value=None),
            title_prefix="/*",
        )
        assert result["type"] == "chat"
        assert result["title"] == "/*test"
        assert "Final answer" in result["data"]["html"]

    async def test_confirm_tool_passed_through(
        self, commands_dir: Path, mock_provider: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from lightercore.prompt_commands import execute_prompt_command

        (commands_dir / "test.md").write_text("# Test\nDo $1", encoding="utf-8")

        confirm = {
            "type": "confirm_tool",
            "session_id": "abc-123",
            "tokens": ["email", "send"],
            "flags": {"to": "user@example.com"},
            "batch": [],
            "message": "Confirm?",
        }
        mock = AsyncMock(return_value=confirm)
        monkeypatch.setattr("lightercore.prompt_commands.run_tool_loop", mock)

        result = await execute_prompt_command(
            name="test",
            args=["hello"],
            commands_dir=commands_dir,
            provider=mock_provider,
            system_prompt_loader=lambda: "System prompt",
            definitions_loader=MagicMock(return_value=[]),
            dispatch_fn=MagicMock(),
            get_handler_metadata_fn=MagicMock(return_value=None),
            get_command_level_fn=MagicMock(return_value=None),
        )
        assert result["type"] == "confirm_tool"
        assert result["session_id"] == "abc-123"
        assert result["tokens"] == ["email", "send"]

    async def test_empty_llm_response(self, commands_dir: Path, mock_provider: MagicMock,
                                       monkeypatch: pytest.MonkeyPatch) -> None:
        from lightercore.prompt_commands import execute_prompt_command

        (commands_dir / "test.md").write_text("# Test\nDo $1", encoding="utf-8")
        mock = AsyncMock(return_value=None)
        monkeypatch.setattr("lightercore.prompt_commands.run_tool_loop", mock)

        result = await execute_prompt_command(
            name="test",
            args=["hello"],
            commands_dir=commands_dir,
            provider=mock_provider,
            system_prompt_loader=lambda: "System prompt",
            definitions_loader=MagicMock(return_value=[]),
            dispatch_fn=MagicMock(),
            get_handler_metadata_fn=MagicMock(return_value=None),
            get_command_level_fn=MagicMock(return_value=None),
        )
        assert result["type"] == "chat"
        assert "(empty response)" in result["data"]["html"]

    async def test_provider_is_available_method_fallback(
        self, commands_dir: Path
    ) -> None:
        """Provider with is_available() method instead of .available property."""
        from lightercore.prompt_commands import execute_prompt_command

        (commands_dir / "test.md").write_text("# Test\nDo $1", encoding="utf-8")

        # Provider with is_available() method, no .available attribute
        provider = MagicMock(spec=[])
        provider.is_available = MagicMock(return_value=True)
        # Remove .available if it was auto-created by MagicMock
        if hasattr(provider, "available"):
            delattr(provider, "available")

        mock = AsyncMock(return_value="LLM says hi.")
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr("lightercore.prompt_commands.run_tool_loop", mock)
        try:
            result = await execute_prompt_command(
                name="test",
                args=["hello"],
                commands_dir=commands_dir,
                provider=provider,
                system_prompt_loader=lambda: "System prompt",
                definitions_loader=MagicMock(return_value=[]),
                dispatch_fn=MagicMock(),
                get_handler_metadata_fn=MagicMock(return_value=None),
                get_command_level_fn=MagicMock(return_value=None),
            )
        finally:
            monkeypatch.undo()

        assert result["type"] == "chat"
        assert "LLM says hi" in result["data"]["html"]
        provider.is_available.assert_called_once()


class TestPromptCommandEventStream:
    """SSE streaming for prompt commands."""

    @pytest.fixture
    def commands_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "commands"
        d.mkdir()
        return d

    async def test_not_found_yields_error_then_done(self, commands_dir: Path) -> None:
        from lightercore.prompt_commands import prompt_command_event_stream

        provider = MagicMock()
        provider.available = True

        events: list[str] = []
        async for event in prompt_command_event_stream(
            name="nonexistent",
            args=[],
            commands_dir=commands_dir,
            provider=provider,
            system_prompt_loader=lambda: "System prompt",
        ):
            events.append(event)

        assert len(events) == 2
        assert "not found" in events[0]
        assert "[DONE]" in events[1]

    async def test_provider_unavailable_yields_status_then_done(
        self, commands_dir: Path
    ) -> None:
        from lightercore.prompt_commands import prompt_command_event_stream

        (commands_dir / "test.md").write_text("# Test\nHello $1", encoding="utf-8")

        provider = MagicMock()
        provider.available = False

        events: list[str] = []
        async for event in prompt_command_event_stream(
            name="test",
            args=["world"],
            commands_dir=commands_dir,
            provider=provider,
            system_prompt_loader=lambda: "System prompt",
        ):
            events.append(event)

        assert len(events) == 2
        assert "not configured" in events[0]
        assert "[DONE]" in events[1]

    async def test_successful_stream(self, commands_dir: Path) -> None:
        from lightercore.prompt_commands import prompt_command_event_stream

        (commands_dir / "test.md").write_text("# Test\nHello $1", encoding="utf-8")

        # Create an async generator for the mock
        async def fake_stream(*args, **kwargs) -> AsyncMock:
            async def _gen():
                yield "Hello "
                yield "world!"
            return _gen()

        provider = MagicMock()
        provider.available = True
        provider.chat = fake_stream

        events: list[str] = []
        async for event in prompt_command_event_stream(
            name="test",
            args=["world"],
            commands_dir=commands_dir,
            provider=provider,
            system_prompt_loader=lambda: "System prompt",
            timeout=5.0,
        ):
            events.append(event)

        assert len(events) == 3
        assert "[DONE]" in events[2]
