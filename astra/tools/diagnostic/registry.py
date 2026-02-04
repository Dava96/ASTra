"""Parser registry for auto-detection and extension."""

import logging

from astra.tools.diagnostic.base import OutputParser
from astra.tools.diagnostic.models import TestResult

logger = logging.getLogger(__name__)

# Global registry of parsers
PARSER_REGISTRY: dict[str, type[OutputParser]] = {}


def register_parser(cls: type[OutputParser]) -> type[OutputParser]:
    """Decorator to register a parser class.

    Usage:
        @register_parser
        class MyParser(OutputParser):
            name = "myparser"
            patterns = ["myframework"]
    """
    if not cls.name:
        raise ValueError(f"Parser {cls.__name__} must define a 'name' attribute")

    PARSER_REGISTRY[cls.name] = cls
    logger.debug(f"Registered parser: {cls.name}")
    return cls


def get_parser(name: str) -> OutputParser | None:
    """Get a parser instance by name."""
    parser_cls = PARSER_REGISTRY.get(name)
    if parser_cls:
        return parser_cls()
    return None


def auto_detect_parser(output: str, hints: list[str] | None = None) -> OutputParser | None:
    """Auto-detect the appropriate parser for the given output.

    Performance:
        - Only scans the first and last 2KB of output (O(1)).
        - Returns early on first match.
        - Prioritizes hinted parsers (from manifest).
    """
    # Optimization: Bound the search space
    # Most framework markers are in the header or footer
    snippet = output
    if len(output) > 4096:
        snippet = output[:2048] + "\n...\n" + output[-2048:]

    # optimization: check hints first
    parsers_to_check = []

    # 1. Add hinted parsers first
    if hints:
        for hint in hints:
            cls = PARSER_REGISTRY.get(hint)
            if cls:
                parsers_to_check.append(cls)

    # 2. Add remaining parsers
    for name, cls in PARSER_REGISTRY.items():
        if name != "generic" and cls not in parsers_to_check:
            parsers_to_check.append(cls)

    for parser_cls in parsers_to_check:
        parser = parser_cls()
        if parser.can_parse(snippet):
            logger.debug(f"Auto-detected parser: {parser.name}")
            return parser
    return None


def parse_test_output(
    output: str, framework: str | None = None, hints: list[str] | None = None
) -> TestResult:
    """Parse test output using auto-detection or specified framework.

    Args:
        output: Raw test output string
        framework: Optional framework name to force usage
        hints: Optional list of framework names to prioritize during auto-detection

    Returns:
        TestResult with parsed information
    """
    if framework:
        parser = get_parser(framework.lower())
        if parser:
            return parser.parse(output)
        logger.warning(f"Unknown framework '{framework}', falling back to auto-detect")

    parser = auto_detect_parser(output, hints=hints)
    if parser:
        return parser.parse(output)

    # Fallback: use generic parser
    generic_parser = get_parser("generic")
    if generic_parser:
        return generic_parser.parse(output)

    # Last resort fallback if generic parser somehow missing
    result = TestResult(framework="unknown")
    result.failed = output.lower().count("fail")
    result.passed = output.lower().count("pass")
    result.total = result.passed + result.failed
    return result


# Import parsers to trigger registration
# Order matters: more specific parsers (jest, phpunit) before general ones (pytest)
# This must be at the bottom to avoid circular imports
from astra.tools.diagnostic.parsers import (  # noqa: E402, F401
    browser,
    generic,
    jest,
    phpunit,
    pytest,
)
