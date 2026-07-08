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

import re
from dataclasses import dataclass, field
from pathlib import Path


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
