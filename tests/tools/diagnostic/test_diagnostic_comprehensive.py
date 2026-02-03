from unittest.mock import patch

import pytest

from astra.tools.diagnostic.models import ParsedError, TestResult
from astra.tools.diagnostic.parsers.pytest import PytestParser, extract_file_context
from astra.tools.diagnostic.registry import PARSER_REGISTRY, auto_detect_parser, get_parser
from astra.tools.diagnostic.tool import DiagnosticTool


@pytest.fixture
def clean_registry():
    # Save original state
    original = PARSER_REGISTRY.copy()
    yield
    # Restore
    PARSER_REGISTRY.clear()
    PARSER_REGISTRY.update(original)

@pytest.fixture
def parser():
    return PytestParser()

def test_extract_file_context(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("\n".join([f"line {i}" for i in range(10)]))

    # Valid extraction
    ctx = extract_file_context(str(f), 5, context_lines=2)
    assert "line 4" in ctx
    assert ">>> line 4" in ctx # 0-indexed code logic vs 1-indexed args?
    # PytestParser passes line=5.
    # extract_file_context implementation:
    # start = max(0, line - context_lines - 1)
    # marker = ">>> " if i == line - 1 else "    "
    # So if line=5 is 5th line (1-indexed), index is 4.
    # i == 4 -> ">>> line 4"

    # Invalid file
    assert extract_file_context("nonexistent", 5) == ""

def test_pytest_parser(parser):
    output = """
============================= test session starts ==============================
collected 3 items

tests/test_foo.py .F.                                                     [100%]

=================================== FAILURES ===================================
__________________________________ test_fail ___________________________________
tests/test_foo.py:10: AssertionError
    assert 1 == 2
E   AssertionError: assert 1 == 2
----------------------------- Captured stdout call -----------------------------
Output
=========================== short test summary info ============================
FAILED tests/test_foo.py::test_fail - AssertionError: assert 1 == 2
========================= 1 failed, 2 passed in 0.12s ==========================
    """

    with patch("astra.tools.diagnostic.parsers.pytest.extract_file_context", return_value="context"):
        result = parser.parse(output)

    assert result.framework == "pytest"
    assert result.passed == 2
    assert result.failed == 1
    assert result.total == 3
    assert len(result.failures) == 1

    fail = result.failures[0]
    assert fail.function == "test_fail"
    assert fail.file == "tests/test_foo.py"
    assert fail.line == 10
    assert fail.error_type == "AssertionError"
    assert "assert 1 == 2" in fail.message
    assert fail.code_snippet == "context"

def test_pytest_parser_alternatives(parser):
    # Test alternative summary regex
    output = "10 passed, 5 failed in 0.5s"
    with patch("astra.tools.diagnostic.parsers.pytest.extract_file_context"):
        result = parser.parse(output)
    assert result.passed == 10
    assert result.failed == 5

def test_registry(clean_registry):
    # Register dummy
    class DummyParser:
        name = "dummy"
        patterns = ["dummy pattern"]
        def can_parse(self, o): return "dummy pattern" in o
        def parse(self, o): return TestResult("dummy")

    from astra.tools.diagnostic.registry import register_parser
    register_parser(DummyParser)

    assert "dummy" in PARSER_REGISTRY
    assert get_parser("dummy") is not None

    parser = auto_detect_parser("some dummy pattern logic")
    assert parser is not None
    assert parser.name == "dummy"

    assert auto_detect_parser("unknown") is None

@pytest.mark.asyncio
async def test_diagnostic_tool():
    tool = DiagnosticTool()

    # Mock parse_test_output
    with patch("astra.tools.diagnostic.tool.parse_test_output") as mock_parse:
        res = TestResult("test_fw", passed=1, failed=0)
        mock_parse.return_value = res

        # Default dict
        out = await tool.execute("output")
        assert out["framework"] == "test_fw"

        # Summary
        out = await tool.execute("output", format="summary")
        assert "✅ PASSED" in out

        # Markdown
        with patch("astra.tools.diagnostic.tool.format_diagnostic_context", return_value="MD"):
            out = await tool.execute("output", format="markdown")
            assert out == "MD"

def test_formatter():
    from astra.tools.diagnostic.formatter import format_diagnostic_context
    result = TestResult("pytest", failed=1)
    result.failures.append(ParsedError(
        error_type="Error", message="Msg", file="f.py", line=1,
        code_snippet="code", suggestion="Fix it"
    ))

    md = format_diagnostic_context(result)
    assert "## Test Results" in md
    assert "❌ FAILED" in md
    assert "### Failures" in md
    assert "f.py:1" in md
    assert "Suggestion" in md
    assert "Fix it" in md

def test_registry_fallback(clean_registry):
    from astra.tools.diagnostic.registry import parse_test_output

    # Test unknown framework
    res = parse_test_output("Some output with 2 fails and 1 pass", framework="unknown_fw")
    # Should fall back to regex
    assert res.framework == "generic"
    assert res.failed == 1
    assert res.passed == 1

    # Test explicit known framework
    class MyParser:
        name = "myfw"
        patterns = []
        def parse(self, o): return TestResult("myfw")
    from astra.tools.diagnostic.registry import register_parser
    register_parser(MyParser)

    res = parse_test_output("out", framework="myfw")
    assert res.framework == "myfw"

def test_browser_parser(clean_registry): # Basic coverage for browser parser
    from astra.tools.diagnostic.parsers.browser import BrowserConsoleParser
    parser = BrowserConsoleParser()

    log = """
    console.error: ReferenceError: foo is not defined
        at http://localhost:3000/main.js:10:5
    """
    res = parser.parse(log)
    assert res.framework == "browser"
    # Logic might vary, but ensure no crash
    # Browser parser logic usually looks for stack traces or console.error
    # We can check if it found failures if implemented


