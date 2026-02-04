"""Tests for system Monitor."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from astra.core.monitor import Monitor


class TestMonitor:
    """Test Monitor health checks."""

    @pytest.fixture(autouse=True)
    def monitor(self):
        with patch("astra.core.monitor.get_config") as mock:
            mock.return_value = MagicMock()
            m = Monitor()
            # Reset cache and singleton state for each test if possible
            # or just clear the cache dictionary
            m._cache.clear()
            return m

    def test_check_disk_usage_ok(self, monitor):
        """Test disk check when space is sufficient."""
        with patch("shutil.disk_usage") as mock:
            mock.return_value = MagicMock(free=20 * 1024**3)  # 20GB free
            ok, msg = monitor.check_disk_usage(threshold_gb=10.0)
            assert ok is True
            assert "20.0GB free" in msg

    def test_check_disk_usage_low(self, monitor):
        """Test disk check when space is low."""
        with patch("shutil.disk_usage") as mock:
            mock.return_value = MagicMock(free=5 * 1024**3)  # 5GB free
            ok, msg = monitor.check_disk_usage(threshold_gb=10.0)
            assert ok is False
            assert "Low disk space" in msg

    def test_check_repos_size_no_dir(self, monitor):
        """Test repos check when directory doesn't exist."""
        monitor._repos_path = Path("/nonexistent/path")
        ok, msg = monitor.check_repos_size()
        assert ok is True
        assert "No repos directory" in msg

    def test_check_repos_size_within_limit(self, monitor):
        """Test repos check when size is acceptable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor._repos_path = Path(tmpdir)
            # Create a small file
            (Path(tmpdir) / "test.txt").write_text("small")

            ok, msg = monitor.check_repos_size(max_size_gb=1.0)
            assert ok is True

    def test_check_graph_staleness_no_file(self, monitor):
        """Test graph check when file doesn't exist."""
        monitor._graph_path = Path("/nonexistent/graph.json")
        ok, msg = monitor.check_graph_staleness()
        assert ok is True
        assert "No knowledge graph" in msg

    def test_check_graph_staleness_fresh(self, monitor):
        """Test graph check when recently updated."""
        import os
        import tempfile

        # Create temp file and close it before checking
        fd, path = tempfile.mkstemp(suffix=".json")
        os.write(fd, b"{}")
        os.close(fd)

        try:
            monitor._graph_path = Path(path)
            ok, msg = monitor.check_graph_staleness(max_age_hours=24)
            assert ok is True
        finally:
            os.unlink(path)

    def test_check_memory_ok(self, monitor):
        """Test memory check when usage is acceptable."""
        with patch("psutil.virtual_memory") as mock:
            mock.return_value = MagicMock(percent=50.0)
            ok, msg = monitor.check_memory(max_percent=85.0)
            assert ok is True
            assert "50.0% used" in msg

    def test_check_memory_high(self, monitor):
        """Test memory check when usage is high."""
        with patch("psutil.virtual_memory") as mock:
            mock.return_value = MagicMock(percent=90.0)
            ok, msg = monitor.check_memory(max_percent=85.0)
            assert ok is False
            assert "High memory usage" in msg

    def test_run_all_checks(self, monitor):
        """Test running all health checks."""
        with patch("shutil.disk_usage") as disk_mock, patch("psutil.virtual_memory") as mem_mock:
            disk_mock.return_value = MagicMock(free=50 * 1024**3)
            mem_mock.return_value = MagicMock(percent=40.0)
            monitor._repos_path = Path("/nonexistent")
            monitor._graph_path = Path("/nonexistent")

            results = monitor.run_all_checks()

            assert "disk" in results
            assert "memory" in results
            assert "repos" in results
            assert "graph" in results

    def test_get_alerts_returns_failures(self, monitor):
        """Test that get_alerts returns failed check messages."""
        with patch("shutil.disk_usage") as disk_mock, patch("psutil.virtual_memory") as mem_mock:
            disk_mock.return_value = MagicMock(free=2 * 1024**3)  # Low
            mem_mock.return_value = MagicMock(percent=95.0)  # High
            monitor._repos_path = Path("/nonexistent")
            monitor._graph_path = Path("/nonexistent")

            alerts = monitor.get_alerts()

            assert len(alerts) >= 2
            assert any("Low disk" in a for a in alerts)
            assert any("High memory" in a for a in alerts)
