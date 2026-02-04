"""Mypy type checker for Python."""

import re

from astra.tools.linters.base import BaseLinter
from astra.tools.linters.models import LintIssue


def _register_mypy(cls):
    """Delayed registration to avoid circular import."""
    from astra.tools.linters.registry import register_linter

    return register_linter(cls)


@_register_mypy
class MypyLinter(BaseLinter):
    """Mypy - Python static type checker."""

    name = "mypy"
    languages = ["python"]
    check_cmd = ["mypy", "."]
    fix_cmd = None  # mypy doesn't auto-fix
    is_type_checker = True
    detect_files = ["*.py", "pyproject.toml"]

    def parse(self, output: str) -> list[LintIssue]:
        """Parse mypy output into issues."""
        issues = []
        # Format: file.py:10: error: message
        for match in re.finditer(r"(\S+):(\d+):\s*(error|warning|note):\s*(.+)", output):
            issues.append(
                LintIssue(
                    file=match.group(1),
                    line=int(match.group(2)),
                    column=None,
                    severity=match.group(3),
                    message=match.group(4),
                    code="mypy",
                    fixable=False,
                )
            )
        return issues
