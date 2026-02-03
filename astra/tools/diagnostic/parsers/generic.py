"""Generic parser for unstructured output."""

import logging
import re

from astra.tools.diagnostic.base import OutputParser
from astra.tools.diagnostic.models import ParsedError, TestResult
from astra.tools.diagnostic.suggestions import get_suggestion

logger = logging.getLogger(__name__)


def _register_generic_parser(cls):
    """Delayed registration."""
    from astra.tools.diagnostic.registry import register_parser
    return register_parser(cls)


@_register_generic_parser
class GenericParser(OutputParser):
    """Fallback parser for unstructured logs."""

    name = "generic"
    patterns = []  # Fallback, no specific patterns for detection

    # Pre-compiled regex for single-pass scanning
    # Captures: ErrorType: Message
    ERROR_REGEX = re.compile(
        r"^(?P<type>[\w\.]*Error|Exception|Fail|Fatal|Crit(?:ical)?):\s*(?P<message>.+)$",
        re.MULTILINE | re.IGNORECASE
    )

    def parse(self, output: str) -> TestResult:
        """Parse unstructured output."""
        result = TestResult(framework="generic")

        # Single-pass scan for errors
        for match in self.ERROR_REGEX.finditer(output):
            error_type = match.group("type")
            message = match.group("message").strip()

            # Skip if it looks like a summary line "Fail: 0"
            if re.match(r"^\d+$", message):
                continue

            result.failed += 1
            result.failures.append(ParsedError(
                error_type=error_type,
                message=message,
                suggestion=get_suggestion(f"{error_type}: {message}")
            ))

        # Attempt to find summary counts if they exist
        # "X passed, Y failed"
        summary_passed = re.search(r"(\d+)\s*(?:tests?)?\s*passed", output, re.IGNORECASE)
        summary_failed = re.search(r"(\d+)\s*(?:tests?)?\s*failed", output, re.IGNORECASE)

        if summary_passed:
            result.passed = int(summary_passed.group(1))
        if summary_failed:
            # If we found explicit failures but no summary, use count
            # If we found summary, use summary
            cnt = int(summary_failed.group(1))
            result.failed = max(result.failed, cnt)

        result.total = result.passed + result.failed

        # If no explicit failures found but text contains "fail",
        # increment failed count (legacy behavior)
        if result.failed == 0 and "fail" in output.lower():
            result.failed = output.lower().count("fail")
            # Don't double count if we have "passed" count which implies structured output
            if not summary_passed:
                result.passed = output.lower().count("pass")

        return result
