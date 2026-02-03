"""Pytest output parser."""

import logging
import re
from functools import lru_cache
from pathlib import Path

from astra.tools.diagnostic.base import OutputParser
from astra.tools.diagnostic.models import ParsedError, TestResult
from astra.tools.diagnostic.suggestions import get_suggestion

logger = logging.getLogger(__name__)


def _register_pytest_parser(cls):
    """Delayed registration to avoid circular import."""
    from astra.tools.diagnostic.registry import register_parser
    return register_parser(cls)


@lru_cache(maxsize=128)
def extract_file_context(file_path: str, line: int, context_lines: int = 5) -> str:
    """Extract code context around a specific line (Cached)."""
    try:
        path = Path(file_path)
        if not path.exists():
            return ""

        # Robust read
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = path.read_text(encoding="latin-1")
            except Exception:
                return "<binary file>"

        lines = content.splitlines()
        start = max(0, line - context_lines - 1)
        end = min(len(lines), line + context_lines)

        context = []
        for i in range(start, end):
            marker = ">>> " if i == line - 1 else "    "
            context.append(f"{i + 1:4d}{marker}{lines[i]}")

        return "\n".join(context)
    except Exception as e:
        logger.warning(f"Failed to extract context from {file_path}: {e}")
        return ""


@_register_pytest_parser
class PytestParser(OutputParser):
    """Parser for pytest output."""

    name = "pytest"
    # Removed generic PASSED/FAILED to avoid false positives with other frameworks
    patterns = ["pytest", "collected", "short test summary info", "====="]

    # Pre-compiled Patterns
    # Flexible summary patterns (search individually)
    PASSED_REGEX = re.compile(r"(\d+) passed", re.IGNORECASE)
    FAILED_REGEX = re.compile(r"(\d+) failed", re.IGNORECASE)
    SKIPPED_REGEX = re.compile(r"(\d+) skipped", re.IGNORECASE)
    DURATION_REGEX = re.compile(r"in ([\d.]+)s", re.IGNORECASE)

    # Single-pass failure scanner
    # Matches:
    # _________________________ test_name _________________________
    # file:line: ErrorType
    # E   message
    FAILURE_BLOCK_REGEX = re.compile(
        r"_{10,}\s*(?P<func>[^\s]+)\s*_{10,}\s*"  # Header
        r"(?P<body>.+?)"                          # Body (lazy)
        r"(?=\n_{10,}|\n=+\s*short test summary|\Z)", # Lookahead for next header/footer
        re.DOTALL
    )

    def parse(self, output: str) -> TestResult:
        """Parse pytest output into structured result."""
        result = TestResult(framework="pytest")

        # 1. Extract Summary (End of file usually)
        summary_block = output[-2048:] # Summary is at end

        passed = self.PASSED_REGEX.search(summary_block)
        failed = self.FAILED_REGEX.search(summary_block)
        skipped = self.SKIPPED_REGEX.search(summary_block)
        duration = self.DURATION_REGEX.search(summary_block)

        if passed: result.passed = int(passed.group(1))
        if failed: result.failed = int(failed.group(1))
        if skipped: result.skipped = int(skipped.group(1))
        if duration: result.duration_seconds = float(duration.group(1))

        # Fallback if no specific format found but "short test summary info" exists
        # (Already handled by regex searches above if lines exist)

        result.total = result.passed + result.failed + result.skipped

        # 2. Extract Failures (Single Pass over full output)
        for match in self.FAILURE_BLOCK_REGEX.finditer(output):
            func_name = match.group("func")
            block = match.group("body")

            error = ParsedError(
                error_type="TestFailure",
                function=func_name,
                traceback=block[:1000] # Initial truncate
            )

            # Extract details from body
            # pattern: path/to/file.py:123: ErrorType
            loc_match = re.search(r"(?P<file>\S+\.py):(?P<line>\d+): (?P<err>\w+)", block)
            if loc_match:
                error.file = loc_match.group("file")
                error.line = int(loc_match.group("line"))
                error.error_type = loc_match.group("err")
                error.code_snippet = extract_file_context(error.file, error.line)

            # Extract specific message "E   assert ..."
            msg_match = re.search(r"^E\s+(.+)$", block, re.MULTILINE)
            if msg_match:
                error.message = msg_match.group(1).strip()
                # Refine suggestion based on specific error
                error.suggestion = get_suggestion(f"{error.error_type}: {error.message}")

            result.failures.append(error)

        return result
