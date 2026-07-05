"""Utility functions for LLM provider management.

Shared across lighterbird and semantika: URL resolution, message construction,
response parsing, and DeepSeek compatibility helpers.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "ollama": "http://localhost:11434/v1",
}

# Semantika-style: bare !command in text
_CMD_PATTERN_BARE = re.compile(r"!(\S+(?:\s+\S+)*)")
# Lighterbird-style: backtick-wrapped !command
_CMD_PATTERN_BACKTICK = re.compile(r"`(![a-z0-9_-]+(?:\s+[^\s`]+)*)`")


def resolve_base_url(provider_type: str, base_url: str) -> str:
    """Resolve the effective API base URL for a provider.

    If *base_url* is non-empty it is returned as-is (trailing slash stripped).
    Otherwise the well-known default for *provider_type* is returned.

    Args:
        provider_type: ``"openai"``, ``"deepseek"``, ``"ollama"``, or custom.
        base_url: User-supplied base URL (may be empty).

    Returns:
        Resolved base URL with trailing slash removed.
    """
    if base_url:
        return base_url.rstrip("/")
    return _DEFAULT_BASE_URLS.get(provider_type, "https://api.openai.com/v1")


def parse_command_result(text: str | None) -> dict[str, Any] | None:
    """Parse an LLM response into a structured command dict.

    Handles bare JSON, markdown-fenced JSON, and plain-text fallback with both
    bare ``!command`` and backtick-wrapped ``\`!command\``` extraction.

    Args:
        text: Raw LLM response text.

    Returns:
        ``{"tokens": [...], "flags": {...}}`` or ``None``.
    """
    if not text:
        return None

    cleaned = text.strip()

    # Strip markdown code fences
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
        cleaned = cleaned.strip()

    # Try JSON parse
    try:
        parsed = json.loads(cleaned)
        if parsed is None:
            return None
        if isinstance(parsed, dict) and "tokens" in parsed:
            return parsed  # type: ignore[typeddict-item]
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: backtick-wrapped !command (lighterbird-style, unambiguous)
    match = _CMD_PATTERN_BACKTICK.search(cleaned)
    if match:
        cmd_text = match.group(1)
        parts = cmd_text[1:].split()  # remove leading !
        if parts:
            return {"tokens": parts, "flags": {}}

    # Fallback: bare !command (semantika-style, permissive)
    match = _CMD_PATTERN_BARE.search(cleaned)
    if match:
        parts = match.group(1).split()
        if parts:
            return {"tokens": parts, "flags": {}}
        cmd_text = match.group(1)
        parts = cmd_text[1:].split()
        if parts:
            return {"tokens": parts, "flags": {}}

    return None


def build_messages(
    message: str,
    context: list[dict[str, Any]] | None = None,
    *,
    system_override: str | None = None,
    default_system: str = "You are a helpful assistant.",
) -> list[dict[str, Any]]:
    """Build a messages list with an optional system prompt prepended.

    Args:
        message: The user's utterance.
        context: Optional message history inserted between system and user.
        system_override: If set, use this as the system message.
        default_system: Fallback system message when no override is given.

    Returns:
        List of ``{"role": ..., "content": ...}`` dicts.
    """
    system_content = system_override if system_override is not None else default_system
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    if context:
        messages.extend(context)
    messages.append({"role": "user", "content": message})
    return messages


def normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise ``role`` / ``type`` fields for DeepSeek API compatibility.

    DeepSeek validates **both** fields depending on the message index.
    This ensures every message carries both keys, avoiding silent failures.

    Args:
        messages: Raw message list from the caller.

    Returns:
        Normalised copy with both ``role`` and ``type`` present.
    """
    normalized: list[dict[str, Any]] = []
    for m in messages:
        entry = dict(m)
        if "role" in entry and "type" not in entry:
            entry["type"] = entry["role"]
        elif "type" in entry and "role" not in entry:
            entry["role"] = entry["type"]
        normalized.append(entry)
    return normalized


def validate_base_url(url: str) -> None:
    """Ensure the base URL is secure (HTTPS or localhost HTTP).

    Args:
        url: The base URL to validate.

    Raises:
        ValueError: If the URL uses HTTP for a non-local endpoint.
    """
    if not url:
        return
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        return  # Will fail on connect — not our problem.
    if parsed.scheme == "http":
        host = parsed.hostname or ""
        if host not in ("127.0.0.1", "localhost"):
            raise ValueError(
                f"Insecure LLM base URL: {url}. "
                "Use HTTPS for remote endpoints or http://localhost for local models."
            )


def response_error_detail(response: httpx.Response) -> str:
    """Extract a human-readable error detail from an API error response.

    Args:
        response: The failed HTTP response.

    Returns:
        A human-readable error string.
    """
    try:
        body = response.json()
        if isinstance(body, dict):
            err = body.get("error", body)
            if isinstance(err, dict):
                return err.get("message", str(err))
            return str(err)
        return str(body)
    except (json.JSONDecodeError, ValueError):
        return response.text or "(no detail)"


__all__ = [
    "build_messages",
    "normalize_messages",
    "parse_command_result",
    "resolve_base_url",
    "response_error_detail",
    "validate_base_url",
]
