"""Comprehensive tests for ChromaDB store with mocking and edge cases."""

from unittest.mock import MagicMock, patch

import pytest

from astra.interfaces.vector_store import ASTNode, QueryResult

# === Fixtures ===


@pytest.fixture
def sample_nodes():
    """Create sample AST nodes for testing."""
    return [
        ASTNode(
            id="node1",
            type="function_definition",
            name="greet",
            content="function greet(name: string) { return 'Hello, ' + name; }",
            file_path="src/utils.ts",
            start_line=1,
            end_line=3,
            language="typescript",
        ),
        ASTNode(
            id="node2",
            type="class_declaration",
            name="UserService",
            content="class UserService { constructor() {} }",
            file_path="src/services/user.ts",
            start_line=1,
            end_line=10,
            language="typescript",
        ),
        ASTNode(
            id="node3",
            type="function_definition",
            name="authenticate",
            content="async function authenticate(user: User): Promise<boolean> { return true; }",
            file_path="src/auth.ts",
            start_line=5,
            end_line=15,
            language="typescript",
        ),
    ]


class TestChromaDBStoreWithMocks:
    """Test ChromaDB store with mocked dependencies."""

    @pytest.fixture
    def mocked_store(self):
        """Create store with mocked ChromaDB client and embedding model."""
        # Patch the CLASSES directly because imports are now local/lazy
        with (
            patch("chromadb.PersistentClient") as mock_client_cls,
            patch("sentence_transformers.SentenceTransformer") as mock_st,
            patch("astra.config.get_config") as mock_config,
            patch("pathlib.Path") as mock_path,
        ):
            # Clear cache to avoid test pollution
            from astra.adapters.chromadb_store import ChromaDBStore

            ChromaDBStore._model_cache.clear()

            # Setup config mock
            # Setup config mock
            config = MagicMock()
            config.get = MagicMock(
                side_effect=lambda *args, default=None: {
                    ("vectordb", "persist_path"): "./test_data/chromadb",
                    ("ingestion", "embedding_model"): "default",
                    ("ingestion", "batch_size"): 10,
                }.get(args, default)
            )
            mock_config.return_value = config

            # Setup path mock
            mock_path.return_value.mkdir = MagicMock()
            mock_path.return_value.exists.return_value = True

            # Setup embedding model mock - needs to return object with tolist()
            embedder = MagicMock()
            mock_encode_result = MagicMock()
            mock_encode_result.tolist.return_value = [[0.1, 0.2, 0.3]] * 10
            embedder.encode = MagicMock(return_value=mock_encode_result)
            mock_st.return_value = embedder

            # Setup ChromaDB client mock
            client = MagicMock()
            collection = MagicMock()
            collection.count.return_value = 100
            client.get_or_create_collection.return_value = collection
            client.list_collections.return_value = [collection]
            mock_client_cls.return_value = client

            from astra.adapters.chromadb_store import ChromaDBStore

            store = ChromaDBStore()

            yield {
                "store": store,
                "client": client,
                "collection": collection,
                "embedder": embedder,
                "config": config,
            }

    def test_create_collection(self, mocked_store):
        """Test collection creation."""
        store = mocked_store["store"]
        client = mocked_store["client"]

        store.create_collection("test_project")

        client.get_or_create_collection.assert_called()

    def test_delete_collection(self, mocked_store):
        """Test collection deletion."""
        store = mocked_store["store"]
        client = mocked_store["client"]

        store.delete_collection("test_project")

        client.delete_collection.assert_called_once_with(name="test_project")

    def test_list_collections(self, mocked_store):
        """Test listing collections."""
        store = mocked_store["store"]

        result = store.list_collections()

        assert isinstance(result, list)

    def test_add_nodes_batches_correctly(self, mocked_store, sample_nodes):
        """Test that nodes are added in batches."""
        store = mocked_store["store"]
        collection = mocked_store["collection"]

        # Add 3 nodes with batch size of 10 (should be 1 batch)
        store.add_nodes("test", sample_nodes)

        # Upsert should be called once for the batch
        collection.upsert.assert_called()

    def test_add_nodes_empty_list(self, mocked_store):
        """Test adding empty node list doesn't crash."""
        store = mocked_store["store"]
        collection = mocked_store["collection"]

        store.add_nodes("test", [])

        # Upsert should not be called
        collection.upsert.assert_not_called()

    def test_add_documents(self, mocked_store):
        """Test adding generic documents."""
        store = mocked_store["store"]
        collection = mocked_store["collection"]
        embedder = mocked_store["embedder"]

        ids = ["doc1", "doc2"]
        documents = ["content1", "content2"]
        metadatas = [{"meta": 1}, {"meta": 2}]

        # Setup customized embedding return for this test
        mock_encode_result = MagicMock()
        mock_encode_result.tolist.return_value = [[0.1, 0.2, 0.3]] * 2
        embedder.encode.return_value = mock_encode_result

        store.add_documents("test", ids, documents, metadatas)

        collection.upsert.assert_called_with(
            ids=ids,
            embeddings=[[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]],
            documents=documents,
            metadatas=metadatas,
        )

    def test_cleanup_stale_collections(self, mocked_store):
        """Test cleaning up stale collections."""
        from datetime import UTC, datetime, timedelta

        store = mocked_store["store"]
        client = mocked_store["client"]

        # Mock collections with different access times
        col_fresh = MagicMock()
        col_fresh.name = "fresh"
        col_fresh.metadata = {"last_accessed": datetime.now(UTC).isoformat()}

        col_stale = MagicMock()
        col_stale.name = "stale"
        col_stale.metadata = {"last_accessed": (datetime.now(UTC) - timedelta(days=40)).isoformat()}

        client.list_collections.return_value = [col_fresh, col_stale]

        deleted = store.cleanup_stale_collections(max_age_days=30)

        assert "stale" in deleted
        assert "fresh" not in deleted
        client.delete_collection.assert_called_with(name="stale")

    def test_query_returns_results(self, mocked_store):
        """Test querying returns formatted results."""
        store = mocked_store["store"]
        collection = mocked_store["collection"]

        # Setup query results
        collection.query.return_value = {
            "ids": [["node1", "node2"]],
            "documents": [["content1", "content2"]],
            "metadatas": [
                [
                    {
                        "type": "function",
                        "name": "greet",
                        "file_path": "src/utils.ts",
                        "start_line": 1,
                        "end_line": 3,
                        "language": "typescript",
                    },
                    {
                        "type": "class",
                        "name": "User",
                        "file_path": "src/user.ts",
                        "start_line": 1,
                        "end_line": 10,
                        "language": "typescript",
                    },
                ]
            ],
            "distances": [[0.1, 0.3]],
        }

        results = store.query("test_collection", "find greeting function")

        assert len(results) == 2
        assert all(isinstance(r, QueryResult) for r in results)
        assert results[0].distance == 0.1
        assert results[0].node.name == "greet"

    def test_query_empty_results(self, mocked_store):
        """Test querying with no results."""
        store = mocked_store["store"]
        collection = mocked_store["collection"]

        collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        results = store.query("test", "nonexistent query")

        assert results == []

    def test_clear_collection_recreates(self, mocked_store):
        """Test clearing a collection."""
        store = mocked_store["store"]
        client = mocked_store["client"]

        store.clear_collection("test")

        # Should delete then recreate
        client.delete_collection.assert_called_with("test")


