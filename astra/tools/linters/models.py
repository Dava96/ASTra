"""Data models for lint results."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LintIssue:
    """A single lint issue."""

    file: str
    line: int
    column: int | None = None
    code: str = ""
    message: str = ""
    severity: str = "warning"  # error, warning, info
    fixable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "fixable": self.fixable,
        }


@dataclass
class LintResult:
    """Result of running a linter."""

    linter: str
    success: bool
    issues: list[LintIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    fixable_count: int = 0
    fixed_count: int = 0
    raw_output: str = ""
    suggestion: str | None = None  # Suggestion if tool is missing

    def to_dict(self) -> dict[str, Any]:
        return {
            "linter": self.linter,
            "success": self.success,
            "issues": [i.to_dict() for i in self.issues],
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "fixable_count": self.fixable_count,
            "fixed_count": self.fixed_count,
        }
