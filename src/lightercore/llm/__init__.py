"""LLM provider and profile management.

Sub-package of lightercore providing the shared LLM infrastructure
used by both lighterbird and semantika:

- :mod:`~lightercore.llm.config` — :class:`ProviderConfig`, keyring helpers
- :mod:`~lightercore.llm.profiles` — :class:`ProfileManager`
- :mod:`~lightercore.llm.protocol` — :class:`LLMProvider` protocol
- :mod:`~lightercore.llm.base` — :class:`BaseLLMProvider`
- :mod:`~lightercore.llm.utils` — URL resolution, message parsing
- :mod:`~lightercore.llm.tool_loop` — multi-round tool-calling loop with HITL
"""

from lightercore.llm.base import (
    BaseLLMProvider,
    ChatResult,
    ToolCall,
    defs_to_tools,
    tool_call_to_command,
)
from lightercore.llm.config import ProviderConfig
from lightercore.llm.config import (
    clear_active_config,
    keyring_delete,
    keyring_get,
    keyring_set,
    load_active_config,
    save_active_config,
)
from lightercore.llm.profiles import ProfileManager
from lightercore.llm.protocol import LLMProvider
from lightercore.llm.tool_loop import (
    _pending_executions,
    resume_execution,
    run_tool_loop,
    sanitize_tool_result,
    tc_path,
)

__all__ = [
    "BaseLLMProvider",
    "ChatResult",
    "LLMProvider",
    "ProfileManager",
    "ProviderConfig",
    "ToolCall",
    "_pending_executions",
    "clear_active_config",
    "defs_to_tools",
    "keyring_delete",
    "keyring_get",
    "keyring_set",
    "load_active_config",
    "resume_execution",
    "run_tool_loop",
    "sanitize_tool_result",
    "save_active_config",
    "tc_path",
    "tool_call_to_command",
]