class TestEmbeddingModelSelection:
    """Test embedding model selection logic."""

    @pytest.mark.parametrize(
        "model_name,expected_model",
        [
            ("default", "all-MiniLM-L6-v2"),
            ("codebert", "microsoft/codebert-base"),
            ("mpnet", "all-mpnet-base-v2"),
            ("custom/model", "custom/model"),  # Unknown model passes through
        ],
    )
    def test_model_selection(self, model_name, expected_model):
        """Test correct model is selected based on config."""
        with (
            patch("chromadb.PersistentClient"),
            patch("sentence_transformers.SentenceTransformer") as mock_st,
            patch("astra.config.get_config") as mock_config,
            patch("pathlib.Path"),
        ):
            from astra.adapters.chromadb_store import ChromaDBStore

            ChromaDBStore._model_cache.clear()

            config = MagicMock()
            config.get = MagicMock(
                side_effect=lambda *args, default=None: {
                    ("ingestion", "embedding_model"): model_name
                }.get(args, default)
            )
            mock_config.return_value = config

            mock_st.return_value = MagicMock()

            from astra.adapters.chromadb_store import ChromaDBStore

            store = ChromaDBStore(embedding_model=model_name)

            # Explicitly trigger lazy loading
            store._embed(["test"])

            # Check that the correct model was attempted
            call_args = mock_st.call_args_list
            assert any(expected_model in str(call) for call in call_args)


