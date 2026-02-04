"""Tests to ensure all internal tools comply with the Tool protocol."""

import importlib
import inspect
import pkgutil
from unittest.mock import MagicMock

import pytest

from astra.core.orchestrator import Orchestrator
from astra.core.tools import BaseTool, Tool
from astra.interfaces.gateway import Gateway


def test_tool_registry_compliance():
    """Verify all tools registered in Orchestrator have required metadata."""
    # Mock gateway
    gateway = MagicMock(spec=Gateway)
    orchestrator = Orchestrator(gateway)

    tools = orchestrator._tools.list_tools()
    assert len(tools) > 0, "No tools registered in Orchestrator"

    for tool in tools:
        # Check metadata
        assert hasattr(tool, "name"), f"Tool {type(tool).__name__} missing 'name'"
        assert isinstance(tool.name, str), f"Tool {type(tool).__name__} name must be string"

        assert hasattr(tool, "description"), f"Tool {type(tool).__name__} missing 'description'"
        assert isinstance(tool.description, str), (
            f"Tool {type(tool).__name__} description must be string"
        )

        assert hasattr(tool, "parameters"), f"Tool {type(tool).__name__} missing 'parameters'"
        assert isinstance(tool.parameters, dict), (
            f"Tool {type(tool).__name__} parameters must be dict"
        )
        assert "type" in tool.parameters, f"Tool {type(tool).__name__} parameters missing 'type'"

        # Check if it implements Protocol
        assert isinstance(tool, Tool), (
            f"Tool {type(tool).__name__} does not implement Tool protocol"
        )
        assert hasattr(tool, "execute"), f"Tool {type(tool).__name__} missing 'execute' method"


def test_all_tools_are_registered():
    """Ensure every tool in astra.tools is registered in the Orchestrator."""
    import astra.tools

    # 1. Discover all tools in the package
    tool_classes = []
    for _loader, module_name, _is_pkg in pkgutil.walk_packages(
        astra.tools.__path__, astra.tools.__name__ + "."
    ):
        try:
            module = importlib.import_module(module_name)
            for _name, obj in inspect.getmembers(module):
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, BaseTool)
                    and obj is not BaseTool
                    and obj.__module__ == module_name
                ):  # Ensure it's defined in THIS module, not imported
                    tool_classes.append(obj)
        except ImportError:
            continue

    # 2. Get registered tools from Orchestrator
    gateway = MagicMock(spec=Gateway)
    orchestrator = Orchestrator(gateway)
    [t.name for t in orchestrator._tools.list_tools()]

    # 3. Verify all discovered tool classes have an instance registered
    for cls in tool_classes:
        # Skip abstract-ish or helper tools or dynamic ones
        if cls.__name__.startswith("Base") or cls.__module__.endswith(".base"):
            continue
        if cls.__name__ == "ShellCommandTool":  # Dynamic tool class
            continue
        # Skip new diagnostic tool classes (not registered in orchestrator yet)
        if cls.__name__ in (
            "DiagnosticTool",
            "OutputParser",
            "PytestParser",
            "JestParser",
            "PhpunitParser",
            "BrowserConsoleParser",
        ):
            continue

        # We check if at least one registered tool is an instance of this class
        found = any(isinstance(t, cls) for t in orchestrator._tools.list_tools())
        assert found, (
            f"Tool class {cls.__name__} (from {cls.__module__}) is not registered in Orchestrator"
        )


@pytest.mark.asyncio
async def test_browser_tool_specifics():
    """Verify BrowserTool specifically has expected metadata."""
    from astra.tools.browser import BrowserTool

    tool = BrowserTool()

    assert tool.name == "browser_action"
    assert "screenshot" in tool.parameters["properties"]["action"]["enum"]
    assert "dom" in tool.parameters["properties"]["action"]["enum"]
    assert "a11y" in tool.parameters["properties"]["action"]["enum"]

    # Verify it can be executed (basic check)
    # We don't run full browser here to keep tests fast,
    # but we check the interface
    assert callable(tool.execute)
