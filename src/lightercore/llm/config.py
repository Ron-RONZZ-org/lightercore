"""LLM provider configuration and keyring-based persistence.

Provides the canonical :class:`ProviderConfig` dataclass along with
keyring CRUD helpers that degrade gracefully when the system keyring
is unavailable.

Usage::

    from lightercore.llm.config import (
        ProviderConfig,
        keyring_set, keyring_get, keyring_delete,
        save_active_config, load_active_config, clear_active_config,
    )

    cfg = ProviderConfig(provider_type="openai", api_key="sk-...")
    save_active_config("myapp-llm", cfg)
    loaded = load_active_config("myapp-llm")
"""

from __future__ import annotations

import importlib.util
import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Graceful keyring import ────────────────────────────────────────────────

_keyring_available: bool = importlib.util.find_spec("keyring") is not None

if _keyring_available:
    import keyring as _kr  # type: ignore[assignment]
else:
    _kr = None  # type: ignore[assignment]

# Keyring account names (parameterised by service name at call sites)
_ACTIVE_CONFIG_KEY = "active-config"


# ── Provider configuration dataclass ───────────────────────────────────────


@dataclass
class ProviderConfig:
    """Unopinionated LLM provider configuration.

    All fields default to empty / sensible fallbacks.  Each application
    is expected to provide its own defaults at the factory level (e.g.
    a ``semantika_defaults()`` helper that fills in ``deepseek``).

    Attributes:
        provider_type: ``"openai"``, ``"deepseek"``, ``"ollama"``, etc.
        api_key: API key for the provider.
        base_url: API base URL.
        model: Model name (e.g. ``"gpt-4o"``).
        temperature: Sampling temperature (0.0 – 2.0).
        max_tokens: Maximum response tokens.
    """

    provider_type: str = ""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048

    def __repr__(self) -> str:
        """Return a safe repr with the API key redacted."""
        redacted = "****" if self.api_key else ""
        return (
            f"ProviderConfig(provider_type={self.provider_type!r}, "
            f"api_key={redacted!r}, "
            f"base_url={self.base_url!r}, "
            f"model={self.model!r}, "
            f"temperature={self.temperature}, "
            f"max_tokens={self.max_tokens})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Return config as a JSON-serialisable dict (includes API key)."""
        return {
            "provider_type": self.provider_type,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderConfig:
        """Create a config from a dict (keys match :meth:`to_dict`)."""
        return cls(
            provider_type=data.get("provider_type", ""),
            api_key=data.get("api_key", ""),
            base_url=data.get("base_url", ""),
            model=data.get("model", ""),
            temperature=float(data.get("temperature", 0.7)),
            max_tokens=int(data.get("max_tokens", 2048)),
        )

    def is_available(self) -> bool:
        """Return ``True`` if this config can reach a provider."""
        return bool(self.api_key) or self.provider_type == "ollama"


# ── Keyring helpers ────────────────────────────────────────────────────────


def keyring_set(service: str, key: str, value: str) -> bool:
    """Store *value* in the system keyring under *service* / *key*.

    Args:
        service: Service name (e.g. ``"semantika-llm"``).
        key: Account / entry name within the service.
        value: The value to store.

    Returns:
        ``True`` on success, ``False`` on failure (keyring unavailable).
    """
    if not _keyring_available or _kr is None:
        logger.warning("Keyring not available — cannot set %s/%s", service, key)
        return False
    try:
        _kr.set_password(service, key, value)  # type: ignore[union-attr]
        return True
    except Exception as exc:
        logger.warning("Keyring set_password failed for %s/%s: %s", service, key, exc)
        return False


def keyring_get(service: str, key: str) -> str | None:
    """Retrieve a value from the system keyring.

    Args:
        service: Service name.
        key: Entry name.

    Returns:
        The stored value or ``None`` if not found / unavailable.
    """
    if not _keyring_available or _kr is None:
        return None
    try:
        return _kr.get_password(service, key)  # type: ignore[union-attr]
    except Exception as exc:
        logger.warning("Keyring get_password failed for %s/%s: %s", service, key, exc)
        return None


def keyring_delete(service: str, key: str) -> bool:
    """Remove an entry from the system keyring.  Idempotent.

    Args:
        service: Service name.
        key: Entry name.

    Returns:
        ``True`` if the entry no longer exists (deleted or not found).
    """
    if not _keyring_available or _kr is None:
        return False
    try:
        _kr.delete_password(service, key)  # type: ignore[union-attr]
        return True
    except _kr.errors.PasswordDeleteError:  # type: ignore[union-attr]
        return True  # Idempotent — already absent.
    except Exception as exc:
        logger.warning("Keyring delete_password failed for %s/%s: %s", service, key, exc)
        return False


# ── Active-config persistence ──────────────────────────────────────────────


def save_active_config(service: str, config: ProviderConfig) -> None:
    """Persist *config* as the active provider for *service*.

    The config is JSON-serialised and stored in the system keyring.

    Args:
        service: Service name (e.g. ``"semantika-llm"``).
        config: The provider configuration to persist.
    """
    keyring_set(service, _ACTIVE_CONFIG_KEY, json.dumps(config.to_dict()))


def load_active_config(service: str) -> ProviderConfig | None:
    """Load the active provider config from the keyring.

    Args:
        service: Service name.

    Returns:
        The persisted :class:`ProviderConfig` or ``None`` if none is stored.
    """
    raw = keyring_get(service, _ACTIVE_CONFIG_KEY)
    if not raw:
        return None
    try:
        return ProviderConfig.from_dict(json.loads(raw))
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("Corrupt active config in keyring for %s", service)
        return None


def clear_active_config(service: str) -> None:
    """Remove the active provider config from the keyring.

    Args:
        service: Service name.
    """
    keyring_delete(service, _ACTIVE_CONFIG_KEY)


__all__ = [
    "ProviderConfig",
    "clear_active_config",
    "keyring_delete",
    "keyring_get",
    "keyring_set",
    "load_active_config",
    "save_active_config",
]
