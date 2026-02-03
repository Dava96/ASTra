
from pathlib import Path
from unittest.mock import MagicMock, patch

from astra.tools.linters.base import BaseLinter
from astra.tools.linters.models import LintIssue


class ConcreteLinter(BaseLinter):
    name = "test_linter"
    check_cmd = ["check"]
    fix_cmd = ["fix"]
    detect_files = ["*.py", "config.json"]

    def parse(self, output: str) -> list[LintIssue]:
        return []

def test_can_run_extensions(tmp_path):
    linter = ConcreteLinter()

    # Empty dir
    assert not linter.can_run(tmp_path)

    # Match extension
    (tmp_path / "test.py").touch()
    assert linter.can_run(tmp_path)

def test_can_run_exact_file(tmp_path):
    linter = ConcreteLinter()
    (tmp_path / "config.json").touch()
    assert linter.can_run(tmp_path)

def test_can_run_no_detect_files():
    class UniversalLinter(BaseLinter):
        def parse(self, o): return []

    assert UniversalLinter().can_run(Path("."))

def test_run_check_only():
    linter = ConcreteLinter()

    with patch("astra.tools.shell.ShellExecutor") as MockShell:
        shell = MockShell.return_value
        shell.run.return_value = MagicMock(stdout="out", stderr="", success=True)

        result = linter.run(Path("."))

        shell.run.assert_called_with(["check"], cwd=".")
        assert result.success is True
        assert result.fixed_count == 0

def test_run_with_fix():
    linter = ConcreteLinter()
    linter.parse = MagicMock(side_effect=[
        [LintIssue(file="f", line=1, message="err", severity="error", fixable=True)], # First run
        [] # Second run (clean)
    ])

    with patch("astra.tools.shell.ShellExecutor") as MockShell:
        shell = MockShell.return_value
        shell.run.return_value = MagicMock(stdout="out", stderr="", success=True)

        result = linter.run(Path("."), auto_fix=True)

        # Verify fix cmd called first
        shell.run.assert_any_call(["fix"], cwd=".")
        # Verify check cmd called second
        shell.run.assert_any_call(["check"], cwd=".")

        assert result.fixed_count == 1
        assert len(result.issues) == 0

def test_run_fix_not_supported():
    class ReadOnlyLinter(BaseLinter):
        check_cmd = ["check"]
        def parse(self, o): return []

    linter = ReadOnlyLinter()

    with patch("astra.tools.shell.ShellExecutor") as MockShell:
        shell = MockShell.return_value
        shell.run.return_value = MagicMock(stdout="", stderr="", success=True)

        linter.run(Path("."), auto_fix=True)

        # Should fall back to check_cmd if no fix_cmd
        shell.run.assert_called_with(["check"], cwd=".")
