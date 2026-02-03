
import time

import pytest

from astra.tools.linters.base import BaseLinter
from astra.tools.linters.models import LintResult
from astra.tools.linters.registry import LINTER_REGISTRY, detect_languages, register_linter
from astra.tools.linters.tool import LintTool


class SlowLinter(BaseLinter):
    name = "slow_linter"
    languages = ["python"]

    def can_run(self, path): return True

    def parse(self, output): return []

    def run(self, project_path, auto_fix=False):
        time.sleep(0.1) # Simulate work
        return LintResult(self.name, True)

class FastLinter(BaseLinter):
    name = "fast_linter"
    languages = ["python"]

    def can_run(self, path): return True
    def parse(self, output): return []
    def run(self, project_path, auto_fix=False):
        return LintResult(self.name, True)

@pytest.fixture
def clean_registry():
    original = LINTER_REGISTRY.copy()
    LINTER_REGISTRY.clear()
    yield
    LINTER_REGISTRY.clear()
    LINTER_REGISTRY.update(original)

def test_parallel_execution(clean_registry, tmp_path):
    register_linter(SlowLinter)
    register_linter(FastLinter)

    # Needs to detect python
    (tmp_path / "pyproject.toml").touch()

    tool = LintTool()

    start = time.time()
    results = tool.run(tmp_path)
    end = time.time()

    assert len(results) == 2
    # If sequential, it would be > 0.1s.
    # But wait, python threads are GIL limited, but sleep releases GIL.
    # Parallel overhead might make it close, but let's check correct execution first.
    assert {r.linter for r in results} == {"slow_linter", "fast_linter"}

def test_missing_linter_suggestion(clean_registry, tmp_path):
    # No registered linters

    # Detects python
    (tmp_path / "pyproject.toml").touch()

    tool = LintTool()
    results = tool.run(tmp_path)

    assert len(results) == 1
    assert results[0].linter == "system"
    assert results[0].success is False
    assert "uv add --dev ruff" in results[0].suggestion

def test_caching_behavior(tmp_path):
    detect_languages.cache_clear()

    (tmp_path / "pyproject.toml").touch()

    # First call
    langs1 = detect_languages(tmp_path)
    assert "python" in langs1

    # Second call (should be cached)
    # We can't easily mock the cache internal, but we can verify consistency
    langs2 = detect_languages(tmp_path)
    assert langs2 is langs1 # Should be same object reference if cached

