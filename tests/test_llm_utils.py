"""Tests for lightercore.llm.utils — URL resolution, message parsing, etc."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from lightercore.llm.utils import (
    build_messages,
    normalize_messages,
    parse_command_result,
    resolve_base_url,
    response_error_detail,
    validate_base_url,
)


# ── resolve_base_url ─────────────────────────────────────────────────────────


class TestResolveBaseUrl:
    def test_custom_url_used(self) -> None:
        assert (
            resolve_base_url("openai", "https://custom.example.com/v1")
            == "https://custom.example.com/v1"
        )

    def test_trailing_slash_stripped(self) -> None:
        assert (
            resolve_base_url("openai", "https://custom.example.com/")
            == "https://custom.example.com"
        )

    def test_openai_default(self) -> None:
        assert resolve_base_url("openai", "") == "https://api.openai.com/v1"

    def test_deepseek_default(self) -> None:
        assert resolve_base_url("deepseek", "") == "https://api.deepseek.com"

    def test_ollama_default(self) -> None:
        assert resolve_base_url("ollama", "") == "http://localhost:11434/v1"

    def test_unknown_defaults_to_openai(self) -> None:
        assert resolve_base_url("unknown", "") == "https://api.openai.com/v1"


# ── parse_command_result ────────────────────────────────────────────────────


class TestParseCommandResult:
    def test_bare_json(self) -> None:
        result = parse_command_result('{"tokens": ["node", "list"], "flags": {}}')
        assert result == {"tokens": ["node", "list"], "flags": {}}

    def test_markdown_fenced_json(self) -> None:
        result = parse_command_result(
            '```json\n{"tokens": ["node", "add"], "flags": {"labels": "Dog"}}\n```'
        )
        assert result is not None
        assert result["tokens"] == ["node", "add"]

    def test_markdown_fenced_no_lang(self) -> None:
        result = parse_command_result('```\n{"tokens": ["predicate", "list"]}\n```')
        assert result is not None
        assert result["tokens"] == ["predicate", "list"]

    def test_null_json(self) -> None:
        assert parse_command_result("null") is None

    def test_empty(self) -> None:
        assert parse_command_result("") is None
        assert parse_command_result(None) is None

    def test_bare_bang_command(self) -> None:
        """Semantika-style: extract !command from plain text (greedy)."""
        result = parse_command_result("Run !node list for me")
        assert result is not None
        # The bare pattern is permissive and captures all remaining text
        assert result["tokens"][0] == "node"
        assert result["tokens"][1] == "list"

    def test_backtick_wrapped_command(self) -> None:
        """Lighterbird-style: extract `!command` from text (unambiguous)."""
        result = parse_command_result("Try `!email list` to see your inbox")
        assert result is not None
        assert result["tokens"] == ["email", "list"]

    def test_no_match(self) -> None:
        assert parse_command_result("I don't understand") is None

    def test_invalid_json_no_command(self) -> None:
        assert parse_command_result('{"something": "else"}') is None

    def test_missing_tokens_key(self) -> None:
        assert parse_command_result('{"response": "hello"}') is None

    def test_fallback_order(self) -> None:
        """Backtick-wrapped is preferred over bare !command."""
        result = parse_command_result("Use `!node list` or just !node show")
        assert result is not None
        # Backtick pattern is tried first, so it finds `!node list`
        assert result["tokens"] == ["node", "list"]


# ── build_messages ──────────────────────────────────────────────────────────


class TestBuildMessages:
    def test_default_system(self) -> None:
        messages = build_messages("hello")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "hello"

    def test_with_context(self) -> None:
        context = [{"role": "assistant", "content": "Hi"}]
        messages = build_messages("hello", context=context)
        assert len(messages) == 3
        assert messages[1] == {"role": "assistant", "content": "Hi"}
        assert messages[2]["role"] == "user"

    def test_system_override(self) -> None:
        messages = build_messages("hello", system_override="Custom prompt")
        assert messages[0]["content"] == "Custom prompt"

    def test_custom_default(self) -> None:
        messages = build_messages("hello", default_system="My app prompt")
        assert messages[0]["content"] == "My app prompt"

    def test_no_context(self) -> None:
        messages = build_messages("hello")
        assert len(messages) == 2


# ── normalize_messages ──────────────────────────────────────────────────────


class TestNormalizeMessages:
    def test_adds_type_from_role(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        result = normalize_messages(messages)
        assert result[0]["role"] == "user"
        assert result[0]["type"] == "user"

    def test_adds_role_from_type(self) -> None:
        messages = [{"type": "assistant", "content": "hi"}]
        result = normalize_messages(messages)
        assert result[0]["role"] == "assistant"
        assert result[0]["type"] == "assistant"

    def test_does_not_duplicate(self) -> None:
        messages = [{"role": "user", "type": "user", "content": "hi"}]
        result = normalize_messages(messages)
        assert result[0]["role"] == "user"
        assert result[0]["type"] == "user"

    def test_preserves_extra_fields(self) -> None:
        messages = [{"role": "user", "content": "hi", "extra": "data"}]
        result = normalize_messages(messages)
        assert result[0]["extra"] == "data"

    def test_empty_list(self) -> None:
        assert normalize_messages([]) == []


# ── validate_base_url ───────────────────────────────────────────────────────


class TestValidateBaseUrl:
    def test_https_passes(self) -> None:
        validate_base_url("https://api.openai.com/v1")  # no raise

    def test_localhost_http_passes(self) -> None:
        validate_base_url("http://localhost:11434/v1")  # no raise
        validate_base_url("http://127.0.0.1:8080")  # no raise

    def test_remote_http_raises(self) -> None:
        with pytest.raises(ValueError, match="Insecure"):
            validate_base_url("http://api.example.com/v1")

    def test_empty_does_nothing(self) -> None:
        validate_base_url("")  # no raise

    def test_no_scheme_does_nothing(self) -> None:
        validate_base_url("localhost:11434")  # no raise


# ── response_error_detail ──────────────────────────────────────────────────


class TestResponseErrorDetail:
    def test_error_message_from_openai_format(self) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.json.return_value = {"error": {"message": "Rate limit exceeded"}}
        assert response_error_detail(resp) == "Rate limit exceeded"

    def test_no_error_key(self) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.json.return_value = {"detail": "Server error"}
        detail = response_error_detail(resp)
        assert "Server error" in detail

    def test_invalid_json_fallback(self) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.json.side_effect = ValueError("bad json")
        resp.text = "Internal Server Error"
        assert response_error_detail(resp) == "Internal Server Error"

    def test_empty_text(self) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.json.side_effect = ValueError("bad json")
        resp.text = ""
        assert response_error_detail(resp) == "(no detail)"
