
from unittest.mock import MagicMock, patch

import pytest

from astra.core.context import ContextGatherer
from astra.core.tools import ToolRegistry


@pytest.fixture
def mock_gatherer():
    vector_store = MagicMock()
    tools = ToolRegistry()
    return ContextGatherer(vector_store, tools)

@pytest.mark.asyncio
async def test_gather_context_guard_limit(mock_gatherer):
    """Test that context guard truncates context when exceeding the limit."""

    # 1. Mock Manifests (get_manifest_files_for_project)
    with patch('astra.core.context.get_manifest_files_for_project') as mock_manifest:
        mock_manifest.return_value = {"huge_file.txt": "A" * 1000}

        # 2. Mock Path operations for Architecture
        with patch('pathlib.Path.exists') as mock_exists, \
             patch('pathlib.Path.read_text') as mock_read:

            # Ensure Architecture file is found and read
            mock_exists.return_value = True
            mock_read.return_value = "B" * 10000

            # 3. Mock Vector Store
            mock_node = MagicMock()
            mock_node.node.file_path = "test.py"
            mock_node.node.start_line = 1
            # Create a large enough content to trigger truncation logic when combined
            # Current: 1000 (Manifest) + 10000 (Arch) = 11000
            # Limit: 24000
            # Vector: 10 items * 2000 chars = 20000 chars. Total potential = 31000.
            mock_node.node.content = "C" * 2000
            mock_gatherer._vector_store.query.return_value = [mock_node] * 10

            # 4. Mock KG (Simple Pass)
            # We mock the tool retrieval to return None so KG logic is skipped for simplicity
            # or we can mock it to return a mock tool.
            mock_gatherer._tools.get = MagicMock(return_value=None)

            # Execute
            result = await mock_gatherer.gather("query", "collection", "project_path")

            # Assertions

            # Priority 1: Manifests - Should be present
            assert "huge_file.txt" in result

            # Priority 2: Architecture - Should be present (10k fits in remaining 23k)
            assert "B" * 100 in result

            # Priority 4: Vector - Should be present BUT truncated
            # We expect the result to contain the vector content...
            assert "Relevant Code Snippets" in result

            # The Critical Check: Did we respect the limit?
            # 24000 char limit. Allow slight overhead for headers/formatting (~2000 chars buffer)
            assert len(result) < 26000

            # Check for truncation marker
            assert "truncated" in result
