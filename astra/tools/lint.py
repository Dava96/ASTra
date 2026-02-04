"""Lint tool for running linters with auto-fix support.

This module is a backward compatibility shim that re-exports from
the new astra.tools.linters package.

New code should import from astra.tools.linters instead.
"""

import warnings

# Re-export for backward compatibility
from astra.tools.linters.implementations.eslint import ESLintLinter
from astra.tools.linters.implementations.mypy import MypyLinter
from astra.tools.linters.implementations.phpstan import PHPStanLinter

# For backward compatibility with code that imports parse functions
from astra.tools.linters.implementations.ruff import RuffLinter
from astra.tools.linters.models import LintIssue, LintResult
from astra.tools.linters.registry import detect_language, get_linters_for_language, run_lint
from astra.tools.linters.tool import LintTool

# Emit deprecation warning on import
warnings.warn(
    "astra.tools.lint is deprecated, use astra.tools.linters instead",
    DeprecationWarning,
    stacklevel=2,
)


def parse_ruff_output(output: str):
    """Parse ruff output into issues. (Backward compatibility)"""
    return RuffLinter().parse(output)


def parse_eslint_output(output: str):
    """Parse eslint output into issues. (Backward compatibility)"""
    return ESLintLinter().parse(output)


def parse_mypy_output(output: str):
    """Parse mypy output into issues. (Backward compatibility)"""
    return MypyLinter().parse(output)


def parse_phpstan_output(output: str):
    """Parse PHPStan output into issues. (Backward compatibility)"""
    return PHPStanLinter().parse(output)


# Backward compatible LINTER_CONFIG (read-only)
LINTER_CONFIG = {
    "python": {
        "linters": [
            {
                "name": "ruff",
                "check_cmd": ["ruff", "check", "."],
                "fix_cmd": ["ruff", "check", "--fix", "."],
                "type_check": False,
            },
            {"name": "mypy", "check_cmd": ["mypy", "."], "fix_cmd": None, "type_check": True},
        ],
        "detect_files": ["*.py", "pyproject.toml", "setup.py"],
    },
    "javascript": {
        "linters": [
            {
                "name": "eslint",
                "check_cmd": ["npx", "eslint", "."],
                "fix_cmd": ["npx", "eslint", "--fix", "."],
                "type_check": False,
            }
        ],
        "detect_files": ["*.js", "*.jsx", "package.json"],
    },
    "typescript": {
        "linters": [
            {
                "name": "eslint",
                "check_cmd": ["npx", "eslint", "."],
                "fix_cmd": ["npx", "eslint", "--fix", "."],
                "type_check": False,
            },
        ],
        "detect_files": ["*.ts", "*.tsx", "tsconfig.json"],
    },
    "php": {
        "linters": [
            {
                "name": "phpstan",
                "check_cmd": ["vendor/bin/phpstan", "analyse"],
                "fix_cmd": None,
                "type_check": True,
            }
        ],
        "detect_files": ["*.php", "composer.json"],
    },
    "go": {
        "linters": [
            {
                "name": "go-vet",
                "check_cmd": ["go", "vet", "./..."],
                "fix_cmd": None,
                "type_check": False,
            },
            {
                "name": "gofmt",
                "check_cmd": ["gofmt", "-l", "."],
                "fix_cmd": ["gofmt", "-w", "."],
                "type_check": False,
            },
        ],
        "detect_files": ["*.go", "go.mod"],
    },
    "rust": {
        "linters": [
            {
                "name": "clippy",
                "check_cmd": ["cargo", "clippy"],
                "fix_cmd": ["cargo", "clippy", "--fix", "--allow-dirty"],
                "type_check": True,
            }
        ],
        "detect_files": ["*.rs", "Cargo.toml"],
    },
}

__all__ = [
    "LintTool",
    "LintIssue",
    "LintResult",
    "detect_language",
    "run_lint",
    "get_linters_for_language",
    "parse_ruff_output",
    "parse_eslint_output",
    "parse_mypy_output",
    "parse_phpstan_output",
    "LINTER_CONFIG",
]
