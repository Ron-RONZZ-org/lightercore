"""LLM provider interface protocol.

Defines a structural ``typing.Protocol`` that both lighterbird and semantika
provider implementations can conform to.  The protocol is **optional** —
apps are not required to inherit from it; they just need to satisfy the
interface (duck-typing).

Usage::

    from lightercore.llm.protocol import LLMProvider

    async def handle(provider: LLMProvider) -> None:
        reply = await provider.chat([{"role": "user", "content": "hi"}])
        ...
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Structural protocol for LLM providers.

    Defines the minimal contract that every provider must satisfy.
    The streaming behaviour is signalled by the return type of
    :meth:`chat` — callers should inspect the result with
    ``isinstance``.

    Conforming implementations must provide at least:
    - ``async def chat(messages, *, stream=False) -> str | AsyncIterator[str]``
    - ``async def generate_command(message, command_defs) -> dict | None``
    """

    async def chat(
        self,
        messages: list[dict],
        *,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        """Send a chat completion request.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            stream: If ``True``, return an async iterator of tokens.

        Returns:
            Full response text (non-streaming) or token iterator (streaming).
        """
        ...

    async def generate_command(
        self,
        message: str,
        command_defs: list[dict],
    ) -> dict | None:
        """Translate natural language to a structured command.

        Args:
            message: User's natural language request.
            command_defs: Available command definitions for the LLM.

        Returns:
            ``{"tokens": [...], "flags": {...}}`` or ``None``.
        """
        ...

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        tool_choice: str | None = None,
    ) -> Any:
        """Send a chat with tool-calling support.

        Args:
            messages: Conversation history.
            tools: OpenAI-compatible tool definitions.
            tool_choice: Tool selection strategy.

        Returns:
            A :class:`ChatResult` with ``content`` and/or ``tool_calls``.
        """
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate vector embeddings for one or more texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors, one per input text.
            Each vector is a ``list[float]`` with dimensionality
            determined by the embedding model.

        Raises:
            AIError: If this provider does not support embeddings.
        """
        ...


__all__ = ["LLMProvider"]
