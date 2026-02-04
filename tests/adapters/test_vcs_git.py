"""Unit tests for Git VCS adapter."""

from unittest.mock import MagicMock, patch

import pytest
from git import GitCommandError

from astra.adapters.vcs_git import AiderGitAdapter


class TestAiderGitAdapter:
    """Test Git adapter operations."""

    @pytest.fixture
    def adapter(self):
        return AiderGitAdapter()

    @patch("astra.adapters.vcs_git.Repo")
    def test_clone_success(self, mock_repo_cls, adapter):
        """Test successful clone."""
        result = adapter.clone("https://github.com/test/repo", "/tmp/repo")

        mock_repo_cls.clone_from.assert_called_once_with(
            "https://github.com/test/repo", "/tmp/repo"
        )
        assert result.success
        assert result.path == "/tmp/repo"

    @patch("astra.adapters.vcs_git.Repo")
    def test_clone_auth_injection(self, mock_repo_cls, adapter):
        """Test authentication token injection."""
        adapter.clone("https://github.com/test/repo", "/tmp/repo", "secret_token")

        mock_repo_cls.clone_from.assert_called_once_with(
            "https://secret_token@github.com/test/repo", "/tmp/repo"
        )

    @patch("astra.adapters.vcs_git.Repo")
    def test_clone_failure(self, mock_repo_cls, adapter):
        """Test clone failure handling."""
        mock_repo_cls.clone_from.side_effect = GitCommandError("clone", "failed")

        result = adapter.clone("url", "dest")
        assert not result.success
        assert "failed" in result.error

    @patch("astra.adapters.vcs_git.Repo")
    def test_create_branch(self, mock_repo_cls, adapter):
        """Test branch creation."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.active_branch.name = "main"

        result = adapter.create_branch("/repo", "feature/test")

        mock_repo.create_head.assert_called_once_with("feature/test")
        mock_repo.create_head.return_value.checkout.assert_called_once()
        assert result.success
        assert result.branch_name == "feature/test"

    @patch("astra.adapters.vcs_git.Repo")
    def test_commit_changes(self, mock_repo_cls, adapter):
        """Test committing changes."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.index.commit.return_value.hexsha = "abc1234"

        result = adapter.commit("/repo", "Initial commit")

        mock_repo.git.add.assert_called_with(A=True)
        mock_repo.index.commit.assert_called_with("Initial commit")
        assert result.success
        assert result.commit_hash == "abc1234"

    @patch("astra.adapters.vcs_git.Repo")
    def test_push_changes(self, mock_repo_cls, adapter):
        """Test pushing changes."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        success = adapter.push("/repo", "feature/test")

        mock_repo.git.push.assert_called_with("--set-upstream", "origin", "feature/test")
        assert success

    @patch("astra.adapters.vcs_git.Repo")
    def test_merge_conflict(self, mock_repo_cls, adapter):
        """Test merge conflict handling."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.git.merge.side_effect = GitCommandError("merge", "CONFLICT: content")

        result = adapter.merge("/repo", "feature", "main")

        assert not result.success
        assert result.has_conflicts
        assert "CONFLICT" in result.error

    @patch("astra.adapters.vcs_git.Repo")
    def test_get_changed_files(self, mock_repo_cls, adapter):
        """Test getting changed files."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        # Mock diff items
        item1 = MagicMock()
        item1.a_path = "file1.py"
        item2 = MagicMock()
        item2.a_path = "file2.py"

        mock_repo.head.commit.diff.return_value = [item1, item2]

        files = adapter.get_changed_files("/repo", "main")

        assert len(files) == 2
        assert "file1.py" in files
        assert "file2.py" in files
