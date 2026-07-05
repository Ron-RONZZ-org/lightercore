"""Named LLM profile management backed by the system keyring.

Profiles are stored as a JSON dict keyed by profile name inside a single
keyring entry (``saved-profiles``) under the application's service namespace.

Usage::

    from lightercore.llm.config import ProviderConfig
    from lightercore.llm.profiles import ProfileManager

    mgr = ProfileManager("semantika-llm")
    mgr.save("work", ProviderConfig(provider_type="openai", api_key="sk-..."))
    mgr.list()   # → [{"name": "work", "provider_type": "openai", ...}]  (no key)
    mgr.get("work")  # → ProviderConfig(...)  (with key)
    mgr.switch_to("work")  # → saves as active config too
"""

from __future__ import annotations

import json
import logging
from typing import Any

from lightercore.llm.config import (
    ProviderConfig,
    keyring_delete as _keyring_delete,
    keyring_get as _keyring_get,
    keyring_set as _keyring_set,
    save_active_config as _save_active,
)

logger = logging.getLogger(__name__)

_PROFILES_KEY = "saved-profiles"


class ProfileManager:
    """Keyring-backed CRUD for named LLM provider profiles.

    Args:
        service_name: Keyring service namespace (e.g. ``"semantika-llm"``).
    """

    def __init__(self, service_name: str) -> None:
        self._service = service_name

    # ── Internal helpers ──────────────────────────────────────────────────

    def _load_all(self) -> dict[str, dict[str, Any]]:
        """Load the full profiles dict from keyring."""
        raw = _keyring_get(self._service, _PROFILES_KEY) or "{}"
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}

    def _save_all(self, profiles: dict[str, dict[str, Any]]) -> None:
        """Persist the full profiles dict to keyring."""
        _keyring_set(self._service, _PROFILES_KEY, json.dumps(profiles))

    @staticmethod
    def _redact(profile: dict[str, Any]) -> dict[str, Any]:
        """Return a profile dict safe for listing (no API key)."""
        return {
            "name": profile.get("name", ""),
            "provider_type": profile.get("provider_type", ""),
            "base_url": profile.get("base_url", ""),
            "model": profile.get("model", ""),
            "has_api_key": bool(profile.get("api_key", "")),
        }

    @staticmethod
    def _extract_config_kwargs(data: dict[str, Any]) -> dict[str, Any]:
        """Extract ProviderConfig-compatible kwargs from a profile dict."""
        return {
            "provider_type": data.get("provider_type", ""),
            "api_key": data.get("api_key", ""),
            "base_url": data.get("base_url", ""),
            "model": data.get("model", ""),
            "temperature": float(data.get("temperature", 0.7)),
            "max_tokens": int(data.get("max_tokens", 2048)),
        }

    # ── Public CRUD ───────────────────────────────────────────────────────

    def save(self, name: str, config: ProviderConfig) -> ProviderConfig:
        """Save a named profile.

        Args:
            name: Profile name (used as lookup key).
            config: The provider configuration to persist.

        Returns:
            The stored config.
        """
        profiles = self._load_all()
        profiles[name] = config.to_dict()
        self._save_all(profiles)
        return config

    def list(self) -> list[dict[str, Any]]:
        """List all saved profiles (API keys **not** included).

        Returns:
            A list of safe profile dicts with ``has_api_key`` boolean.
        """
        profiles = self._load_all()
        result: list[dict[str, Any]] = []
        for name, data in profiles.items():
            entry = self._redact(data)
            entry["name"] = name
            result.append(entry)
        return result

    def get(self, name: str) -> ProviderConfig | None:
        """Retrieve a profile **with** its API key.

        Args:
            name: Profile name.

        Returns:
            :class:`ProviderConfig` or ``None`` if not found.
        """
        profiles = self._load_all()
        data = profiles.get(name)
        if data is None:
            return None
        kwargs = self._extract_config_kwargs(data)
        return ProviderConfig(**kwargs)

    def delete(self, name: str) -> bool:
        """Delete a named profile.

        Args:
            name: Profile name.

        Returns:
            ``True`` if the profile existed and was removed.
        """
        profiles = self._load_all()
        if name not in profiles:
            return False
        del profiles[name]
        self._save_all(profiles)
        return True

    def modify(self, name: str, **updates: Any) -> ProviderConfig | None:
        """Partially update a saved profile.

        Accepted keyword arguments correspond to :class:`ProviderConfig`
        fields.  An empty string for ``api_key`` is treated as "keep current".

        Args:
            name: Profile name.
            **updates: Fields to update.

        Returns:
            Updated :class:`ProviderConfig` or ``None`` if not found.
        """
        profiles = self._load_all()
        if name not in profiles:
            return None

        data = profiles[name]
        for key in ("provider_type", "base_url", "model"):
            if key in updates:
                data[key] = updates[key]
        if updates.get("api_key"):
            data["api_key"] = updates["api_key"]
        if "temperature" in updates:
            data["temperature"] = float(updates["temperature"])
        if "max_tokens" in updates:
            data["max_tokens"] = int(updates["max_tokens"])

        profiles[name] = data
        self._save_all(profiles)

        kwargs = self._extract_config_kwargs(data)
        return ProviderConfig(**kwargs)

    def switch_to(self, name: str) -> ProviderConfig | None:
        """Load a profile and persist it as the active config.

        This is a convenience that combines ``get`` + ``save_active_config``.

        Args:
            name: Profile name.

        Returns:
            The activated :class:`ProviderConfig` or ``None``.
        """
        config = self.get(name)
        if config is None:
            return None
        _save_active(self._service, config)
        return config


__all__ = ["ProfileManager"]
