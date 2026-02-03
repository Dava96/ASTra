from unittest.mock import patch

import pytest

from astra.tools.diagnostic.models import TestResult
from astra.tools.diagnostic.tool import DiagnosticTool


@pytest.fixture
def mock_detect_languages():
    with patch("astra.tools.linters.registry.detect_languages") as mock:
        yield mock

@pytest.mark.asyncio
async def test_missing_test_runner_suggestion(mock_detect_languages):
    tool = DiagnosticTool()

    # Simulate a project with Python files but no test output
    manifest = {"root_path": "/tmp/project", "files": ["main.py"], "dependencies": {}}
    mock_detect_languages.return_value = {"python"}

    # Run with empty output (simulating "command not found" or similar)
    result = await tool.execute(output="", framework="unknown", manifest_info=manifest)

    # Usually tool.execute returns dict or TestResult depending on 'format'.
    # Default format is 'dict'.
    assert result["suggestion"] is not None
    assert "uv add --dev pytest" in result["suggestion"]

@pytest.mark.asyncio
async def test_no_suggestion_if_tests_found(mock_detect_languages):
    tool = DiagnosticTool()
    manifest = {"root_path": "/tmp/project", "files": ["main.py"], "dependencies": {"pytest": "^7.0"}}

    with patch("astra.tools.diagnostic.tool.parse_test_output") as mock_parse:
        mock_parse.return_value = TestResult(framework="pytest", failed=1)

        result = await tool.execute(output="failure", framework="auto", manifest_info=manifest)
        assert result.get("suggestion") is None
