
from unittest.mock import patch

from astra.tools import diagnostic
from astra.tools.diagnostic import parse_jest_output, parse_phpunit_output, parse_pytest_output


def test_diagnostic_shim_exports():
    """Verify that shim re-exports all necessary components."""
    assert hasattr(diagnostic, "ParsedError")
    assert hasattr(diagnostic, "TestResult")
    assert hasattr(diagnostic, "get_suggestion")
    assert hasattr(diagnostic, "extract_file_context")
    assert hasattr(diagnostic, "parse_test_output")
    assert hasattr(diagnostic, "get_parser")
    assert hasattr(diagnostic, "auto_detect_parser")
    assert hasattr(diagnostic, "DiagnosticTool")
    assert hasattr(diagnostic, "PARSER_REGISTRY")

def test_legacy_parse_functions():
    """Test legacy parsing shim functions."""

    # Pytest
    with patch("astra.tools.diagnostic.PytestParser") as MockParser:
        mock_instance = MockParser.return_value
        mock_instance.parse.return_value = "parsed_pytest"

        result = parse_pytest_output("check")
        assert result == "parsed_pytest"
        mock_instance.parse.assert_called_with("check")

    # Jest
    with patch("astra.tools.diagnostic.JestParser") as MockParser:
        mock_instance = MockParser.return_value
        mock_instance.parse.return_value = "parsed_jest"

        result = parse_jest_output("check")
        assert result == "parsed_jest"
        mock_instance.parse.assert_called_with("check")

    # PHPUnit
    with patch("astra.tools.diagnostic.PhpunitParser") as MockParser:
        mock_instance = MockParser.return_value
        mock_instance.parse.return_value = "parsed_phpunit"

        result = parse_phpunit_output("check")
        assert result == "parsed_phpunit"
        mock_instance.parse.assert_called_with("check")
