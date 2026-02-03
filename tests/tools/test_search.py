"""Tests for SearchTool."""

from unittest.mock import patch

import pytest

from astra.tools.search import SearchTool


class TestSearchTool:
    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful search execution."""
        tool = SearchTool(max_results=2)

        mock_results = [
            {"title": "T1", "href": "h1", "body": "b1"},
            {"title": "T2", "href": "h2", "body": "b2"}
        ]

        with patch('astra.tools.search.DDGS') as MockDDGS:
            mock_instance = MockDDGS.return_value.__enter__.return_value
            mock_instance.text.return_value = mock_results

            result = await tool.execute("query")

            result = await tool.execute("query")

            assert isinstance(result, list)
            assert result[0]["title"] == "T1"
            assert result[0]["href"] == "h1"
            assert result[1]["body"] == "b2"

    @pytest.mark.asyncio
    async def test_execute_empty(self):
        """Test empty search results."""
        tool = SearchTool()

        with patch('astra.tools.search.DDGS') as MockDDGS:
            mock_instance = MockDDGS.return_value.__enter__.return_value
            mock_instance.text.return_value = []

            result = await tool.execute("query")
            assert result == []

    @pytest.mark.asyncio
    async def test_execute_error(self):
        """Test search exception handling."""
        tool = SearchTool()

        with patch('astra.tools.search.DDGS') as MockDDGS:
            mock_instance = MockDDGS.return_value.__enter__.return_value
            mock_instance.text.side_effect = Exception("Search API Down")

            result = await tool.execute("query")
            assert result == []
            # Or check generic "Search failed" if implemented?
            # Code: return self._format_results([]) -> "No search results found."
