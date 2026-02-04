"""Resource safeguards and safety checks."""

import logging
import shutil
from pathlib import Path
from urllib.parse import urlparse

import psutil
import requests

from astra.config import get_config

logger = logging.getLogger(__name__)


class Safeguard:
    """Manages system resource and safety limits."""

    def __init__(self):
        self._config = get_config()
        self._max_repo_size_mb = self._config.get("safety", "max_repo_size_mb", default=500)
        self._min_disk_space_mb = self._config.get("safety", "min_disk_space_mb", default=1000)
        self._max_memory_percent = self._config.get("safety", "max_memory_percent", default=90.0)

        # O(1) Caching
        self._cache_repo: dict[str, tuple[float, tuple[bool, str]]] = {}  # url -> (ts, result)
        self._cache_sys: tuple[float, tuple[bool, str]] | None = None

    def clear_cache(self):
        """Clear the internal caches."""
        self._cache_repo.clear()
        self._cache_sys = None

    def check_repo_size(self, repo_url: str) -> tuple[bool, str]:
        """Check if a GitHub repository is within size limits."""
        # Parse URL to get owner/repo
        try:
            path = urlparse(repo_url).path.strip("/")
            if path.endswith(".git"):
                path = path[:-4]
            owner, repo = path.split("/")[-2:]
        except Exception:
            # Fallback for non-standard URLs, treat as safe/unknown but log
            logger.warning(f"Could not parse repo URL for size check: {repo_url}")
            return True, "Could not parse URL"

        if repo_url in self._cache_repo:
            ts, res = self._cache_repo[repo_url]
            import time

            if time.time() - ts < 1800:  # 30 min cache
                return res

        # Call GitHub API
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {"Accept": "application/vnd.github.v3+json"}

        # Add token if available for higher rate limits
        import os

        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"

        try:
            resp = requests.get(api_url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                size_kb = data.get("size", 0)
                size_mb = size_kb / 1024

                if size_mb > self._max_repo_size_mb:
                    res = (
                        False,
                        f"Repository size ({size_mb:.1f}MB) exceeds limit ({self._max_repo_size_mb}MB)",
                    )
                else:
                    res = True, f"Size: {size_mb:.1f}MB"

            elif resp.status_code == 404:
                res = False, "Repository not found or private"
            else:
                logger.warning(f"GitHub API Error: {resp.status_code}")
                res = True, "Skipped check (API error)"
        except Exception as e:
            logger.warning(f"Failed to check repo size: {e}")
            res = True, "Skipped check (Connection error)"

        import time

        self._cache_repo[repo_url] = (time.time(), res)
        return res

    def check_system_resources(self) -> tuple[bool, str]:
        """Check if system has enough resources (Cached 1m)."""
        import time

        if self._cache_sys:
            ts, res = self._cache_sys
            if time.time() - ts < 60:
                return res

        # Check Disk Space
        target_path = Path(".").resolve()
        usage = shutil.disk_usage(target_path)
        free_mb = usage.free / (1024 * 1024)

        if free_mb < self._min_disk_space_mb:
            res = False, f"Low disk space: {free_mb:.1f}MB free (min {self._min_disk_space_mb}MB)"
        else:
            # Check Memory
            mem = psutil.virtual_memory()
            if mem.percent > self._max_memory_percent:
                res = False, f"System memory critical: {mem.percent}% used"
            else:
                res = True, "Resources OK"

        self._cache_sys = (time.time(), res)
        return res
