from unittest.mock import MagicMock, patch

from astra.adapters.chromadb_store import ChromaDBStore

# Test Incremental Optimization
# Using sync test since Store is sync wrapper around Chroma client (mostly)


def test_add_documents_optimization():
    # Setup Mocks
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection

    # Mock existing items return
    # First call: empty
    # Second call: returns existing hash
    mock_collection.get.side_effect = [
        {"ids": [], "metadatas": []},  # Batch 1 (New)
        {
            "ids": ["id1"],
            "metadatas": [
                {"content_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
            ],
        },  # Batch 2 (Unchanged)
    ]

    # Mock embedding model
    mock_model = MagicMock()
    mock_model.encode.return_value.tolist.return_value = [[0.1, 0.2]]  # Fake embedding

    with (
        patch("chromadb.PersistentClient", return_value=mock_client),
        patch("sentence_transformers.SentenceTransformer", return_value=mock_model),
    ):
        store = ChromaDBStore(persist_path=".")
        store._embedding_model = mock_model  # enforce mock

        # 1. Add NEW document
        store.add_documents("test_col", ["id1"], ["content1"], [{"key": "val"}])

        # Assert embedded
        assert mock_model.encode.called
        assert mock_collection.upsert.call_count == 1
        mock_model.encode.reset_mock()
        mock_collection.upsert.reset_mock()

        # 2. Add UNCHANGED document
        import hashlib

        content = "content1"
        meta = {"key": "val"}
        meta_str = str(sorted(meta.items()))
        expected_hash = hashlib.sha256(f"{content}{meta_str}".encode()).hexdigest()

        # Update mock return to have THIS hash
        mock_collection.get.side_effect = None
        mock_collection.get.return_value = {
            "ids": ["id1"],
            "metadatas": [{"content_hash": expected_hash}],
        }

        store.add_documents("test_col", ["id1"], ["content1"], [{"key": "val"}])

        # Assert NOT embedded
        assert not mock_model.encode.called
        assert not mock_collection.upsert.called

        # 3. Add CHANGED document (diff content)
        store.add_documents("test_col", ["id1"], ["content_NEW"], [{"key": "val"}])

        # Assert embedded
        assert mock_model.encode.called
        assert mock_collection.upsert.called
