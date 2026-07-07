"""Tests for lightercore.llm.base — BaseLLMProvider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from lightercore.exceptions import AIError
from lightercore.llm.base import BaseLLMProvider
from lightercore.llm.config import ProviderConfig


# ── Helper ───────────────────────────────────────────────────────────────────


def _config(provider_type: str = "openai", api_key: str = "sk-test", **overrides: object) -> ProviderConfig:
    kwargs = dict(
        provider_type=provider_type,
        api_key=api_key,
        model="gpt-4o",
        temperature=0.7,
        max_tokens=1000,
        base_url="",
    )
    kwargs.update(overrides)
    return ProviderConfig(**kwargs)


# ── BaseLLMProvider init ────────────────────────────────────────────────────


class TestBaseLLMProviderInit:
    def test_init_with_api_key(self) -> None:
        p = BaseLLMProvider(_config(api_key="sk-test"))
        assert p.config.is_available() is True
        assert p.model == "gpt-4o"

    def test_init_ollama_no_key(self) -> None:
        p = BaseLLMProvider(_config(provider_type="ollama", api_key=""))
        assert p.config.is_available() is True

    def test_init_no_key_non_ollama(self) -> None:
        p = BaseLLMProvider(_config(api_key=""))
        assert p.config.is_available() is False

    def test_init_custom_model(self) -> None:
        p = BaseLLMProvider(_config(model="gpt-4o-mini"))
        assert p.model == "gpt-4o-mini"

    def test_init_resolves_base_url(self) -> None:
        p = BaseLLMProvider(_config(provider_type="deepseek", api_key="sk-test"))
        assert "deepseek" in p.base_url

    def test_default_model_by_type(self) -> None:
        p = BaseLLMProvider(_config(provider_type="ollama", api_key="", model=""))
        assert p.model == "llama3.2"


# ── Chat (non-streaming) ────────────────────────────────────────────────────


class TestChat:
    async def test_not_configured_raises(self) -> None:
        p = BaseLLMProvider(_config(api_key=""))
        with pytest.raises(AIError, match="not configured"):
            await p.chat([{"role": "user", "content": "hi"}])

    @patch("httpx.AsyncClient")
    async def test_success(self, mock_client: MagicMock) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = False
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from LLM"}}]
        }

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        p = BaseLLMProvider(_config(api_key="sk-test"))
        result = await p.chat([{"role": "user", "content": "Hi"}])
        assert result == "Hello from LLM"

    @patch("httpx.AsyncClient")
    async def test_api_error_raises(self, mock_client: MagicMock) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = True
        mock_response.status_code = 429
        mock_response.json.return_value = {"error": {"message": "Rate limited"}}

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        p = BaseLLMProvider(_config(api_key="sk-test"))
        with pytest.raises(AIError, match="LLM API error"):
            await p.chat([{"role": "user", "content": "Hi"}])

    @patch("httpx.AsyncClient")
    async def test_empty_choices_raises(self, mock_client: MagicMock) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = False
        mock_response.json.return_value = {"choices": []}

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        p = BaseLLMProvider(_config(api_key="sk-test"))
        with pytest.raises(AIError, match="No response"):
            await p.chat([{"role": "user", "content": "Hi"}])

    @patch("httpx.AsyncClient")
    async def test_deepseek_normalizes_role_type(self, mock_client: MagicMock) -> None:
        """DeepSeek API needs both 'role' and 'type' fields."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = False
        mock_response.json.return_value = {"choices": [{"message": {"content": "OK"}}]}

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        p = BaseLLMProvider(_config(provider_type="deepseek", api_key="sk-test"))
        await p.chat([{"role": "user", "content": "Hi"}])
        call_kwargs = mock_instance.post.call_args[1]
        payload = call_kwargs["json"]
        msg = payload["messages"][0]
        assert msg["role"] == "user"
        assert msg["type"] == "user"


# ── Chat (streaming) ────────────────────────────────────────────────────────


