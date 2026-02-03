"""PR Review tool for analyzing pull requests using Knowledge Graph context."""

import asyncio
import logging
from typing import Any

from astra.core.tools import BaseTool

logger = logging.getLogger(__name__)


class PRReviewTool(BaseTool):
    """Tool for reviewing pull requests and flagging potential issues."""

    name = "review_pr"
    description = "Review a pull request for potential issues using Knowledge Graph analysis"
    parameters = {
        "type": "object",
        "properties": {
            "pr_number": {
                "type": "integer",
                "description": "Pull request number to review"
            },
            "repo": {
                "type": "string",
                "description": "Repository name (owner/repo format)"
            },
            "changed_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of changed file paths (if already known)"
            }
        },
        "required": ["pr_number", "repo"]
    }

    def __init__(self, knowledge_graph=None, vcs=None):
        """Initialize with optional KG and VCS dependencies."""
        self._kg = knowledge_graph
        self._vcs = vcs

    async def execute(
        self,
        pr_number: int,
        repo: str,
        changed_files: list[str] | None = None,
        **kwargs: Any
    ) -> dict[str, Any]:
        """Review a PR and return analysis results.
        
        Returns:
            dict with keys: summary, risks, recommendations, impact_analysis
        """
        results = {
            "pr_number": pr_number,
            "repo": repo,
            "summary": "",
            "risks": [],
            "recommendations": [],
            "impact_analysis": {}
        }

        # 1. Get changed files (from VCS if not provided)
        if not changed_files and self._vcs:
            try:
                changed_files = await self._vcs.get_pr_files(repo, pr_number)
            except Exception as e:
                logger.warning(f"Failed to fetch PR files: {e}")
                changed_files = []

        if not changed_files:
            results["summary"] = "No changed files to analyze"
            return results

        # 2. Analyze each file using Knowledge Graph (Parallelized)
        high_impact_files = []
        affected_dependents = set()

        if self._kg:
            tasks = [self._analyze_file(f) for f in changed_files]
            file_results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in file_results:
                if isinstance(res, Exception):
                    logger.debug(f"KG lookup failed: {res}")
                    continue
                if res and res.get("dependents"):
                    affected_dependents.update(res["dependents"])
                    if len(res["dependents"]) >= 5:
                        high_impact_files.append(res)

        # 3. Build risk assessment
        if high_impact_files:
            results["risks"].append({
                "severity": "high",
                "message": f"{len(high_impact_files)} files have high blast radius",
                "files": [f["file"] for f in high_impact_files]
            })

        # 4. Generate recommendations
        if len(affected_dependents) > 10:
            results["recommendations"].append(
                "Consider breaking this PR into smaller changes"
            )

        if any(f.endswith("package.json") or f.endswith("composer.json") for f in changed_files):
            results["recommendations"].append(
                "Dependency changes detected - verify lock files are updated"
            )

        # 5. Summary
        results["summary"] = (
            f"Reviewed {len(changed_files)} changed files. "
            f"Potential impact on {len(affected_dependents)} dependent files. "
            f"Found {len(results['risks'])} risks."
        )

        results["impact_analysis"] = {
            "changed_files": len(changed_files),
            "affected_dependents": len(affected_dependents),
            "high_impact_files": len(high_impact_files)
        }

        return results

    async def _analyze_file(self, filepath: str) -> dict[str, Any] | None:
        """Analyze a single file (helper for asyncio.gather)."""
        if not self._kg:
            return None
        try:
            dependents = self._kg.get_dependents(filepath)
            return {
                "file": filepath,
                "dependents": dependents
            }
        except Exception:
            return None
