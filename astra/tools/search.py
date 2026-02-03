"""Web search tool using DuckDuckGo."""

import logging
from typing import Any

from duckduckgo_search import DDGS

from astra.core.tools import BaseTool

logger = logging.getLogger(__name__)


class SearchTool(BaseTool):
    """Tool for performing web searches."""

    name = "search_web"
    description = "Search the internet for documentation, libraries, or technical solutions."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to perform"
            },
            "site": {
                "type": "string",
                "description": "Restrict search to a specific domain (e.g. 'python.org')"
            }
        },
        "required": ["query"]
    }

    def __init__(self, max_results: int = 5):
        self._max_results = max_results

    async def execute(self, query: str, site: str | None = None, **kwargs: Any) -> list[dict[str, str]]:
        """Execute web search and return structured results."""
        if site:
            query = f"site:{site} {query}"

        results = self._search(query)
        return results

    def _search(self, query: str) -> list[dict[str, str]]:
        """Perform a web search."""
        logger.info(f"Searching web for: {query}")

        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=self._max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "href": r.get("href", ""),
                        "body": r.get("body", "")
                    })
            return results
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
