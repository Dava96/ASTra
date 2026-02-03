"""Git-based VCS implementation using GitPython and Aider."""

import logging

from git import GitCommandError, Repo

from astra.interfaces.vcs import (
    VCS,
    BranchResult,
    CloneResult,
    CommitResult,
    MergeResult,
    PRResult,
    PRStatus,
)

logger = logging.getLogger(__name__)


class AiderGitAdapter(VCS):
    """Git adapter utilizing GitPython and Aider for repository management."""

    def clone(self, url: str, destination: str, auth_token: str | None = None) -> CloneResult:
        """Clone a repository."""
        try:
            # If auth_token is provided, inject it into the URL
            clone_url = url
            if auth_token and "https://" in url:
                clone_url = url.replace("https://", f"https://{auth_token}@")

            Repo.clone_from(clone_url, destination)
            logger.info(f"Cloned {url} to {destination}")
            return CloneResult(success=True, path=destination)
        except GitCommandError as e:
            logger.error(f"Clone failed: {e}")
            return CloneResult(success=False, path=destination, error=str(e))
        except Exception as e:
            logger.error(f"Clone error: {e}")
            return CloneResult(success=False, path=destination, error=str(e))

    def create_branch(self, repo_path: str, branch_name: str) -> BranchResult:
        """Create and checkout a new branch."""
        try:
            repo = Repo(repo_path)
            current = repo.active_branch

            # Create branch
            new_branch = repo.create_head(branch_name)
            new_branch.checkout()

            logger.info(f"Created and checked out branch {branch_name} from {current.name}")
            return BranchResult(success=True, branch_name=branch_name)
        except GitCommandError as e:
            logger.error(f"Branch creation failed: {e}")
            return BranchResult(success=False, branch_name=branch_name, error=str(e))

    def checkout(self, repo_path: str, branch_name: str) -> BranchResult:
        """Checkout an existing branch."""
        try:
            repo = Repo(repo_path)
            repo.git.checkout(branch_name)
            logger.info(f"Checked out {branch_name}")
            return BranchResult(success=True, branch_name=branch_name)
        except GitCommandError as e:
            return BranchResult(success=False, branch_name=branch_name, error=str(e))

    def commit(self, repo_path: str, message: str, files: list[str] | None = None) -> CommitResult:
        """Commit changes."""
        try:
            repo = Repo(repo_path)

            if files:
                # Add specific files
                repo.index.add(files)
            else:
                # Add all changes (including untracked)
                repo.git.add(A=True)

            commit = repo.index.commit(message)
            return CommitResult(success=True, commit_hash=commit.hexsha)
        except GitCommandError as e:
            return CommitResult(success=False, error=str(e))

    def push(self, repo_path: str, branch_name: str) -> bool:
        """Push changes to remote."""
        try:
            repo = Repo(repo_path)
            # Push and set upstream
            repo.git.push("--set-upstream", "origin", branch_name)
            logger.info(f"Pushed {branch_name} to origin")
            return True
        except GitCommandError as e:
            logger.error(f"Push failed: {e}")
            return False

    def create_pr(
        self,
        repo_path: str,
        title: str,
        body: str,
        base: str = "main",
        head: str | None = None
    ) -> PRResult:
        """Create a pull request (Stub - requires Git host API)."""
        logger.warning("PR creation requires specific host adapter (GitHub/GitLab).")
        return PRResult(success=False, error="Not implemented in base Git adapter")

    def get_pr_status(self, repo_path: str, pr_number: int) -> PRStatus:
        """Get PR status (Stub)."""
        return PRStatus.OPEN

    def rebase(self, repo_path: str, target: str = "main") -> bool:
        """Attempt to rebase current branch onto target."""
        try:
            repo = Repo(repo_path)
            repo.git.pull("origin", target, "--rebase")
            return True
        except GitCommandError as e:
            logger.error(f"Rebase failed: {e}")
            repo.git.rebase("--abort")
            return False

    def merge(
        self,
        repo_path: str,
        source_branch: str,
        target_branch: str = "main",
        no_ff: bool = True
    ) -> MergeResult:
        """Merge source branch into target branch."""
        try:
            repo = Repo(repo_path)

            # Checkout target
            repo.git.checkout(target_branch)

            # Merge
            args = [source_branch]
            if no_ff:
                args.insert(0, "--no-ff")

            repo.git.merge(*args)

            return MergeResult(success=True, merge_commit=repo.head.commit.hexsha)
        except GitCommandError as e:
            logger.error(f"Merge failed: {e}")
            # Check for conflict
            is_conflict = "CONFLICT" in str(e)
            return MergeResult(success=False, error=str(e), has_conflicts=is_conflict)

    def get_changed_files(self, repo_path: str, base: str = "main") -> list[str]:
        """Get list of changed files compared to base branch."""
        try:
            repo = Repo(repo_path)
            # Use diff to get changed files
            diff_index = repo.head.commit.diff(base)
            changed = [item.a_path for item in diff_index]
            return changed
        except Exception as e:
            logger.error(f"Failed to get changed files: {e}")
            return []

    def get_current_branch(self, repo_path: str) -> str:
        """Get the current branch name."""
        try:
            repo = Repo(repo_path)
            return repo.active_branch.name
        except Exception:
            return "unknown"
