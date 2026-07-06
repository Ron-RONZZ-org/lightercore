# AGENTS.md — Root Project Rules for lightercore

This is the canonical, repo-wide instruction file for AI agents working on **lightercore**.

## Hierarchical Context Model

Agents **must** follow this rule:

> When working inside a directory, load the nearest `AGENTS.md` file and merge it with parent `AGENTS.md` files up to root.
> Local rules override global rules.

Context resolution order (highest priority first):
1. `AGENTS-[module].md` in module directories — module-specific context
2. `AGENTS.md` in current working directory (if present)
3. Root `AGENTS.md` — global project rules

---
## Project Overview

**lightercore** is the shared core library for the 3rd-generation PIM/knowledge-graph toolchain. It provides foundational building blocks consumed by both **lighterbird** (personal information manager) and **semantika** (knowledge graph with LLM-native interaction):

- **Database**: SQLite WAL-mode wrapper with per-thread connections
- **Paths**: XDG-compliant directory resolution with sentinel protection
- **Exceptions**: Hierarchical exception classes for all domain errors
- **CRUD**: Generic create/read/update/delete with UUID prefix matching and soft-delete
- **Backup**: Multi-strategy 7z-backed backup/restore with export/import and external sync
- **LLM**: Shared LLM infrastructure — provider config, keyring persistence, profile CRUD, unified chat/command-generation, system prompt management

**Design philosophy**: lightercore is the *one canonical implementation* of these cross-cutting concerns. Improvements flow outward — never inward.

---

## Source Tree Structure

```
lightercore/
├── AGENTS.md
├── README.md
├── LICENSE
├── pyproject.toml
├── .gitignore
├── src/
│   └── lightercore/
│       ├── __init__.py
│       ├── db.py
│       ├── paths.py
│       ├── exceptions.py
│       ├── crud.py
│       ├── backup.py
│       ├── permissions.py      ← PermissionLevel enum, PermissionError, ConfirmationProtocol
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── config.py       ← ProviderConfig, keyring helpers, active config CRUD
│       │   ├── profiles.py     ← ProfileManager (named LLM profiles)
│       │   ├── protocol.py     ← LLMProvider Protocol
│       │   ├── base.py         ← BaseLLMProvider (shared chat + command generation)
│       │   └── utils.py        ← URL resolution, message parsing, DeepSeek compat
│       └── system_prompt.py    ← SystemPromptManager (file-based, auto-seed)
├── docs/
│   ├── AGENTS-db.md
│   ├── AGENTS-paths.md
│   ├── AGENTS-exceptions.md
│   ├── AGENTS-crud.md
│   ├── AGENTS-backup.md
│   ├── AGENTS-permissions.md
│   └── AGENTS-llm.md
└── tests/
    ├── __init__.py
    ├── test_permissions.py
    ├── test_llm_config.py
    ├── test_llm_profiles.py
    ├── test_llm_utils.py
    ├── test_llm_base.py
    └── test_system_prompt.py
```

---

## Coding Conventions

1. **No file > 500 lines.** Split by functional unit.
2. **Type hints on all public functions.** Use `from __future__ import annotations`.
3. **Docstrings on all public functions.** Google-style or reStructuredText.
4. **All public symbols must be exported in `__all__`** in each module.
5. **Backward compatibility is critical.** Do not rename public functions, change signatures, or remove symbols without a deprecation cycle.
6. **Deprecation cycle**: mark old symbols with `warnings.warn(DeprecationWarning(...))` for at least two minor versions before removal.
7. **Best-of-both-worlds**: when adding from lighterbird or semantika, compare the two implementations and merge the best parts. Do not blindly copy one.

---

## Testing Requirements

| Aspect | Convention |
|--------|-----------|
| Framework | pytest |
| Run all tests | `uv run pytest tests/` |
| Coverage target | 90%+ line coverage |

### Principles

1. Test via the public API — consumer projects depend on `lightercore.backup.list_backups()`.
2. Use `tmp_path` for file I/O tests. Never write to real user directories.
3. The backup module uses `py7zr` and `sqlite3` — tests must verify archive integrity.
4. Every bug fix must include a regression test.

---

## Dependency Management

| Operation | Command |
|-----------|---------|
| Install dev | `uv pip install -e ".[dev]"` |
| Run tests | `uv run pytest tests/` |
| Add dependency | `uv add <pkg>` |

---

## What to Avoid

- **Do not import from lighterbird or semantika.** lightercore is upstream.
- **Do not add project-specific logic** that only one consumer would use.
- **Do not depend on FastAPI, uvicorn, or any web framework.**
- **Do not hardcode application-specific paths** — use env vars.

---

## Migration Policy

When migrating code into lightercore:

1. Compare the two implementations (lighterbird vs semantika).
2. Merge the best parts of each into the canonical version.
3. Remove the old copy from the downstream project.
4. Update `pyproject.toml` in the downstream project to add `lightercore`.
5. Run downstream tests to confirm transparent migration.

---

## Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`

---

## Module-Level AGENTS Files

| Module | File |
|--------|------|
| Database | `docs/AGENTS-db.md` |
| Paths | `docs/AGENTS-paths.md` |
| Exceptions | `docs/AGENTS-exceptions.md` |
| CRUD | `docs/AGENTS-crud.md` |
| Backup | `docs/AGENTS-backup.md` |
| Permissions | `docs/AGENTS-permissions.md` |
| LLM | `docs/AGENTS-llm.md` |
| Prompt Commands | `docs/AGENTS-prompt-commands.md` |
