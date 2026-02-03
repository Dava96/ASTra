"""Comprehensive tests for LLM client with mocking and edge cases."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.interfaces.llm import ChatMessage, LLMResponse, TokenUsage


class TestChatMessage:
    """Test ChatMessage dataclass."""

    def test_system_message(self):
        msg = ChatMessage(role="system", content="You are a helpful assistant.")
        assert msg.role == "system"
        assert "helpful" in msg.content

    def test_user_message(self):
        msg = ChatMessage(role="user", content="Hello!")
        assert msg.role == "user"

    def test_assistant_message(self):
        msg = ChatMessage(role="assistant", content="Hello! How can I help you?")
        assert msg.role == "assistant"


class TestLLMResponse:
    """Test LLMResponse dataclass."""

    def test_response_fields(self):
        response = LLMResponse(
            content="This is the response",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="gpt-4",
            finish_reason="stop"
        )

        assert response.content == "This is the response"
        assert response.prompt_tokens == 100
        assert response.completion_tokens == 50
        assert response.total_tokens == 150
        assert response.model == "gpt-4"
        assert response.finish_reason == "stop"


class TestTokenUsage:
    """Test TokenUsage tracking."""

    def test_initial_values(self):
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0
        assert usage.calls == 0

    def test_add_single_response(self):
        usage = TokenUsage()
        response = LLMResponse(
            content="test",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="test"
        )

        usage.add(response)

        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
        assert usage.calls == 1

    def test_add_multiple_responses(self):
        usage = TokenUsage()

        for i in range(5):
            response = LLMResponse(
                content=f"test {i}",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                model="test"
            )
            usage.add(response)

        assert usage.prompt_tokens == 500
        assert usage.completion_tokens == 250
        assert usage.total_tokens == 750
        assert usage.calls == 5


class TestLiteLLMClientMocked:
    """Test LLM client with mocked dependencies."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        # Properly mock the nested llm config
        config.llm = MagicMock()
        config.llm.model = "ollama/qwen2.5-coder:7b"
        config.llm.host = "http://localhost:11434"
        config.llm.context_limit = 32000
        config.llm.base_url = None
        config.llm.planning_model = None
        config.llm.coding_model = None

        # Mock the get method for backward compat
        def mock_get(*args, default=None):
            mapping = {
                ("llm", "host"): "http://localhost:11434",
                ("llm", "context_limit"): 32000,
                ("llm", "base_url"): None,
                ("llm", "planning_model"): None,
                ("llm", "coding_model"): None,
                ("orchestration", "fallback_strategy"): {"escalation_model": "gpt-4o"},
                ("orchestration", "fallback_strategy", "escalation_model"): "gpt-4o"
            }
            return mapping.get(args, default)

        config.get = MagicMock(side_effect=mock_get)
        return config

    @pytest.fixture
    def llm_client(self, mock_config):
        with patch('astra.adapters.llm_client.get_config', return_value=mock_config):
            from astra.adapters.llm_client import LiteLLMClient
            return LiteLLMClient()

    def test_client_initialization(self, llm_client):
        """Test client initializes with correct model."""
        assert "qwen" in llm_client._model.lower() or "ollama" in llm_client._model.lower()

    def test_get_model_name(self, llm_client):
        """Test getting model name."""
        name = llm_client.get_model_name()
        assert len(name) > 0

    def test_get_context_limit(self, llm_client):
        """Test getting context limit."""
        limit = llm_client.get_context_limit()
        assert limit == 32000

    def test_format_messages(self, llm_client):
        """Test message formatting."""
        messages = [
            ChatMessage(role="system", content="System prompt"),
            ChatMessage(role="user", content="User message")
        ]

        formatted = llm_client._format_messages(messages)

        assert len(formatted) == 2
        assert formatted[0] == {"role": "system", "content": "System prompt"}
        assert formatted[1] == {"role": "user", "content": "User message"}

    @pytest.mark.asyncio
    async def test_chat_calls_acompletion(self, llm_client):
        """Test that chat method calls LiteLLM acompletion."""
        with patch('astra.adapters.llm_client.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = MagicMock(
                choices=[MagicMock(
                    message=MagicMock(content="Response text"),
                    finish_reason="stop"
                )],
                usage=MagicMock(
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150
                )
            )
            # Ensure mock integers behave like integers
            mock_completion.return_value.usage.prompt_tokens = 100
            mock_completion.return_value.usage.completion_tokens = 50
            mock_completion.return_value.usage.total_tokens = 150

            messages = [ChatMessage(role="user", content="Hello")]
            response = await llm_client.chat(messages)

            assert response.content == "Response text"
            assert response.total_tokens == 150
            mock_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_tracks_usage(self, llm_client):
        """Test that chat accumulates token usage."""
        with patch('astra.adapters.llm_client.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = MagicMock(
                choices=[MagicMock(
                    message=MagicMock(content="Response"),
                    finish_reason="stop"
                )],
                usage=MagicMock(
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150
                )
            )
            mock_completion.return_value.usage.prompt_tokens = 100
            mock_completion.return_value.usage.completion_tokens = 50
            mock_completion.return_value.usage.total_tokens = 150

            messages = [ChatMessage(role="user", content="Hello")]
            await llm_client.chat(messages)
            await llm_client.chat(messages)

            usage = llm_client.get_usage()
            assert usage.calls == 2
            assert usage.total_tokens == 300

    def test_reset_usage(self, llm_client):
        """Test resetting token usage."""
        llm_client._usage = TokenUsage(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            calls=10
        )

        llm_client.reset_usage()

        usage = llm_client.get_usage()
        assert usage.calls == 0
        assert usage.total_tokens == 0


