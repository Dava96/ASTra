from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """Represents a chat message, matching OpenAI schema."""
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict, excluding None fields to keep payloads clean."""
        return self.model_dump(exclude_none=True)


class LLMResponse(BaseModel):
    """Response from an LLM call."""
    content: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    finish_reason: str | None = None
    tool_calls: list[dict] | None = None


class TokenUsage(BaseModel):
    """Accumulated token usage for a task."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0

    def add(self, response: LLMResponse) -> None:
        """Add tokens from a response."""
        self.prompt_tokens += response.prompt_tokens
        self.completion_tokens += response.completion_tokens
        self.total_tokens += response.total_tokens
        self.calls += 1


class LLM(ABC):
    """Abstract LLM interface."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict] | None = None
    ) -> LLMResponse:
        """Send a chat completion request."""
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.0
    ):
        """Stream a chat completion response."""
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get the current model name."""
        pass

    @abstractmethod
    def get_context_limit(self) -> int:
        """Get the model's context window size."""
        pass
