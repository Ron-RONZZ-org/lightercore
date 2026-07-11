"""File-based prompt command loader and template expander.

Scans ``<config_dir>/commands/*.md`` for user-defined LLM prompt templates.
Shared between lighterbird and semantika.

File format (no YAML frontmatter):
    - First line starting with ``# `` is the description (shown in autocomplete).
    - Everything after is the prompt template with ``$1``, ``$2``, … positional
      placeholders and an optional ``$ARGUMENTS`` catch-all.
    - Files without a ``# `` first line are silently skipped.

Example ``~/.config/lighterbird/commands/summarize.md``::

    # Summarize the last N emails in a folder
    Summarise the last $1 emails in my $2 folder.
    Focus on key information: senders, subjects, and action items.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import mistune

from lightercore.llm.base import defs_to_tools
from lightercore.llm.tool_loop import run_tool_loop

logger = logging.getLogger(__name__)


@dataclass
class PromptCommand:
    """A single prompt command loaded from a ``.md`` file on disk.

    Attributes:
        name: File stem of the ``.md`` file (e.g. ``"weekly"``).
        description: First line starting with ``# ``, stripped of prefix.
        template: Everything after the description / frontmatter.
        path: Absolute filesystem path to the ``.md`` file.
        param_count: Highest ``$N`` placeholder number found (0 if none).
        tools: Optional list of tool domains parsed from YAML frontmatter
            (e.g. ``["node", "predicate", "triple"]``).
    """

    name: str
    description: str
    template: str
    path: Path
    param_count: int = field(default=0, compare=False)
    tools: list[str] | None = field(default=None, compare=False)


_PARAM_RE = re.compile(r"\$([1-9])\b")
_ARGUMENTS_RE = re.compile(r"\$ARGUMENTS\b")


# ── Scanner ──────────────────────────────────────────────────────────────────


def list_prompt_commands(commands_dir: Path) -> list[PromptCommand]:
    """Scan ``commands_dir/*.md`` and return sorted list of ``PromptCommand``.

    Skips files that don't parse:
    - Dotfiles (``.*.md``) and non-``.md`` files.
    - Files whose first line does not start with ``# ``.

    Args:
        commands_dir: Path to the ``commands/`` directory (typically
            ``config_dir() / "commands"``).

    Returns:
        Sorted list of ``PromptCommand`` instances (by name).
    """
    if not commands_dir.is_dir():
        return []

    result: list[PromptCommand] = []
    for path in sorted(commands_dir.iterdir()):
        if not path.name.endswith(".md"):
            continue
        if path.name.startswith("."):
            continue
        cmd = _parse_file(path)
        if cmd is not None:
            result.append(cmd)
    return result


def load_prompt_command(commands_dir: Path, name: str) -> PromptCommand | None:
    """Load a single prompt command by name (file stem, case-insensitive).

    Args:
        commands_dir: Path to the ``commands/`` directory.
        name: Command name (file stem without ``.md``).

    Returns:
        ``PromptCommand`` if found, or ``None``.
    """
    if not commands_dir.is_dir():
        return None
    name_lower = name.lower()
    for path in commands_dir.iterdir():
        if not path.name.endswith(".md"):
            continue
        if path.name.startswith("."):
            continue
        stem = path.stem.lower()
        if stem == name_lower:
            return _parse_file(path)
    return None


def _parse_frontmatter(text: str) -> tuple[str, list[str] | None]:
    """Parse YAML frontmatter from prompt command text.

    Looks for a ``---`` delimited block at the start of the file.
    Currently only the ``tools`` key is recognised (a list of strings).

    Returns:
        ``(remaining_body, tools_list_or_None)``.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return text, None

    end = text.find("\n---", 3)
    if end == -1:
        return text, None  # Unclosed frontmatter — treat as body

    frontmatter = text[4:end]
    body = text[end + 4:].lstrip("\n\r")

    # Parse tools from frontmatter (simple YAML subset)
    tools: list[str] | None = None
    for raw_line in frontmatter.split("\n"):
        line = raw_line.strip()
        # tools: [a, b, c]  — inline list
        if line.startswith("tools:"):
            rest = line[6:].strip()
            if rest.startswith("["):
                # YAML-style list (items may be unquoted)
                inner = rest.strip("[]")
                tools = [s.strip().strip("\"'").lower()
                         for s in inner.split(",") if s.strip()]
            elif rest:
                # Single value (no brackets)
                tools = [rest.lower()]
            else:
                # "tools:" on its own line — block list follows
                tools = []
        # tools:\n  - a\n  - b  — block list
        elif line.startswith("- ") and tools is not None:
            val = line[2:].strip().lower()
            if val:
                tools.append(val)

    return body, tools


def _parse_file(path: Path) -> PromptCommand | None:
    """Parse a single ``.md`` file into a ``PromptCommand``, or None."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    # Strip frontmatter before extracting description
    body, tools = _parse_frontmatter(text)

    lines = body.split("\n")
    # First non-empty line must start with "# "
    first_line = ""
    for line in lines:
        stripped = line.strip()
        if stripped:
            first_line = stripped
            break
    if not first_line.startswith("# "):
        return None

    description = first_line[2:].strip()
    # Everything after the first non-empty line is the template body
    first_line_idx = next(
        i for i, line in enumerate(lines) if line.strip()
    )
    template_lines = lines[first_line_idx + 1 :]
    template = "\n".join(template_lines).strip()

    # Count param placeholders
    param_numbers = set()
    for m in _PARAM_RE.finditer(template):
        param_numbers.add(int(m.group(1)))
    param_count = max(param_numbers) if param_numbers else 0

    return PromptCommand(
        name=path.stem,
        description=description,
        template=template,
        path=path,
        param_count=param_count,
        tools=tools,
    )


# ── Template expansion ───────────────────────────────────────────────────────


def expand_prompt_template(template: str, args: list[str]) -> str:
    """Replace ``$1``, ``$2``, …, ``$N`` and ``$ARGUMENTS`` with positional args.

    - When ``$ARGUMENTS`` is used, it is the catch-all and each ``$N``
      captures its single corresponding arg (legacy behaviour).
    - When ``$ARGUMENTS`` is *absent*, the *last* positional placeholder
      (highest ``$N``) is **greedy**: it captures that arg and all
      remaining args joined with spaces.  This means ``$1`` in a
      single-placeholder template like ``text-to-triple`` captures the
      full free-form text.
    - All earlier placeholders (``$1`` … ``$(N-1)``) capture their
      corresponding single arg as before.

    Args:
        template: The prompt template string with ``$N`` placeholders.
        args: Positional argument values from the user's invocation.

    Returns:
        Expanded prompt string.
    """
    # Find the highest $N in the template
    param_numbers = set()
    for m in _PARAM_RE.finditer(template):
        param_numbers.add(int(m.group(1)))
    max_param = max(param_numbers) if param_numbers else 0

    has_arguments = _ARGUMENTS_RE.search(template) is not None

    result = template

    if has_arguments:
        # Legacy: $ARGUMENTS is the designated catch-all
        for i, arg in enumerate(args, start=1):
            result = result.replace(f"${i}", arg)
        all_args = " ".join(args)
        result = result.replace("$ARGUMENTS", all_args)
    else:
        # No $ARGUMENTS: the last $N is greedy
        for i in range(1, max_param):
            arg = args[i - 1] if i <= len(args) else ""
            result = re.sub(rf"\${i}\b", arg, result)

        if max_param > 0:
            remaining = " ".join(args[max_param - 1:]) if len(args) >= max_param else ""
            result = re.sub(rf"\${max_param}\b", remaining, result)

    return result


# ── Convenience helper ───────────────────────────────────────────────────────


def prompt_command_exists(commands_dir: Path, name: str) -> bool:
    """Check if a prompt command file exists (case-insensitive)."""
    return load_prompt_command(commands_dir, name) is not None


# ── Execution scaffolding ─────────────────────────────────────────────────────


def build_prompt_messages(
    expanded: str,
    system_prompt_loader: Callable[[], str],
) -> list[dict[str, str]]:
    """Build system + user message list for prompt command execution.

    Args:
        expanded: The expanded prompt command template.
        system_prompt_loader: Callable that returns the base system prompt
            string (e.g. from a user-editable file).

    Returns:
        ``[{"role": "system", "content": <prompt>},
          {"role": "user", "content": expanded}]``
    """
    return [
        {"role": "system", "content": system_prompt_loader()},
        {"role": "user", "content": expanded},
    ]


def parse_tool_domains(
    template: str,
    frontmatter_tools: list[str] | None = None,
) -> set[str] | None:
    """Parse tool domain restrictions from a prompt command.

    Priority:
    1. ``frontmatter_tools`` — from YAML frontmatter (already parsed by
       :func:`_parse_frontmatter` into :attr:`PromptCommand.tools`).
    2. ``# +tools: domain1, domain2`` comment in the template body.
    3. ``None`` — include all tools.

    Returns:
        A set of domain strings, or ``None`` for "all tools".
    """
    if frontmatter_tools:
        domains = {d.strip().lower() for d in frontmatter_tools if d.strip()}
        return domains if domains else None

    for line in template.split("\n"):
        stripped = line.strip()
        match = re.match(r"^#\s*\+tools:\s*(.+)$", stripped, re.IGNORECASE)
        if match:
            domains = {d.strip().lower() for d in match.group(1).split(",") if d.strip()}
            return domains if domains else None
    return None


def filter_defs_by_domain(
    defs: list[dict[str, Any]],
    allowed_domains: set[str] | None,
) -> list[dict[str, Any]]:
    """Filter flattened command definitions to only include specified domains.

    Excludes bare group nodes (no params, no flags, empty description)
    which are pure tree scaffolding.

    Args:
        defs: Flattened command definitions from the project's registry.
        allowed_domains: If ``None``, return all definitions unchanged.

    Returns:
        Filtered definition list.
    """
    if allowed_domains is None:
        return defs
    return [
        d for d in defs
        if d["path"][0] in allowed_domains
        and not (
            not d.get("params") and not d.get("flags")
            and not d.get("description", "").strip()
        )
    ]


# ── Full execution pipeline ───────────────────────────────────────────────────


async def execute_prompt_command(
    *,
    name: str,
    args: list[str],
    commands_dir: Path,
    provider: Any,
    system_prompt_loader: Callable[[], str],
    definitions_loader: Callable[[], list[dict[str, Any]]],
    dispatch_fn: Callable[[str, dict[str, str]], dict[str, Any]],
    get_handler_metadata_fn: Callable[[str], dict[str, Any] | None],
    get_command_level_fn: Callable[[str], int | None],
    title_prefix: str = "/",
    max_rounds: int = 20,
) -> dict[str, Any]:
    """Execute a prompt command end-to-end.

    Loads the prompt command file, expands the template with positional
    args, builds messages, filters tool definitions by domain, runs the
    multi-round tool-calling loop, and returns a response dict ready for
    the HTTP handler.

    Caller responsibilities:
    - Handle ``/template`` or other special-case commands before calling
      this function.
    - Raise validation errors (name required, not found) from the
      ``status_code`` key in the return dict.
    - Handle SSE streaming separately.

    Args:
        name: Prompt command name (file stem).
        args: Positional arguments from the user.
        commands_dir: Path to the ``commands/`` directory.
        provider: An :class:`~lightercore.llm.protocol.LLMProvider` instance.
        system_prompt_loader: Callable returning the system prompt string.
        definitions_loader: Callable returning flattened command definitions.
        dispatch_fn: Callable ``(path, flags) -> dict`` to execute a command.
        get_handler_metadata_fn: Callable ``(path) -> dict | None``.
        get_command_level_fn: Callable ``(path) -> int | None``.
        title_prefix: Prefix for the response title (e.g. ``"/*"``).
        max_rounds: Maximum tool-calling iterations.

    Returns:
        One of:
        - ``{"type": "chat", "title": ..., "data": {"html": ..., "actions": []}}``
        - ``{"type": "confirm_tool", "session_id": ..., ...}``
        - ``{"type": "status", "title": ..., "data": {"message": ...}}``
        - ``{"status_code": 404, "detail": ..., ...}`` for not-found errors.
    """
    # 1. Load and expand
    cmd = load_prompt_command(commands_dir, name)
    if cmd is None:
        available = [c.name for c in list_prompt_commands(commands_dir)]
        return {
            "status_code": 404,
            "detail": (
                f"Prompt command '{name}' not found. "
                f"Available: {', '.join(available) or '(none)'}"
            ),
        }

    expanded = expand_prompt_template(cmd.template, args)

    # 2. Check provider availability
    available = getattr(provider, "available", None)
    if available is None:
        available = provider.is_available() if hasattr(provider, "is_available") else False
    if not available:
        return {
            "type": "status",
            "title": f"{title_prefix}{name}",
            "data": {
                "message": (
                    "LLM not configured. "
                    "Use !llm configure or set up a provider in Settings."
                ),
            },
        }

    # 3. Parse tool domains, load + filter definitions, build messages
    allowed_domains = parse_tool_domains(cmd.template, frontmatter_tools=cmd.tools)
    defs = definitions_loader()
    defs = filter_defs_by_domain(defs, allowed_domains)
    tools = defs_to_tools(defs) if defs else []
    messages = build_prompt_messages(expanded, system_prompt_loader)

    # 4. Run multi-round tool loop
    result = await run_tool_loop(
        messages=messages,
        tools=tools,
        name=f"{title_prefix}{name}",
        provider=provider,
        dispatch_fn=dispatch_fn,
        get_handler_metadata_fn=get_handler_metadata_fn,
        get_command_level_fn=get_command_level_fn,
        max_rounds=max_rounds,
    )

    # 5. Handle confirm_tool pause
    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        return result

    # 6. Format chat response
    reply = result if isinstance(result, str) and result.strip() else None
    if reply:
        html = mistune.html(reply)
        return {
            "type": "chat",
            "title": f"{title_prefix}{name}",
            "data": {"html": html, "actions": []},
        }

    return {
        "type": "chat",
        "title": f"{title_prefix}{name}",
        "data": {"html": "<p><em>(empty response)</em></p>", "actions": []},
    }


# ── SSE streaming ────────────────────────────────────────────────────────────


async def prompt_command_event_stream(
    name: str,
    args: list[str],
    commands_dir: Path,
    provider: Any,
    system_prompt_loader: Callable[[], str],
    timeout: float = 120.0,
) -> AsyncIterator[str]:
    """Yield SSE ``data: ...\\n\\n`` events for streaming a prompt command.

    Unlike :func:`execute_prompt_command`, this does NOT use tool-calling
    — it simply expands the template, sends it to the LLM, and streams the
    text tokens back as Server-Sent Events.

    Args:
        name: Prompt command name (file stem).
        args: Positional arguments from the user.
        commands_dir: Path to the ``commands/`` directory.
        provider: An :class:`~lightercore.llm.protocol.LLMProvider` instance.
        system_prompt_loader: Callable returning the system prompt string.
        timeout: Maximum seconds to wait for each streaming token.

    Yields:
        ``data: <json>`` SSE event strings, terminated by ``data: [DONE]``.
    """
    # 1. Load and expand
    cmd = load_prompt_command(commands_dir, name)
    if cmd is None:
        available = [c.name for c in list_prompt_commands(commands_dir)]
        msg = (
            f"Prompt command '{name}' not found. "
            f"Available: {', '.join(available) or '(none)'}"
        )
        yield f"data: {json.dumps({'token': msg})}\n\n"
        yield "data: [DONE]\n\n"
        return

    expanded = expand_prompt_template(cmd.template, args)

    # 2. Check provider
    available = getattr(provider, "available", None)
    if available is None:
        available = provider.is_available() if hasattr(provider, "is_available") else False
    if not available:
        yield f"data: {json.dumps({'token': 'LLM not configured.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # 3. Build messages and stream
    messages = build_prompt_messages(expanded, system_prompt_loader)
    try:
        result = await provider.chat(messages, stream=True)
        async with asyncio.timeout(timeout):
            async for token in result:
                yield f"data: {json.dumps({'token': token})}\n\n"
    except TimeoutError:
        yield f"data: {json.dumps({'token': f'Error: LLM streaming timed out after {timeout}s'})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'token': f'Error: {exc}'})}\n\n"
    finally:
        yield "data: [DONE]\n\n"
