from unittest.mock import patch

import pytest

from astra.tools.diagnostic.tool import DiagnosticTool


@pytest.mark.asyncio
class TestDiagnosticIntegration:
    """Integration test for DiagnosticTool with project context hints."""

    @pytest.fixture
    def diagnostic_tool(self):
        return DiagnosticTool()

    async def test_diagnostic_with_manifest_hints_pytest(self, diagnostic_tool):
        """Test that manifest hints guide the parser to pytest."""
        raw_output = "test_foo.py:10: error: expected 1 but got 2"

        # Manifest hints at python/pytest
        manifest_info = {
            "root_path": "/mock/project",
            "files": ["test_foo.py", "app.py"],
            "dependencies": {"pytest": "8.0.0"}
        }

        with patch("astra.tools.diagnostic.tool.parse_test_output") as mock_parse:
            mock_parse.return_value.to_dict.return_value = {"success": False}
            mock_parse.return_value.framework = "pytest"

            await diagnostic_tool.execute(output=raw_output, manifest_info=manifest_info)

            # Verify hints were passed to the registry parser
            mock_parse.assert_called_once()
            args, kwargs = mock_parse.call_args
            assert "pytest" in kwargs["hints"]

    async def test_diagnostic_suggestion_missing_runner(self, diagnostic_tool):
        """Test suggestion when no test runner output is found for detected language."""
        from astra.tools.diagnostic.models import TestResult
        raw_output = "No tests found."

        # Manifest suggests python project
        manifest_info = {
            "root_path": "/mock/project",
            "files": ["app.py", "requirements.txt"]
        }

        # Mock detect_languages to return python
        with patch("astra.tools.linters.registry.detect_languages", return_value=["python"]):
            # Mock parse_test_output to return "unknown" framework with no results
            # Using a real TestResult object instead of a full mock to ensure to_dict() works
            result_obj = TestResult(framework="unknown", total=0, failed=0, passed=0)

            with patch("astra.tools.diagnostic.tool.parse_test_output", return_value=result_obj):
                result = await diagnostic_tool.execute(output=raw_output, manifest_info=manifest_info)

                # Check for suggestion in the result
                assert result.get("suggestion") is not None
                assert "Python project detected but no test runner output found" in result["suggestion"]
                assert "uv add --dev pytest" in result["suggestion"]

    async def test_diagnostic_format_markdown(self, diagnostic_tool):
        """Test markdown formatting integration."""
        # Include markers that PytestParser looks for
        raw_output = "collected 1 item\nFAILED tests/test_core.py::test_init - AssertionError\n======= short test summary info ======="
        manifest_info = {"root_path": "/mock/project"}

        result = await diagnostic_tool.execute(
            output=raw_output,
            manifest_info=manifest_info,
            format="markdown"
        )

        assert isinstance(result, str)
        assert "## Test Results" in result
        assert "pytest" in result.lower()
