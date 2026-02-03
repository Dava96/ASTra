"""Tests for lint tool."""

from unittest.mock import MagicMock, patch

import pytest

from astra.tools.lint import (
    LintIssue,
    LintResult,
    LintTool,
    detect_language,
    parse_eslint_output,
    parse_mypy_output,
    parse_ruff_output,
)


class TestLanguageDetection:
    """Test project language detection."""

    def test_detect_typescript(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        (tmp_path / "package.json").write_text("{}")

        assert detect_language(tmp_path) == "typescript"

    def test_detect_javascript(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")

        assert detect_language(tmp_path) == "javascript"

    def test_detect_python(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]")

        assert detect_language(tmp_path) == "python"

    def test_detect_php(self, tmp_path):
        (tmp_path / "composer.json").write_text("{}")

        assert detect_language(tmp_path) == "php"

    def test_detect_go(self, tmp_path):
        (tmp_path / "go.mod").write_text("module test")

        assert detect_language(tmp_path) == "go"

    def test_detect_rust(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]")

        assert detect_language(tmp_path) == "rust"

    def test_detect_unknown(self, tmp_path):
        assert detect_language(tmp_path) is None


class TestRuffParser:
    """Test ruff output parsing."""

    def test_parse_issues(self):
        output = """
src/auth.py:10:5: F401 'os' imported but unused
src/auth.py:15:1: E501 Line too long (120 > 88)
src/utils.py:5:10: W293 blank line contains whitespace
        """

        issues = parse_ruff_output(output)

        assert len(issues) == 3
        assert issues[0].file == "src/auth.py"
        assert issues[0].line == 10
        assert issues[0].code == "F401"
        assert issues[0].severity == "warning"  # F codes are warnings

        assert issues[1].code == "E501"
        assert issues[1].severity == "error"  # E codes are errors

    def test_parse_empty(self):
        issues = parse_ruff_output("")
        assert issues == []


class TestMypyParser:
    """Test mypy output parsing."""

    def test_parse_errors(self):
        output = """
src/auth.py:10: error: Incompatible types in assignment
src/auth.py:15: warning: Unused variable 'x'
        """

        issues = parse_mypy_output(output)

        assert len(issues) == 2
        assert issues[0].file == "src/auth.py"
        assert issues[0].line == 10
        assert issues[0].severity == "error"
        assert "Incompatible types" in issues[0].message


class TestEslintParser:
    """Test eslint output parsing."""

    def test_parse_issues(self):
        output = """
/src/app.js
  10:5  error  Unexpected console statement  no-console
  15:1  warning  Missing semicolon  semi

/src/utils.js
  5:10  error  'foo' is not defined  no-undef
        """

        issues = parse_eslint_output(output)

        assert len(issues) == 3
        assert issues[0].file == "/src/app.js"
        assert issues[0].line == 10
        assert issues[0].code == "no-console"
        assert issues[0].severity == "error"

        assert issues[2].file == "/src/utils.js"


class TestLintResult:
    """Test LintResult dataclass."""

    def test_to_dict(self):
        result = LintResult(
            linter="ruff",
            success=False,
            issues=[
                LintIssue(file="test.py", line=10, code="E501", message="too long")
            ],
            error_count=1,
            warning_count=0
        )

        data = result.to_dict()

        assert data["linter"] == "ruff"
        assert data["success"] is False
        assert len(data["issues"]) == 1


class TestLintTool:
    """Test LintTool class."""

    @pytest.fixture
    def tool(self):
        with patch("astra.tools.linters.tool.get_config") as mock:
            mock.return_value = MagicMock()
            mock.return_value.get.return_value = True
            return LintTool(auto_fix=True)

    def test_init(self, tool):
        assert tool._auto_fix is True

    def test_format_results(self, tool):
        results = [
            LintResult(
                linter="ruff",
                success=True,
                error_count=0,
                warning_count=2
            )
        ]

        formatted = tool.format_results(results)

        assert "ruff" in formatted
        assert "Errors: 0" in formatted
        assert "Warnings: 2" in formatted
