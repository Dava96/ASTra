"""Tests for custom tool loader."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from astra.tools.custom_loader import (
    ShellCommandTool,
    load_custom_tools,
)


class TestShellCommandTool:
    """Test ShellCommandTool execution."""

    @pytest.fixture
    def echo_tool(self):
        with patch("astra.tools.shell.ShellExecutor._is_allowed", return_value=(True, None)):
            return ShellCommandTool(
            name="echo_test",
            description="Echo a message",
            command="echo {message}",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message to echo"}
                },
                "required": ["message"]
            }
        )

    @pytest.mark.asyncio
    async def test_execute_simple_command(self, echo_tool):
        """Test executing a simple shell command."""
        result = await echo_tool.execute(message="hello world")
        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_execute_with_substitution(self, echo_tool):
        """Test parameter substitution in commands."""
        result = await echo_tool.execute(message="test123")
        assert "test123" in result

    def test_tool_properties(self, echo_tool):
        """Test tool has correct properties."""
        assert echo_tool.name == "echo_test"
        assert echo_tool.description == "Echo a message"
        assert "message" in echo_tool.parameters["properties"]


class TestLoadCustomTools:
    """Test YAML tool loading."""

    @pytest.fixture
    def tools_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_load_valid_yaml(self, tools_dir):
        """Test loading a valid YAML tool definition."""
        yaml_content = """
name: test_tool
description: A test tool
command: echo test
parameters:
  arg1:
    type: string
    description: An argument
    required: true
"""
        (tools_dir / "test.yaml").write_text(yaml_content)

        tools = load_custom_tools(tools_dir)

        assert len(tools) == 1
        assert tools[0].name == "test_tool"
        assert tools[0].description == "A test tool"
        assert "arg1" in tools[0].parameters["properties"]

    def test_load_multiple_tools(self, tools_dir):
        """Test loading multiple YAML files."""
        (tools_dir / "tool1.yaml").write_text("""
name: tool1
description: First tool
command: echo 1
""")
        (tools_dir / "tool2.yaml").write_text("""
name: tool2
description: Second tool
command: echo 2
""")

        tools = load_custom_tools(tools_dir)

        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"tool1", "tool2"}

    def test_skip_invalid_yaml(self, tools_dir):
        """Test that invalid YAML files are skipped."""
        (tools_dir / "invalid.yaml").write_text("not: valid: yaml: {{{")
        (tools_dir / "valid.yaml").write_text("""
name: valid_tool
description: Valid
command: echo ok
""")

        tools = load_custom_tools(tools_dir)

        assert len(tools) == 1
        assert tools[0].name == "valid_tool"

    def test_skip_missing_fields(self, tools_dir):
        """Test that tools missing required fields are skipped."""
        (tools_dir / "incomplete.yaml").write_text("""
name: incomplete
# Missing description and command
""")

        tools = load_custom_tools(tools_dir)

        assert len(tools) == 0

    def test_empty_directory(self, tools_dir):
        """Test loading from empty directory."""
        tools = load_custom_tools(tools_dir)
        assert len(tools) == 0

    def test_nonexistent_directory(self):
        """Test loading from nonexistent directory."""
        tools = load_custom_tools("/nonexistent/path")
        assert len(tools) == 0
