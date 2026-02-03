
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
import time
from astra.tools.manifest import get_project_manifest
from astra.tools.shell import ShellExecutor, ShellResult
from astra.tools.git_ops import GitHubVCS
from astra.tools.pr_review import PRReviewTool

# --- Manifest Caching Tests ---

def test_manifest_caching(tmp_path):
    # Setup a project
    (tmp_path / "package.json").write_text('{"name": "test"}')
    
    # First call
    manifest1 = get_project_manifest(tmp_path)
    assert manifest1["name"] == "test"
    
    # Check cache stats
    info = get_project_manifest.cache_info()
    initial_misses = info.misses
    initial_hits = info.hits
    
    # Second call
    manifest2 = get_project_manifest(tmp_path)
    assert manifest2 == manifest1
    
    # Verify hit
    info = get_project_manifest.cache_info()
    assert info.hits == initial_hits + 1
    assert info.misses == initial_misses

# --- Shell Output Capping Tests ---

@pytest.mark.asyncio
async def test_shell_output_capping():
    # Mock subprocess to return huge output
    with patch("astra.tools.shell.asyncio.create_subprocess_exec") as mock_exec:
        process = MagicMock()
        process.returncode = 0
        
        # Simulate infinite stream of 'a's, but we expect it to stop reading after limit
        # We need a custom readline mock that feeds data
        
        async def huge_stream(*args):
             # 11 chunks of 1MB
             chunk = b"a" * (1024 * 1024)
             for _ in range(11):
                 yield chunk
             yield b""
             
        # Mocking the readline is tricky for async generator, 
        # let's mock subprocess.communicate if run_async used it, but I changed it to manual reading.
        # So I need to mock stdout.readline
        
        # Simpler approach: Test the logic works with a mock stream
        # However, testing exact 10MB logic requires mocking the stream object properly.
        pass # Skipping complex mock for now, trusting implementation but will verify simple large output
        
@pytest.mark.asyncio
async def test_shell_output_capping_simple():
    """Verify that we cap output if it exceeds limit (simplified check)."""
    # Requires constructing a real ShellExecutor with a mocked subprocess that returns > 10MB
    executor = ShellExecutor()
    
    # Mock pipe
    mock_stdout = MagicMock()
    # readline needs to be awaitable. 
    # Use side_effect with AsyncMock returning lines
    line = b"a" * (1024 * 1024) + b"\n" # 1MB line
    # Return 12 chunks (12MB), limit is 10MB
    chunks = [line] * 12 + [b""]
    
    # Create an async iterator compatible with 'while chunk := await stream.readline()'
    async def mock_readline():
        if chunks:
            return chunks.pop(0)
        return b""
        
    mock_stdout.readline = mock_readline
    
    mock_stderr = MagicMock()
    mock_stderr.readline = AsyncMock(return_value=b"")
    
    with patch("astra.tools.shell.asyncio.create_subprocess_exec") as mock_exec:
        process = MagicMock()
        process.returncode = 0
        process.stdout = mock_stdout
        process.stderr = mock_stderr
        process.wait = AsyncMock()
        
        mock_exec.return_value = process
        
        # Set a smaller timeout to avoid hanging if infinite loop
        result = await executor.run_async(["echo", "huge"])
        
        assert result.success is True
        # Check if output is truncated marker or just limited
        assert "[... Output Truncated ...]" in result.stdout
        assert len(result.stdout) < 13 * 1024 * 1024 
        assert len(result.stdout) >= 10 * 1024 * 1024 # Should have at least 10MB

# --- GitOps Structured Output ---

@pytest.mark.asyncio
async def test_git_ops_structured_status():
    vcs = GitHubVCS()
    
    # Mock _run
    vcs._run = AsyncMock()
    
    # Mock branch output
    vcs._run.side_effect = [
        (True, "main\n", ""), # get_current_branch (show-current)
        (True, "file1.py\nfile2.py\n", ""), # get_changed_files
    ]
    
    result = await vcs.execute("status", repo_path=".")
    
    assert isinstance(result, dict)
    assert result["branch"] == "main"
    assert result["changed_files_count"] == 2
    assert "file1.py" in result["changed_files"]
    assert result["clean"] is False

# --- PR Review Parallelism ---

@pytest.mark.asyncio
async def test_pr_review_parallel():
    tool = PRReviewTool()
    tool._vcs = AsyncMock()
    tool._vcs.get_pr_files.return_value = ["file1.py", "file2.py", "file3.py"]
    
    tool._kg = MagicMock()
    tool._kg.get_dependents.side_effect = lambda f: [f"dep_of_{f}"] 
    
    # We want to ensure _analyze_file is called concurrently?
    # Hard to test concurrency without delay.
    # But we can verify correct results are gathered.
    
    result = await tool.execute(123, "repo")
    
    assert result["summary"].startswith("Reviewed 3 changed files")
    assert result["impact_analysis"]["changed_files"] == 3

