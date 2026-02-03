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

            assert "Source 1: [T1](h1)" in result
            assert "b1" in result
            assert "Source 2: [T2](h2)" in result

    @pytest.mark.asyncio
    async def test_execute_empty(self):
        """Test empty search results."""
        tool = SearchTool()

        with patch('astra.tools.search.DDGS') as MockDDGS:
            mock_instance = MockDDGS.return_value.__enter__.return_value
            mock_instance.text.return_value = []

            result = await tool.execute("query")
            assert "No search results found" in result

    @pytest.mark.asyncio
    async def test_execute_error(self):
        """Test search exception handling."""
        tool = SearchTool()

        with patch('astra.tools.search.DDGS') as MockDDGS:
            mock_instance = MockDDGS.return_value.__enter__.return_value
            mock_instance.text.side_effect = Exception("Search API Down")

            result = await tool.execute("query")
            assert result == "No search results found." # Returns formatted empty list on error
            # Or check generic "Search failed" if implemented?
            # Code: return self._format_results([]) -> "No search results found."
