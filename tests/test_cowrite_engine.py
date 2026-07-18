"""Tests for lightercore/cowrite/engine.py — co-writing engine, diffs, and LLM integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from lightercore.cowrite.engine import (
    _clean_llm_response,
    compute_diffs,
    cowrite,
)


# ── _clean_llm_response ──────────────────────────────────────────────────────


class TestCleanLlmResponse:
    """Parse and validate LLM JSON responses."""

    def test_valid_json_no_fences(self):
        raw = '{"subject": "Hello", "body": "World"}'
        result = _clean_llm_response(raw, {"subject", "body"})
        assert result == {"subject": "Hello", "body": "World"}

    def test_valid_json_with_markdown_fences(self):
        raw = '```json\n{"subject": "Hi", "body": "There"}\n```'
        result = _clean_llm_response(raw, {"subject", "body"})
        assert result == {"subject": "Hi", "body": "There"}

    def test_valid_json_with_triple_backtick_no_lang(self):
        raw = '```\n{"subject": "A", "body": "B"}\n```'
        result = _clean_llm_response(raw, {"subject", "body"})
        assert result == {"subject": "A", "body": "B"}

    def test_surrounding_text_stripped(self):
        raw = 'Here is the revised text:\n{"subject": "Rev", "body": "Body"}\n--- end'
        result = _clean_llm_response(raw, {"subject", "body"})
        assert result == {"subject": "Rev", "body": "Body"}

    def test_raises_value_error_on_malformed_json(self):
        raw = '{"subject": "broken'
        with pytest.raises(ValueError):
            _clean_llm_response(raw, {"subject"})

    def test_raises_value_error_on_missing_fields(self):
        raw = '{"subject": "Only Subject"}'
        with pytest.raises(ValueError, match="missing or empty field 'body'"):
            _clean_llm_response(raw, {"subject", "body"})

    def test_raises_value_error_on_empty_string_field(self):
        raw = '{"subject": "", "body": "Content"}'
        with pytest.raises(ValueError, match="missing or empty field 'subject'"):
            _clean_llm_response(raw, {"subject", "body"})

    def test_raises_value_error_on_none_field(self):
        raw = '{"subject": null, "body": "Content"}'
        with pytest.raises(ValueError, match="missing or empty field 'subject'"):
            _clean_llm_response(raw, {"subject", "body"})

    def test_empty_input_raises_error(self):
        with pytest.raises(ValueError):
            _clean_llm_response("", {"field"})


# ── compute_diffs ────────────────────────────────────────────────────────────


class TestComputeDiffs:
    """Character-level diff computation between original and revised text."""

    def test_no_changes(self):
        diffs = compute_diffs("Hello world", "Hello world")
        assert len(diffs) == 1
        assert diffs[0]["tag"] == "equal"

    def test_simple_replacement(self):
        diffs = compute_diffs("Hello world", "Hello there")
        assert diffs[0]["tag"] == "equal"
        assert diffs[0]["start_orig"] == 0
        assert diffs[0]["end_orig"] == 6
        replace_ops = [d for d in diffs if d["tag"] == "replace"]
        assert len(replace_ops) >= 1

    def test_insertion(self):
        diffs = compute_diffs("Hello", "Hello world")
        insert_ops = [d for d in diffs if d["tag"] == "insert"]
        assert len(insert_ops) >= 1
        assert insert_ops[0]["inserted"] == " world"

    def test_deletion(self):
        diffs = compute_diffs("Hello world", "Hello")
        delete_ops = [d for d in diffs if d["tag"] == "delete"]
        assert len(delete_ops) >= 1
        assert delete_ops[0]["deleted"] == " world"

    def test_complete_replacement(self):
        diffs = compute_diffs("Old text", "New text")
        replace_ops = [d for d in diffs if d["tag"] == "replace"]
        assert any(d["deleted"] and d["inserted"] for d in replace_ops)

    def test_empty_original(self):
        diffs = compute_diffs("", "New content")
        insert_ops = [d for d in diffs if d["tag"] == "insert"]
        assert any(d["inserted"] == "New content" for d in insert_ops)

    def test_empty_revised(self):
        diffs = compute_diffs("Old content", "")
        delete_ops = [d for d in diffs if d["tag"] == "delete"]
        assert any(d["deleted"] == "Old content" for d in delete_ops)

    def test_diffs_contain_position_info(self):
        diffs = compute_diffs("Hello world", "Hello there")
        replace_ops = [d for d in diffs if d["tag"] == "replace"]
        assert len(replace_ops) >= 1
        op = replace_ops[0]
        assert "start_orig" in op
        assert "end_orig" in op
        assert op["start_orig"] <= op["end_orig"]
        assert op["start_orig"] == 6


# ── cowrite (integration with mocked LLM) ────────────────────────────────────


@pytest.mark.asyncio
async def test_cowrite_calls_chat_fn_and_returns_edits():
    """Happy path: chat_fn returns valid JSON → edits are computed."""
    mock_chat = AsyncMock()
    mock_chat.return_value = (
        '{"subject": "Revised Subject", "body": "Revised body text here"}'
    )

    result = await cowrite(
        "email-send",
        {"subject": "Original Subject", "body": "Original body"},
        "make it formal",
        chat_fn=mock_chat,
    )

    assert "edits" in result
    assert "revised" in result
    assert "original" in result
    assert "session_id" in result
    assert result["revised"]["subject"] == "Revised Subject"
    assert result["revised"]["body"] == "Revised body text here"
    assert result["original"] == {
        "subject": "Original Subject",
        "body": "Original body",
    }
    assert "subject" in result["edits"]
    assert "body" in result["edits"]
    assert len(result["edits"]["subject"]) > 0


@pytest.mark.asyncio
async def test_cowrite_appends_style_content():
    """Style content is appended to the protocol prompt."""
    style_applied = False

    async def check_style(messages, **kwargs):
        nonlocal style_applied
        system = messages[0]["content"]
        if "## User Style Guide" in system and "Be concise" in system:
            style_applied = True
        return '{"label": "Hello", "def": "World"}'

    await cowrite(
        "test-form",
        {"label": "Hi", "def": "There"},
        "improve",
        chat_fn=check_style,
        style_content="Be concise.",
    )

    assert style_applied, "Style content was not found in the system prompt"


@pytest.mark.asyncio
async def test_cowrite_passes_context():
    """Context dict is included in the LLM request."""
    context_received = False

    async def check_context(messages, **kwargs):
        nonlocal context_received
        user_msg = messages[1]["content"]
        if '"writing_samples"' in user_msg:
            context_received = True
        return '{"f1": "Rev"}'

    await cowrite(
        "test-form",
        {"f1": "Orig"},
        "improve",
        chat_fn=check_context,
        context={"writing_samples": [{"title": "Sample", "body": "Body"}]},
    )

    assert context_received, "Context was not included in the LLM request"


@pytest.mark.asyncio
async def test_raises_error_on_empty_response():
    """chat_fn returns empty string → RuntimeError."""
    mock_chat = AsyncMock()
    mock_chat.return_value = ""

    with pytest.raises(RuntimeError, match="empty response"):
        await cowrite(
            "test-form",
            {"field": "value"},
            "improve",
            chat_fn=mock_chat,
        )


@pytest.mark.asyncio
async def test_raises_error_on_chat_failure():
    """chat_fn raises → RuntimeError."""
    mock_chat = AsyncMock()
    mock_chat.side_effect = ConnectionError("API unreachable")

    with pytest.raises(RuntimeError, match="LLM call failed"):
        await cowrite(
            "test-form",
            {"field": "value"},
            "improve",
            chat_fn=mock_chat,
        )


@pytest.mark.asyncio
async def test_raises_on_invalid_json():
    """chat_fn returns malformed JSON → ValueError."""
    mock_chat = AsyncMock()
    mock_chat.return_value = "not valid json at all"

    with pytest.raises(ValueError):
        await cowrite(
            "test-form",
            {"field": "value"},
            "improve",
            chat_fn=mock_chat,
        )


@pytest.mark.asyncio
async def test_missing_fields_in_response_raises_value_error():
    """Chat fn returns JSON missing a required field → ValueError."""
    mock_chat = AsyncMock()
    mock_chat.return_value = '{"field1": "Revised"}'

    with pytest.raises(ValueError, match="missing or empty field 'field2'"):
        await cowrite(
            "test-form",
            {"field1": "Orig", "field2": "More text"},
            "improve",
            chat_fn=mock_chat,
        )
