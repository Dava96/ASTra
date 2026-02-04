import functools
import logging
from pathlib import Path

from astra.tools.linters.base import BaseLinter
from astra.tools.linters.models import LintResult

logger = logging.getLogger(__name__)

# Global registry of linters
LINTER_REGISTRY: dict[str, type[BaseLinter]] = {}


def register_linter(cls: type[BaseLinter]) -> type[BaseLinter]:
    """Decorator to register a linter class.

    Usage:
        @register_linter
        class RuffLinter(BaseLinter):
            name = "ruff"
            languages = ["python"]
    """
    if not cls.name:
        raise ValueError(f"Linter {cls.__name__} must define a 'name' attribute")

    LINTER_REGISTRY[cls.name] = cls
    logger.debug(f"Registered linter: {cls.name}")
    return cls


def get_available_linters() -> list[str]:
    """Get list of all registered linter names."""
    return list(LINTER_REGISTRY.keys())


@functools.lru_cache
def detect_languages(project_path: str | Path) -> set[str]:
    """Detect all languages in a project (Cached)."""
    path = Path(project_path)
    langs = set()

    # Fast O(1) checks
    if (path / "tsconfig.json").exists() or (path / "package.json").exists():
        langs.add("javascript")
        langs.add("typescript")

    if (
        (path / "pyproject.toml").exists()
        or (path / "setup.py").exists()
        or (path / "requirements.txt").exists()
    ):
        langs.add("python")

    if (path / "composer.json").exists():
        langs.add("php")

    if (path / "go.mod").exists():
        langs.add("go")

    if (path / "Cargo.toml").exists():
        langs.add("rust")

    return langs


# Deprecated but kept for backward compatibility
def detect_language(project_path: str | Path) -> str | None:
    """Detect primary language (Deprecated)."""
    langs = detect_languages(project_path)
    return next(iter(langs)) if langs else None


@functools.lru_cache
def detect_linters(project_path: str | Path, language: str | None = None) -> list[BaseLinter]:
    """Detect available linters for a project (Cached)."""
    project_path = Path(project_path)
    detected = []

    # If language constraint is given, filter by it
    target_languages = {language} if language else detect_languages(project_path)

    for linter_cls in LINTER_REGISTRY.values():
        # Check language match
        if not any(lang in target_languages for lang in linter_cls.languages):
            continue

        # Check if linter applies (O(1) checks first)
        linter = linter_cls()
        if linter.can_run(project_path):
            detected.append(linter)

    return detected


def get_linter(name: str) -> BaseLinter | None:
    """Get a linter instance by name."""
    linter_cls = LINTER_REGISTRY.get(name)
    if linter_cls:
        return linter_cls()
    return None


def get_linters_for_language(language: str) -> list[BaseLinter]:
    """Get all linters that support a given language."""
    linters = []
    for linter_cls in LINTER_REGISTRY.values():
        if language in linter_cls.languages:
            linters.append(linter_cls())
    return linters


def run_lint(
    project_path: str | Path,
    language: str | None = None,
    type_check: bool = False,
    auto_fix: bool = False,
) -> list[LintResult]:
    """Run linters on a project."""
    project_path = Path(project_path)

    linters = detect_linters(project_path, language)

    # Missing Linter Logic
    if not linters:
        langs = {language} if language else detect_languages(project_path)
        if "python" in langs:
            return [
                LintResult(
                    linter="system",
                    success=False,
                    error_count=1,
                    issues=[],
                    suggestion="Python project detected but no linter found. Recommended: `uv add --dev ruff` or `pip install ruff`.",
                )
            ]
        if "javascript" in langs or "typescript" in langs:
            return [
                LintResult(
                    linter="system",
                    success=False,
                    error_count=1,
                    issues=[],
                    suggestion="JS/TS project detected but no linter found. Recommended: `npm install --save-dev eslint`.",
                )
            ]

        return []

    results = []
    for linter in linters:
        if linter.is_type_checker and not type_check:
            continue

        logger.info(f"Running {linter.name} on {project_path}")
        result = linter.run(project_path, auto_fix=auto_fix)
        results.append(result)
        logger.info(f"{linter.name}: {result.error_count} errors")

    return results


# Import linters to trigger registration
# This must be at the bottom to avoid circular imports
from astra.tools.linters.implementations import (  # noqa: E402, F401
    eslint,
    go,
    mypy,
    phpstan,
    ruff,
    rust,
)
