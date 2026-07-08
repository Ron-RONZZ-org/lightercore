"""Base LLM provider — shared chat, tool-calling, and command-generation infrastructure.

Both lighterbird and semantika subclass :class:`BaseLLMProvider` and
override :meth:`_command_system_prompt` (fallback) and optionally
:meth:`_command_tool_system_prompt` (preferred tool-calling path) to
inject their domain-specific prompt content.  Everything else (HTTP
transport, streaming, error reporting, message normalisation) is shared.

Usage::

    from lightercore.llm.base import BaseLLMProvider
    from lightercore.llm.config import ProviderConfig

    class MyProvider(BaseLLMProvider):
        def _command_system_prompt(self, defs_text: str) -> str:
            return f"You are my app.\\n{defs_text}"

        def _command_tool_system_prompt(self) -> str:
            return "You are my app. Call the right tool."

    provider = MyProvider(ProviderConfig(provider_type="openai", api_key="..."))
    reply = await provider.chat([{"role": "user", "content": "hi"}])
"""

from __future__ import annotations

import json
import logging
import warnings
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from lightercore.exceptions import AIError
from lightercore.llm.config import ProviderConfig
from lightercore.llm.utils import (
    normalize_messages,
    parse_command_result,
    resolve_base_url,
    response_error_detail,
    validate_base_url,
)

logger = logging.getLogger(__name__)


# ── Tool-calling types ───────────────────────────────────────────────────────


@dataclass
class ToolCall:
    """A single tool call returned by the LLM.

    Maps to the ``tool_calls[i]`` entry in an OpenAI-compatible response.
    """

    id: str
    type: str = "function"
    function: dict[str, Any] = field(default_factory=dict)
    """``{"name": "...", "arguments": "..."}`` (arguments is a JSON string)."""


@dataclass
class ChatResult:
    """Structured result from a chat-with-tools call.

    Either ``content`` (plain text) or ``tool_calls`` (tool invocation)
    will be populated, depending on what the LLM chose to do.
    """

    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    finish_reason: str = "stop"


# ── Helpers (tool format conversion) ─────────────────────────────────────────


def defs_to_tools(command_defs: list[dict]) -> list[dict]:
    """Convert flattened command definitions to OpenAI tool-calling format.

    Each definition with ``path`` (list of strings), ``description``,
    ``params``, and ``flags`` is converted to a ``{"type": "function", ...}``
    tool object.  The tool name is the path joined with ``_`` (e.g.
    ``["node", "list"]`` → ``"node_list"``).
    """
    tools: list[dict[str, Any]] = []
    for defn in command_defs:
        name = "_".join(defn["path"])
        description = defn.get("description", "")

        properties: dict[str, Any] = {}
        required: list[str] = []

        for p in defn.get("params", []):
            ptype = {"string": "string", "number": "number"}.get(
                p.get("type", "string"), "string"
            )
            properties[p["name"]] = {
                "type": ptype,
                "description": p.get("description", p.get("name", "")),
            }
            if p.get("required"):
                required.append(p["name"])

        for f in defn.get("flags", []):
            ftype = {
                "string": "string",
                "number": "number",
                "flag": "boolean",
            }.get(f.get("type", "string"), "string")
            properties[f["name"]] = {
                "type": ftype,
                "description": f.get("help", f.get("name", "")),
            }

        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return tools


def tool_call_to_command(tool_call: ToolCall) -> dict[str, Any]:
    """Convert a tool-call response to the ``{tokens, flags}`` command format.

    The tool name ``node_list`` is split on ``_`` to recover tokens
    ``["node", "list"]``.  The arguments JSON dict becomes the flags dict.
    """
    name = tool_call.function.get("name", "")
    tokens = name.split("_")
    raw_args = tool_call.function.get("arguments", "{}")
    try:
        flags = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    except (json.JSONDecodeError, TypeError):
        flags = {}
    return {"tokens": tokens, "flags": flags}


