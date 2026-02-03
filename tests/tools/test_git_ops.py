from unittest.mock import patch

import pytest

from astra.interfaces.vcs import BranchResult, CommitResult, PRResult
from astra.tools.git_ops import GitHubVCS


@pytest.fixture
def vcs():
    return GitHubVCS()

@pytest.mark.asyncio
async def test_vcs_execute_branch(vcs):
    with patch.object(vcs, 'create_branch') as mock_branch:
        mock_branch.return_value = BranchResult(success=True, branch_name="feat")
        result = await vcs.execute(action="branch", repo_path=".", branch_name="feat")
        assert "Created branch feat" in result

@pytest.mark.asyncio
async def test_vcs_execute_checkout(vcs):
    with patch.object(vcs, 'checkout') as mock_checkout:
        mock_checkout.return_value = BranchResult(success=True, branch_name="main")
        result = await vcs.execute(action="checkout", repo_path=".", branch_name="main")
        assert "Switched to main" in result

@pytest.mark.asyncio
async def test_vcs_execute_commit(vcs):
    with patch.object(vcs, 'commit') as mock_commit:
        mock_commit.return_value = CommitResult(success=True, commit_hash="abc")
        result = await vcs.execute(action="commit", repo_path=".", message="docs")
        assert "Committed abc" in result

@pytest.mark.asyncio
async def test_vcs_execute_push(vcs):
    with patch.object(vcs, 'push') as mock_push:
        mock_push.return_value = True
        result = await vcs.execute(action="push", repo_path=".", branch_name="main")
        assert "Pushed main" in result

@pytest.mark.asyncio
async def test_vcs_execute_pr(vcs):
    with patch.object(vcs, 'create_pr') as mock_pr:
        mock_pr.return_value = PRResult(success=True, pr_url="http://pr")
        result = await vcs.execute(action="pr", repo_path=".", title="T", body="B")
        assert "PR created: http://pr" in result

@pytest.mark.asyncio
async def test_vcs_execute_status(vcs):
    with patch.object(vcs, 'get_current_branch') as mock_branch, \
         patch.object(vcs, 'get_changed_files') as mock_files:
        mock_branch.return_value = "main"
        mock_files.return_value = ["f1.py"]

        result = await vcs.execute(action="status", repo_path=".")
        assert result["branch"] == "main"
        assert "f1.py" in result["changed_files"]

@pytest.mark.asyncio
async def test_vcs_error_handling(vcs):
    # Missing args
    assert "Branch name required" in await vcs.execute(action="branch", repo_path=".")
    assert "Branch name required" in await vcs.execute(action="checkout", repo_path=".")
    assert "Message required" in await vcs.execute(action="commit", repo_path=".")
    assert "Unknown action" in await vcs.execute(action="invalid", repo_path=".")

def test_vcs_git_methods(vcs):
    # Mocking self._run which is uses in all git methods
    with patch.object(vcs, '_run') as mock_run:
        mock_run.return_value = (True, "output", "")

        vcs.clone("url", "dest")
        mock_run.assert_called_with(["git", "clone", "url", "dest"])

        vcs.create_branch(".", "b")
        mock_run.assert_called_with(["git", "checkout", "-b", "b"], cwd=".")

        vcs.push(".", "b")
        mock_run.assert_called_with(["git", "push", "-u", "origin", "b"], cwd=".")

        # PR create (gh cli)
        vcs.create_pr(".", "T", "B")
        args, kwargs = mock_run.call_args
        assert "gh" in args[0]
        assert "pr" in args[0]
        assert "create" in args[0]
