"""Tests for Safeguard module."""

from unittest.mock import patch

import pytest

from astra.core.safeguard import Safeguard


class TestSafeguard:
    @pytest.fixture
    def safeguard(self):
        # Mock config via patch if needed, or rely on defaults
        with patch("astra.core.safeguard.get_config") as mock_conf:
            mock_conf.return_value.get.side_effect = lambda s, k, default=None: default
            yield Safeguard()

    def test_check_repo_size_valid(self, safeguard):
        """Test repo size within limits."""
        with patch("astra.core.safeguard.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"size": 10240}  # 10MB

            safe, msg = safeguard.check_repo_size("https://github.com/owner/repo")
            assert safe is True
            assert "10.0MB" in msg

    def test_check_repo_size_exceeded(self, safeguard):
        """Test repo size exceeds limit."""
        safeguard._max_repo_size_mb = 5  # Set low limit

        with patch("astra.core.safeguard.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"size": 10240}  # 10MB

            safe, msg = safeguard.check_repo_size("https://github.com/owner/repo")
            assert safe is False
            assert "exceeds limit" in msg

    def test_check_repo_size_not_found(self, safeguard):
        with patch("astra.core.safeguard.requests.get") as mock_get:
            mock_get.return_value.status_code = 404
            safe, msg = safeguard.check_repo_size("https://github.com/owner/repo")
            assert safe is False
            assert "not found" in msg

    def test_check_repo_size_api_error(self, safeguard):
        with patch("astra.core.safeguard.requests.get") as mock_get:
            mock_get.return_value.status_code = 500
            safe, msg = safeguard.check_repo_size("https://github.com/owner/repo")
            assert safe is True  # Fail open logic in code
            assert "API error" in msg

    def test_check_system_resources_ok(self, safeguard):
        with (
            patch("astra.core.safeguard.shutil.disk_usage") as mock_disk,
            patch("astra.core.safeguard.psutil.virtual_memory") as mock_mem,
        ):
            mock_disk.return_value.free = 2000 * 1024 * 1024  # 2000MB
            mock_mem.return_value.percent = 50.0

            safe, msg = safeguard.check_system_resources()
            assert safe is True
            assert "OK" in msg

    def test_check_system_resources_disk_full(self, safeguard):
        with patch("astra.core.safeguard.shutil.disk_usage") as mock_disk:
            mock_disk.return_value.free = 100 * 1024 * 1024  # 100MB

            safe, msg = safeguard.check_system_resources()
            assert safe is False
            assert "Low disk space" in msg

    def test_check_system_resources_memory_full(self, safeguard):
        with (
            patch("astra.core.safeguard.shutil.disk_usage") as mock_disk,
            patch("astra.core.safeguard.psutil.virtual_memory") as mock_mem,
        ):
            mock_disk.return_value.free = 2000 * 1024 * 1024
            mock_mem.return_value.percent = 95.0

            safe, msg = safeguard.check_system_resources()
            assert safe is False
            assert "memory critical" in msg
