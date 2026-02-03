
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from astra.tools.aider_tool import AiderTool
from astra.tools.shell import ShellResult

@pytest.fixture
def mock_shell():
    with patch("astra.tools.aider_tool.ShellExecutor") as MockShell:
        shell_instance = MockShell.return_value
        shell_instance._is_allowed.return_value = (True, None) # Default allow
        yield shell_instance

@pytest.mark.asyncio
async def test_aider_tool_success(mock_shell):
    tool = AiderTool()
    
    # Mock run_async success
    mock_shell.run_async = AsyncMock(return_value=ShellResult(
        success=True,
        stdout="Applied edits to file.py",
        stderr="",
        return_code=0,
        command=["aider", "edit", "file.py"]
    ))

    res = await tool.execute("edit", instruction="Fix bugs", files=["file.py"])
    
    assert res["success"] is True
    assert "Applied edits" in res["output"]
    
    # Verify command construction
    call_args = mock_shell.run_async.call_args
    # call_args[0] is args tuple. cmd is first arg
    cmd = call_args[0][0]
    assert "aider" in cmd
    assert "--message" in cmd
    assert "Fix bugs" in cmd

@pytest.mark.asyncio
async def test_aider_tool_security_block(mock_shell):
    tool = AiderTool()
    
    # Mock block via _is_allowed check if AiderTool calls it manualy?
    # AiderTool calls shell.run_async, which does the check internally.
    # However, AiderTool explicitly calls _is_allowed first in my refactor? 
    # Let's check aider_tool.py refactor:
    # "allowed, error_msg = self._shell._is_allowed(cmd)"
    # So we mock _is_allowed
    mock_shell._is_allowed.return_value = (False, "Blocked command")
    
    res = await tool.execute("edit", instruction="Delete everything")
    
    assert res["success"] is False
    assert "Blocked" in res["error"]

@pytest.mark.asyncio
async def test_aider_tool_failure(mock_shell):
    tool = AiderTool()
    
    # Mock failure
    # Ensure _is_allowed passes
    mock_shell._is_allowed.return_value = (True, None)
    
    mock_shell.run_async = AsyncMock(return_value=ShellResult(
        success=False,
        stdout="",
        stderr="Aider failed",
        return_code=1,
        command=["aider", "edit"]
    ))

    res = await tool.execute("edit", instruction="Bad things")
    
    assert res["success"] is False
    assert "Aider failed" in res["error"]
