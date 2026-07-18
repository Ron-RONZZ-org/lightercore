"""Shared LLM tool registry — standalone tools for AI consumption.

Provides the :func:`@llm_tool() <llm_tool>` decorator to register tool
handlers with OpenAI-compatible metadata, a :func:`get_llm_tools()`
converter that produces function-calling definitions, a
:func:`dispatch_llm_tool()` for executing handlers by dot-separated path,
a :func:`get_llm_tool_level()` permission callback for
:func:`~lightercore.llm.tool_loop.run_tool_loop`, and a
:func:`get_llm_tool_metadata()` lookup for ``confirm_tool`` dialog
descriptions.

LLM tools use the ``domain.verb`` naming convention (e.g. ``email.find``,
``node.search``) and call domain services **directly** — no CLI flag
parsing, no frontend-shaped response wrapping.  Tools are registered
independently of the CLI command registry; no CLI command uses these exact
dot-paths so there is no collision.

This module is the **canonical source** for the LLM tool infrastructure.
Both lighterbird and semantika import from here and add their own
domain-specific tool files on top.

Usage::

    from lightercore.llm.tools import llm_tool, get_llm_tools

    @llm_tool(
        name="node.search",
        description="Search nodes by ID, label, or FTS text query",
        params=[{"name": "q", "type": "string", "description": "Search query"}],
        permission_level=PermissionLevel.READ,
    )
    def llm_node_search(q: str = "", **kwargs) -> dict:
        ...
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from lightercore.permissions import PermissionLevel

logger = logging.getLogger(__name__)

# ── Registry ──────────────────────────────────────────────────────────────────

_llm_registry: dict[str, dict[str, Any]] = {}
"""Maps dot-separated tool paths (e.g. ``"node.search"``) to their metadata dict.

Each entry has::

    {
        "handler": Callable[..., dict],
        "name": str,          # OpenAI tool name (underscore format)
        "description": str,
        "parameters": dict,   # OpenAI parameters schema
        "permission_level": PermissionLevel,
    }
