"""Tests for SizeEstimator."""

import pytest

from astra.ingestion.size_estimator import SizeEstimator


@pytest.fixture
def estimator():
    return SizeEstimator()


def test_estimate_basic(estimator, tmp_path):
    # Create dummy structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n" * 10)
    (tmp_path / "src" / "utils.py").write_text("class Util: pass\n" * 20)
    (tmp_path / "README.md").write_text("# Test")

    result = estimator.estimate(str(tmp_path), sample_rate=1.0)

    assert result["total_files"] >= 2
    assert result["total_size_mb"] >= 0
    assert result["projected_nodes"] > 0
    assert result["projected_db_size_mb"] >= 0


def test_estimate_nonexistent(estimator):
    result = estimator.estimate("/nonexistent/path")
    assert "error" in result
