"""LLM provider and profile management.

Sub-package of lightercore providing the shared LLM infrastructure
used by both lighterbird and semantika:

- :mod:`~lightercore.llm.config` — :class:`ProviderConfig`, keyring helpers
- :mod:`~lightercore.llm.profiles` — :class:`ProfileManager`
- :mod:`~lightercore.llm.protocol` — :class:`LLMProvider` protocol
- :mod:`~lightercore.llm.base` — :class:`BaseLLMProvider`
- :mod:`~lightercore.llm.utils` — URL resolution, message parsing
"""

from lightercore.llm.base import BaseLLMProvider
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

__all__ = [
    "BaseLLMProvider",
    "LLMProvider",
    "ProfileManager",
    "ProviderConfig",
    "clear_active_config",
    "keyring_delete",
    "keyring_get",
    "keyring_set",
    "load_active_config",
    "save_active_config",
]
