"""LLM provider, profile management, and tool registry.

Sub-package of lightercore providing the shared LLM infrastructure
used by both lighterbird and semantika:

- :mod:`~lightercore.llm.config` — :class:`ProviderConfig`, keyring helpers
- :mod:`~lightercore.llm.profiles` — :class:`ProfileManager`
- :mod:`~lightercore.llm.protocol` — :class:`LLMProvider` protocol
- :mod:`~lightercore.llm.base` — :class:`BaseLLMProvider`
- :mod:`~lightercore.llm.utils` — URL resolution, message parsing
- :mod:`~lightercore.llm.tool_loop` — multi-round tool-calling loop with HITL
- :mod:`~lightercore.llm.tools` — shared ``@llm_tool()`` decorator and registry
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
from lightercore.llm.tools import (
    _llm_registry,
    dispatch_llm_tool,
    get_llm_tool_level,
    get_llm_tool_metadata,
    get_llm_tool_names,
    get_llm_tools,
    is_llm_tool,
    llm_tool,
)

# Re-export for convenience so apps can do:
#   from lightercore.llm import llm_tool, get_llm_tools, ...
# or import individual tool handlers:
#   from lightercore.llm import llm_system_now
from lightercore.llm.tools import system as _lightercore_tools_system  # noqa: F401
from lightercore.llm.tools.system import llm_system_now

__all__ = [
    "BaseLLMProvider",
    "ChatResult",
    "LLMProvider",
    "ProfileManager",
    "ProviderConfig",
    "ToolCall",
    "_llm_registry",
    "_pending_executions",
    "clear_active_config",
    "defs_to_tools",
    "dispatch_llm_tool",
    "get_llm_tool_level",
    "get_llm_tool_metadata",
    "get_llm_tool_names",
    "get_llm_tools",
    "is_llm_tool",
    "keyring_delete",
    "keyring_get",
    "keyring_set",
    "llm_system_now",
    "llm_tool",
    "load_active_config",
    "resume_execution",
    "run_tool_loop",
    "sanitize_tool_result",
    "save_active_config",
    "tc_path",
    "tool_call_to_command",
]
