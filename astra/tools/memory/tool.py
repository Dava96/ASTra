"""Working memory tool for storing and retrieving facts."""

import asyncio
import hashlib
import logging
import uuid
from typing import Any

from astra.adapters.chromadb_store import ChromaDBStore
from astra.core.tools import BaseTool
from astra.interfaces.vector_store import ASTNode
from astra.tools.memory.models import MemoryNode, MemoryOperationResult

logger = logging.getLogger(__name__)

# LRU Cache for recall queries to provide O(1) lookups for frequent patterns
# Key: (project_name, query_string)
# Value: MemoryOperationResult (or list of dicts if we want to be pure)
# We handle this manually or via a wrapper class since it needs invalidation
_RECALL_CACHE: dict[str, Any] = {}
_MAX_CACHE_SIZE = 100


class MemoryTool(BaseTool):
    """Tool for managing working memory (facts, decisions, context)."""

    name = "memory"
    description = "Store, retrieve, and manage working memory to prevent hallucination."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["remember", "recall", "forget", "list", "update", "clear"],
                "description": "Action to perform",
            },
            "content": {
                "type": "string",
                "description": "Content to remember (for 'remember'/'update' action)",
            },
            "query": {"type": "string", "description": "Search query (for 'recall' action)"},
            "memory_id": {
                "type": "string",
                "description": "ID of memory (for 'forget'/'update' action)",
            },
            "tags": {"type": "string", "description": "Comma-separated tags (optional metdata)"},
            "project_name": {
                "type": "string",
                "description": "Active project name (used for scoping memory)",
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "json", "dict"],
                "description": "Output format trigger (default: markdown)",
            },
        },
        "required": ["action"],
    }

    def __init__(self, store: ChromaDBStore | None = None):
        # Allow DI or lazy load
        self._store = store
        self._lock = asyncio.Lock()

    @property
    def store(self) -> ChromaDBStore:
        if self._store is None:
            self._store = ChromaDBStore()
        return self._store

    async def execute(self, action: str, **kwargs: Any) -> Any:
        project_name = kwargs.get("project_name") or "default"
        collection_name = f"{project_name}_memory"
        fmt = kwargs.get(
            "format", "dict"
        )  # Defaulting to dict behavior internally, likely invoked as markdown by users

        try:
            result: MemoryOperationResult

            if action == "remember":
                result = await self._remember(collection_name, kwargs)
            elif action == "recall":
                result = await self._recall(collection_name, kwargs)
            elif action == "forget":
                result = await self._forget(collection_name, kwargs)
            elif action == "list":
                # List is recall with wildcard/empty query
                query = (
                    kwargs.get("query") or " "
                )  # Space triggers 'all' conceptually in vector search sometimes or we handle logic
                result = await self._recall(collection_name, {**kwargs, "query": query})
                result.action = "list"
            elif action == "update":
                result = await self._update(collection_name, kwargs)
            elif action == "clear":
                result = await self._clear(collection_name)
            else:
                result = MemoryOperationResult(False, action, f"❌ Unknown action: {action}")

            # Format Response
            if fmt == "markdown":
                return self._format_markdown(result)
            else:
                return result.to_dict()

        except Exception as e:
            logger.exception("Memory tool interaction failed")
            err_res = MemoryOperationResult(
                False, action, f"❌ Error executing memory action: {str(e)}"
            )
            if fmt == "markdown":
                return f"❌ **Error**: {str(e)}"
            return err_res.to_dict()

    async def _remember(self, collection: str, kwargs: dict[str, Any]) -> MemoryOperationResult:
        content = kwargs.get("content")
        if not content:
            return MemoryOperationResult(False, "remember", "❌ 'content' is required.")

        tags = kwargs.get("tags", "")

        # 1. Content Hashing & Deduplication (O(1) logic)
        content_hash = hashlib.md5(content.encode()).hexdigest()

        # Check existence via metadata filter (Fast ID check ideally, but we use hash)
        # We run this in thread to avoid blocking
        loop = asyncio.get_running_loop()
        existing = await loop.run_in_executor(
            None,
            lambda: self.store.query(
                collection, "", n_results=1, filter_metadata={"content_hash": content_hash}
            ),
        )

        if existing:
            # Found duplicate
            node = existing[0].node
            return MemoryOperationResult(
                True,
                "remember",
                f"🧠 Memory already exists (deduplicated). ID: {node.id}",
                data=[MemoryNode(node.id, node.content, metadata=node.metadata)],
            )

        # 2. Create New
        memory_id = str(uuid.uuid4())
        node = ASTNode(
            id=memory_id,
            type="memory",
            name=f"Memory-{memory_id[:8]}",
            content=content,
            file_path="memory://working-memory",
            start_line=0,
            end_line=0,
            language="text",
            metadata={"tags": tags, "content_hash": content_hash},
        )

        await loop.run_in_executor(None, lambda: self.store.add_nodes(collection, [node]))

        # Invalidate Cache for this collection context
        self._invalidate_cache(collection)

        return MemoryOperationResult(
            True,
            "remember",
            f"✅ Stored memory: {memory_id}",
            data=[MemoryNode(memory_id, content, tags=[tags], metadata=node.metadata)],
        )

    async def _recall(self, collection: str, kwargs: dict[str, Any]) -> MemoryOperationResult:
        query = kwargs.get("query")
        if not query:
            return MemoryOperationResult(False, "recall", "❌ 'query' is required.")

        # Cache Lookup (O(1))
        cache_key = f"{collection}:{query}"
        if cache_key in _RECALL_CACHE:
            logger.debug(f"Memory cache hit for {cache_key}")
            return _RECALL_CACHE[cache_key]

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, lambda: self.store.query(collection, query, n_results=5)
        )

        if not results:
            return MemoryOperationResult(True, "recall", "No relevant memories found.", data=[])

        memory_nodes = []
        for res in results:
            tags_str = str(res.node.metadata.get("tags") or "")
            tags = [t.strip() for t in tags_str.split(",")] if tags_str else []
            memory_nodes.append(
                MemoryNode(
                    id=res.node.id,
                    content=res.node.content,
                    tags=tags,
                    metadata=res.node.metadata,
                    score=res.score,
                )
            )

        res_obj = MemoryOperationResult(
            True, "recall", f"Found {len(memory_nodes)} memories.", data=memory_nodes
        )

        # Update Cache
        if len(_RECALL_CACHE) >= _MAX_CACHE_SIZE:
            _RECALL_CACHE.pop(next(iter(_RECALL_CACHE)))  # Simple FIFO for now/LRU logic approx
        _RECALL_CACHE[cache_key] = res_obj

        return res_obj

    async def _forget(self, collection: str, kwargs: dict[str, Any]) -> MemoryOperationResult:
        memory_id = kwargs.get("memory_id")
        if not memory_id:
            return MemoryOperationResult(False, "forget", "❌ 'memory_id' is required.")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: self.store.delete_nodes(collection, [memory_id]))

        self._invalidate_cache(collection)
        return MemoryOperationResult(True, "forget", f"✅ Forgot memory: {memory_id}")

    async def _update(self, collection: str, kwargs: dict[str, Any]) -> MemoryOperationResult:
        memory_id = kwargs.get("memory_id")
        content = kwargs.get("content")
        tags = kwargs.get("tags")

        if not memory_id:
            return MemoryOperationResult(False, "update", "❌ 'memory_id' is required.")

        # We need to fetch original to merge or overwrite
        # Ideally store supports update, but here we might need delete + add to ensure embedding updates
        # Or just upsert if ID exists. Chroma upsert overwrites.

        # Simple Upsert Logic using existing ID
        loop = asyncio.get_running_loop()

        # 1. Fetch existing to get metadata if needed? Or just overwrite.
        # Let's overwrite but keep hash check?
        # If content changes, hash changes.

        metadata = {}
        if content:
            content_hash = hashlib.md5(content.encode()).hexdigest()
            metadata["content_hash"] = content_hash
        if tags:
            metadata["tags"] = tags

        # We construct a node.
        # Note: If we don't provide content, we can't re-embed.
        # So 'update' usually implies new content or we must fetch old content.
        # For simplicity, if content missing, we error out OR fetch.

        if not content:
            # Fetch existing
            # self.store.get_nodes(...) ?? Store generic doesn't expose get by ID easily without query usually
            # But let's assume valid usage provides content.
            return MemoryOperationResult(
                False,
                "update",
                "❌ New 'content' is required for update (partial update not supported yet).",
            )

        node = ASTNode(
            id=memory_id,
            type="memory",
            name=f"Memory-{memory_id[:8]}",
            content=content,
            file_path="memory://working-memory",
            start_line=0,
            end_line=0,
            language="text",
            metadata=metadata,
        )

        await loop.run_in_executor(
            None, lambda: self.store.add_nodes(collection, [node])
        )  # add_nodes uses upsert usually

        self._invalidate_cache(collection)
        return MemoryOperationResult(True, "update", f"✅ Updated memory: {memory_id}")

    async def _clear(self, collection: str) -> MemoryOperationResult:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: self.store.clear_collection(collection))
        self._invalidate_cache(collection)
        return MemoryOperationResult(True, "clear", f"✅ Cleared all memories in {collection}")

    def _invalidate_cache(self, collection_prefix: str):
        """Invalidate cache entries for this collection."""
        keys_to_remove = [k for k in _RECALL_CACHE if k.startswith(collection_prefix)]
        for k in keys_to_remove:
            del _RECALL_CACHE[k]

    def _format_markdown(self, result: MemoryOperationResult) -> str:
        if not result.success:
            return result.message

        lines = [result.message]
        if result.data:
            lines.append("")
            for node in result.data:
                score_str = f" (Score: {node.score:.2f})" if node.score is not None else ""
                lines.append(f"- **[{node.id}]** {node.content}{score_str}")
                if node.tags:
                    lines.append(f"  - Tags: {', '.join(node.tags)}")

        return "\n".join(lines)
