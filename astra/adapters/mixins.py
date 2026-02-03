"""Mixins for vector store adapters."""

import hashlib
import logging
from collections.abc import Callable
from typing import Any

from astra.config import get_config
from astra.interfaces.vector_store import ASTNode, VectorStore

logger = logging.getLogger(__name__)


class BatchingVectorStoreMixin(VectorStore):
    """Mixin to add batching and deduplication logic to VectorStore implementations.

    Requires the concrete class to implement:
    - _embed(texts: list[str]) -> list[list[float]]
    - _get_collection(name: str) -> Any
    - add_documents(collection: str, ids: list[str], documents: list[str], metadatas: list[dict], ...)
      (Note: add_documents usually calls the backend-specific upsert)
    """

    def add_nodes(
        self,
        collection: str,
        nodes: list[ASTNode],
        progress_callback: Callable[[int, int, int], None] | None = None
    ) -> None:
        """Add AST nodes to a collection with batching."""
        if not nodes:
            return

        ids = []
        documents = []
        metadatas = []

        for n in nodes:
            ids.append(n.id)
            documents.append(n.content)

            meta = {
                "type": n.type,
                "name": n.name,
                "file_path": n.file_path,
                "start_line": n.start_line,
                "end_line": n.end_line,
                "language": n.language
            }
            # Merge custom metadata (e.g. tags)
            if n.metadata:
                meta.update(n.metadata)
            metadatas.append(meta)

        self.add_documents(collection, ids, documents, metadatas, progress_callback)

    def add_documents(
        self,
        collection: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        progress_callback: Callable[[int, int, int], None] | None = None
    ) -> None:
        """Add generic documents to a collection with batching and deduplication."""
        if not ids:
            return

        config = get_config()
        batch_size = config.get("ingestion", "batch_size", default=50)

        # Ensure metadatas is a list if None
        if metadatas is None:
            metadatas = [{} for _ in ids]

        total = len(ids)
        skipped_count = 0

        # Get existing hashes to skip unchanged items
        existing_map = self._get_existing_hashes(collection, ids)

        for i in range(0, total, batch_size):
            end_idx = i + batch_size
            batch_ids = ids[i:end_idx]
            batch_docs = documents[i:end_idx]
            batch_metas = metadatas[i:end_idx]

            # Calculate Hashes
            doc_hashes = []
            for doc, meta in zip(batch_docs, batch_metas):
                # OPTIMIZATION: Use pre-calculated hash if available
                if meta and "content_hash" in meta:
                    doc_hashes.append(meta["content_hash"])
                else:
                    # Ensure stable string representation for metadata
                    meta_str = str(sorted(meta.items())) if meta else ""
                    combined = f"{doc}{meta_str}".encode()
                    doc_hashes.append(hashlib.sha256(combined).hexdigest())

            # Filter for changes
            to_upsert_ids = []
            to_upsert_docs = []
            to_upsert_metas = []

            for j, (doc_id, doc, meta, doc_hash) in enumerate(zip(batch_ids, batch_docs, batch_metas, doc_hashes)):
                # Update metadata with hash so it persists
                meta["content_hash"] = doc_hash

                # Check if hash matches
                if existing_map.get(doc_id) == doc_hash:
                    skipped_count += 1
                    continue

                to_upsert_ids.append(doc_id)
                to_upsert_docs.append(doc)
                to_upsert_metas.append(meta)

            if not to_upsert_ids:
                # All skipped in this batch
                if progress_callback:
                    percent = min(100, int(end_idx / total * 100))
                    progress_callback(percent, min(end_idx, total), total)
                continue

            # Generate embeddings ONLY for changed docs
            embeddings = self._embed(to_upsert_docs)

            # Upsert to handle duplicates
            self._upsert_batch(collection, to_upsert_ids, embeddings, to_upsert_docs, to_upsert_metas)

            if progress_callback:
                percent = min(100, int(end_idx / total * 100))
                progress_callback(percent, min(end_idx, total), total)

        logger.info(f"Added {total} documents to {collection} (Skipped {skipped_count} unchanged)")

    def _get_existing_hashes(self, collection: str, ids: list[str]) -> dict[str, str]:
        """Hook to retrieve existing hashes. Default implementation returns empty dict.
        Override this in subclasses to enable deduplication."""
        return {}

    def _upsert_batch(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict]
    ) -> None:
        """Abstract method to perform the actual upsert."""
        raise NotImplementedError("Subclasses must implement _upsert_batch")

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Abstract method to generate embeddings."""
        raise NotImplementedError("Subclasses must implement _embed")
