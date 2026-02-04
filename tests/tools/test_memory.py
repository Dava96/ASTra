"""Tests for Working Memory Tool."""

from unittest.mock import patch

import pytest

from astra.adapters.chromadb_store import ChromaDBStore
from astra.tools.memory.tool import _RECALL_CACHE, MemoryTool


@pytest.fixture
def memory_tool(tmp_path):
    """Fixture for memory tool with temp store."""
    persist_path = tmp_path / "chroma_memory_test"
    store = ChromaDBStore(persist_path=str(persist_path))
    # Clear cache before each test
    _RECALL_CACHE.clear()
    tool = MemoryTool(store=store)
    yield tool


@pytest.mark.asyncio
async def test_memory_lifecycle_structured(memory_tool):
    """Test full lifecycle with structured output."""
    project = "test_struct"

    # 1. Remember
    res = await memory_tool.execute(
        "remember",
        content="User likes blue.",
        tags="preferences",
        project_name=project,
        format="dict",
    )
    assert res["success"] is True
    assert "✅ Stored memory" in res["message"]
    memory_id = res["data"][0]["id"]

    # 2. Recall (O(1) Cache Miss)
    res = await memory_tool.execute("recall", query="blue", project_name=project, format="dict")
    assert res["success"] is True
    assert len(res["data"]) > 0
    assert res["data"][0]["content"] == "User likes blue."

    # 3. Recall (O(1) Cache Hit)
    # We patch the store to verify it's NOT called
    with patch.object(memory_tool.store, "query", wraps=memory_tool.store.query) as mock_query:
        res_cached = await memory_tool.execute(
            "recall", query="blue", project_name=project, format="dict"
        )
        assert res_cached["success"] is True
        assert res_cached["data"][0]["content"] == "User likes blue."
        # Should not be called because of cache
        mock_query.assert_not_called()

    # 4. Update
    res = await memory_tool.execute(
        "update",
        memory_id=memory_id,
        content="User likes dark blue.",
        tags="pref,updated",
        project_name=project,
        format="dict",
    )
    assert res["success"] is True

    # Verify Cache Invalidated
    # Next recall should hit store
    with patch.object(memory_tool.store, "query", wraps=memory_tool.store.query) as mock_query_2:
        res_new = await memory_tool.execute(
            "recall", query="blue", project_name=project, format="dict"
        )
        assert res_new["data"][0]["content"] == "User likes dark blue."
        mock_query_2.assert_called()

    # 5. Forget
    res = await memory_tool.execute(
        "forget", memory_id=memory_id, project_name=project, format="dict"
    )
    assert res["success"] is True


@pytest.mark.asyncio
async def test_deduplication(memory_tool):
    """Test content hashing deduplication."""
    project = "dedup_proj"
    content = "Unique thought."

    # First Add
    res1 = await memory_tool.execute(
        "remember", content=content, project_name=project, format="dict"
    )
    assert res1["success"] is True
    id1 = res1["data"][0]["id"]

    # Second Add (Duplicate)
    res2 = await memory_tool.execute(
        "remember", content=content, project_name=project, format="dict"
    )
    assert res2["success"] is True
    assert "already exists" in res2["message"]
    id2 = res2["data"][0]["id"]

    assert id1 == id2


@pytest.mark.asyncio
async def test_markdown_format(memory_tool):
    """Test legacy markdown output."""
    project = "md_proj"
    res = await memory_tool.execute(
        "remember", content="Text", project_name=project, format="markdown"
    )
    assert isinstance(res, str)
    assert "✅ Stored memory" in res


@pytest.mark.asyncio
async def test_clear_action(memory_tool):
    """Test clearing memories."""
    project = "clear_proj"
    await memory_tool.execute("remember", content="A", project_name=project)
    await memory_tool.execute("remember", content="B", project_name=project)

    res = await memory_tool.execute("clear", project_name=project, format="dict")
    assert res["success"] is True

    # Verify empty
    res_list = await memory_tool.execute("list", project_name=project, format="dict")
    assert len(res_list["data"]) == 0
