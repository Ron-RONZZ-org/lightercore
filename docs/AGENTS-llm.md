# AGENTS-llm.md — LLM Module Agent Instructions

## Summary

The `lightercore.llm` subpackage provides shared LLM infrastructure consumed by both **lighterbird** and **semantika**. It includes provider configuration, keyring-based persistence, named profile management, a unified chat/command-generation base class, and utility functions.

## Module Structure

| File | Responsibility |
|------|----------------|
| `config.py` | `ProviderConfig` (unopinionated dataclass), `keyring_set/get/delete` (graceful degradation), `save/load/clear_active_config` |
| `profiles.py` | `ProfileManager(service_name)` — keyring-backed named LLM profile CRUD |
| `protocol.py` | `LLMProvider` Protocol — optional duck-type interface for provider implementations |
| `base.py` | `BaseLLMProvider` — shared HTTP-based chat and command generation with hook methods for subclassing |
| `tool_loop.py` | `run_tool_loop()` / `resume_execution()` — multi-round tool-calling loop with HITL confirmation gating (READ/WRITE/DESTRUCTIVE); supports optional `get_tool_level_fn` callback for LLM-tool permission resolution outside the CLI registry |
| `utils.py` | `resolve_base_url()`, `parse_command_result()`, `build_messages()`, `normalize_messages()`, `validate_base_url()`, `response_error_detail()` |
| `system_prompt.py` | `SystemPromptManager(directory, filename)` — file-based user-editable system prompt with auto-seed |

## Design Decisions

### ProviderConfig is unopinionated
- `provider_type` defaults to `""` (empty string), not to `"openai"` or `"deepseek"`
- No `__post_init__` or automatic URL/model resolution
- Each application provides its own defaults at the factory level

### Error handling raises AIError
- `BaseLLMProvider.chat()` raises `lightercore.exceptions.AIError` on failure
- Never swallows errors or returns user-facing strings
- Route layers catch AIError and format appropriate user responses

### Streaming returns AsyncIterator[str]
- `chat(stream=True)` returns an async generator of token strings
- Follows lighterbird's pattern over semantika's "collect all" approach
- `chat(stream=False)` returns a plain `str`

### Command parsing fallback order
1. JSON (bare or markdown-fenced)
2. Backtick-wrapped `!command` (unambiguous, lighterbird-style)
3. Bare `!command` in text (permissive, semantika-style)

### DeepSeek compatibility
- `normalize_messages()` adds both `role` and `type` keys to each message
- Adopted from lighterbird where it was proven necessary

## Subclassing BaseLLMProvider

```python
from lightercore.llm import BaseLLMProvider, ProviderConfig

class MyProvider(BaseLLMProvider):
    def _default_model(self) -> str:
        return "my-default-model"

    def _command_system_prompt(self, defs_text: str) -> str:
        return f"You are MyApp.\\n{defs_text}"
```

Override `_command_system_prompt()` to inject domain-specific prompt content for `generate_command()`. Override `_default_model()` to change the fallback model name.

## Usage in Applications

### semantika
- `LLMProvider(BaseLLMProvider)` extends BaseLLMProvider, adds config/profile persistence via `ProfileManager("semantika-llm")`
- Singleton pattern via `get_provider()` / `reset_provider()`

### lighterbird (future)
- `OpenAICompatibleProvider` and `OllamaProvider` will import `ProviderConfig` from lightercore
- Profile management will use `ProfileManager("lighterbird-llm")`
