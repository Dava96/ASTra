"""Remote provider for acquiring templates from SkillsMP."""

import logging
import time
from pathlib import Path
from typing import Any

import requests

from astra.config import get_config

logger = logging.getLogger(__name__)


class RemoteTemplateProvider:
    """Fetches templates from remote SkillsMP API with caching."""

    def __init__(self, cache_dir: str | Path | None = None):
        self._config = get_config()
        self._api_key = self._config.skills_mp.api_key
        self._base_url = self._config.skills_mp.endpoint

        if cache_dir:
            self._cache_dir = Path(cache_dir)
        else:
            self._cache_dir = Path("./data/cache/skills_mp")

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._index_cache_file = self._cache_dir / "index_cache.json"

    def is_enabled(self) -> bool:
        """Check if remote provider is enabled and configured."""
        return self._config.skills_mp.enabled and bool(self._api_key)

    def search(self, query: str, limit: int = 3, use_ai: bool = False) -> list[dict[str, Any]]:
        """Search for skills/templates matching the query."""
        if not self.is_enabled():
            return []

        headers = {"Authorization": f"Bearer {self._api_key}"}
        endpoint = "/skills/ai-search" if use_ai else "/skills/search"

        try:
            params = {"q": query}
            if not use_ai:
                params["limit"] = limit
                # params["sortBy"] = "stars" # Optional optimization

            response = requests.get(
                f"{self._base_url}{endpoint}",
                params=params,
                headers=headers,
                timeout=5
            )
            response.raise_for_status()
            data = response.json()

            # API returns { "data": { "skills": [...] } }
            skills = data.get("data", {}).get("skills", [])
            return skills[:limit]

        except requests.RequestException as e:
            logger.warning(f"SkillsMP search failed: {e}")
            return []

    def fetch_content(self, skill_id: str) -> str | None:
        """Fetch the content of a specific skill/template."""
        if not self.is_enabled():
            return None

        # Check local cache
        cached_file = self._cache_dir / f"{skill_id}.md"
        expiry_seconds = self._config.skills_mp.cache_expiry_hours * 3600

        if cached_file.exists():
            age = time.time() - cached_file.stat().st_mtime
            if age < expiry_seconds:
                try:
                    return cached_file.read_text(encoding="utf-8")
                except Exception:
                    pass

        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            # Note: API Doc didn't explicitly list GET /skills/{id}, but it is standard.
            # We assume it returns the skill object which contains 'content' or similar.
            response = requests.get(
                f"{self._base_url}/skills/{skill_id}",
                headers=headers,
                timeout=5
            )
            response.raise_for_status()

            data = response.json()
            # Standardizing on 'content' field availability
            skill_data = data.get("data", {})
            content = skill_data.get("content") or skill_data.get("markdown")

            if content:
                # Update cache
                cached_file.write_text(content, encoding="utf-8")
                return content

        except requests.RequestException as e:
            logger.warning(f"SkillsMP fetch failed: {e}")

        return None