class TestChatStreaming:
    @patch("httpx.AsyncClient")
    async def test_stream_returns_collected_text(self, mock_client_cls: MagicMock) -> None:
        """chat(stream=True) returns an async iterator of tokens."""
        lines = [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            'data: {"choices":[{"delta":{"content":" "}}]}',
            'data: {"choices":[{"delta":{"content":"world"}}]}',
            "data: [DONE]",
        ]

        async def _mock_lines():
            for line in lines:
                yield line

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = False
        mock_response.aiter_lines = _mock_lines

        # stream() returns an async context manager
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_cm.__aexit__.return_value = None

        # AsyncMock for the client (supports await on aclose()),
        # but override stream() to return the context manager directly.
        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_cm)
        mock_client_cls.return_value = mock_client

        p = BaseLLMProvider(_config(api_key="sk-test"))
        result = await p.chat(
            [{"role": "user", "content": "Hi"}],
            stream=True,
        )

        tokens = [tok async for tok in result]  # type: ignore[union-attr]
        assert tokens == ["Hello", " ", "world"]


# ── Command generation (tool-calling path) ──────────────────────────────────


class TestGenerateCommand:
    async def test_not_configured_returns_none(self) -> None:
        p = BaseLLMProvider(_config(api_key=""))
        result = await p.generate_command("list nodes", [])
        assert result is None

    @patch.object(BaseLLMProvider, "chat_with_tools")
    async def test_uses_tools_when_defs_given(
        self, mock_tools: MagicMock
    ) -> None:
        from lightercore.llm.base import ChatResult, ToolCall

        mock_tools.return_value = ChatResult(
            tool_calls=[
                ToolCall(
                    id="call_1",
                    function={
                        "name": "node_list",
                        "arguments": '{}',
                    },
                )
            ],
            finish_reason="tool_calls",
        )
        p = BaseLLMProvider(_config(api_key="sk-test"))
        defs = [{"path": ["node", "list"], "description": "List nodes", "params": [], "flags": []}]
        result = await p.generate_command("list nodes", defs)
        assert result == {"tokens": ["node", "list"], "flags": {}}
        mock_tools.assert_called_once()

    @patch.object(BaseLLMProvider, "chat_with_tools")
    async def test_tool_call_with_flags(self, mock_tools: MagicMock) -> None:
        from lightercore.llm.base import ChatResult, ToolCall

        mock_tools.return_value = ChatResult(
            tool_calls=[
                ToolCall(
                    id="call_2",
                    function={
                        "name": "predicate_search",
                        "arguments": '{"q": "author"}',
                    },
                )
            ],
            finish_reason="tool_calls",
        )
        p = BaseLLMProvider(_config(api_key="sk-test"))
        defs = [{"path": ["predicate", "search"], "description": "Search", "params": [{"name": "q", "type": "string", "required": True}], "flags": []}]
        result = await p.generate_command("search predicates about author", defs)
        assert result == {"tokens": ["predicate", "search"], "flags": {"q": "author"}}

    @patch.object(BaseLLMProvider, "chat_with_tools")
    async def test_empty_defs_falls_back_to_json_prompt(
        self, mock_tools: MagicMock
    ) -> None:
        """When command_defs is empty, uses the legacy JSON-in-prompt path."""
        mock_tools.return_value = None  # should not be called
        with patch.object(BaseLLMProvider, "chat") as mock_chat:
            mock_chat.return_value = '{"tokens": ["node", "list"], "flags": {}}'
            p = BaseLLMProvider(_config(api_key="sk-test"))
            result = await p.generate_command("list nodes", [])
            assert result == {"tokens": ["node", "list"], "flags": {}}
            mock_tools.assert_not_called()
            mock_chat.assert_called_once()

    @patch.object(BaseLLMProvider, "chat_with_tools")
    async def test_ai_error_returns_none(self, mock_tools: MagicMock) -> None:
        from lightercore.exceptions import AIError

        mock_tools.side_effect = AIError("API error")
        p = BaseLLMProvider(_config(api_key="sk-test"))
        result = await p.generate_command("list nodes", [{"path": ["node", "list"], "description": "", "params": [], "flags": []}])
        assert result is None

    @patch.object(BaseLLMProvider, "chat_with_tools")
    async def test_no_tool_call_falls_back_to_parse(
        self, mock_tools: MagicMock
    ) -> None:
        from lightercore.llm.base import ChatResult

        mock_tools.return_value = ChatResult(content='{"tokens": ["node", "list"], "flags": {}}')
        p = BaseLLMProvider(_config(api_key="sk-test"))
        result = await p.generate_command("list nodes", [{"path": ["node", "list"], "description": "", "params": [], "flags": []}])
        assert result == {"tokens": ["node", "list"], "flags": {}}


