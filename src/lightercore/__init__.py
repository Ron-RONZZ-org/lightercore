"""lightercore — shared core for the 3rd-gen PIM/knowledge-graph toolchain.

Provides the foundational building blocks used by both **lighterbird** (PIM)
and **semantika** (knowledge graph): database management, path resolution,
backup/restore, CRUD abstraction, and exception hierarchy.

LLM provider infrastructure (llm/, cowrite/, system_prompt, prompt_commands,
prompt_files) has been extracted to the ``lighterllm`` package.

Usage::

    from lightercore.db import LighterDB
    from lightercore.paths import data_dir
    from lightercore.exceptions import LighterError
"""

from lightercore import db, paths, exceptions, backup, crud, permissions, dev_helpers, text_utils
from lightercore.paths import set_app_name

__all__ = [
    "db", "paths", "exceptions", "backup", "crud", "permissions",
    "dev_helpers", "text_utils",
    "set_app_name",
]
