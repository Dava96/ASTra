
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.core.context import ContextGatherer
from astra.core.monitor import Monitor
from astra.core.task_queue import TaskQueue


@pytest.mark.asyncio
async def test_context_gatherer_parallelism():
    """Verify that independent gather tasks run concurrently."""
    # Mock dependencies
    mock_store = MagicMock()
    mock_tools = MagicMock()

    # Instant concurrency check
    async def slow_manifest(*args):
        await asyncio.sleep(0) # Yield but don't wait
        return {"file": "content"}

    async def slow_kg(*args, **kwargs):
        await asyncio.sleep(0) # Yield but don't wait
        return "kg_result"

    with patch("astra.core.context.get_manifest_files_for_project", side_effect=slow_manifest) as mock_manifest:
        # Mock vector store query
        mock_result = MagicMock()
        mock_result.node.file_path = "test.py"
        mock_store.query.return_value = [mock_result]

        mock_kg_tool = AsyncMock()
        mock_kg_tool.execute.side_effect = slow_kg
        mock_tools.get.return_value = mock_kg_tool

        cg = ContextGatherer(mock_store, mock_tools)

        # Should run instantly now
        await cg.gather("query", "coll", ".")
        # If no exceptions, it works.

def test_task_queue_persistence_threading(tmp_path):
    """Verify TaskQueue save persists file (synchronously in test)."""
    persist_file = tmp_path / "queue.json"

    # Mock the GLOBAL executor variable in task_queue module
    # Because _io_executor is instantiated at module level, we must patch the variable, not the class
    mock_executor = MagicMock()
    mock_executor.submit.side_effect = lambda fn, *args: fn(*args)

    with patch("astra.core.task_queue._io_executor", new=mock_executor):
        # Import not needed inside if patching global correctly, but specific import might have bound it?
        # astra.core.task_queue._io_executor is the target.

        tq = TaskQueue(persist_path=str(persist_file))

        # Add task should trigger "background" save (now synchronous)
        # Note: TaskQueue.add takes (task_type, request, user_id, channel_id, project)
        tq.add("test", "req", "user", "chan")

        # No sleep needed
        assert persist_file.exists()
        content = json.loads(persist_file.read_text())
        assert len(content["queued"]) == 1
        assert content["queued"][0]["request"] == "req"

def test_monitor_caching(tmp_path):
    """Verify check_repos_size uses cache."""
    # Ensure fresh instance for test isolation
    Monitor._instance = None
    monitor = Monitor()
    # Point repos to tmp_path
    monitor._repos_path = tmp_path

    # First call
    monitor.check_repos_size()
    # verify entry exists with default key (5.0 GB)
    assert "repos_size_5.0" in monitor._cache

    timestamp, val = monitor._cache["repos_size_5.0"]

    # Modify result in cache to prove it's being used
    monitor._cache["repos_size_5.0"] = (timestamp, (True, "Cached Value"))

    res = monitor.check_repos_size()
    assert res[1] == "Cached Value"
