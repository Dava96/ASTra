from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from astra.core.monitor import Monitor
from astra.core.safeguard import Safeguard


@pytest.fixture
def monitor():
    cfg = MagicMock()

    # Mock get() to return sensible defaults for monitor
    def mock_get(*args, **kwargs):
        if "threshold_gb" in args:
            return 10.0
        return kwargs.get("default")

    cfg.get.side_effect = mock_get

    with patch("astra.core.monitor.get_config", return_value=cfg):
        m = Monitor()
        m._cache.clear()
        return m


@pytest.fixture
def safeguard():
    cfg = MagicMock()

    # Mock get() to return sensible defaults for safeguard
    def mock_get(*args, **kwargs):
        if "max_repo_size_mb" in args:
            return 500
        if "min_disk_space_mb" in args:
            return 1000
        if "max_memory_percent" in args:
            return 90.0
        return kwargs.get("default")

    cfg.get.side_effect = mock_get

    with patch("astra.core.safeguard.get_config", return_value=cfg):
        return Safeguard()


# --- Monitor Tests ---


def test_monitor_disk_usage(monitor):
    with patch("shutil.disk_usage") as mock_ds:
        # Mock 5GB free
        mock_ds.return_value = MagicMock(free=5 * (1024**3))
        ok, msg = monitor.check_disk_usage(threshold_gb=10.0)
        assert ok is False
        assert "Low disk space" in msg

        # Mock 15GB free
        monitor.clear_cache()
        mock_ds.return_value = MagicMock(free=15 * (1024**3))
        ok, msg = monitor.check_disk_usage(threshold_gb=10.0)
        assert ok is True
        assert "15.0GB free" in msg


def test_monitor_repos_size(monitor):
    with patch.object(Path, "exists", return_value=True), patch.object(Path, "rglob") as mock_rglob:
        m1 = MagicMock()
        m1.is_file.return_value = True
        m1.stat.return_value.st_size = 1024 * 1024  # 1MB

        mock_rglob.return_value = [m1]

        ok, msg = monitor.check_repos_size(max_size_gb=0.0001)  # Very small limit
        assert ok is False

        ok, msg = monitor.check_repos_size(max_size_gb=1.0)
        assert ok is True


def test_monitor_graph_staleness(monitor):
    with patch.object(Path, "exists") as mock_exists, patch.object(Path, "stat") as mock_stat:
        mock_exists.return_value = False
        ok, msg = monitor.check_graph_staleness()
        assert ok is True

        mock_exists.return_value = True
        monitor.clear_cache()
        # Mock mtime to be 2 days ago
        two_days_ago = (datetime.now() - timedelta(days=2)).timestamp()
        mock_stat.return_value.st_mtime = two_days_ago

        ok, msg = monitor.check_graph_staleness(max_age_hours=24)
        assert ok is False


def test_monitor_memory(monitor):
    with patch("psutil.virtual_memory") as mock_mem:
        mock_mem.return_value.percent = 90.0
        ok, msg = monitor.check_memory(max_percent=85.0)
        assert ok is False

        mock_mem.return_value.percent = 50.0
        monitor.clear_cache()
        ok, msg = monitor.check_memory(max_percent=85.0)
        assert ok is True


