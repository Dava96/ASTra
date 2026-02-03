"""Rust linters (clippy)."""

import re

from astra.tools.linters.base import BaseLinter
from astra.tools.linters.models import LintIssue


def _register_rust(cls):
    """Delayed registration to avoid circular import."""
    from astra.tools.linters.registry import register_linter
    return register_linter(cls)


@_register_rust
class ClippyLinter(BaseLinter):
    """cargo clippy - Rust linter with auto-fix support."""

    name = "clippy"
    languages = ["rust"]
    check_cmd = ["cargo", "clippy"]
    fix_cmd = ["cargo", "clippy", "--fix", "--allow-dirty"]
    is_type_checker = True  # clippy includes type checking
    detect_files = ["*.rs", "Cargo.toml"]

    def parse(self, output: str) -> list[LintIssue]:
        """Parse clippy output into issues."""
        issues = []
        # Format: warning: message
        #  --> file.rs:10:5
        current_severity = "warning"
        current_message = ""

        for line in output.splitlines():
            # Capture warning/error line
            severity_match = re.match(r"^(warning|error)(?:\[(.+)\])?: (.+)$", line)
            if severity_match:
                current_severity = severity_match.group(1)
                current_message = severity_match.group(3)
                continue

            # Capture location line
            loc_match = re.match(r"^\s*--> (.+):(\d+):(\d+)$", line)
            if loc_match and current_message:
                issues.append(LintIssue(
                    file=loc_match.group(1),
                    line=int(loc_match.group(2)),
                    column=int(loc_match.group(3)),
                    message=current_message,
                    severity=current_severity,
                    code="clippy",
                    fixable=True
                ))
                current_message = ""

        return issues
