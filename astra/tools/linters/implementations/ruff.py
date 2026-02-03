"""Ruff linter for Python."""

import re

from astra.tools.linters.base import BaseLinter
from astra.tools.linters.models import LintIssue


def _register_ruff(cls):
    """Delayed registration to avoid circular import."""
    from astra.tools.linters.registry import register_linter
    return register_linter(cls)


@_register_ruff
class RuffLinter(BaseLinter):
    """Ruff - Fast Python linter with auto-fix support."""

    name = "ruff"
    languages = ["python"]
    check_cmd = ["ruff", "check", "."]
    fix_cmd = ["ruff", "check", "--fix", "."]
    is_type_checker = False
    detect_files = ["*.py", "pyproject.toml", "setup.py"]

    def parse(self, output: str) -> list[LintIssue]:
        """Parse ruff output into issues."""
        issues = []
        # Format: file.py:10:5: E123 error message
        for match in re.finditer(r"(\S+):(\d+):(\d+):\s*(\w+)\s+(.+)", output):
            issues.append(LintIssue(
                file=match.group(1),
                line=int(match.group(2)),
                column=int(match.group(3)),
                code=match.group(4),
                message=match.group(5),
                severity="error" if match.group(4).startswith("E") else "warning",
                fixable=True  # Most ruff issues are fixable
            ))
        return issues
