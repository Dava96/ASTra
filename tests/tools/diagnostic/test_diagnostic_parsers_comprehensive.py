
from unittest.mock import patch

from astra.tools.diagnostic.parsers.browser import BrowserConsoleParser
from astra.tools.diagnostic.parsers.jest import JestParser
from astra.tools.diagnostic.parsers.phpunit import PhpunitParser
from astra.tools.diagnostic.parsers.pytest import PytestParser, extract_file_context


def test_jest_parser_full():
    parser = JestParser()
    output = """
    FAIL tests/auth.test.js
    ● Authentication › should login correctly
      ReferenceError: x is not defined
      at Object.<anonymous> (tests/auth.test.js:10:20)
    
    Tests: 1 failed, 10 passed, 11 total
    Time: 1.5 s
    """
    results = parser.parse(output)
    assert results.failed == 1
    assert results.failures[0].error_type == "ReferenceError"

def test_phpunit_parser_full():
    parser = PhpunitParser()
    output = """
    1) Tests\\Feature\\ExampleTest::test_basic_test
    Failed asserting that false is true.
    /app/tests/Feature/ExampleTest.php:15
    
    Tests: 10, Failures: 2
    """
    results = parser.parse(output)
    assert results.failed == 2
    assert results.total == 10
    assert len(results.failures) == 1

def test_browser_parser_uncaught():
    parser = BrowserConsoleParser()
    output = """
    Uncaught TypeError: Cannot read property 'x' of null
    at User (http://localhost:3000/main.js:123:45)
    
    console.error: Some random error
    """
    results = parser.parse(output)
    # Check that it caught at least one failure
    assert results.failed >= 1
    assert any(f.error_type in ["TypeError", "Uncaught"] for f in results.failures)

def test_pytest_parser_complex():
    parser = PytestParser()
    output = """
    ============================= FAILURES =============================
    __________________________ test_fail ___________________________
    def test_fail():
    >       assert False
    E       assert False
    tests/test_a.py:10: AssertionError
    
    ========================= 1 failed in 0.1s =========================
    """
    results = parser.parse(output)
    assert results.failed == 1

    # Summary variants (hit lines 64-72)
    res2 = parser.parse("2 failed, 5 passed")
    assert res2.failed == 2
    assert res2.passed == 5

    res3 = parser.parse("10 passed in 1.0s")
    assert res3.passed == 10
    assert res3.duration_seconds == 1.0

def test_pytest_extract_context():
    """Test extract_file_context helper."""
    with patch("astra.tools.diagnostic.parsers.pytest.Path") as mock_path:
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.read_text.return_value = "line1\nline2\nline3\nline4\nline5\nline6"

        ctx = extract_file_context("f.py", 3, context_lines=1)
        assert "line3" in ctx
        assert ">>>" in ctx

        # Test missing file
        mock_path.return_value.exists.return_value = False
        assert extract_file_context("missing.py", 1) == ""

        # Test error path
        mock_path.return_value.exists.side_effect = Exception("access denied")
        assert extract_file_context("error.py", 1) == ""

def test_parsers_empty_input():
    parsers = [JestParser(), PhpunitParser(), BrowserConsoleParser(), PytestParser()]
    for p in parsers:
        res = p.parse("")
        assert res.failures == []
