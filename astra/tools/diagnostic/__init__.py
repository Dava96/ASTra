"""Diagnostic tool package with parser registry.

This package provides a modular diagnostic tool for parsing test output
and errors from various frameworks (pytest, jest, phpunit, browser console).

Usage:
    from astra.tools.diagnostic import DiagnosticTool, parse_test_output

    # Auto-detect and parse
    result = parse_test_output(output)

    # Or use specified parser
    result = parse_test_output(output, framework="pytest")
"""

from astra.tools.diagnostic.models import ParsedError, TestResult
from astra.tools.diagnostic.parsers.jest import JestParser
from astra.tools.diagnostic.parsers.phpunit import PhpunitParser
from astra.tools.diagnostic.parsers.pytest import PytestParser, extract_file_context
from astra.tools.diagnostic.registry import (
    PARSER_REGISTRY,
    auto_detect_parser,
    get_parser,
    parse_test_output,
)
from astra.tools.diagnostic.suggestions import get_suggestion
from astra.tools.diagnostic.tool import DiagnosticTool


# Legacy function shims
def parse_pytest_output(output: str) -> TestResult:
    """Parse pytest output (legacy shim)."""
    return PytestParser().parse(output)


def parse_jest_output(output: str) -> TestResult:
    """Parse Jest output (legacy shim)."""
    return JestParser().parse(output)


def parse_phpunit_output(output: str) -> TestResult:
    """Parse PHPUnit output (legacy shim)."""
    return PhpunitParser().parse(output)


__all__ = [
    # Tool
    "DiagnosticTool",
    # Models
    "ParsedError",
    "TestResult",
    # Registry
    "parse_test_output",
    "get_parser",
    "auto_detect_parser",
    "PARSER_REGISTRY",
    # Suggestions
    "get_suggestion",
    # Utilities
    "extract_file_context",
    # Legacy shims
    "parse_pytest_output",
    "parse_jest_output",
    "parse_phpunit_output",
]
