# lightercore

**Shared core library for the 3rd-generation PIM/knowledge-graph toolchain.**

Provides foundational building blocks for both [lighterbird](https://github.com/Ron-RONZZ-org/lighterbird) (PIM) and [semantika](https://github.com/Ron-RONZZ-org/semantika) (knowledge graph):

- **Database** — Thread-safe SQLite3 WAL-mode wrapper
- **Paths** — XDG-compliant directory resolution with sentinel protection
- **Exceptions** — Structured error hierarchy
- **CRUD** — Generic CRUD with UUID prefix matching + soft-delete
- **Backup** — Multi-strategy 7z backup/restore with SHA-256 verification
- **Permissions** — `PermissionLevel` enum (READ/WRITE/DESTRUCTIVE/SYSTEM), `PermissionError`, and `ConfirmationProtocol` for LLM command safety
- **Prompt Files** — `PromptFile` dataclass and `PromptFilesManager` for tracking, comparing, resetting, and saving shipped prompt files (`system_prompt.md`, `AGENTS.md`, command files, etc.)

## Installation

```bash
git clone https://github.com/Ron-RONZZ-org/lightercore.git
cd lightercore
uv pip install -e ".[dev]"
```

## Quick Start

```python
from lightercore.db import LighterbirdDB
from lightercore.paths import data_dir, ensure_dirs

ensure_dirs()
db = LighterbirdDB(data_dir() / "app.db")
db.execute("CREATE TABLE IF NOT EXISTS items (uuid TEXT PRIMARY KEY, name TEXT)")
```

See `docs/` for per-module documentation.

## Environment Variables

| Purpose | Primary | Fallback 1 | Fallback 2 |
|---------|---------|------------|------------|
| Data dir | `LIGHTERCORE_DATA_DIR` | `LIGHTERBIRD_DATA_DIR` | `SEMANTIKA_DATA_DIR` |
| Config dir | `LIGHTERCORE_CONFIG_DIR` | `LIGHTERBIRD_CONFIG_DIR` | `SEMANTIKA_CONFIG_DIR` |
| Cache dir | `LIGHTERCORE_CACHE_DIR` | `LIGHTERBIRD_CACHE_DIR` | `SEMANTIKA_CACHE_DIR` |
| State dir | `LIGHTERCORE_STATE_DIR` | `LIGHTERBIRD_STATE_DIR` | `SEMANTIKA_STATE_DIR` |

## Web Package (`@lightercore/ui`)

The `web/` directory is a standalone npm package (`@lightercore/ui`) providing shared Svelte 5 stores, utilities, and components consumed by both lighterbird and semantika:

- **`tabStore.svelte.js`** — Reactive tab management
- **`dirtyFormStore.svelte.js`** — Unsaved-changes tracking
- **`bannerStore.svelte.js`** — Auto-dismissing notification banner
- **`commandHistory.svelte.js`** — Persistent command history
- **`keyboardShortcuts.svelte.js`** — Keyboard shortcut registration
- **`listTabSelection.svelte.js`** — Selection/range navigation for list tabs
- **`listTabShared.svelte.js`** — Shared list tab utilities (clipboard, date formatting)
- **`preview.svelte.js`** — Content preview modal
- **`multiCommand.js`** — Multi-command input parsing (`splitCommands()`, `isMultiCommand()`)

## Design

lightercore is the **one canonical implementation** of shared infrastructure. Improvements flow outward — no more fork-and-strip degradation.

## License

AGPL-3.0
