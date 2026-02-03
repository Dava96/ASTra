import logging
import os

# Disable ChromaDB telemetry globally
os.environ["ANONYMIZED_TELEMETRY"] = "False"

# Silence common telemetry noise loggers
for logger_name in ["chromadb.telemetry", "posthog"]:
    l = logging.getLogger(logger_name)
    l.setLevel(logging.CRITICAL)
    l.propagate = False

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astra.adapters.mixins import BatchingVectorStoreMixin
from astra.config import get_config
from astra.interfaces.vector_store import ASTNode, QueryResult

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class ChromaDBStore(BatchingVectorStoreMixin):
    """ChromaDB-based vector store with CodeBERT embeddings."""

    def __init__(
        self,
        persist_path: str | None = None,
        embedding_model: str | None = None,
        ephemeral: bool = False
    ):
        config = get_config()
        self._persist_path = persist_path or config.get("vectordb", "persist_path", default="./data/chromadb")
        self._embedding_model_name = embedding_model or config.get("ingestion", "embedding_model", default="default")
        self._ephemeral = ephemeral

        # Ensure directory exists only if not ephemeral use
        if not self._ephemeral:
            Path(self._persist_path).mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB (Lazy Import)
        import chromadb
        from chromadb.config import Settings

        if self._ephemeral:
             self._client = chromadb.EphemeralClient(
                settings=Settings(anonymized_telemetry=False)
            )
             logger.info("ChromaDB initialized in EPHEMERAL mode")
        else:
            self._client = chromadb.PersistentClient(
                path=self._persist_path,
                settings=Settings(anonymized_telemetry=False)
            )
            logger.info(f"ChromaDB initialized at {self._persist_path}")

        # Lazy load embedding model
        self._embedding_model = None

        # Track collection metadata
        self._collection_access: dict[str, str] = {}

    # Class-level cache for embedding models
    _model_cache: dict[str, Any] = {}

    def _load_embedding_model(self) -> "SentenceTransformer":
        """Load the embedding model."""
        from sentence_transformers import SentenceTransformer

        model_map = {
            "default": "all-MiniLM-L6-v2",
            "mini": "all-MiniLM-L6-v2",
            "codebert": "microsoft/codebert-base",
            "mpnet": "all-mpnet-base-v2"
        }

        model_name = model_map.get(self._embedding_model_name, self._embedding_model_name)

        # Check cache
        if model_name in ChromaDBStore._model_cache:
            logger.info(f"Using cached embedding model: {model_name}")
            return ChromaDBStore._model_cache[model_name]

        logger.info(f"Loading embedding model: {model_name}")

        try:
            model = SentenceTransformer(model_name)
            ChromaDBStore._model_cache[model_name] = model
            return model
        except Exception as e:
            logger.warning(f"Failed to load {model_name}, falling back to MiniLM: {e}")
            fallback = "all-MiniLM-L6-v2"

            # Check cache for fallback
            if fallback in ChromaDBStore._model_cache:
                 return ChromaDBStore._model_cache[fallback]

            model = SentenceTransformer(fallback)
            ChromaDBStore._model_cache[fallback] = model
            return model

    def _get_collection(self, name: str):
        """Get or create a collection."""
        self._collection_access[name] = datetime.now(UTC).isoformat()
        return self._client.get_or_create_collection(
            name=name,
            metadata={"last_accessed": self._collection_access[name]}
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        if self._embedding_model is None:
            self._embedding_model = self._load_embedding_model()
        return self._embedding_model.encode(texts, show_progress_bar=False).tolist()

    def create_collection(self, name: str) -> None:
        """Create a new collection."""
        self._client.get_or_create_collection(name=name)
        logger.info(f"Created collection: {name}")

    def delete_collection(self, name: str) -> None:
        """Delete a collection."""
        try:
            self._client.delete_collection(name=name)
            self._collection_access.pop(name, None)
            logger.info(f"Deleted collection: {name}")
        except Exception as e:
            logger.error(f"Failed to delete collection {name}: {e}")

    def list_collections(self) -> list[dict[str, Any]]:
        """List all collections with metadata."""
        collections = []
        for col in self._client.list_collections():
            try:
                count = col.count()
                collections.append({
                    "name": col.name,
                    "count": count,
                    "last_accessed": self._collection_access.get(col.name, "unknown")
                })
            except Exception:
                collections.append({
                    "name": col.name,
                    "count": 0,
                    "last_accessed": "unknown"
                })
        return collections

    def _get_existing_hashes(self, collection: str, ids: list[str]) -> dict[str, str]:
        """Retrieve existing content hashes for deduplication."""
        try:
            col = self._get_collection(collection)
            existing = col.get(ids=ids, include=["metadatas"])
            existing_map = {}
            if existing and existing["ids"]:
                for j, eid in enumerate(existing["ids"]):
                    if existing["metadatas"] and j < len(existing["metadatas"]):
                            ex_meta = existing["metadatas"][j]
                            if ex_meta:
                                existing_map[eid] = ex_meta.get("content_hash")
            return existing_map
        except Exception:
            return {}

    def _upsert_batch(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict]
    ) -> None:
        """Perform the actual upsert to ChromaDB."""
        try:
            col = self._get_collection(collection)
            col.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
        except Exception as e:
            logger.error(f"Failed to add batch to collection {collection}: {e}")
            # We log and do not re-raise to ensure one bad batch doesn't kill the whole process
            # (Similar to original behavior)

    def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 10,
        filter_metadata: dict[str, Any] | None = None
    ) -> list[QueryResult]:
        """Query for similar nodes."""
        col = self._get_collection(collection)

        # Generate query embedding
        query_embedding = self._embed([query_text])[0]

        results = col.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filter_metadata
        )

        query_results = []
        if results and results["ids"] and results["ids"][0]:
            for i, node_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                document = results["documents"][0][i] if results["documents"] else ""
                distance = results["distances"][0][i] if results["distances"] else 0.0

                node = ASTNode(
                    id=node_id,
                    type=metadata.get("type", ""),
                    name=metadata.get("name", ""),
                    content=document,
                    file_path=metadata.get("file_path", ""),
                    start_line=metadata.get("start_line", 0),
                    end_line=metadata.get("end_line", 0),
                    language=metadata.get("language", ""),
                    metadata=metadata
                )

                query_results.append(QueryResult(
                    node=node,
                    score=1.0 - distance,  # Convert distance to similarity
                    distance=distance
                ))

        return query_results

    def get_collection_stats(self, collection: str) -> dict[str, Any]:
        """Get statistics for a collection."""
        try:
            col = self._get_collection(collection)
            return {
                "name": collection,
                "count": col.count(),
                "last_accessed": self._collection_access.get(collection, "unknown")
            }
        except Exception as e:
            return {"name": collection, "error": str(e)}

    def clear_collection(self, collection: str) -> None:
        """Clear all nodes from a collection."""
        try:
            self._client.delete_collection(collection)
            self.create_collection(collection)
            logger.info(f"Cleared collection: {collection}")
        except Exception as e:
            logger.error(f"Failed to clear collection {collection}: {e}")

    def cleanup_stale_collections(self, max_age_days: int = 30) -> list[str]:
        """Remove collections that haven't been accessed recently.
        
        This helps recover disk space when you've moved on from one language
        stack to another (e.g., from JavaScript to Go).
        
        Args:
            max_age_days: Delete collections not accessed in this many days
            
        Returns:
            List of deleted collection names
        """
        deleted = []
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)

        for col in self._client.list_collections():
            last_accessed_str = self._collection_access.get(col.name)

            if not last_accessed_str:
                # Unknown access time - check if collection metadata has it
                meta = col.metadata or {}
                last_accessed_str = meta.get("last_accessed")

            if last_accessed_str:
                try:
                    last_accessed = datetime.fromisoformat(last_accessed_str)
                    if last_accessed < cutoff:
                        logger.info(f"Deleting stale collection: {col.name} (last accessed: {last_accessed_str})")
                        self.delete_collection(col.name)
                        deleted.append(col.name)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid access timestamp for {col.name}: {last_accessed_str}")

        if deleted:
            logger.info(f"Cleaned up {len(deleted)} stale collections")

        return deleted

    def delete_nodes(self, collection: str, node_ids: list[str]) -> None:
        """Delete specific nodes from a collection."""
        try:
            col = self._get_collection(collection)
            col.delete(ids=node_ids)
            logger.info(f"Deleted {len(node_ids)} nodes from {collection}")
        except Exception as e:
            logger.error(f"Failed to delete nodes from {collection}: {e}")
