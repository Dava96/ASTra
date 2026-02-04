"""Context gathering for RAG and Knowledge Graph."""

import contextlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from astra.core.tools import ToolRegistry
from astra.ingestion.parser import get_manifest_files_for_project

if TYPE_CHECKING:
    from astra.adapters.chromadb_store import ChromaDBStore

logger = logging.getLogger(__name__)


class ContextGatherer:
    """Gathers context for LLM tasks from various sources."""

    def __init__(self, vector_store: "ChromaDBStore", tools: ToolRegistry):
        self._vector_store = vector_store
        self._tools = tools

    async def gather(self, query: str, collection: str, project_path: str) -> str:
        """Gather context from Vector Store and Knowledge Graph (RAG-First) in parallel."""
        import asyncio

        # Define tasks for parallel execution

        async def get_manifests():
            try:
                manifests = get_manifest_files_for_project(project_path)
                if manifests:
                    manifest_ctx = []
                    for filename, content in manifests.items():
                        manifest_ctx.append(f"#### {filename}\n```\n{content}\n```")
                    return "### Project Dependencies:\n" + "\n".join(manifest_ctx)
            except Exception as e:
                logger.warning(f"Manifest detection failed: {e}")
            return ""

        async def get_architecture():
            try:
                # Check .astra/ARCHITECTURE.md first
                arch_path = Path(project_path) / ".astra" / "ARCHITECTURE.md"
                if not arch_path.exists():
                    # Fallback to root
                    arch_path = Path(project_path) / "ARCHITECTURE.md"

                if arch_path.exists():
                    arch_content = arch_path.read_text(encoding="utf-8")
                    return f"### Architecture & Guidelines:\n{arch_content}"
            except Exception as e:
                logger.warning(f"Failed to read ARCHITECTURE.md: {e}")
            return ""

        async def get_vector_search():
            try:
                results = self._vector_store.query(collection, query, n_results=10)
                if results:
                    vector_ctx = "\n".join(
                        [
                            f"// File: {r.node.file_path}:{r.node.start_line}\n{r.node.content}"
                            for r in results
                        ]
                    )
                    return vector_ctx, results
            except Exception as e:
                logger.warning(f"Vector search failed: {e}")
            return "", []

        # Execute independent tasks in parallel
        manifest_res, arch_res, (vector_str, vector_results) = await asyncio.gather(
            get_manifests(), get_architecture(), get_vector_search()
        )

        # Combine results with Context Window Guard
        # Estimate: 1 token ~= 4 chars. Max limit: 6000 tokens (~24k chars) for context
        MAX_CONTEXT_CHARS = 24000
        current_chars = 0
        context_parts = []

        # Priority 1: Manifests (High Value, usually small)
        if manifest_res:
            context_parts.append(manifest_res)
            current_chars += len(manifest_res)

        # Priority 2: Architecture (High Value, moderate size)
        if arch_res:
            if current_chars + len(arch_res) <= MAX_CONTEXT_CHARS:
                context_parts.append(arch_res)
                current_chars += len(arch_res)
            else:
                # Truncate architecture if somehow massive (unlikely)
                remain = MAX_CONTEXT_CHARS - current_chars
                if remain > 500:
                    part = arch_res[:remain] + "\n...(truncated)"
                    context_parts.append(part)
                    current_chars += len(part)

        kg_context = ""
        if vector_results:
            top_file = vector_results[0].node.file_path
            try:
                kg_tool = self._tools.get("query_knowledge_graph")
                if kg_tool:
                    # Run KG queries in parallel
                    deps, impact = await asyncio.gather(
                        kg_tool.execute("dependencies", target=top_file),
                        kg_tool.execute("impact", target=top_file),
                    )
                    kg_check = f"### Knowledge Graph Analysis for {top_file}:\n{deps}\n{impact}"
                    # Priority 3: KG Analysis (High Value)
                    if current_chars + len(kg_check) <= MAX_CONTEXT_CHARS:
                        kg_context = kg_check
            except Exception as e:
                logger.warning(f"KG query failed: {e}")

        if kg_context:
            context_parts.append(kg_context)
            current_chars += len(kg_context)

        # Priority 4: Vector Search Details (Lowest Priority - can be truncated or compressed)
        if vector_str:
            remain = MAX_CONTEXT_CHARS - current_chars
            if remain > 100:  # Minimum useful chunk
                # Try compression first if enabled
                from astra.core.compression import ContextCompressor

                compressor = ContextCompressor()

                # Check if we are over the "safe" limit for vector data
                # If vector_str is huge, compress it to fit 'remain' or a target token count
                # Heuristic: 1 token ~ 4 chars. Target tokens = remain / 4
                target_tokens = int(remain / 4)

                # Only compress if it's significantly larger than target (save CPU otherwise)
                if len(vector_str) > remain:
                    with contextlib.suppress(Exception):
                        vector_str = compressor.compress(
                            vector_str, target_token_count=target_tokens
                        )

                header = "### Relevant Code Snippets (Vector Search"
                full_vector_part = f"{header}):\n{vector_str}"

                if len(full_vector_part) <= remain:
                    context_parts.append(full_vector_part)
                else:
                    # Truncate if still too big after compression
                    suffix = "\n...(truncated)"
                    chunk_size = remain - 100
                    if chunk_size > 0:
                        context_parts.append(
                            f"{header} - Truncated):\n{vector_str[:chunk_size]}{suffix}"
                        )

        return "\n\n".join(context_parts)
