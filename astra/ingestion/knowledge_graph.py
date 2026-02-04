import logging
import pickle
from pathlib import Path
from typing import Any

import networkx as nx

from astra.config import get_config
from astra.interfaces.vector_store import ASTNode

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """Code relationship graph using NetworkX."""

    def __init__(self, persist_path: str | None = None):
        config = get_config()
        self._config = config
        self._persist_path = persist_path or config.get(
            "knowledge_graph", "persist_path", default="./data/knowledge_graph.pkl"
        )
        self._graph = nx.DiGraph()
        self._load()

    def set_persist_path(self, path: str) -> None:
        """Change the persistence path and reload the graph."""
        self._persist_path = path
        self._graph = nx.DiGraph()
        self._load()

    def _load(self) -> None:
        """Load graph from disk."""
        path = Path(self._persist_path)
        if path.exists():
            try:
                with open(path, "rb") as f:
                    self._graph = pickle.load(f)
                logger.info(
                    f"Loaded knowledge graph: {self._graph.number_of_nodes()} nodes, {self._graph.number_of_edges()} edges"
                )
            except Exception as e:
                logger.warning(f"Failed to load knowledge graph: {e}")
                self._graph = nx.DiGraph()

    def save(self) -> None:
        """Persist graph to disk."""
        path = Path(self._persist_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "wb") as f:
                pickle.dump(self._graph, f)
            logger.info(f"Saved knowledge graph: {self._graph.number_of_nodes()} nodes")
        except Exception as e:
            logger.error(f"Failed to save knowledge graph: {e}")

    def add_node(self, node: ASTNode) -> None:
        """Add an AST node to the graph."""
        # Ensure file node exists
        file_path = node.file_path
        if file_path not in self._graph:
            self._graph.add_node(
                file_path, type="file", name=Path(file_path).name, file_path=file_path
            )

        self._graph.add_node(
            node.id,
            type=node.type,
            name=node.name,
            file_path=node.file_path,
            language=node.language,
            start_line=node.start_line,
            end_line=node.end_line,
        )

        # Link AST node to its file
        self._graph.add_edge(node.id, file_path, relationship="contained_in")

    def add_nodes(self, nodes: list[ASTNode]) -> None:
        """Add multiple AST nodes to the graph."""
        for node in nodes:
            self.add_node(node)

    def add_relationship(self, source_id: str, target_id: str, relationship: str) -> None:
        """Add a relationship between nodes."""
        self._graph.add_edge(source_id, target_id, relationship=relationship)

    def add_import(self, importer_file: str, imported_file: str) -> None:
        """Add an import relationship between files."""
        self._graph.add_edge(importer_file, imported_file, relationship="imports")

    def add_call(self, caller_id: str, callee_id: str) -> None:
        """Add a function call relationship."""
        self._graph.add_edge(caller_id, callee_id, relationship="calls")

    def get_dependents(self, node_id: str) -> list[str]:
        """Get all nodes that depend on this node."""
        try:
            return list(self._graph.predecessors(node_id))
        except nx.NetworkXError:
            return []

    def get_dependencies(self, node_id: str) -> list[str]:
        """Get all nodes this node depends on."""
        try:
            return list(self._graph.successors(node_id))
        except nx.NetworkXError:
            return []

    def get_impact_analysis(self, node_id: str, max_depth: int = 3) -> dict[str, list[str]]:
        """Analyze the impact of changing a node."""
        result = {"direct": [], "indirect": []}
        visited = set()

        def traverse(current: str, depth: int):
            if depth > max_depth or current in visited:
                return
            visited.add(current)

            for pred in self._graph.predecessors(current):
                if pred not in visited:
                    if depth == 1:
                        result["direct"].append(pred)
                    else:
                        result["indirect"].append(pred)
                    traverse(pred, depth + 1)

        traverse(node_id, 1)
        return result

    def find_circular_dependencies(self) -> list[list[str]]:
        """Find all circular dependencies in the graph."""
        try:
            cycles = list(nx.simple_cycles(self._graph))
            return [c for c in cycles if len(c) > 1]
        except Exception:
            return []

    def get_node_info(self, node_id: str) -> dict[str, Any] | None:
        """Get information about a node."""
        if node_id in self._graph:
            return dict(self._graph.nodes[node_id])
        return None

    def clear(self) -> None:
        """Clear the graph."""
        self._graph = nx.DiGraph()
        logger.info("Knowledge graph cleared")

    def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        return {
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
            "files": len([n for n, d in self._graph.nodes(data=True) if d.get("type") == "file"]),
            "functions": len(
                [n for n, d in self._graph.nodes(data=True) if "function" in d.get("type", "")]
            ),
            "classes": len(
                [n for n, d in self._graph.nodes(data=True) if "class" in d.get("type", "")]
            ),
        }

    def get_file_dependencies(self, file_path: str) -> list[str]:
        """Get all files that a given file imports."""
        deps = []
        for _, target, data in self._graph.out_edges(file_path, data=True):
            if data.get("relationship") == "imports":
                deps.append(target)
        return deps

    def get_file_dependents(self, file_path: str) -> list[str]:
        """Get all files that import a given file."""
        deps = []
        for source, _, data in self._graph.in_edges(file_path, data=True):
            if data.get("relationship") == "imports":
                deps.append(source)
        return deps

        def calculate_centrality(self) -> dict[str, float]:
        """
        Calculate PageRank centrality for all nodes.
        Returns a dict of {node_id: score}
        """
        try:
            # Pagerank emphasizes nodes that are connected to other important nodes
            return nx.pagerank(self._graph, alpha=0.85)
        except Exception as e:
            logger.warning(f"Failed to calculate centrality: {e}")
            return {}
