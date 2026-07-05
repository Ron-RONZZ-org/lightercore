"""Tests for lightercore.permissions module."""
from __future__ import annotations

import pytest
from lightercore.permissions import ConfirmationProtocol, PermissionError, PermissionLevel


class TestPermissionLevel:
    """Enum ordering and member access."""

    def test_ordering(self) -> None:
        assert PermissionLevel.READ < PermissionLevel.WRITE
        assert PermissionLevel.WRITE < PermissionLevel.DESTRUCTIVE
        assert PermissionLevel.DESTRUCTIVE < PermissionLevel.SYSTEM

    def test_comparison_ge(self) -> None:
        assert PermissionLevel.DESTRUCTIVE >= PermissionLevel.DESTRUCTIVE
        assert PermissionLevel.SYSTEM >= PermissionLevel.DESTRUCTIVE
        assert not (PermissionLevel.WRITE >= PermissionLevel.DESTRUCTIVE)

    def test_int_values(self) -> None:
        assert PermissionLevel.READ.value == 1
        assert PermissionLevel.WRITE.value == 2
        assert PermissionLevel.DESTRUCTIVE.value == 3
        assert PermissionLevel.SYSTEM.value == 4

    def test_from_int(self) -> None:
        assert PermissionLevel(2) == PermissionLevel.WRITE
        assert PermissionLevel(3) == PermissionLevel.DESTRUCTIVE

    def test_member_names(self) -> None:
        names = {m.name for m in PermissionLevel}
        assert names == {"READ", "WRITE", "DESTRUCTIVE", "SYSTEM"}


class TestPermissionError:
    """Exception attributes and message formatting."""

    def test_default_message(self) -> None:
        err = PermissionError("reset", PermissionLevel.DESTRUCTIVE, PermissionLevel.WRITE)
        assert "!reset" in str(err)
        assert "DESTRUCTIVE" in str(err)
        assert "WRITE" in str(err)

    def test_custom_message(self) -> None:
        err = PermissionError("node.delete", PermissionLevel.SYSTEM, PermissionLevel.READ, message="Custom message.")
        assert str(err) == "Custom message."

    def test_attributes(self) -> None:
        err = PermissionError("trash.purge", PermissionLevel.DESTRUCTIVE, PermissionLevel.WRITE)
        assert err.command_path == "trash.purge"
        assert err.required == PermissionLevel.DESTRUCTIVE
        assert err.actual == PermissionLevel.WRITE

    def test_is_exception(self) -> None:
        """PermissionError should be catchable as Exception."""
        err = PermissionError("x", PermissionLevel.READ, PermissionLevel.READ)
        assert isinstance(err, Exception)
        assert isinstance(err, PermissionError)


class TestConfirmationProtocol:
    """Duck-type conformance tests (all synchronous — protocol is interface-only)."""

    def test_runtime_checkable_valid(self) -> None:
        """A class with an async confirm() method satisfies the protocol."""

        class ValidConfirm:
            async def confirm(self, command_path: str, description: str, level: PermissionLevel) -> bool:  # noqa: PLR6301
                return True

        assert isinstance(ValidConfirm(), ConfirmationProtocol)

    def test_runtime_checkable_invalid(self) -> None:
        """A class without confirm() does not satisfy the protocol."""

        class NotAConfirm:
            pass

        assert not isinstance(NotAConfirm(), ConfirmationProtocol)

    def test_confirm_signature_mismatch(self) -> None:
        """A class with confirm() but wrong signature still works at runtime level."""

        class WrongSig:
            def confirm(self, x: int) -> int:  # noqa: PLR6301
                return x

        # runtime_checkable only checks for method existence, not signature
        assert isinstance(WrongSig(), ConfirmationProtocol)