class BaseLLMProvider:
    """Shared LLM provider with unified error handling, streaming, and commands.

    Args:
        config: Provider configuration.
    """

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.base_url = resolve_base_url(config.provider_type, config.base_url)
        self.model = config.model or self._default_model()
        self._validate_base_url()

    # ── Hooks for subclasses ──────────────────────────────────────────────

    def _default_model(self) -> str:
        """Return the default model when none is configured.

        Override in subclasses to provide app-specific defaults.
        """
        defaults = {
            "openai": "gpt-4o",
            "deepseek": "deepseek-chat",
            "ollama": "llama3.2",
        }
        return defaults.get(self.config.provider_type, "gpt-4o")

    def _command_system_prompt(self, defs_text: str) -> str:
        """Return the system prompt for **fallback** (JSON-in-prompt)
        command generation.

        This is called only when no tool definitions are available.
        Subclasses **must** override this to inject app-specific command
        descriptions and instructions.

        Args:
            defs_text: JSON-serialised command definitions.

        Returns:
            The system prompt string.
        """
        return (
            "You are a command parser. "
            "Translate natural language into structured commands.\n\n"
            "Respond with ONLY a valid JSON object — no markdown, no extra text.\n"
            '{"tokens": ["command", "subcommand", ...], "flags": {"--flag": "value"}}\n\n'
            "Available commands:\n" + defs_text
        )

    def _command_tool_system_prompt(self) -> str:
        """Return the system prompt for the **tool-calling** command
        generation path.

        This is called when tool definitions are available and native
        tool-calling is used.  Subclasses may override this to provide
        domain-specific context (e.g. "You are a PIM assistant").
        The default provides a generic instruction.
        """
        return (
            "You are a command parser. "
            "Translate the user's request into a command by "
            "calling the appropriate tool. If the user asks about "
            "data (list, search, stats, etc.), ALWAYS pick a "
            "tool — never refuse or say you cannot do it."
        )

    # ── URL validation ────────────────────────────────────────────────────

    def _validate_base_url(self) -> None:
        """Validate the provider base URL (optional — swallowing is fine)."""
        try:
            validate_base_url(self.base_url)
        except ValueError:
            logger.warning("Invalid base URL %s — will fail at connect time", self.base_url)

    # ── Chat ──────────────────────────────────────────────────────────────

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers for the API request."""
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _build_payload(
        self,
        messages: list[dict],
        *,
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> dict[str, Any]:
        """Build the JSON payload for the chat completion request.

        Args:
            messages: Conversation history.
            stream: Whether to request a streaming response.
            tools: OpenAI-compatible tool definitions (function calling).
            tool_choice: ``"auto"``, ``"none"``, ``"required"``, or
                        ``{"type": "function", "function": {"name": "..."}}``.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": normalize_messages(messages),
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        return payload

    def _chat_url(self) -> str:
        """Return the full chat completions URL."""
        return f"{self.base_url}/chat/completions"

    # ── Embedding ───────────────────────────────────────────────────────────

    def _embed_url(self) -> str:
        """Return the full embeddings API URL.

        Subclasses may override for provider-specific endpoints
        (e.g. Ollama uses ``/api/embed`` instead of ``/v1/embeddings``).
        """
        return f"{self.base_url}/embeddings"

    def _embedding_model(self) -> str:
        """Return the model name to use for embeddings.

        Resolution order:
        1. ``config.embedding_model`` (explicitly configured)
        2. Provider-specific default based on ``config.provider_type``
        3. ``text-embedding-3-small`` (OpenAI-compatible default)
        """
        if self.config.embedding_model:
            return self.config.embedding_model
        defaults = {
            "openai": "text-embedding-3-small",
            "deepseek": "deepseek-embedding",
        }
        return defaults.get(self.config.provider_type, "text-embedding-3-small")

    def _build_embed_payload(self, texts: list[str]) -> dict[str, Any]:
        """Build the JSON payload for an embedding request.

        Subclasses may override for provider-specific payload formats.

        Args:
            texts: List of text strings to embed.

        Returns:
            Dict with ``input``, ``model`` keys.
        """
        return {
            "model": self._embedding_model(),
            "input": texts if len(texts) > 1 else texts[0],
        }

    def _parse_embed_response(self, data: dict[str, Any]) -> list[list[float]]:
        """Parse the embedding response into a list of vectors.

        Override in subclasses for non-OpenAI-compatible response formats.

        Args:
            data: Parsed JSON response from the embedding API.

        Returns:
            List of embedding vectors, one per input text, in input order.
        """
        raw = data.get("data", [])
        raw.sort(key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in raw]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via the configured provider's embedding endpoint.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors.

        Raises:
            AIError: If the provider is not configured or the API call fails.
        """
        if not self.config.is_available():
            raise AIError("LLM provider not configured.")

        headers = self._build_headers()
        payload = self._build_embed_payload(texts)
        url = self._embed_url()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.is_error:
                detail = response_error_detail(response)
                raise AIError(
                    f"Embedding API error (HTTP {response.status_code}): {detail}"
                )
            return self._parse_embed_response(response.json())

    async def chat(
        self,
        messages: list[dict],
        *,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        """Send a chat completion request.

        Args:
            messages: List of message dicts.
            stream: If ``True``, return an async iterator of content tokens.

        Returns:
            Full response string (non-streaming) or async iterator (streaming).

        Raises:
            AIError: If the provider is not configured or the API call fails.
        """
        if not self.config.is_available():
            raise AIError("LLM provider not configured.")

        headers = self._build_headers()
        payload = self._build_payload(messages, stream=stream)
        url = self._chat_url()

        if stream:
            return self._stream_chat(url, headers, payload)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.is_error:
                detail = response_error_detail(response)
                raise AIError(
                    f"LLM API error (HTTP {response.status_code}): {detail}"
                )
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise AIError("No response from LLM (empty choices).")
            return choices[0].get("message", {}).get("content", "")

    # ── Tool calling (chat with function tools) ───────────────────────────

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        tool_choice: str | None = None,
    ) -> ChatResult:
        """Send a chat completion with tool-calling support (non-streaming).

        Unlike :meth:`chat`, this method **always** returns a
        :class:`ChatResult` that may contain either plain text
        (``content``) or tool invocations (``tool_calls``), depending
        on what the LLM chose.

        Args:
            messages: Conversation history.
            tools: OpenAI-compatible tool definitions.
            tool_choice: ``"auto"`` (default), ``"none"``, ``"required"``,
                        or a specific tool dict.

        Returns:
            :class:`ChatResult` with either ``content`` or ``tool_calls``.

        Raises:
            AIError: If the provider is not configured or the API fails.
        """
        if not self.config.is_available():
            raise AIError("LLM provider not configured.")

        headers = self._build_headers()
        payload = self._build_payload(
            messages, stream=False, tools=tools, tool_choice=tool_choice,
        )
        url = self._chat_url()

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.is_error:
                detail = response_error_detail(response)
                raise AIError(
                    f"LLM API error (HTTP {response.status_code}): {detail}"
                )
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise AIError("No response from LLM (empty choices).")

            msg = choices[0].get("message", {})
            content = msg.get("content")
            raw_tool_calls = msg.get("tool_calls")
            finish_reason = choices[0].get("finish_reason", "stop")

            tool_calls: list[ToolCall] | None = None
            if raw_tool_calls:
                tool_calls = [
                    ToolCall(
                        id=tc.get("id", ""),
                        type=tc.get("type", "function"),
                        function=tc.get("function", {}),
                    )
                    for tc in raw_tool_calls
                ]

            return ChatResult(
                content=content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )

    async def _stream_chat(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> AsyncIterator[str]:
        """Stream tokens from an OpenAI-compatible SSE endpoint.

        Manages its own ``httpx`` client lifecycle — the client stays open
        as long as the iterator is alive, and is closed when iteration
        completes or is cancelled.
        """
        client = httpx.AsyncClient(timeout=60.0)
        try:
            async with client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
            ) as response:
                if response.is_error:
                    await response.aread()
                    detail = response_error_detail(response)
                    raise AIError(
                        f"LLM API error (HTTP {response.status_code}): {detail}"
                    )

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        if not data_str:
                            continue
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                yield token
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        finally:
            await client.aclose()

    # ── Command generation ────────────────────────────────────────────────

    async def generate_command(
        self,
        message: str,
        command_defs: list[dict],
    ) -> dict[str, Any] | None:
        """Ask the LLM to generate a structured command from natural language.

        .. deprecated::
            Use :meth:`chat_with_tools` inside a :func:`run_tool_loop`
            instead.  ``generate_command`` is a single-shot wrapper that
            discards all but the first tool call.  The ``run_tool_loop``
            pattern in ``lighterbird.server.llm.tool_loop`` supports
            multi-round iteration and human-in-the-loop approval.

        Uses **native tool calling** when ``command_defs`` is non-empty
        (OpenAI, DeepSeek, and Ollama all support it).  Falls back to the
        JSON-in-prompt approach only when tool calling is unavailable.

        Args:
            message: User's natural language input.
            command_defs: List of available command definitions.

        Returns:
            ``{"tokens": [...], "flags": {...}}`` or ``None``.
        """
        import warnings
        warnings.warn(
            "generate_command is deprecated. Use chat_with_tools() inside "
            "a run_tool_loop() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not self.config.is_available():
            return None

        # ── Tool-calling path (preferred) ────────────────────────────
        tools = defs_to_tools(command_defs) if command_defs else []
        if tools:
            sys_msg = {
                "role": "system",
                "content": self._command_tool_system_prompt(),
            }
            try:
                result = await self.chat_with_tools(
                    [sys_msg, {"role": "user", "content": message}],
                    tools,
                    tool_choice="auto",
                )
            except AIError:
                return None
            except Exception:
                logger.exception("Unexpected error in generate_command (tools)")
                return None

            if result.tool_calls:
                return tool_call_to_command(result.tool_calls[0])

            # LLM chose text response — try to parse as JSON anyway
            if result.content:
                return parse_command_result(result.content.strip())
            return None

        # ── Fallback: JSON-in-prompt (legacy) ────────────────────────
        defs_text = json.dumps(command_defs, indent=2) if command_defs else "[]"
        system = self._command_system_prompt(defs_text)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ]

        try:
            result = await self.chat(messages, stream=False)
            if isinstance(result, str):
                return parse_command_result(result.strip())
            return None
        except AIError:
            return None
        except Exception:
            logger.exception("Unexpected error in generate_command (fallback)")
            return None


__all__ = ["BaseLLMProvider"]
