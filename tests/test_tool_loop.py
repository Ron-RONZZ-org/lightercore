"""Tests for tool_loop helper functions and resume_execution.

Focuses on the pure functions extracted/added for feedback injection:
- :func:`_format_command_str`
- :func:`_resolve_feedback`
- :func:`_inject_feedback_summary`
- :func:`resume_execution` — decisions key-type regression test
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lightercore.llm.tool_loop import (
    _format_command_str,
    _get_tool_level,
    _inject_feedback_summary,
    _resolve_feedback,
    resume_execution,
    run_tool_loop,
    _pending_executions,
)
from lightercore.llm.base import ChatResult, ToolCall
from lightercore.permissions import PermissionLevel


class TestFormatCommandStr:
    def test_basic_tokens(self):
        """Tokens-only: !node list"""
        assert _format_command_str(["node", "list"], {}) == "!node list"

    def test_tokens_with_flags(self):
        """Tokens + flags with values: !node add --label Alice"""
        assert (
            _format_command_str(["node", "add"], {"label": "Alice"})
            == "!node add --label Alice"
        )

    def test_boolean_flag(self):
        """Flag with empty value: !node add --force"""
        assert (
            _format_command_str(["node", "add"], {"force": ""})
            == "!node add --force"
        )

    def test_multiple_flags(self):
        """Multiple flags: !search --q hello --limit 10"""
        result = _format_command_str(["search"], {"q": "hello", "limit": "10"})
        assert "!search" in result
        assert "--q hello" in result
        assert "--limit 10" in result

    def test_mixed_flags(self):
        """Mixed value and boolean flags."""
        result = _format_command_str(
            ["triple", "add"], {"subject": "n1", "predicate": "p1", "object": "n2", "force": ""}
        )
        assert "!triple add" in result
        assert "--subject n1" in result
        assert "--predicate p1" in result
        assert "--object n2" in result
        assert "--force" in result


class TestResolveFeedback:
    def test_no_feedback(self):
        """None feedback returns None."""
        assert _resolve_feedback(0, {0: False}, None) is None

    def test_approved_tool(self):
        """Approved tool with feedback returns None."""
        assert _resolve_feedback(0, {0: True}, "Some feedback") is None

    def test_rejected_tool_global_feedback_string(self):
        """Global string feedback applied to rejected tool."""
        assert _resolve_feedback(0, {0: False}, "Try searching first") == "Try searching first"

    def test_rejected_tool_per_index_feedback(self):
        """Per-index dict feedback."""
        feedback = {0: "Wrong label", 1: "Different approach"}
        assert _resolve_feedback(0, {0: False}, feedback) == "Wrong label"
        assert _resolve_feedback(1, {1: False}, feedback) == "Different approach"

    def test_approved_with_per_index_ignored(self):
        """Approved tool with per-index feedback returns None."""
        feedback = {0: "Some feedback"}
        assert _resolve_feedback(0, {0: True}, feedback) is None

    def test_missing_index_in_per_index(self):
        """Index not in dict returns None."""
        feedback = {1: "Feedback for tool 1"}
        assert _resolve_feedback(0, {0: False}, feedback) is None

    def test_empty_string_feedback(self):
        """Empty string in per-index dict returns empty string (falsy but valid)."""
        feedback = {0: ""}
        assert _resolve_feedback(0, {0: False}, feedback) == ""


class TestInjectFeedbackSummary:
    def make_tc(self, idx: int, name: str = "node.list", args: str = "{}") -> dict:
        """Create a tool-call dict matching the stored format."""
        return {
            "id": f"call_{idx}",
            "type": "function",
            "function": {"name": name, "arguments": args},
        }

    def test_no_feedback_no_change(self):
        """No feedback -> decision summary still injected (no feedback text)."""
        messages = [{"role": "user", "content": "hello"}]
        tool_calls = [self.make_tc(0)]
        resolved = {0: False}
        _inject_feedback_summary(messages, tool_calls, resolved, None)
        assert len(messages) == 2
        assert messages[1]["role"] == "user"
        assert "- Rejected: !node list" in messages[1]["content"]

    def test_all_approved_injection(self):
        """All tools approved -> summary lists all as approved."""
        messages = [{"role": "user", "content": "hello"}]
        tool_calls = [self.make_tc(0, "node.list"), self.make_tc(1, "node.add")]
        resolved = {0: True, 1: True}
        _inject_feedback_summary(messages, tool_calls, resolved, "Global feedback")
        assert len(messages) == 2
        assert "- Approved: !node list" in messages[1]["content"]
        assert "- Approved: !node add" in messages[1]["content"]

    def test_single_rejected_tool_with_feedback(self):
        """Single rejected tool -> summary injected with feedback."""
        messages = [{"role": "user", "content": "hello"}]
        tool_calls = [self.make_tc(0, "node.add", '{"label": "Alice"}')]
        resolved = {0: False}
        _inject_feedback_summary(messages, tool_calls, resolved, "Use a different label")
        assert len(messages) == 2
        assert messages[1]["role"] == "user"
        assert "- Rejected: !node add --label Alice (feedback: Use a different label)" in messages[1]["content"]

    def test_mixed_approval_rejection(self):
        """Mix of approved and rejected -> both appear in summary."""
        messages = [{"role": "user", "content": "hello"}]
        tool_calls = [
            self.make_tc(0, "node.add", '{"label": "Alice"}'),
            self.make_tc(1, "search", '{"q": "test"}'),
        ]
        resolved = {0: False, 1: True}
        _inject_feedback_summary(
            messages, tool_calls, resolved,
            {0: "Wrong label", 1: "N/A"},
        )
        assert len(messages) == 2
        content = messages[1]["content"]
        assert "- Rejected: !node add --label Alice (feedback: Wrong label)" in content
        assert "- Approved: !search --q test" in content

    def test_multiple_rejected_tools(self):
        """Multiple rejected tools with feedback -> all appear in summary."""
        messages = [{"role": "user", "content": "hello"}]
        tool_calls = [
            self.make_tc(0, "node.add", '{"label": "X"}'),
            self.make_tc(1, "triple.add", '{"s": "n1"}'),
        ]
        resolved = {0: False, 1: False}
        feedback = {
            0: "Label is too short",
            1: "Wrong triple structure",
        }
        _inject_feedback_summary(messages, tool_calls, resolved, feedback)
        assert len(messages) == 2
        content = messages[1]["content"]
        assert "- Rejected: !node add --label X (feedback: Label is too short)" in content
        assert "- Rejected: !triple add --s n1 (feedback: Wrong triple structure)" in content

    def test_empty_feedback_dict(self):
        """Empty feedback dict -> summary still injected (no feedback text)."""
        messages = [{"role": "user", "content": "hello"}]
        tool_calls = [self.make_tc(0, "node.list")]
        resolved = {0: False}
        _inject_feedback_summary(messages, tool_calls, resolved, {})
        assert len(messages) == 2
        assert "- Rejected: !node list" in messages[1]["content"]


class TestResumeExecutionDecisionsKeyType:
    """Regression tests for the decisions key-type fix.

    The frontend sends decisions as JSON, which deserializes with *string*
    keys ("0", "1"). The code iterates tool_calls with integer indices (0, 1).
    Before the fix, ``resolved.get(0, False)`` would miss the string key "0"
    and silently treat ALL tools as rejected.

    These tests verify that string-keyed decisions are correctly converted.
    """

    @pytest.fixture(autouse=True)
    def cleanup_pending(self):
        """Clear _pending_executions before and after each test."""
        _pending_executions.clear()
        yield
        _pending_executions.clear()

    def _make_session(self, tool_names: list[str]) -> str:
        """Create a mock pending session and return its session_id."""
        import uuid

        session_id = str(uuid.uuid4())
        _pending_executions[session_id] = {
            "messages": [{"role": "user", "content": "do it"}],
            "tool_calls": [
                {
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": "{}",
                    },
                }
                for i, name in enumerate(tool_names)
            ],
            "tools": [],
            "name": "test_session",
            "write_paths": {
                tuple(name.split(".")): {"tokens": name.split("."), "flags": {}}
                for name in tool_names
            },
        }
        return session_id

    async def _run_resume(self, session_id: str, decisions: dict) -> None:
        """Run resume_execution with mocked dependencies."""
        mock_provider = MagicMock()
        mock_dispatch = MagicMock(return_value={"status": "ok"})
        # get_handler_metadata returns truthy so tool_loop treats these as known commands
        handler_meta = MagicMock()
        mock_get_meta = MagicMock(return_value=handler_meta)
        # get_command_level_fn returns WRITE so they are gated
        mock_level = MagicMock(return_value=2)  # PermissionLevel.WRITE = 2

        # resume_execution calls run_tool_loop at the end — it will fail because
        # the LLM won't have messages. Catch that gracefully.
        with patch(
            "lightercore.llm.tool_loop.run_tool_loop",
            new_callable=AsyncMock,
            return_value={"type": "chat", "data": {"html": "<p>done</p>"}},
        ):
            result = await resume_execution(
                session_id=session_id,
                decisions=decisions,
                provider=mock_provider,
                dispatch_fn=mock_dispatch,
                get_handler_metadata_fn=mock_get_meta,
                get_command_level_fn=mock_level,
            )

        return mock_dispatch, result

    async def test_string_keys_approved(self):
        """Decisions with string keys {"0": true} execute the approved tool."""
        session_id = self._make_session(["template.save"])
        mock_dispatch, result = await self._run_resume(
            session_id, {"0": True}
        )
        mock_dispatch.assert_called_once()

    async def test_string_keys_rejected(self):
        """Decisions with string keys {"0": false} skip the rejected tool."""
        session_id = self._make_session(["template.save"])
        mock_dispatch, result = await self._run_resume(
            session_id, {"0": False}
        )
        mock_dispatch.assert_not_called()

    async def test_mixed_string_keys(self):
        """Mix of approved/rejected with string keys."""
        session_id = self._make_session(["node.add", "predicate.add"])
        mock_dispatch, result = await self._run_resume(
            session_id, {"0": True, "1": False}
        )
        # Only the first tool should be dispatched
        assert mock_dispatch.call_count == 1
        # Verify it was called with the right path
        call_args = mock_dispatch.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] == "node.add"

    async def test_int_keys_still_work(self):
        """Existing int-keyed decisions still work (backward compat)."""
        session_id = self._make_session(["template.save"])
        mock_dispatch, result = await self._run_resume(
            session_id, {0: True}
        )
        mock_dispatch.assert_called_once()


# ── get_tool_level_fn support ────────────────────────────────────────


class TestGetToolLevel:
    """Unit tests for _get_tool_level helper."""

    def test_tool_level_fn_takes_priority(self):
        """get_tool_level_fn overrides CLI registry when it returns a level."""
        result = _get_tool_level(
            "email.send",
            get_tool_level_fn=lambda p: PermissionLevel.WRITE,
            get_handler_metadata_fn=lambda p: None,
            get_command_level_fn=lambda p: None,
        )
        assert result == PermissionLevel.WRITE

    def test_tool_level_fn_provided_returns_its_value(self):
        """When get_tool_level_fn is provided, its return value is authoritative (no fallback)."""
        result = _get_tool_level(
            "todo.add",
            get_tool_level_fn=lambda p: None,  # callback exists but returns None
            get_handler_metadata_fn=lambda p: {"description": "Add todo"},
            get_command_level_fn=lambda p: PermissionLevel.WRITE,
        )
        # The callback is the single source of truth — no CLI fallback
        assert result is None

    def test_tool_level_fn_prevents_cli_override(self):
        """get_tool_level_fn returning READ prevents CLI WRITE from gating."""
        result = _get_tool_level(
            "todo.add",
            get_tool_level_fn=lambda p: PermissionLevel.READ,
            get_handler_metadata_fn=lambda p: {"description": "Add todo"},
            get_command_level_fn=lambda p: PermissionLevel.WRITE,
        )
        assert result == PermissionLevel.READ

    def test_no_tool_fn_cli_handler(self):
        """No get_tool_level_fn, CLI has handler → use CLI level."""
        result = _get_tool_level(
            "email.list",
            get_tool_level_fn=None,
            get_handler_metadata_fn=lambda p: {"description": "List"},
            get_command_level_fn=lambda p: PermissionLevel.READ,
        )
        assert result == PermissionLevel.READ

    def test_no_tool_fn_no_handler(self):
        """No get_tool_level_fn, no CLI handler → None."""
        result = _get_tool_level(
            "llm.custom_tool",
            get_tool_level_fn=None,
            get_handler_metadata_fn=lambda p: None,
            get_command_level_fn=lambda p: None,
        )
        assert result is None

    def test_both_fn_and_handler_get_tool_wins(self):
        """Both get_tool_level_fn and CLI handler present → tool_fn wins."""
        result = _get_tool_level(
            "email.list",
            get_tool_level_fn=lambda p: PermissionLevel.DESTRUCTIVE,
            get_handler_metadata_fn=lambda p: {"description": "List"},
            get_command_level_fn=lambda p: PermissionLevel.READ,
        )
        assert result == PermissionLevel.DESTRUCTIVE


class TestRunToolLoopGetToolLevelFn:
    """run_tool_loop with get_tool_level_fn callback."""

    def _make_mock_provider(self, responses: list[ChatResult]) -> MagicMock:
        mock = MagicMock()
        mock.chat_with_tools = AsyncMock()
        mock.chat_with_tools.side_effect = responses
        return mock

    def _make_meta_fn(self, known: set[str] | None = None):
        known = known or set()

        def meta_fn(path: str) -> dict | None:
            if path in known:
                return {"description": f"Handler for {path}"}
            return None
        return meta_fn

    def _make_level_fn(self, levels: dict[str, int] | None = None):
        levels = levels or {}

        def level_fn(path: str) -> int | None:
            return levels.get(path, None)
        return level_fn

    async def test_llm_tool_write_gated(self):
        """LLM tool with WRITE level via get_tool_level_fn is gated."""
        mock = self._make_mock_provider([
            ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(id="c1", function={"name": "email_send", "arguments": '{"to": "a@b.com"}'}),
                ],
            ),
        ])

        result = await run_tool_loop(
            messages=[{"role": "user", "content": "send email"}],
            tools=[],
            name="test",
            provider=mock,
            dispatch_fn=lambda p, f: {"status": "ok"},
            get_handler_metadata_fn=self._make_meta_fn(),  # NOT in CLI registry
            get_command_level_fn=self._make_level_fn(),
            get_tool_level_fn=lambda p: PermissionLevel.WRITE,  # LLM tool registry says WRITE
        )

        assert isinstance(result, dict)
        assert result["type"] == "confirm_tool"
        assert len(result["batch"]) == 1
        assert result["batch"][0]["tokens"] == ["email", "send"]

    async def test_llm_tool_destructive_gated(self):
        """LLM tool with DESTRUCTIVE level is gated."""
        mock = self._make_mock_provider([
            ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(id="c1", function={"name": "email_trash", "arguments": '{"uuid": "abc"}'}),
                ],
            ),
        ])

        result = await run_tool_loop(
            messages=[{"role": "user", "content": "trash email"}],
            tools=[],
            name="test",
            provider=mock,
            dispatch_fn=lambda p, f: {"status": "ok"},
            get_handler_metadata_fn=self._make_meta_fn(),
            get_command_level_fn=self._make_level_fn(),
            get_tool_level_fn=lambda p: PermissionLevel.DESTRUCTIVE,
        )

        assert isinstance(result, dict)
        assert result["type"] == "confirm_tool"
        assert len(result["batch"]) == 1

    async def test_llm_tool_read_executes_immediately(self):
        """LLM tool with READ level passes without confirmation."""
        mock = self._make_mock_provider([
            ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(id="c1", function={"name": "email_find", "arguments": '{"query": "hello"}'}),
                ],
            ),
            ChatResult(content="Found matching emails."),
        ])

        dispatched = []

        def dispatch(path, flags):
            dispatched.append((path, flags))
            return {"status": "ok", "count": 5}

        result = await run_tool_loop(
            messages=[{"role": "user", "content": "find emails"}],
            tools=[],
            name="test",
            provider=mock,
            dispatch_fn=dispatch,
            get_handler_metadata_fn=self._make_meta_fn(),
            get_command_level_fn=self._make_level_fn(),
            get_tool_level_fn=lambda p: PermissionLevel.READ,
        )

        assert result == "Found matching emails."
        assert dispatched == [("email.find", {"query": "hello"})]

    async def test_no_tool_level_fn_unknown_tool_executes(self):
        """No get_tool_level_fn + no CLI handler → tool executes (backward compat)."""
        mock = self._make_mock_provider([
            ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(id="c1", function={"name": "unknown_tool", "arguments": "{}"}),
                ],
            ),
            ChatResult(content="Done."),
        ])

        dispatched = []

        def dispatch(path, flags):
            dispatched.append((path, flags))
            return {"status": "ok"}

        result = await run_tool_loop(
            messages=[{"role": "user", "content": "do thing"}],
            tools=[],
            name="test",
            provider=mock,
            dispatch_fn=dispatch,
            get_handler_metadata_fn=self._make_meta_fn(),  # NOT in CLI
            get_command_level_fn=self._make_level_fn(),     # no levels
            get_tool_level_fn=None,                          # NOT provided
        )

        assert result == "Done."
        # tc_path converts _ to . — "unknown_tool" becomes "unknown.tool"
        assert dispatched == [("unknown.tool", {})]


class TestResumeExecutionGetToolLevelFn:
    """Resume execution preserves get_tool_level_fn through pause/continue."""

    @pytest.fixture(autouse=True)
    def cleanup_pending(self):
        _pending_executions.clear()
        yield
        _pending_executions.clear()

    def _make_session(self, tool_name: str, tool_level: PermissionLevel | None = None) -> str:
        import uuid
        session_id = str(uuid.uuid4())
        state = {
            "messages": [
                {"role": "user", "content": "do it"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": tool_name, "arguments": "{}"}},
                ]},
            ],
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": tool_name, "arguments": "{}"}},
            ],
            "tools": [],
            "name": "test",
            "write_paths": {tuple(tool_name.split(".")): {"tokens": tool_name.split("."), "flags": {}}},
        }
        if tool_level is not None:
            state["get_tool_level_fn"] = lambda p: tool_level
        _pending_executions[session_id] = state
        return session_id

    async def test_resume_uses_stored_get_tool_level_fn(self):
        """Resume uses the get_tool_level_fn stored in session state."""
        mock_provider = MagicMock()
        mock_provider.chat_with_tools = AsyncMock(return_value=ChatResult(content="Done."))
        dispatch = MagicMock(return_value={"status": "ok"})

        session_id = self._make_session("email.send", tool_level=PermissionLevel.WRITE)

        with patch(
            "lightercore.llm.tool_loop.run_tool_loop",
            new_callable=AsyncMock,
            return_value="Done.",
        ):
            result = await resume_execution(
                session_id=session_id,
                decisions={0: True},
                provider=mock_provider,
                dispatch_fn=dispatch,
                get_handler_metadata_fn=lambda p: None,  # NOT in CLI
                get_command_level_fn=lambda p: None,
                # Don't pass get_tool_level_fn — should use stored value
            )

        dispatch.assert_called_once()

    async def test_resume_explicit_param_overrides_stored(self):
        """Explicit get_tool_level_fn param overrides stored state value."""
        mock_provider = MagicMock()
        mock_provider.chat_with_tools = AsyncMock(return_value=ChatResult(content="Done."))
        dispatch = MagicMock(return_value={"status": "ok"})

        session_id = self._make_session("email.send", tool_level=PermissionLevel.DESTRUCTIVE)

        with patch(
            "lightercore.llm.tool_loop.run_tool_loop",
            new_callable=AsyncMock,
            return_value="Done.",
        ):
            await resume_execution(
                session_id=session_id,
                decisions={0: True},
                provider=mock_provider,
                dispatch_fn=dispatch,
                get_handler_metadata_fn=lambda p: None,
                get_command_level_fn=lambda p: None,
                get_tool_level_fn=lambda p: PermissionLevel.READ,  # override
            )

        # The explicit READ-level fn changes the tool to READ, which is
        # skipped on resume (READ tools already executed in initial loop).
        dispatch.assert_not_called()
