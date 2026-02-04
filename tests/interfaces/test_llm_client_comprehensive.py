from unittest.mock import MagicMock, patch

import pytest

from astra.adapters.llm_client import LiteLLMClient
from astra.interfaces.llm import ChatMessage


@pytest.fixture
def llm_client():
    with patch("astra.adapters.llm_client.get_config") as mock_config:
        # Mock internal config structure
        mock_config.return_value.get.side_effect = (
            lambda *args, **kwargs: "gpt-4" if "model" in args[1] else kwargs.get("default")
        )
        return LiteLLMClient()


@pytest.mark.asyncio
async def test_llm_chat_success(llm_client):
    """Test successful chat completion with acompletion mock."""
    with patch("astra.adapters.llm_client.acompletion") as mock_acompletion:
        mock_res = MagicMock()
        mock_res.choices = [MagicMock()]
        message = MagicMock()
        message.content = "hello"
        message.tool_calls = None
        mock_res.choices[0].message = message
        mock_res.choices[0].finish_reason = "stop"
        mock_res.usage.prompt_tokens = 10
        mock_res.usage.completion_tokens = 5
        mock_res.usage.total_tokens = 15

        mock_acompletion.return_value = mock_res

        messages = [ChatMessage(role="user", content="hi")]
        response = await llm_client.chat(messages)

        assert response.content == "hello"
        assert response.total_tokens == 15
        assert llm_client._usage.total_tokens == 15


@pytest.mark.asyncio
async def test_llm_tool_calls(llm_client):
    """Test chat with tool calls."""
    with patch("astra.adapters.llm_client.acompletion") as mock_acompletion:
        mock_res = MagicMock()
        mock_res.choices = [MagicMock()]
        message = MagicMock()
        message.content = ""

        tool_call = MagicMock()
        tool_call.function.name = "my_tool"
        tool_call.function.arguments = '{"a": 1}'
        tool_call.id = "tc1"
        tool_call.type = "function"

        message.tool_calls = [tool_call]
        mock_res.choices[0].message = message
        mock_res.choices[0].finish_reason = "tool_calls"
        mock_res.usage.prompt_tokens = 20
        mock_res.usage.completion_tokens = 10
        mock_res.usage.total_tokens = 30

        mock_acompletion.return_value = mock_res

        response = await llm_client.chat([], tools=[{"name": "my_tool"}])
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["function"]["name"] == "my_tool"


def test_llm_specialized_clients(llm_client):
    """Test specialized client wrappers."""
    p_client = LiteLLMClient.for_planning()
    assert p_client._purpose == "planning"

    e_client = LiteLLMClient.for_coding()
    assert e_client._purpose == "coding"


@pytest.mark.asyncio
async def test_llm_chat_failure(llm_client):
    """Test chat failure handling."""
    with patch(
        "astra.adapters.llm_client.acompletion", side_effect=Exception("API Error")
    ), pytest.raises(Exception, match="API Error"):
        await llm_client.chat([ChatMessage(role="user", content="hi")])


@pytest.mark.asyncio
async def test_llm_chat_stream(llm_client):
    """Test streaming completion."""
    with patch("astra.adapters.llm_client.acompletion") as mock_acompletion:

        async def mock_gen():
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="part1"))])
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="part2"))])

        mock_acompletion.return_value = mock_gen()

        parts = []
        async for chunk in llm_client.chat_stream([ChatMessage(role="user", content="hi")]):
            parts.append(chunk)

        assert parts == ["part1", "part2"]
