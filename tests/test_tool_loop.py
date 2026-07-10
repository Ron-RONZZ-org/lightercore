"""Tests for tool_loop helper functions.

Focuses on the pure functions extracted/added for feedback injection:
- :func:`_format_command_str`
- :func:`_resolve_feedback`
- :func:`_inject_feedback_summary`
"""

from __future__ import annotations

from lightercore.llm.tool_loop import (
    _format_command_str,
    _inject_feedback_summary,
    _resolve_feedback,
)
from lightercore.llm.base import ToolCall


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
        """No feedback -> messages unchanged."""
        messages = [{"role": "user", "content": "hello"}]
        tool_calls = [self.make_tc(0)]
        resolved = {0: False}
        _inject_feedback_summary(messages, tool_calls, resolved, None)
        assert len(messages) == 1
        assert messages[0]["content"] == "hello"

    def test_all_approved_no_injection(self):
        """All tools approved -> no injection even with feedback."""
        messages = [{"role": "user", "content": "hello"}]
        tool_calls = [self.make_tc(0), self.make_tc(1)]
        resolved = {0: True, 1: True}
        _inject_feedback_summary(messages, tool_calls, resolved, "Global feedback")
        assert len(messages) == 1

    def test_single_rejected_tool_with_feedback(self):
        """Single rejected tool -> summary injected."""
        messages = [{"role": "user", "content": "hello"}]
        tool_calls = [self.make_tc(0, "node.add", '{"label": "Alice"}')]
        resolved = {0: False}
        _inject_feedback_summary(messages, tool_calls, resolved, "Use a different label")
        assert len(messages) == 2
        assert messages[1]["role"] == "user"
        # _format_command_str uses spaces (not dots) for display
        assert "Rejected !node add --label Alice" in messages[1]["content"]
        assert "Use a different label" in messages[1]["content"]

    def test_mixed_approval_rejection(self):
        """Mix of approved and rejected -> only rejected in summary."""
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
        assert "Rejected !node add --label Alice" in messages[1]["content"]
        assert "Wrong label" in messages[1]["content"]
        # Approved tool should not appear
        assert "search" not in messages[1]["content"]

    def test_multiple_rejected_tools(self):
        """Multiple rejected tools -> all appear in summary."""
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
        assert "Rejected !node add --label X" in content
        assert "Label is too short" in content
        assert "Rejected !triple add --s n1" in content
        assert "Wrong triple structure" in content

    def test_empty_feedback_dict(self):
        """Empty feedback dict -> no injection."""
        messages = [{"role": "user", "content": "hello"}]
        tool_calls = [self.make_tc(0)]
        resolved = {0: False}
        _inject_feedback_summary(messages, tool_calls, resolved, {})
        assert len(messages) == 1
