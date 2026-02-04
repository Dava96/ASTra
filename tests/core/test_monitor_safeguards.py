"""Integration tests for ASTra Monitoring and Safeguards."""

from unittest.mock import MagicMock, patch

import pytest

from astra.core.monitor import Monitor


class TestMonitorSafeguards:
    """Tests the proactive monitoring and resource safeguard logic."""

    @pytest.fixture
    def monitor(self):
        # Clear singleton instance if it exists
        Monitor._instance = None
        m = Monitor()
        m.clear_cache()
        return m

    def test_disk_usage_alert(self, monitor):
        """Verify that low disk space triggers an alert."""
        # Mock shutil.disk_usage to return a very small free space
        # usage = (total, used, free)
        mock_usage = MagicMock()
        mock_usage.free = 1 * (1024**3) # 1GB free
        mock_usage.total = 100 * (1024**3)
        mock_usage.used = 99 * (1024**3)

        with patch("shutil.disk_usage", return_value=mock_usage):
            # Check with a 10GB threshold
            ok, msg = monitor.check_disk_usage(threshold_gb=10.0)

            assert ok is False
            assert "Low disk space" in msg

    def test_memory_usage_alert(self, monitor):
        """Verify that high memory usage triggers an alert."""
        mock_mem = MagicMock()
        mock_mem.percent = 90.0

        with patch("psutil.virtual_memory", return_value=mock_mem):
            ok, msg = monitor.check_memory(max_percent=85.0)

            assert ok is False
            assert "High memory usage" in msg

    def test_graph_staleness_alert(self, monitor):
        """Verify that a stale knowledge graph triggers an alert."""
        # Mock file stat to be 2 days old
        import time

        stale_time = time.time() - (48 * 3600) # 48 hours ago

        mock_stat = MagicMock()
        mock_stat.st_mtime = stale_time

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.stat", return_value=mock_stat):

            ok, msg = monitor.check_graph_staleness(max_age_hours=24)

            assert ok is False
            assert "Knowledge graph stale" in msg

    def test_run_all_checks_summary(self, monitor):
        """Verify that run_all_checks compiles results correctly."""
        with patch.object(monitor, "check_disk_usage", return_value=(False, "Disk fail")), \
             patch.object(monitor, "check_memory", return_value=(True, "Mem ok")), \
             patch.object(monitor, "check_repos_size", return_value=(True, "Repo ok")), \
             patch.object(monitor, "check_graph_staleness", return_value=(True, "Graph ok")), \
             patch.object(monitor, "check_docker_container", return_value=(True, "Docker ok")):

            results = monitor.run_all_checks()
            assert results["disk"][0] is False
            assert results["memory"][0] is True

            alerts = monitor.get_alerts()
            assert len(alerts) == 1
            assert "Disk fail" in alerts