class TestTokenCounting:
    """Test token counting functionality."""

    @pytest.fixture
    def llm_client(self):
        config = MagicMock()
        config.model = "gpt-4"
        config.get = MagicMock(return_value=None)

        with patch('astra.adapters.llm_client.get_config', return_value=config):
            from astra.adapters.llm_client import LiteLLMClient
            return LiteLLMClient()

    def test_count_tokens_short_text(self, llm_client):
        """Test counting tokens in short text."""
        with patch('astra.adapters.llm_client.token_counter', return_value=5):
            count = llm_client.count_tokens("Hello world!")
            assert count == 5

    def test_count_tokens_fallback(self, llm_client):
        """Test fallback when token_counter fails."""
        with patch('astra.adapters.llm_client.token_counter', side_effect=Exception("Failed")):
            count = llm_client.count_tokens("Hello world!")  # 12 chars -> ~3 tokens
            assert count >= 1  # Fallback estimate

    @pytest.mark.parametrize("text,expected_min,expected_max", [
        ("", 0, 1),
        ("a", 0, 2),
        ("Hello, how are you today?", 5, 10),
        ("x" * 1000, 200, 300),  # Long text
    ])
    def test_count_tokens_ranges(self, llm_client, text, expected_min, expected_max):
        """Test token counting for various text lengths."""
        with patch('astra.adapters.llm_client.token_counter', side_effect=Exception("Use fallback")):
            count = llm_client.count_tokens(text)
            # Fallback is len(text) // 4
            expected = len(text) // 4
            assert count == expected


class TestFallbackBehavior:
    """Test fallback to cloud model behavior."""

    @pytest.fixture
    def llm_with_fallback(self):
        config = MagicMock()
        config.model = "ollama/qwen2.5-coder:7b"
        config.get = MagicMock(side_effect=lambda *args, default=None: {
            ("llm", "planning_model"): "ollama/qwen2.5-coder:7b",
            ("llm", "coding_model"): None,
            ("llm", "base_url"): None,
            ("llm", "host"): "http://localhost:11434",
            ("llm", "context_limit"): 32000,
            ("orchestration", "fallback_strategy"): {"escalation_model": "gpt-4o"},
        }.get(args, default))

        with patch('astra.adapters.llm_client.get_config', return_value=config):
            from astra.adapters.llm_client import LiteLLMClient
            return LiteLLMClient()

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self, llm_with_fallback):
        """Test fallback is used when primary model fails."""
        call_count = 0

        async def mock_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Primary model unavailable")
            mock_resp = MagicMock(
                choices=[MagicMock(
                    message=MagicMock(content="Fallback response"),
                    finish_reason="stop"
                )],
                usage=MagicMock(prompt_tokens=50, completion_tokens=25, total_tokens=75)
            )
            mock_resp.usage.prompt_tokens = 50
            mock_resp.usage.completion_tokens = 25
            mock_resp.usage.total_tokens = 75
            return mock_resp

        with patch('astra.adapters.llm_client.acompletion', side_effect=mock_acompletion):
            messages = [ChatMessage(role="user", content="Hello")]
            response = await llm_with_fallback.chat_with_fallback(messages)

            assert response.content == "Fallback response"
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_also_fails(self, llm_with_fallback):
        """Test handling when both primary and fallback fail."""
        with patch('astra.adapters.llm_client.acompletion', new_callable=AsyncMock) as mock:
            mock.side_effect = Exception("All models failed")

            messages = [ChatMessage(role="user", content="Hello")]

            with pytest.raises(Exception, match="All models failed"):
                await llm_with_fallback.chat_with_fallback(messages)


