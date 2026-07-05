"""Cross-cutting permission and confirmation abstraction for LLM command safety.

Provides severity levels and a confirmation protocol that app-level
command dispatchers use to gate destructive LLM-generated operations.

Usage::

    from lightercore.permissions import PermissionLevel, PermissionError, ConfirmationProtocol

    if level >= PermissionLevel.DESTRUCTIVE:
        confirmed = await confirm_ui.confirm(path, description, level)
        if not confirmed:
            raise PermissionError(path, level, caller_level)
"""

from __future__ import annotations

import enum
from typing import Protocol, runtime_checkable

__all__ = [
    "PermissionLevel",
    "PermissionError",
    "ConfirmationProtocol",
]


class PermissionLevel(enum.IntEnum):
    """Severity levels for command permissions.

    Higher value = higher severity. Comparisons use ``>=`` so that
    ``if level >= DESTRUCTIVE`` catches all destructive and above.

    Members:
        READ:         Read-only operations — view, search, stats.
        WRITE:        Mutations — add, update, rename (default).
        DESTRUCTIVE:  Irreversible — delete, purge, reset.
        SYSTEM:       System configuration — backup config, credentials.
    """

    READ = 1
    WRITE = 2
    DESTRUCTIVE = 3
    SYSTEM = 4


class PermissionError(Exception):
    """Raised when a command's permission level exceeds the caller's authority.

    Attributes:
        command_path: Dot-separated command path (e.g. ``"reset"``).
        required:     The minimum :class:`PermissionLevel` required.
        actual:       The caller's effective :class:`PermissionLevel`.
    """

    def __init__(
        self,
        command_path: str,
        required: PermissionLevel,
        actual: PermissionLevel,
        *,
        message: str = "",
    ) -> None:
        self.command_path = command_path
        self.required = required
        self.actual = actual
        if not message:
            message = (
                f"Command '!{command_path}' requires permission level "
                f"{required.name} but caller has {actual.name}."
            )
        super().__init__(message)


@runtime_checkable
class ConfirmationProtocol(Protocol):
    """Protocol/interface for requesting user confirmation.

    Apps implement this to show a modal dialog, CLI prompt, or
    notification. The single method is async to support both
    blocking (CLI input) and non-blocking (modal callback) patterns.

    Example implementation for CLI::

        class CliConfirm:
            async def confirm(self, command_path, description, level):
                print(f"{description}\\nProceed? [y/N] ", end="")
                return input().strip().lower() in ("y", "yes")

    Example for web (FastAPI)::

        class ModalConfirm:
            async def confirm(self, command_path, description, level):
                # Store in a future, resolve on button click
                self._pending = asyncio.get_event_loop().create_future()
                await send_to_frontend({"type": "confirm", ...})
                return await self._pending
    """

    async def confirm(
        self,
        command_path: str,
        description: str,
        level: PermissionLevel,
    ) -> bool:
        """Request user confirmation.  Return ``True`` if confirmed."""
        ...