"""


# ── Decorator ────────────────────────────────────────────────────────────────


def llm_tool(
    name: str,
    description: str,
    params: list[dict] | None = None,
    permission_level: PermissionLevel = PermissionLevel.READ,
) -> Callable:
    """Register a tool handler in the LLM tool registry.

    Args:
        name: Dot-separated tool path (e.g. ``"node.search"``).
            Stored as-is in the registry; the OpenAI function name
            (underscore format) is derived from this by ``get_llm_tools()``.
        description: Human-readable description for the LLM.
        params: List of parameter dicts, each with ``name``, ``type``
            (``"string"``, ``"number"``, ``"boolean"``), ``description``,
            and optionally ``required`` (bool).  Parameters that lack
            ``required`` are treated as optional.
        permission_level: Minimum :class:`~lightercore.permissions.PermissionLevel`
            required to execute.  READ-level tools run without confirmation;
            WRITE (and above) gate behind human-in-the-loop approval.

    Returns:
        The decorator that registers the handler function.

    The decorated function **must** accept ``**kwargs`` and return a dict
    with ``success`` (bool) and either ``data`` or ``error``.
    """
    def decorator(func: Callable[..., dict]) -> Callable:
        _validate_tool_name(name)
        properties: dict[str, dict] = {}
        required: list[str] = []
        for p in (params or []):
            ptype = _map_param_type(p.get("type", "string"))
            prop: dict[str, Any] = {
                "type": ptype,
                "description": p.get("description", ""),
            }
            if p.get("default") is not None:
                prop["default"] = p["default"]
            properties[p["name"]] = prop
            if p.get("required"):
                required.append(p["name"])

        _llm_registry[name] = {
            "handler": func,
            "name": name.replace(".", "_"),  # OpenAI function name uses underscores
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
            "permission_level": permission_level,
        }
        return func

    return decorator


def _validate_tool_name(name: str) -> None:
    """Validate a tool name (dot-separated, lowercase, no leading/trailing dots)."""
    if not name or not name.replace(".", "").isidentifier():
        raise ValueError(
            f"Invalid LLM tool name: {name!r}. "
            "Use dot-separated lowercase identifiers (e.g. 'node.search')."
        )


def _map_param_type(raw: str) -> str:
    """Map simplified param types to JSON Schema types."""
    mapping = {
        "string": "string",
        "number": "number",
        "boolean": "boolean",
        "integer": "integer",
    }
    return mapping.get(raw, "string")


# ── OpenAI-compatible conversions ────────────────────────────────────────────


def get_llm_tools() -> list[dict[str, Any]]:
    """Return all registered LLM tools in OpenAI function-calling format.

    Each tool's ``function.name`` uses underscores (e.g. ``"node_search"``)
    so that :func:`~lightercore.llm.tool_loop.tc_path` correctly converts
    it back to the dot-separated path (``"node.search"``).

    Returns:
        List of ``{"type": "function", "function": {...}}`` dicts.
    """
    tools: list[dict[str, Any]] = []
    for path, entry in _llm_registry.items():
        tools.append({
            "type": "function",
            "function": {
                "name": entry["name"],  # underscore format
                "description": entry["description"],
                "parameters": entry["parameters"],
            },
        })
    return tools


# ── Dispatch ─────────────────────────────────────────────────────────────────


def dispatch_llm_tool(path: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Execute an LLM tool by its dot-separated path.

    Looks up the tool in the LLM registry (NOT the CLI command registry)
    and calls its handler with the provided keyword arguments.

    Args:
        path: Dot-separated tool path (e.g. ``"node.search"``).
        kwargs: Keyword arguments to pass to the handler.

    Returns:
        ``{"success": True, "data": ...}`` on success, or
        ``{"success": False, "error": "..."}`` on failure.
    """
    entry = _llm_registry.get(path)
    if not entry:
        return {"success": False, "error": f"Unknown LLM tool: {path}"}

    handler = entry["handler"]
    try:
        return handler(**kwargs)
    except Exception as exc:
        logger.exception("LLM tool %s failed: %s", path, exc)
        return {"success": False, "error": str(exc)}


# ── Permission callback ──────────────────────────────────────────────────────


def get_llm_tool_level(path: str) -> PermissionLevel | None:
    """Get the :class:`~lightercore.permissions.PermissionLevel` for an LLM tool.

    This function is designed to be passed as the ``get_tool_level_fn``
    callback to :func:`~lightercore.llm.tool_loop.run_tool_loop` and
    :func:`~lightercore.llm.tool_loop.resume_execution`.

    Args:
        path: Dot-separated tool path (e.g. ``"node.search"``).

    Returns:
        The permission level, or ``None`` if the tool is unknown
        (treated as READ-level by the tool loop).
    """
    entry = _llm_registry.get(path)
    if entry:
        return entry["permission_level"]
    return None


# ── Query helpers ────────────────────────────────────────────────────────────


def get_llm_tool_names() -> list[str]:
    """Return a sorted list of all registered dot-path tool names."""
    return sorted(_llm_registry.keys())


def is_llm_tool(path: str) -> bool:
    """Check if a dot-separated path is a registered LLM tool."""
    return path in _llm_registry


def get_llm_tool_metadata(path: str) -> dict | None:
    """Return the metadata dict for a registered LLM tool, or ``None``.

    The returned dict has the same structure as the registry entry
    (``handler``, ``name``, ``description``, ``parameters``,
    ``permission_level``).  This is useful for the chat endpoint's
    combined metadata lookup when populating ``confirm_tool`` dialogs.

    Args:
        path: Dot-separated tool path (e.g. ``"node.search"``).

    Returns:
        The registry entry dict, or ``None`` if *path* is not registered.
    """
    return _llm_registry.get(path)


__all__ = [
    "_llm_registry",
    "dispatch_llm_tool",
    "get_llm_tool_level",
    "get_llm_tool_metadata",
    "get_llm_tool_names",
    "get_llm_tools",
    "is_llm_tool",
    "llm_tool",
]
