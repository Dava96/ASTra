"""DiagnosticTool for orchestrator integration."""

import logging
from typing import Any

from astra.core.tools import BaseTool
from astra.tools.diagnostic.formatter import format_diagnostic_context
from astra.tools.diagnostic.models import TestResult
from astra.tools.diagnostic.registry import PARSER_REGISTRY, parse_test_output

logger = logging.getLogger(__name__)


class DiagnosticTool(BaseTool):
    """Tool for parsing test output and error diagnostics.

    This tool can be called by the orchestrator to parse test output
    and provide structured diagnostic information.
    """

    name = "parse_diagnostics"
    description = "Parse test output or error logs from various frameworks (pytest, jest, phpunit, browser console) into structured diagnostics."
    parameters = {
        "type": "object",
        "properties": {
            "output": {"type": "string", "description": "Raw test output or error log to parse"},
            "framework": {
                "type": "string",
                "enum": ["auto", "pytest", "jest", "phpunit", "browser"],
                "description": "Framework to use for parsing (default: auto-detect)",
            },
            "format": {
                "type": "string",
                "enum": ["dict", "markdown", "summary"],
                "description": "Output format (default: dict)",
            },
        },
        "required": ["output"],
    }

    async def execute(
        self,
        output: str,
        framework: str = "auto",
        format: str = "dict",
        manifest_info: dict | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute diagnostic parsing.

        Args:
            output: Raw test output to parse
            framework: Framework name or "auto" for auto-detection
            format: Output format ("dict", "markdown", "summary")
            manifest_info: Optional manifest info for context

        Returns:
            Parsed diagnostic information in requested format
        """
        # Parse output
        fw = None if framework == "auto" else framework

        # Extract hints from manifest
        hints = []
        if manifest_info and not fw:
            # Map manifest keys to parser names
            files = manifest_info.get("files", [])
            deps = manifest_info.get("dependencies", {})

            # Python hinting
            if any(f.endswith(".py") for f in files) or "pytest" in deps:
                hints.append("pytest")

            # JS/TS hinting
            if any(f.endswith((".js", ".ts", ".tsx")) for f in files) or "jest" in deps:
                hints.append("jest")

            # PHP Hinting
            if any(f.endswith(".php") for f in files) or "phpunit" in deps:
                hints.append("phpunit")

        result = parse_test_output(output, framework=fw, hints=hints)

        # Missing Test Runner Logic (Diagnostic Consistency)
        # If unknown/generic framework with no results, and we detect languages, suggest a runner.
        if (
            (result.framework == "unknown" or result.total == 0)
            and not result.failed
            and not result.passed
        ):
            # Lazy import to avoid circular dependency, though registry is separate
            from astra.tools.linters.registry import detect_languages

            # We need a project path to detect languages.
            # If manifest_info has a 'path' key, use it. Otherwise, this feature is limited.
            # Alternatively, look at 'files' list if they are absolute paths.
            # But manifest_info usually comes from 'codebase_search' or similar which has paths.
            # Let's try to infer from manifest_info['root_path'] if available, or skip.

            root_path = manifest_info.get("root_path") if manifest_info else None
            if root_path:
                langs = detect_languages(root_path)
                if "python" in langs:
                    result.suggestion = "Python project detected but no test runner output found. Recommended: `uv add --dev pytest`."
                elif "javascript" in langs or "typescript" in langs:
                    result.suggestion = "JS/TS project detected but no test runner output found. Recommended: `npm install --save-dev jest`."

        if format == "markdown":
            return format_diagnostic_context(result, manifest_info)
        elif format == "summary":
            return self._format_summary(result)
        else:
            return result.to_dict()

    def _format_summary(self, result: TestResult) -> str:
        """Format a brief summary of test results."""
        status = "✅ PASSED" if result.to_dict()["success"] else "❌ FAILED"
        return (
            f"{status} | {result.framework} | "
            f"{result.passed} passed, {result.failed} failed, {result.skipped} skipped"
        )

    @classmethod
    def get_available_parsers(cls) -> list[str]:
        """Get list of available parser names."""
        return list(PARSER_REGISTRY.keys())
