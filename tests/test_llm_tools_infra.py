"""Tests for lightercore.llm.tools — shared @llm_tool infrastructure.

Covers the decorator, registry, dispatch, permission callbacks, and
query helpers that are shared between lighterbird and semantika.

Domain-specific tool files (email.*, node.*, etc.) are tested in each
app's own test suite.  This file tests the infrastructure only.
"""

from __future__ import annotations

import pytest
from lightercore.permissions import PermissionLevel
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


# ── Cleanup helpers ──────────────────────────────────────────────────────────


def _clear_registry() -> None:
    _llm_registry.clear()


# ── Decorator ────────────────────────────────────────────────────────────────


class TestDecorator:
    """@llm_tool() decorator basic functionality."""

    def setup_method(self) -> None:
        _clear_registry()

    def teardown_method(self) -> None:
        _clear_registry()

    def test_registers_handler(self) -> None:
        @llm_tool(name="test.basic", description="A basic test tool")
        def handler(**kwargs) -> dict:
            return {"success": True, "data": "ok"}

        assert is_llm_tool("test.basic")

    def test_dispatch_executes_handler(self) -> None:
        @llm_tool(name="test.exec", description="Exec test")
        def handler(**kwargs) -> dict:
            return {"success": True, "data": f"got:{kwargs}"}

        result = dispatch_llm_tool("test.exec", {"x": 1})
        assert result["success"] is True
        assert result["data"] == "got:{'x': 1}"

    def test_default_permission_is_read(self) -> None:
        @llm_tool(name="test.default_perm", description="Default perm")
        def handler(**kwargs) -> dict:
            return {"success": True}

        level = get_llm_tool_level("test.default_perm")
        assert level == PermissionLevel.READ

    def test_writes_permission_level(self) -> None:
        @llm_tool(
            name="test.write_perm",
            description="Write perm",
            permission_level=PermissionLevel.WRITE,
        )
        def handler(**kwargs) -> dict:
            return {"success": True}

        level = get_llm_tool_level("test.write_perm")
        assert level == PermissionLevel.WRITE

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid LLM tool name"):
            llm_tool(name="", description="empty")(lambda **kw: {})

    def test_params_conversion(self) -> None:
        @llm_tool(
            name="test.params",
            description="Param test",
            params=[
                {"name": "q", "type": "string", "description": "A query"},
                {"name": "count", "type": "integer", "description": "Count"},
            ],
        )
        def handler(**kwargs) -> dict:
            return {"success": True}

        entry = _llm_registry["test.params"]
        props = entry["parameters"]["properties"]
        assert props["q"]["type"] == "string"
        assert props["count"]["type"] == "integer"

    def test_required_params(self) -> None:
        @llm_tool(
            name="test.req",
            description="Required test",
            params=[
                {"name": "reqd", "type": "string", "description": "Required", "required": True},
                {"name": "opt", "type": "string", "description": "Optional"},
            ],
        )
        def handler(**kwargs) -> dict:
            return {"success": True}

        entry = _llm_registry["test.req"]
        assert entry["parameters"]["required"] == ["reqd"]

    def test_default_value_in_schema(self) -> None:
        """Params with a 'default' key produce a 'default' in the JSON Schema."""
        @llm_tool(
            name="test.default_val",
            description="Default value test",
            params=[
                {"name": "limit", "type": "integer", "description": "Max results", "default": 20},
                {"name": "q", "type": "string", "description": "Query"},
            ],
        )
        def handler(**kwargs) -> dict:
            return {"success": True}

        entry = _llm_registry["test.default_val"]
        props = entry["parameters"]["properties"]
        assert props["limit"]["default"] == 20
        # Params without 'default' should not have it in schema
        assert "default" not in props["q"]


# ── OpenAI format ────────────────────────────────────────────────────────────


class TestGetLlmTools:
    """get_llm_tools() OpenAI format conversion."""

    def setup_method(self) -> None:
        _clear_registry()

    def teardown_method(self) -> None:
        _clear_registry()

    def test_returns_list(self) -> None:
        @llm_tool(name="test.foo", description="Foo")
        def handler(**kwargs) -> dict:
            return {"success": True}

        tools = get_llm_tools()
        assert isinstance(tools, list)
        assert len(tools) == 1

    def test_openai_format(self) -> None:
        @llm_tool(
            name="test.foo",
            description="Foo tool",
            params=[{"name": "x", "type": "string", "description": "X val"}],
        )
        def handler(**kwargs) -> dict:
            return {"success": True}

        tool = get_llm_tools()[0]
        assert tool["type"] == "function"
        fn = tool["function"]
        assert fn["name"] == "test_foo"  # underscore format
        assert fn["description"] == "Foo tool"
        assert "parameters" in fn

    def test_underscore_names(self) -> None:
        """Tool names use underscores for OpenAI (dots are not allowed)."""
        @llm_tool(name="domain.verb.sub", description="Sub tool")
        def handler(**kwargs) -> dict:
            return {"success": True}

        fn = get_llm_tools()[0]["function"]
        assert fn["name"] == "domain_verb_sub"

    def test_empty_registry(self) -> None:
        _clear_registry()
        assert get_llm_tools() == []


