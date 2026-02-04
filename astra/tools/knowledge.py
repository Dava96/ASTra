"""Tool for querying the knowledge graph."""

import logging

from astra.core.tools import BaseTool
from astra.ingestion.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

# Global singleton to prevent expensive re-loading from disk on every tool call
# The KnowledgeTool is stateless otherwise, but the graph is stateful (loaded from pickle)
_SHARED_GRAPH = None


def get_shared_graph() -> KnowledgeGraph:
    global _SHARED_GRAPH
    if _SHARED_GRAPH is None:
        _SHARED_GRAPH = KnowledgeGraph()
    return _SHARED_GRAPH


class KnowledgeTool(BaseTool):
    """Tool for querying the codebase knowledge graph."""

    name = "query_knowledge_graph"
    description = "Query the codebase knowledge graph for dependencies, usage, and structure."
    parameters = {
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": ["dependencies", "dependents", "info", "impact", "stats"],
                "description": "Type of query to perform",
            },
            "target": {
                "type": "string",
                "description": "Target file path or node ID (required for non-stats queries)",
            },
        },
        "required": ["query_type"],
    }

    def __init__(self):
        # Use singleton
        self._graph = get_shared_graph()

    async def execute(self, query_type: str, target: str | None = None, **kwargs) -> str:
        """Execute knowledge graph query."""
        if query_type == "stats":
            return str(self._graph.get_stats())

        if not target:
            return "❌ Target is required for this query type."

        if query_type == "dependencies":
            deps = self._graph.get_file_dependencies(target)
            return (
                f"Dependencies of {target}:\n" + "\n".join(deps)
                if deps
                else "No dependencies found."
            )

        elif query_type == "dependents":
            deps = self._graph.get_file_dependents(target)
            return (
                f"Dependents of {target}:\n" + "\n".join(deps) if deps else "No dependents found."
            )

        elif query_type == "info":
            info = self._graph.get_node_info(target)
            return str(info) if info else "Node not found."

        elif query_type == "impact":
            impact = self._graph.get_impact_analysis(target)
            return f"Impact Analysis for {target}:\nDirect: {impact['direct']}\nIndirect: {impact['indirect']}"

        return "❌ Unknown query type."
