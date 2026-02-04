"""Diagnostic output formatting utilities."""

from astra.tools.diagnostic.models import TestResult


def format_diagnostic_context(test_result: TestResult, manifest_info: dict | None = None) -> str:
    """Format diagnostic information for LLM context.

    Args:
        test_result: Parsed test result
        manifest_info: Optional manifest/package info for context

    Returns:
        Markdown-formatted diagnostic context
    """
    parts = ["## Test Results\n"]

    result = test_result.to_dict()
    parts.append(f"**Status**: {'✅ PASSED' if result['success'] else '❌ FAILED'}\n")
    parts.append(f"**Framework**: {result['framework']}\n")
    parts.append(
        f"**Summary**: {result['passed']} passed, {result['failed']} failed, {result['skipped']} skipped\n"
    )

    if result["failures"]:
        parts.append("\n### Failures\n")
        for i, failure in enumerate(result["failures"], 1):
            parts.append(f"\n#### Failure {i}: {failure['function'] or 'Unknown'}\n")
            if failure["file"] and failure["line"]:
                parts.append(f"**Location**: `{failure['file']}:{failure['line']}`\n")
            if failure["error_type"] and failure["message"]:
                parts.append(f"**Error**: `{failure['error_type']}: {failure['message']}`\n")
            if failure["suggestion"]:
                parts.append(f"**Suggestion**: {failure['suggestion']}\n")
            if failure["code_snippet"]:
                parts.append(f"```\n{failure['code_snippet']}\n```\n")

    if manifest_info:
        parts.append("\n### Available Scripts\n")
        for script, cmd in manifest_info.get("scripts", {}).items():
            parts.append(f"- `{script}`: `{cmd}`\n")

    return "\n".join(parts)
