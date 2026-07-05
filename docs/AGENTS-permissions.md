# AGENTS-permissions.md — Permission Module Agent Instructions

## Summary
`permissions.py` provides a lightweight, framework-agnostic permission/confirmation abstraction for LLM command safety. It is consumed by both semantika and lighterbird to gate destructive commands that originate from the LLM.

## Exported Symbols

| Symbol | Kind | Description |
|--------|------|-------------|
| `PermissionLevel` | `IntEnum` | Severity levels: `READ(1)`, `WRITE(2)`, `DESTRUCTIVE(3)`, `SYSTEM(4)` |
| `PermissionError` | Exception | Raised when a command exceeds the caller's authority |
| `ConfirmationProtocol` | `Protocol` | Async interface for requesting user confirmation |

## Constraints and Invariants
- No imports from lighterbird, semantika, or any web framework
- No new dependencies beyond Python stdlib
- `PermissionLevel.WRITE` is the default — backward compatible with existing behavior
- Check pattern: `if level >= PermissionLevel.DESTRUCTIVE:` — catches all levels above the threshold

## Usage in Downstream Apps

### Tagging commands
```python
@command("reset", permission_level=PermissionLevel.DESTRUCTIVE, ...)
```

### Gate in LLM route
```python
if level >= PermissionLevel.DESTRUCTIVE:
    return {"type": "confirm", "tokens": cmd["tokens"], "flags": cmd["flags"], "message": "..."}
```

### Implementing ConfirmationProtocol
```python
class WebConfirm:
    async def confirm(self, command_path, description, level):
        # Show modal, resolve on button click
        ...
```

## Important Notes
- Do NOT include `permission_level` in command definitions sent to the LLM — it provides no value server-side and adds prompt-injection surface area.
- The permission gate runs **before** `dispatch()`, so handler-level `confirmed` flags are irrelevant for LLM-originated commands.
