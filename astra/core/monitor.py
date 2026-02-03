import logging
import shutil
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import psutil

from astra.config import get_config

logger = logging.getLogger(__name__)

def ttl_cache(seconds: int):
    """Simple TTL cache decorator."""
    def decorator(func: Callable):
        cache = {}
        async def wrapper(*args, **kwargs):
            now = time.time()
            # Use args as part of the key if needed, or just the function name for simple checks
            key = f"{func.__name__}:{args}:{kwargs}"
            if key in cache:
                timestamp, result = cache[key]
                if now - timestamp < seconds:
                    return result

            # Note: Health checks are currently synchronous in this class
            # but we'll wrap them for potential future async or just use directly
            import asyncio
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            cache[key] = (now, result)
            return result
        return wrapper
    return decorator

class Monitor:
    """Monitors system health and resource usage with O(1) caching."""

    _instance = None
    _cache: dict[str, tuple[float, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Monitor, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._config = get_config()
        self._repos_path = Path("./repos")
        self._graph_path = Path("./data/knowledge_graph.graphml")
        self._chroma_path = Path("./data/chromadb")
        self._initialized = True

    def _get_from_cache(self, key: str, ttl: int) -> Any | None:
        """Get value from internal cache if valid."""
        now = time.time()
        if key in self._cache:
            ts, val = self._cache[key]
            if now - ts < ttl:
                return val
        return None

    def _save_to_cache(self, key: str, val: Any):
        """Save value to internal cache with current timestamp."""
        self._cache[key] = (time.time(), val)

    def check_disk_usage(self, threshold_gb: float = 10.0) -> tuple[bool, str]:
        """Check if disk usage is within acceptable limits (Cached 1m)."""
        cache_key = f"disk_usage_{threshold_gb}"
        cached = self._get_from_cache(cache_key, 60)
        if cached: return cached

        usage = shutil.disk_usage(".")
        free_gb = usage.free / (1024 ** 3)

        if free_gb < threshold_gb:
            res = False, f"⚠️ Low disk space: {free_gb:.1f}GB free (threshold: {threshold_gb}GB)"
        else:
            percent = (usage.used / usage.total) * 100
            bar_len = 20
            filled_len = int(bar_len * percent / 100)
            bar = "|" * filled_len + "." * (bar_len - filled_len)
            res = True, f"Disk: [{bar}] {percent:.1f}% ({free_gb:.1f}GB free)"

        self._save_to_cache(cache_key, res)
        return res

    def check_repos_size(self, max_size_gb: float = 5.0) -> tuple[bool, str]:
        """Check total size of cloned repositories (Cached 5m)."""
        cache_key = f"repos_size_{max_size_gb}"
        cached = self._get_from_cache(cache_key, 300)
        if cached: return cached

        if not self._repos_path.exists():
            res = True, "No repos directory"
        else:
            try:
                total_bytes = sum(
                    f.stat().st_size for f in self._repos_path.rglob("*") if f.is_file()
                )
                total_gb = total_bytes / (1024 ** 3)
                if total_gb > max_size_gb:
                    res = False, f"⚠️ Repos directory large: {total_gb:.2f}GB (max: {max_size_gb}GB)"
                else:
                    res = True, f"Repos: {total_gb:.2f}GB"
            except Exception as e:
                res = True, f"Repos: Size check failed ({e})"

        self._save_to_cache(cache_key, res)
        return res

    def check_graph_staleness(self, max_age_hours: int = 24) -> tuple[bool, str]:
        """Check if knowledge graph is stale (Cached 10m)."""
        cache_key = f"graph_staleness_{max_age_hours}"
        cached = self._get_from_cache(cache_key, 600)
        if cached: return cached

        if not self._graph_path.exists():
            res = True, "No knowledge graph"
        else:
            try:
                mtime = datetime.fromtimestamp(self._graph_path.stat().st_mtime)
                age = datetime.now() - mtime
                if age > timedelta(hours=max_age_hours):
                    res = False, f"⚠️ Knowledge graph stale: last updated {age.days}d {age.seconds // 3600}h ago"
                else:
                    res = True, f"Graph: Updated {age.seconds // 60}m ago"
            except Exception:
                res = True, "Graph: Check failed"

        self._save_to_cache(cache_key, res)
        return res

    def check_memory(self, max_percent: float = 85.0) -> tuple[bool, str]:
        """Check system memory usage (Cached 30s)."""
        cache_key = f"memory_{max_percent}"
        cached = self._get_from_cache(cache_key, 30)
        if cached: return cached

        mem = psutil.virtual_memory()
        if mem.percent > max_percent:
            res = False, f"⚠️ High memory usage: {mem.percent}%"
        else:
            bar_len = 20
            filled_len = int(bar_len * mem.percent / 100)
            bar = "|" * filled_len + "." * (bar_len - filled_len)
            res = True, f"Memory: [{bar}] {mem.percent}% used"

        self._save_to_cache(cache_key, res)
        return res

    def check_docker_container(self, container_name: str = "astra") -> tuple[bool, str]:
        """Check Docker container status (Cached 1m)."""
        cache_key = f"docker_{container_name}"
        cached = self._get_from_cache(cache_key, 60)
        if cached: return cached

        try:
            import subprocess
            # Use a faster check if possible
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Status}}"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                res = True, f"Docker: {result.stdout.strip()}"
            else:
                res = True, "Docker: Not in container environment or not found"
        except Exception:
            res = True, "Docker: Check unavailable"

        self._save_to_cache(cache_key, res)
        return res

    def run_all_checks(self) -> dict[str, tuple[bool, str]]:
        """Run all health checks and return results."""
        return {
            "disk": self.check_disk_usage(),
            "repos": self.check_repos_size(),
            "graph": self.check_graph_staleness(),
            "memory": self.check_memory(),
            "docker": self.check_docker_container()
        }

    def get_alerts(self) -> list[str]:
        """Get list of alert messages for failed checks."""
        results = self.run_all_checks()
        return [msg for ok, msg in results.values() if not ok]
