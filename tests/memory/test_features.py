
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch


class TestChromaMemoryFeatures:

    def test_ephemeral_init(self):
        """Test initialization in ephemeral mode."""
        with patch('chromadb.EphemeralClient') as mock_ephemeral, \
             patch('chromadb.PersistentClient') as mock_persistent, \
             patch('astra.config.get_config') as mock_config, \
             patch('pathlib.Path') as mock_path:

            mock_conf = MagicMock()
            mock_conf.get.side_effect = lambda s, k, default=None: default
            mock_config.return_value = mock_conf

            from astra.memory.store import ChromaMemoryStore

            # Explicit ephemeral=True
            store = ChromaMemoryStore(ephemeral=True)

            mock_ephemeral.assert_called_once()
            mock_persistent.assert_not_called()
            mock_path.return_value.mkdir.assert_not_called()

    def test_cleanup_expired(self):
        """Test TTL cleanup logic."""
        with patch('chromadb.PersistentClient'), \
             patch('astra.config.get_config'), \
             patch('pathlib.Path'):

            from astra.memory.store import ChromaMemoryStore
            store = ChromaMemoryStore()

            # Mock collection and get/delete
            mock_col = MagicMock()
            store._client.get_or_create_collection.return_value = mock_col

            # Setup mock data: 2 expired, 1 fresh
            now = datetime.now(UTC)
            expired_ts = (now - timedelta(hours=25)).timestamp()
            fresh_ts = (now - timedelta(hours=1)).timestamp()

            # Mock return from col.get()
            mock_col.get.return_value = {
                "ids": ["exp1", "exp2"]
            }

            deleted_count = store.cleanup_expired("test_col", ttl_hours=24)

            assert deleted_count == 2

            # Verify query structure
            call_args = mock_col.get.call_args
            where_clause = call_args.kwargs['where']
            assert "created_at" in where_clause
            assert "$lt" in where_clause["created_at"]

            # Verify delete call
            mock_col.delete.assert_called_with(ids=["exp1", "exp2"])

    def test_cleanup_no_expired(self):
            """Test cleanup when nothing is expired."""
            with patch('chromadb.PersistentClient'), \
                 patch('astra.config.get_config'), \
                 patch('pathlib.Path'):

                from astra.memory.store import ChromaMemoryStore
                store = ChromaMemoryStore()

                mock_col = MagicMock()
                store._client.get_or_create_collection.return_value = mock_col

                # empty result
                mock_col.get.return_value = {"ids": []}

                deleted_count = store.cleanup_expired("test_col")
                assert deleted_count == 0
                mock_col.delete.assert_not_called()
