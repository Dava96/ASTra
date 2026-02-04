"""LintTool wrapper for orchestrator integration."""

import logging
from pathlib import Path

from astra.config import get_config
from astra.tools.linters.models import LintResult
from astra.tools.linters.registry import run_lint

logger = logging.getLogger(__name__)


class LintTool:
    """Run linters on a project with optional auto-fix.

    This tool integrates with the linter registry to run appropriate
    linters based on project language detection.
    """

    def __init__(self, auto_fix: bool = True):
        config = get_config()
        self._auto_fix = config.get("orchestration", "auto_fix_lint", default=auto_fix)

    def run(
        self,
        project_path: str | Path,
        language: str | None = None,
        type_check: bool = False,
        auto_fix: bool | None = None,
    ) -> list[LintResult]:
        """Run linters for a project (Parallelized)."""
        from astra.tools.linters.registry import detect_linters

        # We delegate to registry's run_lint for logic, but we can parallelize
        # actual linter execution if we pull it up here or rely on registry improvement.
        # Actually, let's strictly follow the plan: modify tool.py to use ThreadPoolExecutor.
        # But wait, registry.py `run_lint` orchestrates the loop.
        # I should have modified registry.py to parallelize, OR I modify this tool to
        # call valid linters in parallel.
        # Let's override the behavior here using the new registry functions we exposed.

        project_path = Path(project_path)
        should_fix = auto_fix if auto_fix is not None else self._auto_fix

        # 1. Detect linters (Fast O(1))
        linters = detect_linters(project_path, language)

        # 2. Check for missing linter case
        if not linters:
            return run_lint(project_path, language, type_check, should_fix)

        # 3. Run in parallel
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = []
        with ThreadPoolExecutor() as executor:
            future_to_linter = {
                executor.submit(linter.run, project_path, auto_fix=should_fix): linter
                for linter in linters
                if (not linter.is_type_checker or type_check)
            }

            for future in as_completed(future_to_linter):
                linter = future_to_linter[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(f"{linter.name}: {result.error_count} errors")
                except Exception as e:
                    logger.error(f"Linter {linter.name} failed: {e}")
                    results.append(
                        LintResult(
                            linter=linter.name,
                            success=False,
                            error_count=1,
                            issues=[],
                            raw_output=str(e),
                        )
                    )

        return results

    def format_results(self, results: list[LintResult]) -> str:
        """Format lint results for LLM context."""
        parts = ["## Lint Results\n"]

        all_success = all(r.success for r in results)
        parts.append(f"**Overall**: {'✅ PASSED' if all_success else '⚠️ ISSUES FOUND'}\n")

        for result in results:
            parts.append(f"\n### {result.linter}\n")

            if result.suggestion:
                parts.append(f"**Suggestion**: {result.suggestion}\n")
                continue

            parts.append(f"- Errors: {result.error_count}\n")
            parts.append(f"- Warnings: {result.warning_count}\n")

            if result.fixed_count:
                parts.append(f"- Auto-fixed: {result.fixed_count}\n")

            if result.issues:
                parts.append("\n**Issues:**\n```\n")
                for issue in result.issues[:10]:  # Limit output
                    parts.append(f"{issue.file}:{issue.line}: [{issue.code}] {issue.message}\n")
                if len(result.issues) > 10:
                    parts.append(f"... and {len(result.issues) - 10} more\n")
                parts.append("```\n")

        return "".join(parts)

    @staticmethod
    def get_available_linters() -> list[str]:
        """Get list of all registered linter names."""
        from astra.tools.linters.registry import get_available_linters

        return get_available_linters()
