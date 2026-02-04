"""Domain-agnostic ingestion pipeline."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from astra.adapters.chromadb_store import ChromaDBStore
from astra.config import get_config
from astra.ingestion.dependency_resolver import DependencyResolver
from astra.ingestion.ingestion_cache import IngestionCache
from astra.ingestion.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

# Callback type: (percent, current_count, total_count) -> Awaitable[None]
ProgressCallback = Callable[[float, int, int], Awaitable[None]]


# Top-level worker function for ProcessPoolExecutor (must be picklable)
def _parse_worker(
    file_path: str, directory: str, ast_depth: int
) -> tuple[str, list[Any] | None, str | None]:
    """
    Worker function to parse a file in a separate process.
    Returns: (file_path_str, nodes, content_hash)
    """
    try:
        from astra.ingestion.ingestion_cache import IngestionCache
        from astra.ingestion.parser import ASTParser

        fp = Path(file_path)
        # Calculate hash first - if we are here, we need it
        content_hash = IngestionCache.calculate_hash(fp)

        parser = ASTParser()
        nodes = parser.parse_file(fp, Path(directory), ast_depth=ast_depth)

        return (file_path, nodes, content_hash)
    except Exception as e:
        # Return None to indicate failure, but don't crash the worker
        print(f"Worker failed on {file_path}: {e}")
        return (file_path, None, None)


class IngestionPipeline:
    """
    Handles the end-to-end ingestion process:
    Parsing -> Batching -> Vector Store -> Knowledge Graph.

    This class is purely domain-agnostic and relies on callbacks for reporting.
    """

    def __init__(self):
        self.config = get_config()
        # self.parser is NOT used here anymore, creating fresh in worker
        self.store = ChromaDBStore()
        self.graph = KnowledgeGraph()
        self.resolver = DependencyResolver()
        self.cache = IngestionCache()
        self.batch_size = 10
        self._last_progress_time = 0
        self._progress_throttle_sec = 0.5

    async def run_async(
        self,
        directory: str,
        collection_name: str,
        progress_callback: ProgressCallback | None = None,
        max_depth: int | None = None,
        ast_depth: int | None = None,
    ) -> int:
        """
        Run the ingestion pipeline asynchronously.
        Uses ProcessPoolExecutor for parsing (CPU bound) and main thread for DB (IO/Safety).
        """
        import os
        from concurrent.futures import ProcessPoolExecutor, as_completed

        from astra.ingestion.parser import get_language_for_file

        logger.info(f"Starting ingestion pipeline for {directory} -> {collection_name}")

        ignore_patterns = self.config.get("ingestion", "ignore_patterns", default=[])
        max_size_kb = self.config.get("ingestion", "max_file_size_kb", default=100)
        ast_depth = ast_depth or self.config.get("ingestion", "ast_depth", default=3)

        # 1. Parsing with Progress Wrapper
        async def on_parse_progress(p, c, t):
            if progress_callback:
                await progress_callback(p, c, t)

        def sync_progress_bridge(p, c, t):
            now = time.time()
            if p >= 100 or (now - self._last_progress_time) >= self._progress_throttle_sec:
                self._last_progress_time = now
                coro = on_parse_progress(p, c, t)
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(coro)
                    else:
                        coro.close()
                except Exception:
                    coro.close()

        # -------------------------------------------------------------
        #  RUTHLESS OPTIMIZATION: O(1) Check + Parallel Parse
        # -------------------------------------------------------------

        # RUTHLESS OPTIMIZATION: Preload model in background to avoid heartbeat blackouts
        # This prevents the 10s+ freeze when first accessing embeddings
        await self.store.preload_model()

        directory_path = Path(directory)
        files_to_process = []
        skipped_count = 0

        # 1a. Fast Scan (O(N) walk, O(1) check)
        logger.info("Scanning files...")
        for root, dirs, files in os.walk(directory_path):
            root_path = Path(root)
            if max_depth is not None:
                try:
                    depth = len(root_path.relative_to(directory_path).parts)
                    if depth > max_depth:
                        dirs[:] = []
                        continue
                except ValueError:
                    pass

            if any(
                p in str(root_path)
                for p in [".git", "__pycache__", "node_modules", ".venv", "env"] + ignore_patterns
            ):
                dirs[:] = []
                continue

            for file in files:
                fp = root_path / file
                if get_language_for_file(fp) and fp.stat().st_size <= max_size_kb * 1024:
                    # KEY OPTIMIZATION: Check metadata cache (mtime/size)
                    if self.cache.check_file(fp):
                        skipped_count += 1
                    else:
                        files_to_process.append(str(fp))

        total_files = len(files_to_process) + skipped_count
        logger.info(
            f"Total files: {total_files}. Skipped (O(1)): {skipped_count}. To process: {len(files_to_process)}"
        )

        if not files_to_process:
            # Just save graph (it might have updates from other runs if we shared it, but usually fine)
            # If completely skipped, we are done.
            sync_progress_bridge(100, total_files, total_files)
            return 0

        # 1b. Parallel Parsing
        nodes_buffer = []
        total_nodes = 0
        processed_count = 0

        # We use a limited number of workers to avoid memory explosion
        max_workers = 2  # Conservative for stability

        logger.info(f"Spinning up {max_workers} worker processes...")

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = {
                executor.submit(_parse_worker, fp, str(directory_path), ast_depth): fp
                for fp in files_to_process
            }

            for future in as_completed(futures):
                fp_str, nodes, content_hash = future.result()
                processed_count += 1

                if nodes:
                    nodes_buffer.extend(nodes)
                    # Queue cache update (don't save yet)
                    if content_hash:
                        self.cache.update(fp_str, content_hash)

                # Batch Process if full
                if len(nodes_buffer) >= self.batch_size:
                    await self._process_batch(collection_name, nodes_buffer)
                    total_nodes += len(nodes_buffer)
                    nodes_buffer = []
                    self.cache.save()  # Save cache checkpoints

                current_total_progress = skipped_count + processed_count
                sync_progress_bridge(
                    int(current_total_progress / total_files * 100),
                    current_total_progress,
                    total_files,
                )

        # Process remaining
        if nodes_buffer:
            await self._process_batch(collection_name, nodes_buffer)
            total_nodes += len(nodes_buffer)
            self.cache.save()

        print(f"DEBUG PIPELINE: Saving graph to {self.graph._persist_path}")
        self.graph.save()


            # In IngestionPipeline._process_batch or at the end of run_async
    
        # 1. Build Graph
        # ... (existing graph building) ...
        
        # 2. Calculate Importance
        centrality_scores = self.graph.calculate_centrality()
        
        # 3. Update nodes with importance before upserting to Chroma
        for node in nodes_buffer:
            # Get score, default to low value if isolated
            score = centrality_scores.get(node.id, 0.0)
            node.metadata["importance"] = score
            
        # 4. Upsert to Chroma
        self.store.add_nodes(collection_name, nodes_buffer)

        logger.info(
            f"Ingestion complete. Total nodes: {total_nodes}. Skipped files: {skipped_count}/{total_files}"
        )
        return total_nodes

    async def _process_batch(self, collection: str, nodes: list[Any]):
        """
        Process a single batch of nodes synchronously.
        Running in executor caused crashes with ChromaDB/SQLite on Windows.
        Since we are CLI-focused, blocking for batch insertion is acceptable.
        """
        # 1. Add to Vector DB
        self.store.add_nodes(collection, nodes)

        # 2. Add to Knowledge Graph
        self.graph.add_nodes(nodes)

        # 3. Dependency Resolution
        # Index current batch
        self.resolver.index_files(nodes)

        # Resolve and link
        dependencies = self.resolver.resolve(nodes)
        for source, target in dependencies:
            self.graph.add_import(source, target)

        # Explicit GC to prevent OOM on large ingestions
        import gc

        gc.collect()
