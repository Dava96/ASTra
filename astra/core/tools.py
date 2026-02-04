"""Tool interface and registry for agentic capabilities."""

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class Tool(Protocol):
    """Protocol that all agent tools must implement."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for parameters

    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with given arguments."""
        ...


class BaseTool:
    """Helper base class for tools."""

    name: str
    description: str
    parameters: dict[str, Any]

    async def execute(self, **kwargs: Any) -> Any:
        raise NotImplementedError


class ToolRegistry:
    """Registry for managing available tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a new tool."""
        if tool.name in self._tools:
            logger.warning(f"Overwriting existing tool: {tool.name}")
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get JSON schema definitions for all tools (for LLM)."""
        definitions = []
        for tool in self._tools.values():
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return definitions
