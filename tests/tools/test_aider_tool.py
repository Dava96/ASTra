
import os
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from astra.tools.aider_tool import AiderResult, AiderTool

# --- Standard AsyncMock for Stream ---

# Replace AsyncStream with standard AsyncMock usage in tests
# We can't easily mock __aiter__ on AsyncMock in older python versions without extra work, 
# but for readline(), side_effect is enough.

@pytest.fixture
def aider_tool():
    with patch("astra.tools.shell.ShellExecutor._is_allowed", return_value=(True, None)):
        yield AiderTool(model="gpt-4")

@pytest.mark.asyncio
async def test_aider_security_block(aider_tool):
    """Test verification of security blocking."""
    # Mock the internal shell's _is_allowed method which AiderTool uses
    with patch.object(aider_tool._shell, "_is_allowed", return_value=(False, "Blocked command")):
         res = await aider_tool.execute("edit", instruction="bad cmd")
         assert res["success"] is False
         assert "Blocked" in res["error"]

def test_aider_tool_init_variants():
    """Test __init__ with different config structures."""
    with patch("astra.tools.aider_tool.get_config") as mock_config:
        # Case 1: dict fallback config
        # We need to simulate multiple calls to .get(). 
        # First call 'orchestration', 'fallback_strategy'.
        def mock_get(*args, **kwargs):
            if args == ("orchestration", "fallback_strategy"):
                return {"api_key_env_var": "KEY"}
            return kwargs.get("default")
        
        mock_config.return_value.get.side_effect = mock_get
        tool = AiderTool()
        assert tool._api_key_env == "KEY"

def test_aider_run_sync(aider_tool):
    """Test synchronous run method."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Applying edits to f1.py\nWriting f2.py\nTokens: 100 sent"
        mock_run.return_value.stderr = ""

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
        # ShellExecutor returns "Command timed out after..."
        assert "timed out" in str(result.error).lower() or "timeout" in str(result.error).lower()

        # Not Found
        mock_run.side_effect = FileNotFoundError("executable not found")
        result = aider_tool.run("msg", ".")
        assert "not found" in str(result.error).lower()

@pytest.mark.asyncio
async def test_aider_run_async_success(aider_tool):
    """Test successful async run."""
    with patch("asyncio.create_subprocess_exec") as mock_exec, \
         patch.dict(os.environ, {"MY_KEY": "secret"}):

        aider_tool._api_key_env = "MY_KEY"
        mock_proc = AsyncMock()
        mock_exec.return_value = mock_proc
        mock_proc.returncode = 0
        
        # Configure stdout readline side effects
        # Must return bytes, ending with empty bytes
        import itertools
        # Start with content, then infinite empty bytes to avoid StopIteration
        mock_proc.stdout.readline.side_effect = itertools.chain(
            [
                b"Applying edits to f1.py",
                b"Writing f2.py",
                b"Tokens: 100 sent",
            ],
            itertools.repeat(b"")
        )
        # stderr empty
        mock_proc.stderr.readline.side_effect = itertools.repeat(b"")
        
        mock_proc.wait = AsyncMock(return_value=0)

        result = await aider_tool.run_async("msg", ".")
        assert result.success
        assert "f1.py" in result.files_modified
        assert result.tokens_used == 100

@pytest.mark.asyncio
async def test_aider_run_async_generic_exception(aider_tool):
    """Test generic Exception in run_async."""
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_exec.return_value = mock_proc
        mock_proc.wait.side_effect = Exception("General Failure")
        
        # Setup streams to finish immediately so we hit the exception in wait()
        mock_proc.stdout.readline.side_effect = [b""]
        mock_proc.stderr.readline.side_effect = [b""]

        result = await aider_tool.run_async("msg", ".")
        assert result.success is False
        assert "General Failure" in result.error

@pytest.mark.asyncio
async def test_aider_stream_output(aider_tool):
    """Test stream_output generator."""
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_exec.return_value = mock_proc
        mock_proc.stdout.readline.side_effect = [b"line1", b"line2", b""]
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
        mock_proc.stdout.readline.side_effect = [b"Thinking..."] # Infinite or just one line

        with patch("asyncio.wait_for", side_effect=TimeoutError()):
            result = await aider_tool.run_async("msg", ".", timeout=0.1)
            assert not result.success
            mock_proc.kill.assert_called()
            assert "timed out" in result.error.lower() or "timeout" in result.error.lower()

def test_aider_token_parsing_robust(aider_tool):
    """Test token parsing with malformed input."""
    assert aider_tool._parse_token_usage("Tokens:") is None
    assert aider_tool._parse_token_usage("Tokens: abc sent") is None
    assert aider_tool._parse_token_usage("Some other output") is None

def test_aider_check_installed_robust(aider_tool):
    """Test check_installed."""
    with patch("subprocess.run") as mock_run:
        # Success case
        # We need the return value of run() to have a returncode attribute
        process_mock = MagicMock()
        process_mock.returncode = 0
        mock_run.return_value = process_mock
        
        assert aider_tool.check_installed() is True

        # Failure case (return code 1)
        process_mock_fail = MagicMock()
        process_mock_fail.returncode = 1
        mock_run.return_value = process_mock_fail
        
        assert aider_tool.check_installed() is False

        # Exception case
        mock_run.side_effect = Exception("err")
        assert aider_tool.check_installed() is False
