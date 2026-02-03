"""Data models for diagnostic parsing."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedError:
    """Structured representation of an error."""
    error_type: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    function: str | None = None
    message: str = ""
    traceback: str = ""
    code_snippet: str = ""
    suggestion: str = ""
    related_files: list[str] = field(default_factory=list)

    def _smart_truncate(self, text: str, max_len: int = 1500) -> str:
        """Keep the head and tail of long text."""
        if len(text) <= max_len:
            return text
        half = max_len // 2
        return text[:half] + "\n... [truncated] ...\n" + text[-half:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "function": self.function,
            "message": self.message,
            "traceback": self._smart_truncate(self.traceback) if self.traceback else "",
            "code_snippet": self.code_snippet,
            "suggestion": self.suggestion,
            "related_files": self.related_files
        }


@dataclass
class TestResult:
    """Structured test run result."""
    __test__ = False # Prevent pytest from collecting this as a test class
    framework: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_seconds: float = 0
    failures: list[ParsedError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework": self.framework,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
            "failures": [f.to_dict() for f in self.failures],
            "failures": [f.to_dict() for f in self.failures],
            "success": self.failed == 0 and self.errors == 0,
            "suggestion": self.suggestion
        }

    suggestion: str | None = None  # Suggestion if test runner is missing
