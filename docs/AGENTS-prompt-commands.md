# AGENTS-prompt-commands.md — Prompt Commands Module Agent Instructions

## Summary

File-based LLM prompt command loader and template expander. Shared between lighterbird and semantika.

Scans ``<config_dir>/commands/*.md`` for user-defined prompt templates that can be invoked via the ``/*`` prefix in the command bar.

## Key Files

- ``prompt_commands.py`` — ``PromptCommand`` dataclass, scanner, loader, and template expander

## Public API

| Function | Returns | Description |
|----------|---------|-------------|
| ``list_prompt_commands(commands_dir)`` | ``list[PromptCommand]`` | Scan ``*.md`` files, sorted by name |
| ``load_prompt_command(commands_dir, name)`` | ``PromptCommand \| None`` | Load single command (case-insensitive) |
| ``expand_prompt_template(template, args)`` | ``str`` | Replace ``$1..$9`` + ``$ARGUMENTS`` |
| ``prompt_command_exists(commands_dir, name)`` | ``bool`` | Check if command file exists |

## File Format

No YAML frontmatter. Files must have a ``# `` first line as description:

```markdown
# Description shown in autocomplete
Prompt template text with $1 and $2 placeholders.
```

- Files without a ``# `` first line are silently skipped.
- ``$1``–``$9`` are replaced by positional arguments.
- ``$ARGUMENTS`` is replaced by all arguments joined with spaces.
- Dotfiles (``.*.md``) and non-``.md`` files are ignored.

## Constraints

- **Pure I/O** — no HTTP, no app-specific logic.
- **No YAML frontmatter** — simpler than OpenCode's model.
- **No recursive expansion** — templates are plain text, not executed.
- **Backward compatibility** — do not rename or remove public functions without a deprecation cycle.

## Exported via

``lightercore/__init__.py`` imports ``lightercore.prompt_commands`` and includes it in ``__all__``.
