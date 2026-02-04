from unittest.mock import MagicMock, patch

import pytest

from astra.tools.linters.models import LintIssue, LintResult
from astra.tools.linters.tool import LintTool


class TestLintIntegration:
    """Integration test for LintTool parallel execution."""

    @pytest.fixture
    def lint_tool(self):
        return LintTool(auto_fix=False)

    def test_parallel_lint_execution(self, lint_tool, tmp_path):
        """Test that multiple linters are called in parallel."""
        # Mock detect_linters to return two fake linters
        linter1 = MagicMock()
        linter1.name = "ruff"
        linter1.is_type_checker = False
        linter1.run.return_value = LintResult(linter="ruff", success=True, error_count=0)

        linter2 = MagicMock()
        linter2.name = "mypy"
        linter2.is_type_checker = True
        linter2.run.return_value = LintResult(linter="mypy", success=True, error_count=0)

        with patch("astra.tools.linters.registry.detect_linters", return_value=[linter1, linter2]):
            # Run linters with type_check=True
            results = lint_tool.run(tmp_path, type_check=True)

            assert len(results) == 2
            # Verify both were run
            linter1.run.assert_called_once()
            linter2.run.assert_called_once()

    def test_lint_result_formatting(self, lint_tool):
        """Test formatting of lint results for LLM context."""
        results = [
            LintResult(
                linter="ruff",
                success=False,
                error_count=2,
                warning_count=1,
                issues=[
                    LintIssue(file="app.py", line=1, column=1, message="unused import", code="F401", severity="error"),
                    LintIssue(file="app.py", line=5, column=1, message="line too long", code="E501", severity="error")
                ]
            ),
            LintResult(
                linter="mypy",
                success=True,
                error_count=0
            )
        ]

        formatted = lint_tool.format_results(results)

        assert "## Lint Results" in formatted
        assert "⚠️ ISSUES FOUND" in formatted
        assert "### ruff" in formatted
        assert "Errors: 2" in formatted
        assert "app.py:1: [F401] unused import" in formatted
        assert "### mypy" in formatted
        assert "✅ PASSED" not in formatted # "Overall" section has it, but per-linter doesn't show PASSED text by default in format_results
        # Wait, let's check format_results logic: it says "Overall: PASSED" if all success.
        # Per linter it just shows name and stats.
        assert "Errors: 0" in formatted

    def test_lint_tool_truncates_many_issues(self, lint_tool):
        """Test that formatting truncates if there are too many issues."""
        issues = [
            LintIssue(file="app.py", line=i, column=1, message=f"error {i}", code="ERR", severity="error")
            for i in range(20)
        ]
        results = [LintResult(linter="ruff", success=False, error_count=20, issues=issues)]

        formatted = lint_tool.format_results(results)

        # Should show 10 issues and then "and 10 more"
        assert "error 0" in formatted
        assert "error 9" in formatted
        assert "error 10" not in formatted
        assert "... and 10 more" in formatted