class TestChromaDBEdgeCases:
    """Edge case tests for ChromaDB store."""

    def test_handle_large_content(self, sample_nodes):
        """Test handling of very large code content."""
        large_node = ASTNode(
            id="large",
            type="function",
            name="bigFunction",
            content="x" * 100000,  # 100KB of content
            file_path="src/big.ts",
            start_line=1,
            end_line=1000,
            language="typescript",
        )

        # Node should be created without issues
        assert len(large_node.content) == 100000

    def test_handle_unicode_content(self):
        """Test handling of unicode in code content."""
        unicode_node = ASTNode(
            id="unicode",
            type="function",
            name="greet_日本語",
            content="function greet_日本語(名前: string) { return `こんにちは、${名前}！`; }",
            file_path="src/国際化.ts",
            start_line=1,
            end_line=3,
            language="typescript",
        )

        assert "日本語" in unicode_node.name
        assert "こんにちは" in unicode_node.content

    def test_handle_special_characters_in_path(self):
        """Test handling of special characters in file paths."""
        node = ASTNode(
            id="special",
            type="function",
            name="test",
            content="function test() {}",
            file_path="src/[components]/login-form.tsx",
            start_line=1,
            end_line=1,
            language="tsx",
        )

        assert "[components]" in node.file_path


class TestQueryFiltering:
    """Test query filtering permutations."""

    @pytest.fixture
    def store_with_query(self):
        """Create store setup for query testing."""
        with (
            patch("chromadb.PersistentClient") as mock_client_cls,
            patch("sentence_transformers.SentenceTransformer") as mock_st,
            patch("astra.config.get_config") as mock_config,
            patch("pathlib.Path"),
        ):
            config = MagicMock()
            config.get = MagicMock(return_value=None)
            mock_config.return_value = config

            embedder = MagicMock()
            mock_encode_result = MagicMock()
            mock_encode_result.tolist.return_value = [[0.1, 0.2, 0.3]]
            embedder.encode = MagicMock(return_value=mock_encode_result)
            mock_st.return_value = embedder

            client = MagicMock()
            collection = MagicMock()
            collection.query.return_value = {
                "ids": [[]],
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
            }
            client.get_or_create_collection.return_value = collection
            mock_client_cls.return_value = client

            from astra.adapters.chromadb_store import ChromaDBStore

            store = ChromaDBStore()

            yield {"store": store, "collection": collection}

    @pytest.mark.parametrize("n_results", [1, 5, 10, 50, 100])
    def test_query_result_limits(self, store_with_query, n_results):
        """Test query respects n_results parameter."""
        store = store_with_query["store"]
        collection = store_with_query["collection"]

        store.query("test", "search query", n_results=n_results)

        # Verify n_results was passed to collection.query
        call_kwargs = collection.query.call_args[1]
        assert call_kwargs["n_results"] == n_results

    def test_query_with_filter(self, store_with_query):
        """Test query with metadata filter."""
        store = store_with_query["store"]
        collection = store_with_query["collection"]

        store.query("test", "search query", filter_metadata={"language": "typescript"})

        call_kwargs = collection.query.call_args[1]
        assert call_kwargs["where"] == {"language": "typescript"}