def test_monitor_docker(monitor):
    with patch("astra.core.monitor.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "100MB / 1GB"
        ok, msg = monitor.check_docker_container()
        assert ok is True
        assert "100MB" in msg

        mock_run.side_effect = Exception("No docker")
        ok, msg = monitor.check_docker_container()
        assert ok is True  # Failure returns True (unavailable)


def test_monitor_run_all(monitor):
    with (
        patch.object(monitor, "check_disk_usage", return_value=(True, "ok")),
        patch.object(monitor, "check_repos_size", return_value=(False, "bad")),
        patch.object(monitor, "check_graph_staleness", return_value=(True, "ok")),
        patch.object(monitor, "check_memory", return_value=(True, "ok")),
        patch.object(monitor, "check_docker_container", return_value=(True, "ok")),
    ):
        results = monitor.run_all_checks()
        assert results["repos"][0] is False
        alerts = monitor.get_alerts()
        assert len(alerts) == 1
        assert alerts[0] == "bad"


# --- Safeguard Tests ---


def test_safeguard_repo_size(safeguard):
    with patch("requests.get") as mock_get:
        # Success path
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"size": 102400}  # 100MB
        mock_get.return_value = mock_resp

        ok, msg = safeguard.check_repo_size("https://github.com/owner/repo")
        assert ok is True

        # Too large
        safeguard.clear_cache()
        safeguard._max_repo_size_mb = 10
        ok, msg = safeguard.check_repo_size("https://github.com/owner/repo")
        assert ok is False

        # 404
        safeguard.clear_cache()
        mock_resp.status_code = 404
        ok, msg = safeguard.check_repo_size("https://github.com/owner/repo")
        assert ok is False

        # Error skipping
        safeguard.clear_cache()
        mock_resp.status_code = 500
        ok, msg = safeguard.check_repo_size("https://github.com/owner/repo")
        assert ok is True  # Skips on API error


def test_monitor_repos_size_missing(monitor):
    with patch.object(Path, "exists", return_value=False):
        ok, msg = monitor.check_repos_size()
        assert ok is True
        assert "No repos directory" in msg


def test_monitor_graph_not_stale(monitor):
    with patch.object(Path, "exists", return_value=True), patch.object(Path, "stat") as mock_stat:
        # Mock mtime to be 10 minutes ago
        ten_mins_ago = (datetime.now() - timedelta(minutes=10)).timestamp()
        mock_stat.return_value.st_mtime = ten_mins_ago

        ok, msg = monitor.check_graph_staleness(max_age_hours=24)
        assert ok is True
        assert "Graph: Updated" in msg


def test_monitor_docker_not_env(monitor):
    with patch("astra.core.monitor.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        ok, msg = monitor.check_docker_container()
        assert ok is True
        assert "Not in container environment" in msg


# --- Safeguard Tests ---


def test_safeguard_repo_size_edge_cases(safeguard):
    with patch("requests.get") as mock_get:
        # Git suffix
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"size": 1024}
        mock_get.return_value = mock_resp

        ok, msg = safeguard.check_repo_size("https://github.com/owner/repo.git")
        assert ok is True

        # Parse error
        ok, msg = safeguard.check_repo_size("not-a-url")
        assert ok is True
        assert "Could not parse URL" in msg

        # Connection error
        mock_get.side_effect = Exception("Connection refused")
        ok, msg = safeguard.check_repo_size("https://github.com/owner/repo")
        assert ok is True
        assert "Connection error" in msg


def test_safeguard_token_usage(safeguard):
    with patch("os.getenv", return_value="fake-token"), patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"size": 1024}
        mock_get.return_value = mock_resp

        safeguard.check_repo_size("https://github.com/owner/repo")
        args, kwargs = mock_get.call_args
        assert "Authorization" in kwargs["headers"]
        assert "token fake-token" in kwargs["headers"]["Authorization"]


def test_safeguard_resources(safeguard):
    with patch("shutil.disk_usage") as mock_ds, patch("psutil.virtual_memory") as mock_mem:
        mock_ds.return_value = MagicMock(free=2000 * (1024**2))  # 2000MB
        mock_mem.return_value.percent = 50.0

        ok, msg = safeguard.check_system_resources()
        assert ok is True

        # Low disk
        safeguard.clear_cache()
        mock_ds.return_value = MagicMock(free=500 * (1024**2))  # 500MB
        ok, msg = safeguard.check_system_resources()
        assert ok is False

        # High memory
        safeguard.clear_cache()
        mock_ds.return_value = MagicMock(free=2000 * (1024**2))
        mock_mem.return_value.percent = 95.0
        ok, msg = safeguard.check_system_resources()
        assert ok is False
