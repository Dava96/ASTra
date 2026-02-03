"""ESLint linter for JavaScript/TypeScript."""

import re

from astra.tools.linters.base import BaseLinter
from astra.tools.linters.models import LintIssue


def _register_eslint(cls):
    """Delayed registration to avoid circular import."""
    from astra.tools.linters.registry import register_linter
    return register_linter(cls)


@_register_eslint
class ESLintLinter(BaseLinter):
    """ESLint - JavaScript/TypeScript linter with auto-fix support."""

    name = "eslint"
    languages = ["javascript", "typescript"]
    check_cmd = ["npx", "eslint", "."]
    fix_cmd = ["npx", "eslint", "--fix", "."]
    is_type_checker = False
    detect_files = ["*.js", "*.jsx", "*.ts", "*.tsx", "package.json"]

    def parse(self, output: str) -> list[LintIssue]:
        """Parse eslint output into issues."""
        issues = []
        current_file = None

        for line in output.splitlines():
            # File header line
            file_match = re.match(r"^(/\S+|\S+\.\w+)$", line.strip())
            if file_match:
                current_file = file_match.group(1)
                continue

            # Issue line: "  10:5  error  message  rule-name"
            issue_match = re.match(r"\s*(\d+):(\d+)\s+(error|warning)\s+(.+?)\s+(\S+)$", line)
            if issue_match and current_file:
                issues.append(LintIssue(
                    file=current_file,
                    line=int(issue_match.group(1)),
                    column=int(issue_match.group(2)),
                    severity=issue_match.group(3),
                    message=issue_match.group(4),
                    code=issue_match.group(5),
                    fixable=True
                ))

        return issues
