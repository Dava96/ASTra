"""Go linters (go vet and gofmt)."""

import re

from astra.tools.linters.base import BaseLinter
from astra.tools.linters.models import LintIssue


def _register_go(cls):
    """Delayed registration to avoid circular import."""
    from astra.tools.linters.registry import register_linter

    return register_linter(cls)


@_register_go
class GoVetLinter(BaseLinter):
    """go vet - Go static analyzer."""

    name = "go-vet"
    languages = ["go"]
    check_cmd = ["go", "vet", "./..."]
    fix_cmd = None
    is_type_checker = False
    detect_files = ["*.go", "go.mod"]

    def parse(self, output: str) -> list[LintIssue]:
        """Parse go vet output into issues."""
        issues = []
        # Format: file.go:10:5: message
        for match in re.finditer(r"(\S+\.go):(\d+):(\d+):\s*(.+)", output):
            issues.append(
                LintIssue(
                    file=match.group(1),
                    line=int(match.group(2)),
                    column=int(match.group(3)),
                    message=match.group(4),
                    severity="warning",
                    code="go-vet",
                    fixable=False,
                )
            )
        return issues


@_register_go
class GofmtLinter(BaseLinter):
    """gofmt - Go formatter (lint mode)."""

    name = "gofmt"
    languages = ["go"]
    check_cmd = ["gofmt", "-l", "."]
    fix_cmd = ["gofmt", "-w", "."]
    is_type_checker = False
    detect_files = ["*.go", "go.mod"]

    def parse(self, output: str) -> list[LintIssue]:
        """Parse gofmt output - lists files that need formatting."""
        issues = []
        for line in output.strip().splitlines():
            if line.endswith(".go"):
                issues.append(
                    LintIssue(
                        file=line.strip(),
                        line=1,
                        message="File needs formatting",
                        severity="warning",
                        code="gofmt",
                        fixable=True,
                    )
                )
        return issues
