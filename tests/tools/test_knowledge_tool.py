from unittest.mock import patch

import pytest

from astra.tools.knowledge import KnowledgeTool


@pytest.fixture
def mock_graph():
    from astra.tools import knowledge
    knowledge._SHARED_GRAPH = None  # Force re-init with mock
    with patch("astra.tools.knowledge.KnowledgeGraph") as MockKG:
        yield MockKG.return_value


@pytest.mark.asyncio
async def test_knowledge_tool(mock_graph):
    tool = KnowledgeTool()

    # Stats
    mock_graph.get_stats.return_value = {"nodes": 10}
    assert "nodes" in await tool.execute("stats")

    # Missing target
    assert "Target is required" in await tool.execute("dependencies")

    # Dependencies
    mock_graph.get_file_dependencies.return_value = ["a.py"]
    res = await tool.execute("dependencies", target="b.py")
    assert "Dependencies of b.py" in res
    assert "a.py" in res

    # Dependents
    mock_graph.get_file_dependents.return_value = ["c.py"]
    res = await tool.execute("dependents", target="b.py")
    assert "Dependents of b.py" in res
    assert "c.py" in res

    # Info
    mock_graph.get_node_info.return_value = {"type": "function"}
    res = await tool.execute("info", target="func")
    assert "'type': 'function'" in res

    # Impact
    mock_graph.get_impact_analysis.return_value = {"direct": 1, "indirect": 2}
    res = await tool.execute("impact", target="f.py")
    assert "Direct: 1" in res

    # Unknown
    assert "Unknown query" in await tool.execute("magic", target="foo")
