from astra.tools.diagnostic import (
    extract_file_context,
    get_suggestion,
    parse_jest_output,
    parse_pytest_output,
    parse_test_output,
)


def test_get_suggestion():
    assert "pip install" in get_suggestion("ImportError: No module named 'requests'")
    assert "brackets" in get_suggestion("SyntaxError: invalid syntax")
    assert "not defined" in get_suggestion("NameError: name 'x' is not defined")
    assert get_suggestion("Unknown error message") == ""


def test_extract_file_context(tmp_path):
    test_file = tmp_path / "code.py"
    test_file.write_text("line1\nline2\nline3\nline4\nline5\n")

    context = extract_file_context(str(test_file), line=3, context_lines=1)
    assert "line2" in context
    assert ">>> line3" in context
    assert "line4" in context

    # Non-existent
    assert extract_file_context("none.py", 1) == ""


def test_parse_pytest_output():
    output = "5 passed, 2 failed in 0.5s\n"
    res = parse_pytest_output(output)
    assert res.passed == 5
    assert res.failed == 2
    assert res.duration_seconds == 0.5

    # Complex output with failures
    complex_output = """
============================= FAILURES =============================
_________________________ test_fail _________________________
tests/t1.py:10: AssertionError
E  assert 1 == 2
    """
    res = parse_pytest_output(complex_output)
    assert len(res.failures) == 1
    assert res.failures[0].function == "test_fail"


def test_parse_jest_output():
    output = "Tests: 1 failed, 10 passed, 11 total\nTime: 5.2s"
    res = parse_jest_output(output)
    assert res.failed == 1
    assert res.passed == 10
    assert res.duration_seconds == 5.2


def test_parse_test_output_detection():
    # Pytest detection - use pytest-specific pattern
    res = parse_test_output("===== collected 5 items =====")
    assert res.framework == "pytest"

    # Jest detection - use jest-specific pattern (Test Suites is Jest-only)
    res = parse_test_output("Test Suites: 1 passed")
    assert res.framework == "jest"

    # Fallback counts still work (Generic Parser)
    res = parse_test_output("random output without framework markers")
    assert res.framework == "generic"
