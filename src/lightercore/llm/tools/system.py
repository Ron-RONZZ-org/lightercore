"""Canonical ``system.now`` tool — shared between lighterbird and semantika.

Provides the LLM with temporal awareness so it can accurately answer
"today", "this week", or date-relative questions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from lightercore.permissions import PermissionLevel
from lightercore.llm.tools import llm_tool


@llm_tool(
    name="system.now",
    description=(
        "Get the current date and time in UTC and the local timezone. "
        "Use this for any temporal reasoning — determining what 'today' "
        "means, filtering by date, scheduling, or interpreting relative "
        "time references from the user."
    ),
    permission_level=PermissionLevel.READ,
)
def llm_system_now(**kwargs) -> dict:
    """Return the current timestamp with UTC and local timezone info."""
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone()
    return {
        "success": True,
        "data": {
            "utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "local": now_local.isoformat(),
            "timezone": str(now_local.tzinfo or "UTC"),
            "iso": now_utc.isoformat(),
            "datetime": now_utc.isoformat(),
            "date": now_utc.strftime("%Y-%m-%d"),
            "weekday": now_utc.strftime("%A"),
        },
    }
