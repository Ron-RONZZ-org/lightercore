"""Tests for lightercore.llm.profiles — ProfileManager."""

from __future__ import annotations

import pytest

from lightercore.llm.config import ProviderConfig
from lightercore.llm.profiles import ProfileManager


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


@pytest.fixture
def mgr() -> ProfileManager:
    return ProfileManager("test-app-llm")


# ── ProfileManager ───────────────────────────────────────────────────────────


class TestProfileManager:
    def test_save_and_list(self, mgr: ProfileManager) -> None:
        cfg = ProviderConfig(provider_type="openai", api_key="sk-work", model="gpt-4o")
        mgr.save("work", cfg)
        profiles = mgr.list()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "work"
        assert profiles[0]["has_api_key"] is True

    def test_list_omits_api_key(self, mgr: ProfileManager) -> None:
        mgr.save("secret", ProviderConfig(provider_type="openai", api_key="sk-hidden"))
        profiles = mgr.list()
        entry = next(p for p in profiles if p["name"] == "secret")
        assert "api_key" not in entry
        assert entry["has_api_key"] is True

    def test_get_returns_api_key(self, mgr: ProfileManager) -> None:
        mgr.save("secret", ProviderConfig(provider_type="openai", api_key="sk-hidden"))
        cfg = mgr.get("secret")
        assert cfg is not None
        assert cfg.api_key == "sk-hidden"

    def test_get_nonexistent(self, mgr: ProfileManager) -> None:
        assert mgr.get("nope") is None

    def test_delete(self, mgr: ProfileManager) -> None:
        mgr.save("delete-me", ProviderConfig(provider_type="openai"))
        assert mgr.delete("delete-me") is True
        assert mgr.get("delete-me") is None

    def test_delete_nonexistent(self, mgr: ProfileManager) -> None:
        assert mgr.delete("nope") is False

    def test_modify(self, mgr: ProfileManager) -> None:
        mgr.save("work", ProviderConfig(provider_type="openai", model="gpt-3.5", api_key="sk-old"))
        updated = mgr.modify("work", model="gpt-4o")
        assert updated is not None
        assert updated.model == "gpt-4o"
        assert updated.api_key == "sk-old"  # unchanged

    def test_modify_updates_api_key(self, mgr: ProfileManager) -> None:
        mgr.save("work", ProviderConfig(provider_type="openai", api_key="sk-old"))
        mgr.modify("work", api_key="sk-new")
        cfg = mgr.get("work")
        assert cfg is not None
        assert cfg.api_key == "sk-new"

    def test_modify_empty_api_key_keeps_current(self, mgr: ProfileManager) -> None:
        mgr.save("work", ProviderConfig(provider_type="openai", api_key="sk-old"))
        mgr.modify("work", api_key="")
        cfg = mgr.get("work")
        assert cfg is not None
        assert cfg.api_key == "sk-old"

    def test_modify_nonexistent(self, mgr: ProfileManager) -> None:
        assert mgr.modify("nope", model="gpt-4o") is None

    def test_switch_to(self, mgr: ProfileManager) -> None:
        mgr.save("work", ProviderConfig(provider_type="openai", api_key="sk-work", model="gpt-4o"))
        config = mgr.switch_to("work")
        assert config is not None
        assert config.provider_type == "openai"
        assert config.api_key == "sk-work"
        # Also persisted as active config
        from lightercore.llm.config import load_active_config

        active = load_active_config("test-app-llm")
        assert active is not None
        assert active.provider_type == "openai"

    def test_switch_to_nonexistent(self, mgr: ProfileManager) -> None:
        assert mgr.switch_to("nope") is None

    def test_list_empty(self, mgr: ProfileManager) -> None:
        assert mgr.list() == []

    def test_multiple_profiles(self, mgr: ProfileManager) -> None:
        mgr.save("work", ProviderConfig(provider_type="openai", api_key="sk-work"))
        mgr.save("local", ProviderConfig(provider_type="ollama"))
        profiles = mgr.list()
        assert len(profiles) == 2
        names = {p["name"] for p in profiles}
        assert names == {"work", "local"}
