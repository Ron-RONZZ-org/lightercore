"""Base LLM provider — shared chat and command-generation infrastructure.

Both lighterbird and semantika subclass :class:`BaseLLMProvider` and
override :meth:`_command_system_prompt` to inject their domain-specific
prompt content.  Everything else (HTTP transport, streaming, error
reporting, message normalisation) is shared.

Usage::

    from lightercore.llm.base import BaseLLMProvider
    from lightercore.llm.config import ProviderConfig

    class MyProvider(BaseLLMProvider):
        def _command_system_prompt(self, defs_text: str) -> str:
            return f"You are my app.\\n{defs_text}"

    provider = MyProvider(ProviderConfig(provider_type="openai", api_key="..."))
    reply = await provider.chat([{"role": "user", "content": "hi"}])
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
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
        """Return the system prompt for command generation.

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
    ) -> dict[str, Any]:
        """Build the JSON payload for the chat completion request."""
        return {
            "model": self.model,
            "messages": normalize_messages(messages),
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": stream,
        }

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

        Args:
            message: User's natural language input.
            command_defs: List of available command definitions.

        Returns:
            ``{"tokens": [...], "flags": {...}}`` or ``None``.
        """
        if not self.config.is_available():
            return None

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
            logger.exception("Unexpected error in generate_command")
            return None


__all__ = ["BaseLLMProvider"]
