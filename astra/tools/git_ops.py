"""Git and GitHub operations via subprocess and gh CLI."""

import logging
import re
from typing import Any

from astra.core.tools import BaseTool
from astra.interfaces.vcs import (
    VCS,
    BranchResult,
    CloneResult,
    CommitResult,
    MergeResult,
    PRResult,
    PRStatus,
)
from astra.tools.shell import ShellExecutor

logger = logging.getLogger(__name__)


class GitHubVCS(VCS, BaseTool):
    """Git/GitHub implementation via subprocess and gh CLI with async support."""

    name = "vcs_action"
    description = "Perform version control operations like branching, committing, pushing, and PR creation."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["branch", "checkout", "commit", "push", "pr", "merge", "status"],
                "description": "The VCS action to perform"
            },
            "repo_path": {
                "type": "string",
                "description": "Path to the repository"
            },
            "branch_name": {
                "type": "string",
                "description": "Name of the branch (for branch/checkout/push)"
            },
            "message": {
                "type": "string",
                "description": "Commit message (for commit)"
            },
            "title": {
                "type": "string",
                "description": "PR title"
            },
            "body": {
                "type": "string",
                "description": "PR description"
            }
        },
        "required": ["action", "repo_path"]
    }

    def __init__(self):
        self._shell = ShellExecutor()

    async def execute(self, action: str, repo_path: str, **kwargs: Any) -> Any:
        """Execute the requested VCS action."""
        if action == "branch":
            name = kwargs.get("branch_name")
            if not name: return "❌ Branch name required."
            res = await self.create_branch(repo_path, name)
            return f"✅ Created branch {name}" if res.success else f"❌ Failed: {res.error}"
        elif action == "checkout":
            name = kwargs.get("branch_name")
            if not name: return "❌ Branch name required."
            res = await self.checkout(repo_path, name)
            return f"✅ Switched to {name}" if res.success else f"❌ Failed: {res.error}"
        elif action == "commit":
            msg = kwargs.get("message")
            if not msg: return "❌ Message required."
            res = await self.commit(repo_path, msg)
            return f"✅ Committed {res.commit_hash}" if res.success else f"❌ Failed: {res.error}"
        elif action == "push":
            name = kwargs.get("branch_name") or await self.get_current_branch(repo_path)
            success = await self.push(repo_path, name)
            return f"✅ Pushed {name}" if success else "❌ Failed to push."
        elif action == "pr":
            title = kwargs.get("title", "Update")
            body = kwargs.get("body", "")
            res = await self.create_pr(repo_path, title, body)
            return f"✅ PR created: {res.pr_url}" if res.success else f"❌ Failed: {res.error}"
        elif action == "status":
            branch = await self.get_current_branch(repo_path)
            changed = await self.get_changed_files(repo_path)
            # Structured output for status
            return {
                "branch": branch,
                "changed_files_count": len(changed),
                "changed_files": changed,
                "clean": len(changed) == 0
            }
        elif action == "merge":
            source = kwargs.get("source_branch")
            target = kwargs.get("target_branch", "main")
            if not source: return "❌ Source branch required."
            res = await self.merge(repo_path, source, target)
            if res.success:
                return f"✅ Merged {source} into {target} ({res.merge_commit})"
            elif res.has_conflicts:
                return f"❌ Merge conflicts in: {', '.join(res.conflicting_files or [])}"
            else:
                return f"❌ Failed: {res.error}"
        else:
            return f"❌ Unknown action: {action}"

    async def _run(self, command: list[str], cwd: str | None = None) -> tuple[bool, str, str]:
        """Run a git command asynchronously."""
        result = await self._shell.run_async(command, cwd=cwd)
        return result.success, result.stdout, result.stderr

    async def clone(self, url: str, destination: str, auth_token: str | None = None) -> CloneResult:
        """Clone a repository."""
        if auth_token and "github.com" in url:
            url = url.replace("https://", f"https://{auth_token}@")

        success, stdout, stderr = await self._run(["git", "clone", url, destination])

        return CloneResult(
            success=success,
            path=destination,
            error=stderr if not success else None
        )

    async def create_branch(self, repo_path: str, branch_name: str) -> BranchResult:
        """Create and checkout a new branch."""
        success, stdout, stderr = await self._run(
            ["git", "checkout", "-b", branch_name],
            cwd=repo_path
        )

        return BranchResult(
            success=success,
            branch_name=branch_name,
            error=stderr if not success else None
        )

    async def checkout(self, repo_path: str, branch_name: str) -> BranchResult:
        """Checkout an existing branch."""
        success, stdout, stderr = await self._run(
            ["git", "checkout", branch_name],
            cwd=repo_path
        )

        return BranchResult(
            success=success,
            branch_name=branch_name,
            error=stderr if not success else None
        )

    async def get_current_branch(self, repo_path: str) -> str:
        """Get the current branch name."""
        # Prioritize --show-current which is cleaner
        success, stdout, _ = await self._run(
            ["git", "branch", "--show-current"],
            cwd=repo_path
        )
        if success and stdout.strip():
            return stdout.strip()

        # Fallback for older git versions
        success, stdout, stderr = await self._run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path
        )
        return stdout.strip() if success else "unknown"

    async def commit(self, repo_path: str, message: str, files: list[str] | None = None) -> CommitResult:
        """Commit changes."""
        if files:
            for f in files:
                await self._run(["git", "add", f], cwd=repo_path)
        else:
            await self._run(["git", "add", "-A"], cwd=repo_path)

        success, stdout, stderr = await self._run(
            ["git", "commit", "-m", message],
            cwd=repo_path
        )

        if success:
            _, hash_out, _ = await self._run(["git", "rev-parse", "HEAD"], cwd=repo_path)
            return CommitResult(
                success=True,
                commit_hash=hash_out.strip()
            )

        return CommitResult(
            success=False,
            error=stderr
        )

    async def push(self, repo_path: str, branch_name: str) -> bool:
        """Push changes to remote."""
        success, _, _ = await self._run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=repo_path
        )
        return success

    async def create_pr(
        self,
        repo_path: str,
        title: str,
        body: str,
        base: str = "main",
        head: str | None = None
    ) -> PRResult:
        """Create a pull request using gh CLI."""
        cmd = ["gh", "pr", "create", "--title", title, "--body", body, "--base", base]
        if head:
            cmd.extend(["--head", head])

        success, stdout, stderr = await self._run(cmd, cwd=repo_path)

        if success:
            pr_url = stdout.strip()
            pr_number = None
            match = re.search(r"/pull/(\d+)", pr_url)
            if match:
                pr_number = int(match.group(1))

            return PRResult(
                success=True,
                pr_url=pr_url,
                pr_number=pr_number
            )

        return PRResult(
            success=False,
            error=stderr
        )

    async def get_pr_status(self, repo_path: str, pr_number: int) -> PRStatus:
        """Get the status of a pull request."""
        success, stdout, stderr = await self._run(
            ["gh", "pr", "view", str(pr_number), "--json", "state"],
            cwd=repo_path
        )

        if success:
            import json
            try:
                data = json.loads(stdout)
                state = data.get("state", "").upper()
                if state == "MERGED":
                    return PRStatus.MERGED
                elif state == "CLOSED":
                    return PRStatus.CLOSED
                else:
                    return PRStatus.OPEN
            except json.JSONDecodeError:
                pass

        return PRStatus.OPEN

    async def rebase(self, repo_path: str, target: str = "main") -> bool:
        """Attempt to rebase current branch onto target."""
        await self._run(["git", "fetch", "origin", target], cwd=repo_path)
        success, _, stderr = await self._run(
            ["git", "rebase", f"origin/{target}"],
            cwd=repo_path
        )

        if not success:
            await self._run(["git", "rebase", "--abort"], cwd=repo_path)
            logger.warning(f"Rebase failed: {stderr}")
            return False

        return True

    async def merge(
        self,
        repo_path: str,
        source_branch: str,
        target_branch: str = "main",
        no_ff: bool = True
    ) -> MergeResult:
        """Merge source branch into target branch."""
        checkout_result = await self.checkout(repo_path, target_branch)
        if not checkout_result.success:
            return MergeResult(
                success=False,
                error=f"Failed to checkout {target_branch}: {checkout_result.error}"
            )

        merge_cmd = ["git", "merge", source_branch]
        if no_ff:
            merge_cmd.append("--no-ff")

        success, stdout, stderr = await self._run(merge_cmd, cwd=repo_path)

        if success:
            _, hash_out, _ = await self._run(["git", "rev-parse", "HEAD"], cwd=repo_path)
            return MergeResult(
                success=True,
                merge_commit=hash_out.strip()
            )

        if "CONFLICT" in stderr or "CONFLICT" in stdout:
            _, conflict_out, _ = await self._run(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                cwd=repo_path
            )
            conflicting_files = [f.strip() for f in conflict_out.strip().split("\n") if f.strip()]
            await self._run(["git", "merge", "--abort"], cwd=repo_path)

            return MergeResult(
                success=False,
                has_conflicts=True,
                conflicting_files=conflicting_files,
                error="Merge conflicts detected"
            )

        return MergeResult(success=False, error=stderr or "Merge failed")

    async def get_changed_files(self, repo_path: str, base: str = "main", limit: int = 100) -> list[str]:
        """Get list of files changed compared to base branch (limited to prevent OOM)."""
        success, stdout, _ = await self._run(
            ["git", "diff", "--name-only", f"origin/{base}"],
            cwd=repo_path
        )
        if success:
            files = [f.strip() for f in stdout.strip().split("\n") if f.strip()]
            return files[:limit] # Return capped list
        return []

    async def pull_latest(self, repo_path: str, branch: str = "main") -> bool:
        """Pull latest changes for a branch."""
        await self.checkout(repo_path, branch)
        success, _, _ = await self._run(["git", "pull", "origin", branch], cwd=repo_path)
        return success
