"""Abstract base class for version control systems."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class PRStatus(Enum):
    """Pull request status."""

    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"
    CONFLICT = "conflict"


@dataclass
class CloneResult:
    """Result of a clone operation."""

    success: bool
    path: str
    error: str | None = None


@dataclass
class BranchResult:
    """Result of a branch operation."""

    success: bool
    branch_name: str
    error: str | None = None


@dataclass
class CommitResult:
    """Result of a commit operation."""

    success: bool
    commit_hash: str | None = None
    error: str | None = None


@dataclass
class PRResult:
    """Result of a PR creation."""

    success: bool
    pr_url: str | None = None
    pr_number: int | None = None
    error: str | None = None


@dataclass
class MergeResult:
    """Result of a merge operation."""

    success: bool
    merge_commit: str | None = None
    has_conflicts: bool = False
    conflicting_files: list[str] | None = None
    error: str | None = None


class VCS(ABC):
    """Abstract version control system interface."""

    @abstractmethod
    def clone(self, url: str, destination: str, auth_token: str | None = None) -> CloneResult:
        """Clone a repository."""
        pass

    @abstractmethod
    def create_branch(self, repo_path: str, branch_name: str) -> BranchResult:
        """Create and checkout a new branch."""
        pass

    @abstractmethod
    def checkout(self, repo_path: str, branch_name: str) -> BranchResult:
        """Checkout an existing branch."""
        pass

    @abstractmethod
    def commit(self, repo_path: str, message: str, files: list[str] | None = None) -> CommitResult:
        """Commit changes."""
        pass

    @abstractmethod
    def push(self, repo_path: str, branch_name: str) -> bool:
        """Push changes to remote."""
        pass

    @abstractmethod
    def create_pr(
        self, repo_path: str, title: str, body: str, base: str = "main", head: str | None = None
    ) -> PRResult:
        """Create a pull request."""
        pass

    @abstractmethod
    def get_pr_status(self, repo_path: str, pr_number: int) -> PRStatus:
        """Get the status of a pull request."""
        pass

    @abstractmethod
    def rebase(self, repo_path: str, target: str = "main") -> bool:
        """Attempt to rebase current branch onto target."""
        pass

    @abstractmethod
    def merge(
        self, repo_path: str, source_branch: str, target_branch: str = "main", no_ff: bool = True
    ) -> "MergeResult":
        """Merge source branch into target branch."""
        pass

    @abstractmethod
    def get_changed_files(self, repo_path: str, base: str = "main") -> list[str]:
        """Get list of files changed compared to base branch."""
        pass

    @abstractmethod
    def get_current_branch(self, repo_path: str) -> str:
        """Get the current branch name."""
        pass