# ── Tool calling — chat_with_tools ──────────────────────────────────────────


class TestChatWithTools:
    @patch("httpx.AsyncClient")
    async def test_returns_tool_call(self, mock_client_cls: MagicMock) -> None:
        from lightercore.llm.base import ChatResult

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = False
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_abc",
                        "type": "function",
                        "function": {"name": "node_list", "arguments": "{}"},
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client_cls.return_value = mock_instance

        p = BaseLLMProvider(_config(api_key="sk-test"))
        tools = [{"type": "function", "function": {"name": "node_list", "parameters": {"type": "object", "properties": {}}}}]
        result = await p.chat_with_tools(
            [{"role": "user", "content": "list nodes"}],
            tools,
        )
        assert isinstance(result, ChatResult)
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].function["name"] == "node_list"
        assert result.content is None

    @patch("httpx.AsyncClient")
    async def test_returns_text_when_no_tool(self, mock_client_cls: MagicMock) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = False
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "Hello from LLM"},
                "finish_reason": "stop",
            }]
        }

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client_cls.return_value = mock_instance

        p = BaseLLMProvider(_config(api_key="sk-test"))
        result = await p.chat_with_tools(
            [{"role": "user", "content": "hi"}],
            [],
        )
        assert result.content == "Hello from LLM"
        assert result.tool_calls is None

    async def test_not_configured_raises(self) -> None:
        p = BaseLLMProvider(_config(api_key=""))
        with pytest.raises(AIError, match="not configured"):
            await p.chat_with_tools([{"role": "user", "content": "hi"}], [])


# ── Tool format conversion — defs_to_tools & tool_call_to_command ────────────


class TestDefsToTools:
    def test_converts_params_and_flags(self) -> None:
        from lightercore.llm.base import defs_to_tools

        defs = [
            {
                "path": ["node", "add"],
                "description": "Add a node",
                "params": [{"name": "labels", "type": "string", "required": True}],
                "flags": [{"name": "id", "type": "string", "help": "Node ID"}],
            },
        ]
        tools = defs_to_tools(defs)
        assert len(tools) == 1
        fn = tools[0]["function"]
        assert fn["name"] == "node_add"
        assert "labels" in fn["parameters"]["properties"]
        assert fn["parameters"]["required"] == ["labels"]

    def test_empty_defs(self) -> None:
        from lightercore.llm.base import defs_to_tools

        assert defs_to_tools([]) == []


class TestToolCallToCommand:
    def test_basic_conversion(self) -> None:
        from lightercore.llm.base import ToolCall, tool_call_to_command

        tc = ToolCall(id="c1", function={"name": "node_list", "arguments": "{}"})
        result = tool_call_to_command(tc)
        assert result == {"tokens": ["node", "list"], "flags": {}}

    def test_with_flags(self) -> None:
        from lightercore.llm.base import ToolCall, tool_call_to_command

        tc = ToolCall(
            id="c2",
            function={"name": "predicate_search", "arguments": '{"q": "author"}'},
        )
        result = tool_call_to_command(tc)
        assert result["tokens"] == ["predicate", "search"]
        assert result["flags"] == {"q": "author"}

    def test_invalid_args_returns_empty_flags(self) -> None:
        from lightercore.llm.base import ToolCall, tool_call_to_command

        tc = ToolCall(id="c3", function={"name": "node_list", "arguments": "not-json"})
        result = tool_call_to_command(tc)
        assert result["flags"] == {}


# ── Hook overrides ──────────────────────────────────────────────────────────


class TestHooks:
    def test_default_model_by_type(self) -> None:
        class CustomProvider(BaseLLMProvider):
            def _default_model(self) -> str:  # noqa: PLR6301
                return "custom-model"

        p = CustomProvider(_config(model=""))
        assert p.model == "custom-model"

    def test_command_system_prompt_override(self) -> None:
        class CustomProvider(BaseLLMProvider):
            def _command_system_prompt(self, defs_text: str) -> str:
                return f"DOMAIN-SPECIFIC:\n{defs_text}"

        p = CustomProvider(_config(api_key="sk-test", model=""))
        prompt = p._command_system_prompt('[{"name": "test"}]')
        assert "DOMAIN-SPECIFIC" in prompt
        assert "test" in prompt
