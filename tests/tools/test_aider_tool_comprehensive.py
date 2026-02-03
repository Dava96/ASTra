
import os
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.tools.aider_tool import AiderResult, AiderTool


class AsyncStream:
    """Helper to mock asyncio stream readline."""
    def __init__(self, lines):
        self.lines = iter(lines)
    async def readline(self):
        try:
            return next(self.lines)
        except StopIteration:
            return b""

@pytest.fixture
def aider_tool():
    return AiderTool(model="gpt-4")

def test_aider_tool_init_variants():
    """Test __init__ with different config structures."""
    with patch("astra.tools.aider_tool.get_config") as mock_config:
        # Case 1: dict fallback config
        mock_config.return_value.get.side_effect = lambda *args, **kwargs: {"api_key_env_var": "KEY"} if args[1] == "fallback_strategy" else kwargs.get("default")
        tool = AiderTool()
        assert tool._api_key_env == "KEY"

        # Case 2: non-dict fallback config
        mock_config.return_value.get.side_effect = lambda *args, **kwargs: "some_val" if args[1] == "fallback_strategy" else kwargs.get("default")
        tool = AiderTool(api_key_env="DIRECT")
        assert tool._api_key_env == "DIRECT"

def test_aider_run_sync(aider_tool):
    """Test synchronous run method."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Applying edits to f1.py\nWriting f2.py\nTokens: 100 sent"
        mock_run.return_value.stderr = ""

        # Pass files to hit line 97
        result = aider_tool.run("msg", ".", files=["f1.py"])
        assert result.success
        assert "f1.py" in result.files_modified
        assert "f2.py" in result.files_modified
        assert result.tokens_used == 100

def test_aider_run_sync_errors(aider_tool):
    """Test sync run error paths."""
    with patch("subprocess.run") as mock_run:
        # Timeout
        mock_run.side_effect = subprocess.TimeoutExpired(["cmd"], 10)
        result = aider_tool.run("msg", ".")
        assert not result.success
        assert "Timeout" in result.error

        # Not Found
        mock_run.side_effect = FileNotFoundError()
        result = aider_tool.run("msg", ".")
        assert "not found" in result.error

        # Generic Exception
        mock_run.side_effect = RuntimeError("oops")
        result = aider_tool.run("msg", ".")
        assert "oops" in result.error

@pytest.mark.asyncio
async def test_aider_run_async_success(aider_tool):
    """Test successful async run."""
    with patch("asyncio.create_subprocess_exec") as mock_exec, \
         patch.dict(os.environ, {"MY_KEY": "secret"}):

        aider_tool._api_key_env = "MY_KEY"
        mock_proc = AsyncMock()
        mock_exec.return_value = mock_proc
        mock_proc.returncode = 0
        mock_proc.stdout = AsyncStream([
            b"Applying edits to f1.py",
            b"Writing f2.py",
            b"Tokens: 100 sent"
        ])
        mock_proc.stderr = AsyncStream([])
        mock_proc.wait = AsyncMock(return_value=0)

        # Test progress callback (hits line 211)
        cb = MagicMock()
        result = await aider_tool.run_async("msg", ".", progress_callback=cb)
        assert result.success
        assert "f1.py" in result.files_modified
        assert "f2.py" in result.files_modified
        assert result.tokens_used == 100
        cb.assert_called()

@pytest.mark.asyncio
async def test_aider_run_async_generic_exception(aider_tool):
    """Test generic Exception in run_async (hits line 245-247)."""
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_exec.return_value = mock_proc
        # Mocking wait to raise generic Exception
        mock_proc.wait.side_effect = Exception("General Failure")
        mock_proc.stdout = AsyncStream([])
        mock_proc.stderr = AsyncStream([])

        result = await aider_tool.run_async("msg", ".")
        assert result.success is False
        assert "General Failure" in result.error

@pytest.mark.asyncio
async def test_aider_stream_output(aider_tool):
    """Test stream_output generator."""
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_exec.return_value = mock_proc
        mock_proc.stdout = AsyncStream([b"line1", b"line2"])
        mock_proc.wait = AsyncMock(return_value=0)

        lines = []
        async for line in aider_tool.stream_output("hi", "."):
            lines.append(line)

        assert lines == ["line1", "line2"]

@pytest.mark.asyncio
async def test_aider_run_async_timeout(aider_tool):
    """Test timeout in run_async."""
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_exec.return_value = mock_proc
        mock_proc.stdout = AsyncStream([b"Thinking..."])

        with patch("asyncio.wait_for", side_effect=TimeoutError()):
            result = await aider_tool.run_async("msg", ".", timeout=0.1)
            assert not result.success
            mock_proc.kill.assert_called()

@pytest.mark.asyncio
async def test_aider_execute_method(aider_tool):
    """Test the execute wrapper."""
    with patch.object(aider_tool, "run_async", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = AiderResult(success=True, output="ok", files_modified=["f.py"])
        res = await aider_tool.execute("msg", cwd=".")
        assert res["success"] is True
        assert res["modified"] == ["f.py"]

def test_aider_token_parsing_robust(aider_tool):
    """Test token parsing with malformed input (hits line 304)."""
    # Malformed index (IndexError)
    assert aider_tool._parse_token_usage("Tokens:") is None
    # Malformed value (ValueError)
    assert aider_tool._parse_token_usage("Tokens: abc sent") is None
    # No tokens at all
    assert aider_tool._parse_token_usage("Some other output") is None

def test_aider_check_installed_robust(aider_tool):
    """Test check_installed."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        assert aider_tool.check_installed() is True

        mock_run.return_value.returncode = 1
        assert aider_tool.check_installed() is False

        mock_run.side_effect = Exception("err")
        assert aider_tool.check_installed() is False
