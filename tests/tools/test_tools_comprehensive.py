import subprocess
from unittest.mock import MagicMock, patch

import pytest

from astra.tools.file_ops import FileOps
from astra.tools.search import SearchTool
from astra.tools.shell import ShellExecutor

# === FileOps Tests ===

def test_file_ops_max_depth(tmp_path):
    """Test max_depth in list_files."""
    # Create structure:
    # root/
    #   level1.txt
    #   sub/
    #     level2.txt
    #     subsub/
    #       level3.txt

    (tmp_path / "level1.txt").touch()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "level2.txt").touch()
    (tmp_path / "sub" / "subsub").mkdir()
    (tmp_path / "sub" / "subsub" / "level3.txt").touch()

    ops = FileOps()

    # Depth 0: only root children? No, depth is relative logic.
    # Logic in code: len(parts) - base_depth <= max_depth
    # base_depth = len(tmp_path.parts)
    # level1: parts = base + 1. diff = 1.
    # default max_depth logic: if passed 0, should get only immediate children?
    # Let's see: if max_depth=0, diff <= 0? No, file is usually depth 1 relative to dir.
    # Wait, my logic was: `if len(path.parts) - base_depth <= max_depth`.
    # root parts = N. file parts = N+1. Diff = 1.
    # So max_depth=1 should return level1.

    files_d1 = list(ops.list_files(tmp_path, max_depth=1))
    names_d1 = [f.name for f in files_d1]
    assert "level1.txt" in names_d1
    assert "level2.txt" not in names_d1

    files_d2 = list(ops.list_files(tmp_path, max_depth=2))
    names_d2 = [f.name for f in files_d2]
    assert "level1.txt" in names_d2
    assert "level2.txt" in names_d2
    assert "level3.txt" not in names_d2

def test_file_ops_backup_restore(tmp_path):
    """Test backup and restore functionality."""
    f = tmp_path / "important.txt"
    f.write_text("v1")

    ops = FileOps(backup_enabled=True)

    # Write v2 with backup
    ops.write(f, "v2")

    assert f.read_text() == "v2"
    assert (tmp_path / "important.txt.bak").exists()
    assert (tmp_path / "important.txt.bak").read_text() == "v1"

    # Restore
    res = ops.restore_backup(f)
    assert res is True
    assert f.read_text() == "v1"
    assert not (tmp_path / "important.txt.bak").exists()

# === Search Tool Tests ===

@pytest.mark.asyncio
async def test_search_tool_mock_ripgrep(tmp_path):
    """Test search tool mocking internal libs."""
    with patch("astra.tools.search.DDGS") as MockDDGS:
        # Mock web search (existing)
        MockDDGS.return_value.__enter__.return_value.text.return_value = [{"title": "T", "body": "B", "href": "H"}]

        tool = SearchTool()

        # Test web search - SearchTool takes query directly
        res = await tool.execute(query="test")
        assert "Source 1" in res
        assert "T" in res

# === Shell Executor Tests ===

@pytest.mark.asyncio
async def test_shell_timeout():
    """Test shell command timeout."""
    # Mock config to allow 'sleep'
    mock_config = MagicMock()
    mock_config.is_command_allowed.return_value = True

    with patch("astra.tools.shell.get_config", return_value=mock_config), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="sleep 1", timeout=0.1)):

        shell = ShellExecutor(timeout=300)
        res = await shell.execute("sleep 1", timeout=0.1)

        assert res["code"] != 0
        assert "timed out" in res.get("stderr", "").lower() or "timed out" in res.get("message", "").lower()

@pytest.mark.asyncio
async def test_shell_allowlist():
    """Test deny allowed commands."""

    mock_config = MagicMock()
    # allow 'ls', deny 'rm'
    mock_config.is_command_allowed.side_effect = lambda cmd: cmd == "ls"

    with patch("astra.tools.shell.get_config", return_value=mock_config):
        shell = ShellExecutor()

        # Allowed (mock subprocess success)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "ok"
            mock_run.return_value.stderr = ""

            res = await shell.execute("ls -la")
            assert res["code"] == 0
            assert res["stdout"] == "ok"

        # Denied (subprocess not called)
        res = await shell.execute("rm -rf /")
        assert res["code"] != 0
        assert res.get("blocked") is True
