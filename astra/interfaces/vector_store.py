"""Abstract base class for vector storage backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ASTNode:
    """Represents a parsed AST node for storage."""

    id: str
    type: str  # function, class, interface, etc.
    name: str
    content: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    metadata: dict[str, Any] | None = None


@dataclass
class QueryResult:
    """Result from a vector similarity query."""

    node: ASTNode
    score: float
    distance: float


class VectorStore(ABC):
    """Abstract vector storage interface."""

    @abstractmethod
    def create_collection(self, name: str) -> None:
        """Create a new collection for a project."""
        pass

    @abstractmethod
    def delete_collection(self, name: str) -> None:
        """Delete a collection."""
        pass

    @abstractmethod
    def list_collections(self) -> list[dict[str, Any]]:
        """List all collections with metadata (name, size, last_accessed)."""
        pass

    @abstractmethod
    def add_nodes(self, collection: str, nodes: list[ASTNode]) -> None:
        """Add AST nodes to a collection."""
        pass

    @abstractmethod
    def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[QueryResult]:
        """Query for similar nodes."""
        pass

    @abstractmethod
    def get_collection_stats(self, collection: str) -> dict[str, Any]:
        """Get statistics for a collection (node count, size, etc.)."""
        pass

    @abstractmethod
    def clear_collection(self, collection: str) -> None:
        """Clear all nodes from a collection without deleting it."""
        pass

    @abstractmethod
    def delete_nodes(self, collection: str, node_ids: list[str]) -> None:
        """Delete specific nodes from a collection."""
        pass
