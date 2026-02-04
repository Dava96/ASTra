"""PHPStan static analyzer for PHP."""

import json
import re

from astra.tools.linters.base import BaseLinter
from astra.tools.linters.models import LintIssue


def _register_phpstan(cls):
    """Delayed registration to avoid circular import."""
    from astra.tools.linters.registry import register_linter

    return register_linter(cls)


@_register_phpstan
class PHPStanLinter(BaseLinter):
    """PHPStan - PHP static analyzer."""

    name = "phpstan"
    languages = ["php"]
    check_cmd = ["vendor/bin/phpstan", "analyse"]
    fix_cmd = None  # PHPStan doesn't auto-fix
    is_type_checker = True
    detect_files = ["*.php", "composer.json"]

    def parse(self, output: str) -> list[LintIssue]:
        """Parse PHPStan output into issues."""
        issues = []
        # Format varies, try JSON first
        try:
            data = json.loads(output)
            for file_path, file_errors in data.get("files", {}).items():
                for error in file_errors.get("messages", []):
                    issues.append(
                        LintIssue(
                            file=file_path,
                            line=error.get("line", 0),
                            message=error.get("message", ""),
                            severity="error",
                            code="phpstan",
                        )
                    )
        except json.JSONDecodeError:
            # Fallback to text parsing
            for match in re.finditer(r"(\S+\.php):(\d+):(.+)", output):
                issues.append(
                    LintIssue(
                        file=match.group(1),
                        line=int(match.group(2)),
                        message=match.group(3).strip(),
                        severity="error",
                        code="phpstan",
                    )
                )
        return issues
