"""Base class for linters."""

from abc import ABC, abstractmethod
from pathlib import Path

from astra.tools.linters.models import LintIssue, LintResult


class BaseLinter(ABC):
    """Abstract base class for linters.

    Subclasses must define:
    - name: Unique linter identifier
    - languages: List of language codes this linter supports
    - check_cmd: Command to run linter (list of args)
    - fix_cmd: Command to auto-fix (list of args, or None if not supported)
    - is_type_checker: Whether this is a type checker
    - parse(): Method to parse output into LintIssue list
    """

    name: str = ""
    languages: list[str] = []
    check_cmd: list[str] = []
    fix_cmd: list[str] | None = None
    is_type_checker: bool = False
    detect_files: list[str] = []  # Legacy Pattern detection
    manifest_files: list[str] = []  # Files that define project metadata (e.g. pyproject.toml)
    config_files: list[str] = []  # Files that configure this tool (e.g. ruff.toml)

    def can_run(self, project_path: Path) -> bool:
        """Check if this linter can run on the project."""
        if not self.detect_files:
            return True

        for pattern in self.detect_files:
            if pattern.startswith("*."):
                # File extension pattern
                if list(project_path.rglob(pattern)):
                    return True
            else:
                # Exact file match
                if (project_path / pattern).exists():
                    return True
        return False

    @abstractmethod
    def parse(self, output: str) -> list[LintIssue]:
        """Parse linter output into structured issues."""
        pass

    def run(self, project_path: Path, auto_fix: bool = False) -> LintResult:
        """Run the linter on a project.

        This is a template method - subclasses typically don't override this.
        """
        from astra.tools.shell import ShellExecutor

        shell = ShellExecutor()

        # Decide which command to run
        if auto_fix and self.fix_cmd:
            cmd = self.fix_cmd
            is_fix_run = True
        else:
            cmd = self.check_cmd
            is_fix_run = False

        result = shell.run(cmd, cwd=str(project_path))
        issues = self.parse(result.stdout + result.stderr)

        lint_result = LintResult(
            linter=self.name,
            success=result.success,
            issues=issues,
            error_count=sum(1 for i in issues if i.severity == "error"),
            warning_count=sum(1 for i in issues if i.severity == "warning"),
            fixable_count=sum(1 for i in issues if i.fixable),
            raw_output=result.stdout[:2000],
        )

        # If we did a fix run, check what's remaining
        if is_fix_run:
            check_result = shell.run(self.check_cmd, cwd=str(project_path))
            remaining_issues = self.parse(check_result.stdout + check_result.stderr)
            lint_result.fixed_count = len(issues) - len(remaining_issues)
            lint_result.issues = remaining_issues

        return lint_result
