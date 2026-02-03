from unittest.mock import patch

import pytest

from astra.tools.linters.base import BaseLinter
from astra.tools.linters.models import LintResult
from astra.tools.linters.registry import (
    LINTER_REGISTRY,
    detect_language,
    detect_languages,  # Added
    detect_linters,  # Added
    get_linter,
    get_linters_for_language,
    register_linter,
    run_lint,
)


@pytest.fixture
def clean_registry():
    original = LINTER_REGISTRY.copy()
    yield
    LINTER_REGISTRY.clear()
    LINTER_REGISTRY.update(original)
    # Clear caches
    detect_language.cache_clear() if hasattr(detect_language, "cache_clear") else None
    detect_languages.cache_clear()
    detect_linters.cache_clear()
    # Also clear manifest cache since detect_language uses it
    from astra.tools.manifest import get_project_manifest
    get_project_manifest.cache_clear()

class MockLinter(BaseLinter):
    name = "mock_linter"
    languages = ["python"]
    is_type_checker = False

    def can_run(self, path): return True
    def run(self, path, auto_fix=False): return LintResult(self.name, True, 0, 0)
    def parse(self, output): return [] # Abstract method from BaseLinter?

class MockTypeChecker(BaseLinter):
    name = "mock_type"
    languages = ["python"]
    is_type_checker = True

    def can_run(self, path): return True
    def run(self, path, auto_fix=False): return LintResult(self.name, True, 0, 0)
    def parse(self, output): return []

def test_registry_mechanics(clean_registry):
    LINTER_REGISTRY.clear()

    register_linter(MockLinter)
    assert "mock_linter" in LINTER_REGISTRY

    linter = get_linter("mock_linter")
    assert isinstance(linter, MockLinter)

    assert get_linter("unknown") is None

def test_get_linters_for_language(clean_registry):
    LINTER_REGISTRY.clear()
    register_linter(MockLinter)
    register_linter(MockTypeChecker)

    py_linters = get_linters_for_language("python")
    assert len(py_linters) == 2

    js_linters = get_linters_for_language("javascript")
    assert len(js_linters) == 0

def test_detect_language(tmp_path, clean_registry):
    assert detect_language(tmp_path) is None

    (tmp_path / "pyproject.toml").touch()
    assert detect_language(tmp_path) == "python"
    (tmp_path / "pyproject.toml").unlink()

    (tmp_path / "package.json").touch()
    assert detect_language(tmp_path) == "javascript"
    (tmp_path / "package.json").unlink()

    (tmp_path / "tsconfig.json").touch()
    assert detect_language(tmp_path) == "typescript"

def test_run_lint(clean_registry, tmp_path):
    LINTER_REGISTRY.clear()
    register_linter(MockLinter)
    register_linter(MockTypeChecker)

    # Auto detect python
    (tmp_path / "pyproject.toml").touch()

    # Normal run (no type check)
    results = run_lint(tmp_path)
    assert len(results) == 1
    assert results[0].linter == "mock_linter"

    # With type check
    results = run_lint(tmp_path, type_check=True)
    assert len(results) == 2

    # Force language
    results = run_lint(tmp_path, language="javascript")
    assert len(results) == 0

def test_run_lint_skips(clean_registry, tmp_path):
    LINTER_REGISTRY.clear()
    register_linter(MockLinter)

    with patch.object(MockLinter, 'can_run', return_value=False):
        results = run_lint(tmp_path, language="python")
        assert len(results) == 0