class TestTemperatureSettings:
    """Test temperature parameter handling."""

    @pytest.fixture
    def llm_client(self):
        config = MagicMock()
        config.model = "test-model"
        config.llm = MagicMock()
        config.llm.model = "test-model"
        config.get = MagicMock(return_value=None)

        with patch('astra.adapters.llm_client.get_config', return_value=config):
            from astra.adapters.llm_client import LiteLLMClient
            return LiteLLMClient()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("temperature", [0.0, 0.5, 0.7, 1.0, 1.5, 2.0])
    async def test_temperature_passed_correctly(self, llm_client, temperature):
        """Test that temperature is passed to the API."""
        with patch('astra.adapters.llm_client.acompletion', new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=""), finish_reason="stop")],
                usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            )
            mock.return_value.usage.prompt_tokens = 10
            mock.return_value.usage.completion_tokens = 5
            mock.return_value.usage.total_tokens = 15

            await llm_client.chat([ChatMessage(role="user", content="test")], temperature=temperature)

            call_kwargs = mock.call_args[1]
            assert call_kwargs['temperature'] == temperature


class TestEdgeCases:
    """Edge case tests for LLM client."""

    @pytest.fixture
    def llm_client(self):
        config = MagicMock()
        config.model = "test-model"
        config.llm = MagicMock()
        config.llm.model = "test-model"
        config.get = MagicMock(return_value=None)

        with patch('astra.adapters.llm_client.get_config', return_value=config):
            from astra.adapters.llm_client import LiteLLMClient
            return LiteLLMClient()

    @pytest.mark.asyncio
    async def test_empty_message_list(self, llm_client):
        """Test handling of empty message list."""
        with patch('astra.adapters.llm_client.acompletion', new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=""), finish_reason="stop")],
                usage=MagicMock(prompt_tokens=0, completion_tokens=0, total_tokens=0)
            )
            mock.return_value.usage.prompt_tokens = 0
            mock.return_value.usage.completion_tokens = 0
            mock.return_value.usage.total_tokens = 0

            response = await llm_client.chat([])

            assert response.total_tokens == 0

    @pytest.mark.asyncio
    async def test_very_long_message(self, llm_client):
        """Test handling of very long messages."""
        long_content = "x" * 100000  # 100KB message

        with patch('astra.adapters.llm_client.acompletion', new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Response"), finish_reason="length")],
                usage=MagicMock(prompt_tokens=25000, completion_tokens=100, total_tokens=25100)
            )
            mock.return_value.usage.prompt_tokens = 25000
            mock.return_value.usage.completion_tokens = 100
            mock.return_value.usage.total_tokens = 25100

            response = await llm_client.chat([ChatMessage(role="user", content=long_content)])

            assert response.finish_reason == "length"

    @pytest.mark.asyncio
    async def test_unicode_content(self, llm_client):
        """Test handling of unicode in messages."""
        with patch('astra.adapters.llm_client.acompletion', new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="こんにちは！"), finish_reason="stop")],
                usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            )
            mock.return_value.usage.prompt_tokens = 10
            mock.return_value.usage.completion_tokens = 5
            mock.return_value.usage.total_tokens = 15

            messages = [ChatMessage(role="user", content="こんにちは、世界！")]
            response = await llm_client.chat(messages)

            assert "こんにちは" in response.content
