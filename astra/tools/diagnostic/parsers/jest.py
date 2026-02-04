"""Jest output parser."""

import re

from astra.tools.diagnostic.base import OutputParser
from astra.tools.diagnostic.models import ParsedError, TestResult
from astra.tools.diagnostic.suggestions import get_suggestion


def _register_jest_parser(cls):
    """Delayed registration to avoid circular import."""
    from astra.tools.diagnostic.registry import register_parser

    return register_parser(cls)


@_register_jest_parser
class JestParser(OutputParser):
    """Parser for Jest test output."""

    name = "jest"
    patterns = ["jest", "● ", "Test Suites:", "Tests:"]

    def parse(self, output: str) -> TestResult:
        """Parse Jest output into structured result."""
        result = TestResult(framework="jest")

        # Extract summary: "Tests: 1 failed, 10 passed, 11 total"
        tests_match = re.search(
            r"Tests:\s*(?:(\d+) failed,?\s*)?(?:(\d+) passed,?\s*)?(\d+) total", output
        )
        if tests_match:
            result.failed = int(tests_match.group(1) or 0)
            result.passed = int(tests_match.group(2) or 0)
            result.total = int(tests_match.group(3))

        # Extract duration
        time_match = re.search(r"Time:\s*([\d.]+)\s*s", output)
        if time_match:
            result.duration_seconds = float(time_match.group(1))

        # Extract failures - Jest uses "● test name"
        failure_matches = re.finditer(r"●\s*(.+?)\n([\s\S]+?)(?=●|\Z)", output)
        for match in failure_matches:
            test_name = match.group(1).strip()
            block = match.group(2)

            error = ParsedError(error_type="TestFailure", function=test_name, traceback=block[:500])

            # Extract file and line
            file_match = re.search(r"at\s+.+?\s+\((.+?):(\d+):(\d+)\)", block)
            if file_match:
                error.file = file_match.group(1)
                error.line = int(file_match.group(2))
                error.column = int(file_match.group(3))

            # Extract error message
            msg_match = re.search(r"(Error|TypeError|ReferenceError):\s*(.+)", block)
            if msg_match:
                error.error_type = msg_match.group(1)
                error.message = msg_match.group(2).strip()
                error.suggestion = get_suggestion(f"{error.error_type}: {error.message}")

            result.failures.append(error)

        return result
