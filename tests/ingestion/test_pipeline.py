"""Unit tests for the IngestionPipeline."""

from unittest.mock import MagicMock, patch

import pytest

from astra.ingestion.pipeline import IngestionPipeline


@pytest.fixture
def mock_dependencies():
    """Mock all pipeline dependencies."""
    with patch("astra.ingestion.pipeline.ChromaDBStore") as MockStore, \
         patch("astra.ingestion.pipeline.KnowledgeGraph") as MockKG, \
         patch("astra.ingestion.pipeline.DependencyResolver") as MockResolver, \
         patch("astra.ingestion.pipeline.IngestionCache") as MockCache, \
         patch("astra.ingestion.pipeline.get_config") as MockConfig:

        config = MagicMock()
        config.get.side_effect = lambda section, key, default=None: default
        MockConfig.return_value = config

        yield {
            "store": MockStore.return_value,
            "graph": MockKG.return_value,
            "resolver": MockResolver.return_value,
            "cache": MockCache.return_value,
            "config": config,
            "MockStore": MockStore,
            "MockKG": MockKG
        }

@pytest.fixture
def pipeline(mock_dependencies):
    """Create a pipeline instance with mocked dependencies."""
    return IngestionPipeline()

def test_initialization(pipeline, mock_dependencies):
    """Test pipeline initialization."""
    assert pipeline.store == mock_dependencies["store"]
    assert pipeline.graph == mock_dependencies["graph"]
    assert pipeline.resolver == mock_dependencies["resolver"]
    assert pipeline.cache == mock_dependencies["cache"]

@pytest.mark.asyncio
async def test_run_async_empty_directory(pipeline, tmp_path):
    """Test running on empty directory."""
    with patch("os.walk", return_value=[]):
        count = await pipeline.run_async(str(tmp_path), "test_collection")
        assert count == 0

@pytest.mark.asyncio
async def test_run_async_skips_ignored(pipeline, tmp_path):
    """Test that ignored directories are skipped."""
    # Mock os.walk to yield a .git directory
    mock_walk = [
        (str(tmp_path), [".git"], ["file.txt"]),
        (str(tmp_path / ".git"), [], ["HEAD"])
    ]

    # Create dummy files
    (tmp_path / "file.txt").touch()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").touch()

    with patch("os.walk", return_value=mock_walk), \
         patch("astra.ingestion.parser.get_language_for_file", return_value="python"), \
         patch("concurrent.futures.as_completed", return_value=[]):

        # Configure cache to say file is NOT cached (so it tries to process)
        pipeline.cache.check_file.return_value = False

        # But we want to ensure .git is skipped from processing list
        # The logic in pipeline.py modifies 'dirs' in-place.
        # It's hard to test in-place modification of os.walk yield with return_value
        # Instead, we check if HEAD is processed (it shouldn't be because .git is ignored in the loop check)

        # Actually logic is: if any(p in root_path ...): dirs[:] = []

        # Let's mock ProcessPoolExecutor to fail if called
        with patch("concurrent.futures.ProcessPoolExecutor") as MockExecutor:
             # If .git is processed, it would try to submit a task
             await pipeline.run_async(str(tmp_path), "test_collection")

             # Should only submit for file.txt, not HEAD
             # Wait, file.txt is in root, so it is submitted?
             # Yes. But HEAD is in .git.

             # Verify submit called only once for file.txt
             assert MockExecutor.return_value.__enter__.return_value.submit.call_count == 1

@pytest.mark.asyncio
async def test_run_async_uses_cache(pipeline, tmp_path):
    """Test that cached files are skipped."""
    mock_walk = [(str(tmp_path), [], ["cached.py", "uncached.py"])]
    (tmp_path / "cached.py").touch()
    (tmp_path / "uncached.py").touch()

    with patch("os.walk", return_value=mock_walk), \
         patch("astra.ingestion.parser.get_language_for_file", return_value="python"), \
         patch("concurrent.futures.as_completed", return_value=[]):

        # Cache returns True for first file, False for second
        pipeline.cache.check_file.side_effect = lambda p: p.name == "cached.py"

        with patch("concurrent.futures.ProcessPoolExecutor") as MockExecutor:
             await pipeline.run_async(str(tmp_path), "test_collection")

             # Should submit only uncached.py
             assert MockExecutor.return_value.__enter__.return_value.submit.call_count == 1

@pytest.mark.asyncio
async def test_run_async_processing(pipeline, tmp_path):
    """Test full processing flow."""
    mock_walk = [(str(tmp_path), [], ["main.py"])]
    (tmp_path / "main.py").touch()

    # Mock Future result
    mock_future = MagicMock()
    mock_future.result.return_value = (str(tmp_path/"main.py"), [{"id": "node1"}], "hash123")

    # Ensure cache check returns False
    pipeline.cache.check_file.return_value = False

    with patch("os.walk", return_value=mock_walk), \
         patch("astra.ingestion.parser.get_language_for_file", return_value="python"), \
         patch("concurrent.futures.ProcessPoolExecutor") as MockExecutor, \
         patch("concurrent.futures.as_completed", return_value=[mock_future]):

        mock_executor_instance = MockExecutor.return_value.__enter__.return_value
        mock_executor_instance.submit.return_value = mock_future

        total = await pipeline.run_async(str(tmp_path), "test_collection")

        assert total == 1
        pipeline.store.add_nodes.assert_called()
        pipeline.graph.add_nodes.assert_called()
        pipeline.resolver.index_files.assert_called()
        pipeline.cache.update.assert_called()
        pipeline.cache.save.assert_called()
        pipeline.graph.save.assert_called()

@pytest.mark.asyncio
async def test_process_batch(pipeline):
    """Test batch processing logic."""
    nodes = [{"id": "1", "content": "test"}]

    pipeline.resolver.resolve.return_value = [("src", "dst")]

    await pipeline._process_batch("test_col", nodes)

    pipeline.store.add_nodes.assert_called_with("test_col", nodes)
    pipeline.graph.add_nodes.assert_called_with(nodes)
    pipeline.resolver.index_files.assert_called_with(nodes)
    pipeline.resolver.resolve.assert_called_with(nodes)
    pipeline.graph.add_import.assert_called_with("src", "dst")

@pytest.mark.asyncio
async def test_parse_worker_integration(tmp_path):
    """Test the worker function standalone."""
    from astra.ingestion.pipeline import _parse_worker

    f = tmp_path / "test.py"
    f.write_text("def foo(): pass")

    # Mock parser inside worker (since it imports fresh)
    with patch("astra.ingestion.parser.ASTParser") as MockParser, \
         patch("astra.ingestion.ingestion_cache.IngestionCache") as MockCache:

         MockCache.calculate_hash.return_value = "abc"
         MockParser.return_value.parse_file.return_value = ["node"]

         res = _parse_worker(str(f), str(tmp_path), 3)

         assert res == (str(f), ["node"], "abc")

@pytest.mark.asyncio
async def test_parse_worker_exception(tmp_path):
    """Test worker handles exceptions."""
    from astra.ingestion.pipeline import _parse_worker

    with patch("astra.ingestion.ingestion_cache.IngestionCache") as MockCache:
         MockCache.calculate_hash.side_effect = Exception("Boom")

         res = _parse_worker("bad.py", str(tmp_path), 3)

         assert res == ("bad.py", None, None)
