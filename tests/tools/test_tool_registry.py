"""Tests for ToolRegistry."""

import pytest

from astra.core.tools import BaseTool, ToolRegistry


class DummyTool(BaseTool):
    name = "dummy"
    description = "A dummy tool"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return "executed"


class TestToolRegistry:
    @pytest.fixture
    def registry(self):
        return ToolRegistry()

    def test_register_and_get(self, registry):
        tool = DummyTool()
        registry.register(tool)

        retrieved = registry.get("dummy")
        assert retrieved == tool
        assert registry.get("missing") is None

    def test_list_tools(self, registry):
        t1 = DummyTool()
        t2 = DummyTool()
        t2.name = "dummy2"

        registry.register(t1)
        registry.register(t2)

        tools = registry.list_tools()
        assert len(tools) == 2
        assert t1 in tools
        assert t2 in tools

    def test_get_definitions(self, registry):
        tool = DummyTool()
        registry.register(tool)

        defs = registry.get_definitions()
        assert len(defs) == 1
        d = defs[0]
        assert d["type"] == "function"
        assert d["function"]["name"] == "dummy"
        assert d["function"]["description"] == "A dummy tool"

    def test_overwrite_warning(self, registry):
        t1 = DummyTool()
        registry.register(t1)

        t2 = DummyTool()
        t2.description = "New desc"
        # Logic allows overwrite but logs warning (not asserted here unless we capture logs)
        registry.register(t2)

        assert registry.get("dummy").description == "New desc"