# ── Dispatch ─────────────────────────────────────────────────────────────────


class TestDispatchLlmTool:
    """dispatch_llm_tool() error handling."""

    def setup_method(self) -> None:
        _clear_registry()

    def teardown_method(self) -> None:
        _clear_registry()

    def test_known_tool(self) -> None:
        @llm_tool(name="test.echo", description="Echo")
        def handler(**kwargs) -> dict:
            return {"success": True, "data": kwargs}

        result = dispatch_llm_tool("test.echo", {"msg": "hi"})
        assert result["success"] is True
        assert result["data"]["msg"] == "hi"

    def test_unknown_tool(self) -> None:
        result = dispatch_llm_tool("nonexistent", {})
        assert result["success"] is False
        assert "Unknown" in result["error"]

    def test_handler_exception(self) -> None:
        @llm_tool(name="test.crash", description="Crashes")
        def handler(**kwargs) -> dict:
            raise RuntimeError("boom")

        result = dispatch_llm_tool("test.crash", {})
        assert result["success"] is False
        assert "boom" in result["error"]


# ── Permission ────────────────────────────────────────────────────────────────


class TestGetLlmToolLevel:
    """get_llm_tool_level() permission callback."""

    def setup_method(self) -> None:
        _clear_registry()

    def teardown_method(self) -> None:
        _clear_registry()

    def test_known_tool_returns_level(self) -> None:
        @llm_tool(name="test.perm", description="Perm", permission_level=PermissionLevel.WRITE)
        def handler(**kwargs) -> dict:
            return {"success": True}

        assert get_llm_tool_level("test.perm") == PermissionLevel.WRITE

    def test_unknown_tool_returns_none(self) -> None:
        assert get_llm_tool_level("nonexistent") is None


# ── Query helpers ────────────────────────────────────────────────────────────


class TestQueryHelpers:
    """is_llm_tool(), get_llm_tool_names(), get_llm_tool_metadata()."""

    def setup_method(self) -> None:
        _clear_registry()

    def teardown_method(self) -> None:
        _clear_registry()

    def test_is_llm_tool(self) -> None:
        @llm_tool(name="test.check", description="Check")
        def handler(**kwargs) -> dict:
            return {"success": True}

        assert is_llm_tool("test.check")
        assert not is_llm_tool("nonexistent")

    def test_get_llm_tool_names_sorted(self) -> None:
        @llm_tool(name="beta.second", description="Second")
        def h2(**kwargs) -> dict:
            return {"success": True}

        @llm_tool(name="alpha.first", description="First")
        def h1(**kwargs) -> dict:
            return {"success": True}

        names = get_llm_tool_names()
        assert names == ["alpha.first", "beta.second"]

    def test_get_llm_tool_metadata_known(self) -> None:
        @llm_tool(
            name="test.meta",
            description="Meta test",
            params=[{"name": "x", "type": "string", "description": "X"}],
            permission_level=PermissionLevel.READ,
        )
        def handler(**kwargs) -> dict:
            return {"success": True}

        meta = get_llm_tool_metadata("test.meta")
        assert meta is not None
        assert meta["description"] == "Meta test"
        assert meta["name"] == "test_meta"
        assert meta["permission_level"] == PermissionLevel.READ
        assert "handler" in meta

    def test_get_llm_tool_metadata_unknown(self) -> None:
        assert get_llm_tool_metadata("nonexistent") is None


# ── Import from lightercore.llm parent ───────────────────────────────────────


class TestParentReExports:
    """Verify re-exports from lightercore.llm.__init__ work."""

    def test_can_import_from_parent(self) -> None:
        from lightercore.llm import llm_tool as parent_llm_tool
        from lightercore.llm import get_llm_tools as parent_get_tools

        # Verify they're the same functions
        assert parent_llm_tool is llm_tool
        assert parent_get_tools is get_llm_tools



