"""Tests for lightercore.llm.config — ProviderConfig, keyring helpers, active config CRUD."""

from __future__ import annotations

import json

import pytest

from lightercore.llm.config import (
    ProviderConfig,
    clear_active_config,
    keyring_delete,
    keyring_get,
    keyring_set,
    load_active_config,
    save_active_config,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_keyring(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Replace system keyring with an in-memory dict."""
    store: dict[str, str] = {}

    def set_pw(service: str, key: str, value: str) -> None:
        store[f"{service}:{key}"] = value

    def get_pw(service: str, key: str) -> str | None:
        return store.get(f"{service}:{key}")

    def del_pw(service: str, key: str) -> None:
        store.pop(f"{service}:{key}", None)

    import keyring as _kr

    monkeypatch.setattr(_kr, "set_password", set_pw)
    monkeypatch.setattr(_kr, "get_password", get_pw)
    monkeypatch.setattr(_kr, "delete_password", del_pw)

    return store


# ── ProviderConfig ───────────────────────────────────────────────────────────


class TestProviderConfig:
    def test_defaults(self) -> None:
        cfg = ProviderConfig()
        assert cfg.provider_type == ""
        assert cfg.api_key == ""
        assert cfg.temperature == 0.7
        assert cfg.max_tokens == 2048
        assert cfg.base_url == ""
        assert cfg.model == ""

    def test_custom_values(self) -> None:
        cfg = ProviderConfig(
            provider_type="custom",
            api_key="sk-test",
            base_url="http://localhost:8080/v1",
            model="my-model",
            temperature=0.5,
            max_tokens=4096,
        )
        assert cfg.provider_type == "custom"
        assert cfg.api_key == "sk-test"
        assert cfg.base_url == "http://localhost:8080/v1"
        assert cfg.model == "my-model"
        assert cfg.temperature == 0.5
        assert cfg.max_tokens == 4096

    def test_repr_redacts_api_key(self) -> None:
        cfg = ProviderConfig(api_key="sk-secret")
        assert "sk-secret" not in repr(cfg)
        assert "****" in repr(cfg)

    def test_repr_empty_key(self) -> None:
        cfg = ProviderConfig()
        assert "''" in repr(cfg)  # Empty string repr

    def test_to_dict(self) -> None:
        cfg = ProviderConfig(provider_type="openai", api_key="sk-test", model="gpt-4o")
        d = cfg.to_dict()
        assert d["provider_type"] == "openai"
        assert d["api_key"] == "sk-test"
        assert d["model"] == "gpt-4o"

    def test_from_dict(self) -> None:
        d = {
            "provider_type": "deepseek",
            "api_key": "sk-ds",
            "base_url": "",
            "model": "deepseek-chat",
            "temperature": "0.3",
            "max_tokens": "1024",
        }
        cfg = ProviderConfig.from_dict(d)
        assert cfg.provider_type == "deepseek"
        assert cfg.api_key == "sk-ds"
        assert cfg.temperature == 0.3
        assert cfg.max_tokens == 1024

    def test_is_available_with_api_key(self) -> None:
        cfg = ProviderConfig(api_key="sk-test")
        assert cfg.is_available() is True

    def test_is_available_ollama_no_key(self) -> None:
        cfg = ProviderConfig(provider_type="ollama")
        assert cfg.is_available() is True

    def test_is_available_false(self) -> None:
        cfg = ProviderConfig()
        assert cfg.is_available() is False


# ── Keyring helpers ──────────────────────────────────────────────────────────


class TestKeyringHelpers:
    def test_set_and_get(self) -> None:
        assert keyring_set("svc", "k1", "v1") is True
        assert keyring_get("svc", "k1") == "v1"

    def test_get_nonexistent(self) -> None:
        assert keyring_get("svc", "nonexistent") is None

    def test_delete(self) -> None:
        keyring_set("svc", "k1", "v1")
        assert keyring_delete("svc", "k1") is True
        assert keyring_get("svc", "k1") is None

    def test_delete_nonexistent_is_idempotent(self) -> None:
        assert keyring_delete("svc", "nonexistent") is True

    def test_overwrite(self) -> None:
        keyring_set("svc", "k1", "v1")
        keyring_set("svc", "k1", "v2")
        assert keyring_get("svc", "k1") == "v2"


# ── Active config CRUD ───────────────────────────────────────────────────────


class TestActiveConfig:
    def test_save_and_load(self) -> None:
        cfg = ProviderConfig(provider_type="openai", api_key="sk-test", model="gpt-4o")
        save_active_config("test-app-llm", cfg)
        loaded = load_active_config("test-app-llm")
        assert loaded is not None
        assert loaded.provider_type == "openai"
        assert loaded.api_key == "sk-test"
        assert loaded.model == "gpt-4o"

    def test_load_none(self) -> None:
        assert load_active_config("nonexistent-app") is None

    def test_clear(self) -> None:
        cfg = ProviderConfig(provider_type="deepseek", api_key="sk-ds")
        save_active_config("test-app-llm", cfg)
        clear_active_config("test-app-llm")
        assert load_active_config("test-app-llm") is None

    def test_roundtrip_via_json(self, mock_keyring: dict) -> None:
        cfg = ProviderConfig(provider_type="ollama", model="llama3.2")
        save_active_config("app", cfg)
        raw = mock_keyring.get("app:active-config")
        assert raw is not None
        data = json.loads(raw)
        assert data["provider_type"] == "ollama"
        assert data["model"] == "llama3.2"
