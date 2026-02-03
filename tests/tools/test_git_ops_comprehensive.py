from unittest.mock import MagicMock, patch

import pytest

from astra.tools.git_ops import GitHubVCS


@pytest.fixture
def vcs_and_shell():
    with patch("astra.tools.git_ops.ShellExecutor") as MockShell:
        shell = MockShell.return_value
        vcs = GitHubVCS()
        yield vcs, shell

# Stub helper
def mock_run(stdout="", stderr="", success=True):
    return MagicMock(success=success, stdout=stdout, stderr=stderr)

@pytest.mark.asyncio
async def test_execute_tool_actions(vcs_and_shell):
    vcs, shell = vcs_and_shell

    # Branch
    shell.run.return_value = mock_run()
    res = await vcs.execute("branch", ".", branch_name="feat/new")
    assert "✅ Created branch" in res

    # Missing branch name
    res = await vcs.execute("branch", ".")
    assert "Branch name required" in res

    # Checkout
    res = await vcs.execute("checkout", ".", branch_name="main")
    assert "✅ Switched to" in res

    # Commit failure
    shell.run.return_value = mock_run(success=False, stderr="Nothing to commit")
    res = await vcs.execute("commit", ".", message="fail")
    assert "❌ Failed" in res

    # Push
    shell.run.return_value = mock_run()
    # Mock current branch lookup
    with patch.object(vcs, 'get_current_branch', return_value="main"):
        res = await vcs.execute("push", ".")
        assert "✅ Pushed" in res

    # PR
    with patch.object(vcs, 'create_pr') as mock_pr:
        mock_pr.return_value = MagicMock(success=True, pr_url="http://pr/1")
        res = await vcs.execute("pr", ".", title="My PR")
        assert "http://pr/1" in res

    # Status
    with patch.object(vcs, 'get_changed_files', return_value=["f.py"]):
        res = await vcs.execute("status", ".")
        assert res["changed_files"] == ["f.py"]

    # Merge
    with patch.object(vcs, 'merge') as mock_merge:
        mock_merge.return_value = MagicMock(success=True, merge_commit="abc")
        res = await vcs.execute("merge", ".", source_branch="feat", target_branch="main")
        assert "Merged feat" in res

    # Unknown
    res = await vcs.execute("dance", ".")
    assert "Unknown action" in res

def test_clone_auth(vcs_and_shell):
    vcs, shell = vcs_and_shell
    shell.run.return_value = mock_run()

    vcs.clone("https://github.com/repo.git", ".", "token123")

    args = shell.run.call_args[0][0]
    assert "https://token123@github.com/repo.git" in args

def test_create_branch_fail(vcs_and_shell):
    vcs, shell = vcs_and_shell
    shell.run.return_value = mock_run(success=False, stderr="Branch exists")

    res = vcs.create_branch(".", "b1")
    assert not res.success
    assert res.error == "Branch exists"

def test_commit_success(vcs_and_shell):
    vcs, shell = vcs_and_shell
    # Sequence: [add, commit, rev-parse]
    shell.run.side_effect = [
        mock_run(), # add
        mock_run(), # commit
        mock_run(stdout="hash123") # rev-parse
    ]

    res = vcs.commit(".", "msg", files=["a.py"])
    assert res.success
    assert res.commit_hash == "hash123"

def test_create_pr_parser(vcs_and_shell):
    vcs, shell = vcs_and_shell

    # Success case
    shell.run.return_value = mock_run(stdout="https://github.com/user/repo/pull/123")
    res = vcs.create_pr(".", "Title", "Body")
    assert res.success
    assert res.pr_number == 123

    # Fail case
    shell.run.return_value = mock_run(success=False, stderr="Error")
    res = vcs.create_pr(".", "Title", "Body")
    assert not res.success

def test_pr_status(vcs_and_shell):
    vcs, shell = vcs_and_shell
    from astra.interfaces.vcs import PRStatus

    shell.run.return_value = mock_run(stdout='{"state": "MERGED"}')
    status = vcs.get_pr_status(".", 1)
    assert status == PRStatus.MERGED

    shell.run.return_value = mock_run(stdout='{"state": "OPEN"}')
    status = vcs.get_pr_status(".", 1)
    assert status == PRStatus.OPEN

    # JSON Error
    shell.run.return_value = mock_run(stdout="invalid json")
    status = vcs.get_pr_status(".", 1)
    assert status == PRStatus.OPEN

def test_rebase(vcs_and_shell):
    vcs, shell = vcs_and_shell

    # Success
    shell.run.return_value = mock_run()
    assert vcs.rebase(".")

    # Fail
    shell.run.side_effect = [
        mock_run(), # fetch
        mock_run(success=False, stderr="conflict"), # rebase
        mock_run() # abort
    ]
    assert not vcs.rebase(".")

def test_merge_flow(vcs_and_shell):
    vcs, shell = vcs_and_shell

    # Checkout Fail
    with patch.object(vcs, 'checkout', return_value=MagicMock(success=False, error="chk fail")):
        res = vcs.merge(".", "src")
        assert not res.success
        assert "chk fail" in res.error

    # Merge Conflict
    shell.run.side_effect = [
        mock_run(success=False, stdout="CONFLICT (content): Merge conflict in file.txt"), # merge
        mock_run(stdout="file.txt"), # diff check
        mock_run() # abort
    ]

    # We must patch checkout to succeed this time
    with patch.object(vcs, 'checkout', return_value=MagicMock(success=True)):
        res = vcs.merge(".", "src")
        assert not res.success
        assert res.has_conflicts
        assert "file.txt" in res.conflicting_files

    # Generic Merge Fail
    shell.run.side_effect = [
        mock_run(success=False, stderr="Fatal error"), # merge
    ]
    with patch.object(vcs, 'checkout', return_value=MagicMock(success=True)):
        res = vcs.merge(".", "src")
        assert not res.success
        assert "Fatal error" in res.error

def test_get_changed_files(vcs_and_shell):
    vcs, shell = vcs_and_shell

    shell.run.return_value = mock_run(stdout="file1.py\nfile2.py\n")
    files = vcs.get_changed_files(".")
    assert files == ["file1.py", "file2.py"]

    shell.run.return_value = mock_run(success=False)
    assert vcs.get_changed_files(".") == []

def test_pull_latest(vcs_and_shell):
    vcs, shell = vcs_and_shell
    shell.run.return_value = mock_run()
    assert vcs.pull_latest(".", "main")
