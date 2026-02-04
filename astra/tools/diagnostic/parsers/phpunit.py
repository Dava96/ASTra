"""PHPUnit output parser."""

import re

from astra.tools.diagnostic.base import OutputParser
from astra.tools.diagnostic.models import ParsedError, TestResult


def _register_phpunit_parser(cls):
    """Delayed registration to avoid circular import."""
    from astra.tools.diagnostic.registry import register_parser

    return register_parser(cls)


@_register_phpunit_parser
class PhpunitParser(OutputParser):
    """Parser for PHPUnit test output."""

    name = "phpunit"
    patterns = ["phpunit", "PHPUnit", "Tests:", "Assertions:"]

    def parse(self, output: str) -> TestResult:
        """Parse PHPUnit output into structured result."""
        result = TestResult(framework="phpunit")

        # Extract summary: "Tests: 10, Assertions: 20, Failures: 2"
        summary_match = re.search(r"Tests:\s*(\d+).*?Failures:\s*(\d+)", output)
        if summary_match:
            result.total = int(summary_match.group(1))
            result.failed = int(summary_match.group(2))
            result.passed = result.total - result.failed

        # Extract failures
        failure_matches = re.finditer(r"\d+\)\s+(\S+::\S+)\n(.+?)(?=\d+\)|\Z)", output, re.DOTALL)
        for match in failure_matches:
            test_name = match.group(1)
            block = match.group(2)

            error = ParsedError(error_type="TestFailure", function=test_name, traceback=block[:500])

            # Extract file and line
            file_match = re.search(r"(\S+\.php):(\d+)", block)
            if file_match:
                error.file = file_match.group(1)
                error.line = int(file_match.group(2))

            result.failures.append(error)

        return result
