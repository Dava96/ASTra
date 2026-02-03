"""Browser console output parser."""

import re

from astra.tools.diagnostic.base import OutputParser
from astra.tools.diagnostic.models import ParsedError, TestResult
from astra.tools.diagnostic.suggestions import get_suggestion


def _register_browser_parser(cls):
    """Delayed registration to avoid circular import."""
    from astra.tools.diagnostic.registry import register_parser
    return register_parser(cls)


@_register_browser_parser
class BrowserConsoleParser(OutputParser):
    """Parser for browser console output (Chrome DevTools, etc.)."""

    name = "browser"
    patterns = [
        "Uncaught",
        "console.error",
        "TypeError:",
        "ReferenceError:",
        "SyntaxError:",
        "[ERROR]",
        "at http://",
        "at https://",
    ]

    # Combined single-pass regex
    # Capture groups:
    # 1. prefix (optional)
    # 2. type (optional)
    # 3. message (required)
    # Modified to allow spaced optional groups and leading whitespace
    ERROR_REGEX = re.compile(
        r"^\s*(?:(?P<prefix>Uncaught|console\.error[:\(]|\[ERROR\])\s*)?" # Optional Prefix
        r"(?:(?P<type>\w+Error):\s*)?"                                    # Optional Type
        r"(?P<message>.+)",                                               # Message
        re.MULTILINE
    )

    STACK_REGEX = re.compile(
        r"(?:at\s+.+?\s+\()?(?:https?://[^/]+)?(?P<file>/[^:]+):(?P<line>\d+):(?P<col>\d+)",
        re.IGNORECASE
    )

    def parse(self, output: str) -> TestResult:
        """Parse browser console output into structured result."""
        result = TestResult(framework="browser")

        for match in self.ERROR_REGEX.finditer(output):
            prefix = match.group("prefix")
            err_type = match.group("type")
            message = match.group("message")

            # Filter out non-errors if needed, or simple debug logs
            # For now, if it matches our strictly defined prefixes or ends in Error, take it
            if not (prefix or err_type):
                continue

            result.failed += 1

            final_type = err_type or (prefix.strip() if prefix else "Error")
            final_type = final_type.replace(":", "").replace("(", "") # clean up

            error = ParsedError(
                error_type=final_type,
                message=message.strip()[:200],
                suggestion=get_suggestion(f"{final_type}: {message}")
            )

            # Look ahead for stack trace in immediate context (next 500 chars)
            start_idx = match.end()
            context = output[start_idx:start_idx+500]
            stack_match = self.STACK_REGEX.search(context)

            if stack_match:
                error.file = stack_match.group("file")
                error.line = int(stack_match.group("line"))
                error.column = int(stack_match.group("col"))

            result.failures.append(error)

        result.total = result.failed
        return result
