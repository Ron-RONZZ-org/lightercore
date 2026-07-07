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
- **Svelte UI**: Shared Svelte 5 components and stores — reactive stores (bannerStore, keyboardShortcuts, dirtyFormStore, tabStore), utility functions (listTabFormat, listTabSelection), and UI components (BannerContainer). Published as a separate npm package (`@lightercore/ui`) from `web/`.

**Design philosophy**: lightercore is the *one canonical implementation* of these cross-cutting concerns. Improvements flow outward — never inward.

> **Dual-build architecture**: The `web/` subdirectory is a standalone npm package (`@lightercore/ui`) with its own `package.json` and `vitest.config.js`. The Python package (Hatchling, `src/lightercore/`) and JS package (Vite, `web/`) are fully independent build systems sharing the same repo.

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
├── tests/
│   ├── __init__.py
│   ├── test_permissions.py
│   ├── test_llm_config.py
│   ├── test_llm_profiles.py
│   ├── test_llm_utils.py
│   ├── test_llm_base.py
│   └── test_system_prompt.py
└── web/                           ← Svelte UI component package (@lightercore/ui)
    ├── package.json               # npm package with exports field
    ├── vitest.config.js           # Vitest with @sveltejs/vite-plugin-svelte
    ├── .gitignore
    └── src/lib/                   # Shared Svelte components, stores, utilities
        ├── bannerStore.svelte.js
        ├── keyboardShortcuts.svelte.js
        ├── dirtyFormStore.svelte.js
        ├── tabStore.svelte.js
        ├── listTabFormat.js
        ├── listTabSelection.svelte.js
        ├── listTabShared.svelte.js     (barrel)
        ├── BannerContainer.svelte
        └── *.test.js              (75+ tests)
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

| Layer | Framework | Command | Coverage |
|-------|-----------|---------|----------|
| Python (pytest) | pytest | `uv run pytest tests/` | 90%+ line |
| Svelte/JS (vitest) | vitest + jsdom | `cd web && npm test` | 75+ tests |

### Python Principles

1. Test via the public API — consumer projects depend on `lightercore.backup.list_backups()`.
2. Use `tmp_path` for file I/O tests. Never write to real user directories.
3. The backup module uses `py7zr` and `sqlite3` — tests must verify archive integrity.
4. Every bug fix must include a regression test.

### Svelte/JS Principles

1. Test stores and pure functions with vitest + jsdom environment.
2. Svelte 5 rune modules (`.svelte.js`) are compiled by `@sveltejs/vite-plugin-svelte` during tests.
3. The `CSS.escape` polyfill is required in test setup since jsdom doesn't provide it.
4. Consumer projects run their own tests; lightercore tests validate the canonical implementation.

---

## Dependency Management

### Python

| Operation | Command |
|-----------|---------|
| Install dev | `uv pip install -e ".[dev]"` |
| Run tests | `uv run pytest tests/` |
| Add dependency | `uv add <pkg>` |

### Svelte/JS

| Operation | Command |
|-----------|---------|
| Install deps | `cd web && npm install` |
| Run tests | `cd web && npm test` |
| Add dependency | `cd web && npm install --save-dev <pkg>` |

Consumers reference the UI package via npm `file:` dependency:
```json
{
  "devDependencies": {
    "@lightercore/ui": "file:../../lightercore/web"
  }
}
```

---

## What to Avoid

- **Do not import from lighterbird or semantika.** lightercore is upstream.
- **Do not add project-specific logic** that only one consumer would use.
- **Do not depend on FastAPI, uvicorn, or any web framework.**
- **Do not hardcode application-specific paths** — use env vars.
- **Do not add Svelte components with consumer-specific imports** — components in `web/src/lib/` must only import from other lightercore modules or from standard libraries. Imports like `"../TabView.svelte"` or `"../HomeTab.svelte"` that reference consumer-specific components must NOT be added.

---

## Migration Policy

### Python Code

When migrating Python code into lightercore:

1. Compare the two implementations (lighterbird vs semantika).
2. Merge the best parts of each into the canonical version.
3. Remove the old copy from the downstream project.
4. Update `pyproject.toml` in the downstream project to add `lightercore`.
5. Run downstream tests to confirm transparent migration.

### Svelte/JS Code

When migrating Svelte/JS code into lightercore's `web/`:

1. Compare the two implementations (lighterbird vs semantika).
2. Merge the best parts of each into the canonical version under `web/src/lib/`.
3. In consumer projects, replace the local file with a re-export from `@lightercore/ui`.
4. For `.svelte` components, update imports to use `@lightercore/ui/<component>`.
5. For `.svelte.js` stores/utilities, export/import from the barrel or directly.
6. Add tests in lightercore's `web/src/lib/` for the canonical implementation.
7. Run consumer tests + `npm test` in lightercore/web to verify.
8. Follow the same "merge → delete local → test" pattern — never leave stale copies.

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
