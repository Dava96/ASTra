
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.tools.shell import ShellExecutor, ShellResult


@pytest.mark.asyncio
class TestShellExecutorAsync:
    """Tests for async shell execution."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.is_command_allowed = MagicMock(return_value=True)
        return config

    @pytest.fixture
    def executor(self, mock_config):
        with patch("astra.tools.shell.get_config", return_value=mock_config):
            yield ShellExecutor(timeout=30)

    async def test_run_async_blocked(self):
        """Test blocked command in run_async."""
        config = MagicMock()
        config.is_command_allowed.return_value = False
        with patch("astra.tools.shell.get_config", return_value=config):
            executor = ShellExecutor()
            result = await executor.run_async(["rm", "-rf"])
            assert result.blocked
            assert not result.success

    async def test_run_async_success(self, executor):
        """Test successful async execution with output."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.stdout.readline.side_effect = [b"Line 1\n", b"Line 2\n", b""]
        mock_process.stderr.readline.side_effect = [b""]
        mock_process.wait.return_value = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            result = await executor.run_async(["echo", "hello"])

            assert result.success
            assert "Line 1" in result.stdout
            assert "Line 2" in result.stdout
            assert result.return_code == 0

            mock_exec.assert_called_once()

    async def test_run_async_timeout(self, executor):
        """Test timeout in run_async."""
        # Mock create_subprocess_exec to hang or just trigger timeout logic via wait_for side effect
        mock_process = AsyncMock()
        mock_process.kill = MagicMock()  # kill is synchronous

        # We need to simulate the timeout during one of the reads or the wait
        # We need to simulate the timeout during one of the reads or the wait
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError), \
             patch("asyncio.create_subprocess_exec", return_value=mock_process):
                result = await executor.run_async(["sleep", "100"], timeout=1)

                assert not result.success
                assert "timed out" in result.stderr
                # Ensure kill was called
                mock_process.kill.assert_called()

    async def test_run_async_exception(self, executor):
        """Test general exception handling in run_async."""
        with patch("asyncio.create_subprocess_exec", side_effect=RuntimeError("Async boom")):
            result = await executor.run_async(["boom"])

            assert not result.success
            assert "Async boom" in result.stderr

    async def test_run_string_async_valid(self, executor):
        """Test run_string_async with valid string."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.stdout.readline.return_value = b""
        mock_process.stderr.readline.return_value = b""

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
             result = await executor.run_string_async("ls -la")
             assert result.success
             mock_exec.assert_called()
             # Verify split
             args = mock_exec.call_args[0]
             assert args == ('ls', '-la')

    async def test_run_string_async_invalid(self, executor):
        """Test run_string_async with parse error."""
        result = await executor.run_string_async('echo "unclosed')
        assert result.blocked
        assert "Parse error" in result.stderr

    async def test_execute_entry_point(self, executor):
        """Test the execute method (entry point)."""
        # Use AsyncMock for the async method
        with patch.object(executor, "run_string_async", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ShellResult(True, "out", "err", 0, [], False)

            res = await executor.execute("echo test")

            assert res["success"] is True
            assert res["stdout"] == "out"
            assert res["stderr"] == "err"
