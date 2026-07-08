"""Multi-round tool-calling loop with HITL support.

Shared across lighterbird and semantika for both ``/api/v1/chat`` and
``/api/v1/prompt-commands/execute`` endpoints.

Provides:
- :func:`run_tool_loop` — core multi-round loop with permission gating
- :func:`resume_execution` — resume a paused session after user approval
- :data:`_pending_executions` — in-memory store for paused sessions

The loop gives the LLM tool definitions for all registered ``!commands``.
READ-level tools execute immediately without confirmation.
WRITE-level (and above) tools are gated behind user confirmation via
a ``confirm_tool`` response type and the ``resume`` endpoint.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from lightercore.exceptions import AIError
from lightercore.llm.base import ChatResult, ToolCall
from lightercore.permissions import PermissionLevel

logger = logging.getLogger(__name__)

# ── In-memory store for paused executions ──────────────────────────────────

_pending_executions: dict[str, dict] = {}
"""Maps session UUID to state dicts for paused HITL sessions."""


# ── Helpers ────────────────────────────────────────────────────────────────


def tc_path(tc: ToolCall) -> tuple[str, dict[str, str]]:
    """Extract command path and flags from a tool call.

    The tool name ``node_list`` becomes path ``"node.list"``.
    The arguments JSON dict becomes the flags dict.

    Returns:
        ``(path, flags)`` — e.g. ``("email.search", {"q": "hello"})``
    """
    name = tc.function.get("name", "")
    path = name.replace("_", ".")
    raw_args = tc.function.get("arguments", "{}")
    try:
        flags = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    except (json.JSONDecodeError, TypeError):
        flags = {}
    return path, flags


def sanitize_tool_result(result: dict) -> dict:
    """Recursively parse JSON-encoded strings inside dispatch results.

    DB rows often contain JSON fields stored as encoded strings
    (e.g. ``'{"en": "Alice"}'``).  When the tool loop sends this back
    to the LLM via ``json.dumps(result)``, the inner JSON gets
    double-escaped.  This function walks the dict and converts any
    parseable JSON string values into their parsed form.
    """
    def _walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: _walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_walk(v) for v in value]
        if isinstance(value, str) and len(value) > 1:
            stripped = value.strip()
            if stripped.startswith(("{", "[")):
                try:
                    parsed = json.loads(stripped)
                    return _walk(parsed)
                except (json.JSONDecodeError, ValueError):
                    pass
        return value
    return _walk(result)


# ── Core tool loop ─────────────────────────────────────────────────────────


async def run_tool_loop(
    messages: list[dict],
    tools: list[dict],
    name: str,
    provider: Any,
    dispatch_fn: Any,
    get_handler_metadata_fn: Any,
    get_command_level_fn: Any,
    max_rounds: int = 20,
) -> str | dict | None:
    """Run the multi-round tool-calling loop.

    The LLM sees the messages (system prompt + user input) plus tool
    definitions.  It can call tools, get real results, and iterate
    until it produces a final text answer.

    Args:
        messages: Conversation history with system prompt.
        tools: OpenAI-compatible tool definitions.
        name: Human-readable name for the session (for error messages).
        provider: An :class:`~lightercore.llm.protocol.LLMProvider` instance.
        dispatch_fn: Callable ``(path: str, flags: dict) -> dict`` that
            executes a command by its dot-separated path.
        get_handler_metadata_fn: Callable ``(path: str) -> dict | None``.
        get_command_level_fn: Callable ``(path: str) -> PermissionLevel | None``.
        max_rounds: Maximum tool-calling rounds before giving up.

    Returns:
        - ``str`` — final answer on success.
        - ``dict`` with ``{"type": "confirm_tool", ...}`` if write tools
          need user approval.
        - ``None`` if the loop exhausted or the provider is unavailable.
    """
    for _round in range(max_rounds):
        try:
            result: ChatResult = await provider.chat_with_tools(messages, tools)
        except AIError:
            logger.exception("AIError in tool loop for %s (round %d)", name, _round)
            return None
        except Exception:
            logger.exception("Unexpected error in tool loop for %s (round %d)", name, _round)
            return None

        if not result.tool_calls:
            # Text response — final answer
            return result.content

        # ── Append the assistant message with tool_calls ──────────────
        # Required by the API protocol: every ``role: "tool"`` message
        # must be preceded by a ``role: "assistant"`` message whose
        # ``tool_calls`` array contains matching IDs.
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": result.content,
        }
        if result.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.get("name", ""),
                        "arguments": tc.function.get("arguments", "{}"),
                    },
                }
                for tc in result.tool_calls
            ]
        messages.append(assistant_msg)

        # Process tool calls in this batch
        write_batch: list[dict] = []
        for tc in result.tool_calls:
            path, flags = tc_path(tc)
            level = get_command_level_fn(path) if get_handler_metadata_fn(path) is not None else None

            # Collect write+ tools for user review.  READ tools execute
            # immediately without confirmation.
            if level is not None and level >= PermissionLevel.WRITE:
                meta = get_handler_metadata_fn(path) or {}
                write_batch.append({
                    "tokens": path.split("."),
                    "flags": flags,
                    "description": meta.get("description", ""),
                })
                continue

            # READ-level tool: execute immediately
            try:
                cmd_result = dispatch_fn(path, flags)
            except Exception as exc:
                cmd_result = {"error": str(exc)}
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(sanitize_tool_result(cmd_result)),
            })

        # If there are pending write+ tools, gate them behind user review
        if write_batch:
            session_id = str(uuid.uuid4())
            _pending_executions[session_id] = {
                "messages": list(messages),
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.get("name", ""),
                            "arguments": tc.function.get("arguments", "{}"),
                        },
                    }
                    for tc in result.tool_calls
                ],
                "tools": tools,
                "name": name,
                "write_paths": {tuple(w["tokens"]): w for w in write_batch},
            }

            return {
                "type": "confirm_tool",
                "session_id": session_id,
                "batch": write_batch,
                "message": (
                    f"The LLM wants to perform **{len(write_batch)}** operation(s). "
                    f"Review and approve individually below."
                ),
            }

    logger.warning("Tool loop exhausted for %s (max %d rounds)", name, max_rounds)
    return None


# ── Resume ─────────────────────────────────────────────────────────────────


async def resume_execution(
    session_id: str,
    decisions: dict[int, bool] | None = None,
    confirmed: bool | None = None,
    *,
    provider: Any,
    dispatch_fn: Any,
    get_handler_metadata_fn: Any,
    get_command_level_fn: Any,
) -> str | dict | None:
    """Resume a paused execution after user confirmation.

    Called by the ``resume`` endpoint.

    Args:
        session_id: The session UUID from the ``confirm_tool`` response.
        decisions: Per-tool-index approval e.g. ``{0: true, 1: false}``.
            Overrides *confirmed* when present.
        confirmed: Blanket approval for all tools (``true`` = approve all,
            ``false`` = reject all).
        provider: LLM provider instance.
        dispatch_fn: Command dispatch callable.
        get_handler_metadata_fn: Registry metadata lookup.
        get_command_level_fn: Registry permission-level lookup.

    Returns:
        Same as :func:`run_tool_loop`.
    """
    state = _pending_executions.pop(session_id, None)
    if state is None:
        raise LookupError(f"Session not found or expired: {session_id}")

    messages: list[dict] = state["messages"]
    tool_calls: list[dict] = state["tool_calls"]
    tools: list[dict] = state["tools"]
    name: str = state["name"]
    write_paths: dict = state["write_paths"]

    # Resolve decisions
    if decisions is not None:
        resolved = decisions
    elif confirmed is not None:
        # Find the write tools by index
        write_indices = set()
        for idx, tc in enumerate(tool_calls):
            path, _ = tc_path(ToolCall(id=tc.get("id", ""), function=tc.get("function", {})))
            level = get_command_level_fn(path) if get_handler_metadata_fn(path) is not None else None
            if level is not None and level >= PermissionLevel.WRITE:
                write_indices.add(idx)
        resolved = {idx: confirmed for idx in write_indices}
    else:
        resolved = {}

    # Process ALL tools, executing approved writes and recording rejections
    for idx, tc_data in enumerate(tool_calls):
        tc = ToolCall(
            id=tc_data.get("id", ""),
            type=tc_data.get("type", "function"),
            function=tc_data.get("function", {}),
        )
        path, flags = tc_path(tc)
        level = get_command_level_fn(path) if get_handler_metadata_fn(path) is not None else None

        if level is not None and level >= PermissionLevel.WRITE:
            approved = resolved.get(idx, False)
            if approved:
                try:
                    cmd_result = dispatch_fn(path, flags)
                except Exception as exc:
                    cmd_result = {"error": str(exc)}
            else:
                cmd_result = {"error": f"User rejected !{'.'.join(path.split('.'))}"}
        else:
            # READ tool already executed in the loop — skip
            continue

        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": json.dumps(sanitize_tool_result(cmd_result)),
        })

    # Continue the loop
    return await run_tool_loop(
        messages=messages,
        tools=tools,
        name=name,
        provider=provider,
        dispatch_fn=dispatch_fn,
        get_handler_metadata_fn=get_handler_metadata_fn,
        get_command_level_fn=get_command_level_fn,
    )


__all__ = [
    "_pending_executions",
    "run_tool_loop",
    "resume_execution",
    "sanitize_tool_result",
    "tc_path",
]
