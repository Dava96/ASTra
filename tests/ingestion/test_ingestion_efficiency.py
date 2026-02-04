"""Integration tests for Ingestion Pipeline efficiency."""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from astra.ingestion.ingestion_cache import IngestionCache
from astra.ingestion.pipeline import IngestionPipeline


@pytest.mark.asyncio
class TestIngestionEfficiency:
    """Tests focused on the O(1) delta-check and caching logic."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project structure."""
        temp_dir = tempfile.mkdtemp()
        project_path = Path(temp_dir) / "project"
        project_path.mkdir()

        # Create some files
        (project_path / "f1.py").write_text("def a(): pass")
        (project_path / "f2.py").write_text("def b(): pass")

        yield project_path

        shutil.rmtree(temp_dir)

    async def test_delta_ingestion_skips_unchanged_files(self, temp_project):
        """Verify that unchanged files are skipped during ingestion."""
        cache_path = temp_project.parent / "cache.json"

        # 1. Setup mocks
        with patch("astra.ingestion.pipeline.ChromaDBStore"), \
             patch("astra.ingestion.pipeline.KnowledgeGraph"), \
             patch("astra.ingestion.pipeline.DependencyResolver"), \
             patch("astra.ingestion.pipeline.get_config") as mock_config:

            mock_config.return_value.get.side_effect = lambda s, k, default=None: default

            pipeline = IngestionPipeline()
            pipeline.cache = IngestionCache(persist_path=str(cache_path))

            # 2. First Run - Should process 2 files
            processed_nodes = await pipeline.run_async(str(temp_project), "test_coll")
            # Note: run_async returns total_nodes. ASTParser for 2 files should return > 0 nodes.
            assert processed_nodes > 0

            # 3. Second Run - Files haven't changed, should process 0 files
            with patch("astra.ingestion.pipeline._parse_worker") as mock_worker:
                # If skipped, _parse_worker is NOT called
                processed_nodes_second = await pipeline.run_async(str(temp_project), "test_coll")

                assert processed_nodes_second == 0
                mock_worker.assert_not_called()

    async def test_delta_ingestion_detects_changed_files(self, temp_project):
        """Verify that changed files ARE processed."""
        cache_path = temp_project.parent / "cache_changed.json"

        with patch("astra.ingestion.pipeline.ChromaDBStore"), \
             patch("astra.ingestion.pipeline.KnowledgeGraph"), \
             patch("astra.ingestion.pipeline.DependencyResolver"), \
             patch("astra.ingestion.pipeline.get_config") as mock_config:

            mock_config.return_value.get.side_effect = lambda s, k, default=None: default

            pipeline = IngestionPipeline()
            pipeline.cache = IngestionCache(persist_path=str(cache_path))

            # Initial Run
            await pipeline.run_async(str(temp_project), "test_coll")

            # Modify one file
            (temp_project / "f1.py").write_text("def a_new(): pass")

            # Second Run
            # Instead of mocking the worker, we mock the executor to see what was submitted
            with patch("concurrent.futures.ProcessPoolExecutor.submit") as mock_submit:
                # We need to return a mock future that returns a valid result
                mock_future = MagicMock()
                mock_future.result.return_value = ("f1.py", [], "new_hash")
                mock_submit.return_value = mock_future

                # Mock as_completed to return our future
                with patch("concurrent.futures.as_completed", return_value=[mock_future]):
                    await pipeline.run_async(str(temp_project), "test_coll")

                    # Should be called for f1.py
                    assert mock_submit.called
                    args = mock_submit.call_args[0]
                    assert "f1.py" in str(args[1]) # args[1] is the file path
