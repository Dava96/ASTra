"""LiteLLM-based LLM client with token accounting."""

import logging
from collections.abc import AsyncGenerator

import litellm
from litellm import acompletion, token_counter

from astra.config import get_config
from astra.interfaces.llm import LLM, ChatMessage, LLMResponse, TokenUsage

logger = logging.getLogger(__name__)

# Suppress LiteLLM's verbose logging
litellm.suppress_debug_info = True


class LiteLLMClient(LLM):
    """LLM client using LiteLLM for unified API access."""

    def __init__(
        self,
        model: str | None = None,
        api_base: str | None = None,
        fallback_model: str | None = None,
        purpose: str = "planning"
    ):
        config = get_config()

        # Support separate planning vs coding vs critic models
        if purpose == "coding":
            config_model = config.get("llm", "coding_model") or config.get("llm", "planning_model")
        elif purpose == "critic":
            config_model = config.get("llm", "critic_model") or config.get("llm", "planning_model")
        else:
            config_model = config.get("llm", "planning_model") or config.llm.model

        self._model = model or config_model
        self._purpose = purpose

        # Support custom base_url (for Open WebUI etc)
        custom_base = config.get("llm", "base_url")
        self._api_base = api_base or custom_base or config.get("llm", "host")

        fallback_config = config.get("orchestration", "fallback_strategy", default={})
        if isinstance(fallback_config, dict):
            self._fallback_model = fallback_model or fallback_config.get("escalation_model")
        else:
            self._fallback_model = fallback_model

        self._context_limit = config.get("llm", "context_limit", default=32000)
        self._usage = TokenUsage()

    @classmethod
    def for_coding(cls) -> "LiteLLMClient":
        """Factory method to get a client configured for coding tasks."""
        return cls(purpose="coding")

    @classmethod
    def for_planning(cls) -> "LiteLLMClient":
        """Factory method to get a client configured for planning tasks."""
        return cls(purpose="planning")

    @classmethod
    def for_critic(cls) -> "LiteLLMClient":
        """Factory method to get a client configured for critiquing plans."""
        return cls(purpose="critic")

    def _format_messages(self, messages: list[ChatMessage]) -> list[dict]:
        """Convert ChatMessages to LiteLLM format."""
        return [m.model_dump(exclude_none=True) for m in messages]

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict] | None = None
    ) -> LLMResponse:
        """Send a chat completion request."""
        formatted = self._format_messages(messages)

        try:
            response = await acompletion(
                model=self._model,
                messages=formatted,
                temperature=temperature,
                max_tokens=max_tokens,
                api_base=self._api_base,
                tools=tools
            )

            # Extract tool calls if present
            tool_calls = None
            msg = response.choices[0].message
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in msg.tool_calls
                ]

            result = LLMResponse(
                content=msg.content,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                model=self._model,
                finish_reason=response.choices[0].finish_reason,
                tool_calls=tool_calls
            )

            self._usage.add(result)
            logger.debug(f"LLM call: {result.prompt_tokens}p + {result.completion_tokens}c = {result.total_tokens}t")

            return result

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.0
    ) -> AsyncGenerator[str, None]:
        """Stream a chat completion response."""
        formatted = self._format_messages(messages)

        try:
            response = await acompletion(
                model=self._model,
                messages=formatted,
                temperature=temperature,
                api_base=self._api_base,
                stream=True
            )

            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"Streaming LLM call failed: {e}")
            raise

    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string."""
        try:
            return token_counter(model=self._model, text=text)
        except Exception:
            # Fallback: rough estimate
            return len(text) // 4

    def get_model_name(self) -> str:
        """Get the current model name."""
        return self._model

    def get_context_limit(self) -> int:
        """Get the model's context window size."""
        return self._context_limit

    def get_usage(self) -> TokenUsage:
        """Get accumulated token usage."""
        return self._usage

    def reset_usage(self) -> None:
        """Reset token usage counter."""
        self._usage = TokenUsage()

    async def chat_with_fallback(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None
    ) -> LLMResponse:
        """Try primary model, fall back to cloud if it fails."""
        try:
            return await self.chat(messages, temperature, max_tokens)
        except Exception as primary_error:
            if self._fallback_model:
                original_model = self._model
                original_api_base = self._api_base
                try:
                    self._model = self._fallback_model
                    self._api_base = None  # Use default for cloud escalation
                    logger.warning(f"Primary model failed, trying fallback: {self._fallback_model}")
                    return await self.chat(messages, temperature, max_tokens)
                finally:
                    self._model = original_model
                    self._api_base = original_api_base
            raise primary_error
