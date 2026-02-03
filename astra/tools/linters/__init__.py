"""Linters package with registry-based extensibility.

This package provides a pluggable linter system where each linter is
a separate module that registers itself via the @register_linter decorator.

Usage:
    from astra.tools.linters import LintTool, run_lint
    
    # Run linters on a project
    result = run_lint("/path/to/project")
    
    # Get available linters
    from astra.tools.linters.registry import LINTER_REGISTRY
    print(LINTER_REGISTRY.keys())
"""

from astra.tools.linters.models import LintIssue, LintResult
from astra.tools.linters.registry import get_linters_for_language, run_lint
from astra.tools.linters.tool import LintTool

__all__ = [
    "LintTool",
    "LintIssue",
    "LintResult",
    "run_lint",
    "get_linters_for_language",
]
