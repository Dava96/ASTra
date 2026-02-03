"""ChromaDB implementation for working memory."""

import logging

from astra.adapters.chromadb_store import ChromaDBStore
from astra.config import get_config

logger = logging.getLogger(__name__)

class ChromaMemoryStore(ChromaDBStore):
    """Dedicated vector store for working memory."""

    def __init__(
        self,
        persist_path: str | None = None,
        embedding_model: str | None = None,
        ephemeral: bool = False
    ):
        config = get_config()
        # Use a separate path for memory to avoid mixing with code embeddings
        # and potentially allow for different lifecycle/backup policies.
        default_path = "./data/memory"
        default_model = "all-MiniLM-L6-v2"

        path = persist_path or config.get("memory", "persist_path", default=default_path)
        model = embedding_model or config.get("memory", "embedding_model", default=default_model)
        is_ephemeral = ephemeral or config.get("memory", "ephemeral", default=False)

        # We enforce a lightweight model for memory as it's mostly natural language
        # and we want low latency.
        super().__init__(
            persist_path=path,
            embedding_model=model,
            ephemeral=is_ephemeral
        )
        mode = "EPHEMERAL" if is_ephemeral else f"PERSISTENT({path})"
        logger.info(f"ChromaMemoryStore initialized in {mode} mode with model {model}")

    def cleanup_expired(self, collection_name: str, ttl_hours: int = 24) -> int:
        """Remove memory items older than the TTL.
        
        Args:
            collection_name: Name of the collection to clean.
            ttl_hours: Age in hours to consider expired.
            
        Returns:
            Number of items deleted.
        """
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(hours=ttl_hours)).timestamp()

        try:
            col = self._get_collection(collection_name)

            # ChromaDB filtering: metadata field "created_at" < cutoff
            # Note: We need to ensure created_at is stored as a float/int timestamp in metadata
            result = col.get(
                where={"created_at": {"$lt": cutoff}}
            )

            if result and result["ids"]:
                ids_to_delete = result["ids"]
                col.delete(ids=ids_to_delete)
                logger.info(f"Cleaned up {len(ids_to_delete)} expired memory items from {collection_name}")
                return len(ids_to_delete)

            return 0

        except Exception as e:
            logger.error(f"Failed to cleanup expired memory: {e}")
            return 0
