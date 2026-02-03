
from unittest.mock import MagicMock, patch


class TestChromaMemoryStore:
    def test_init_config_defaults(self):
        """Test that it picks up defaults from config if not provided."""
        # We also need to patch the lazy imports inside ChromaDBStore if we instantiated it real,
        # but here we are mocking super().__init__ which is simpler to just check argument passing.

        with patch('astra.adapters.chromadb_store.ChromaDBStore.__init__', return_value=None) as mock_super, \
             patch('astra.memory.store.get_config') as mock_get_config:

            mock_config = MagicMock()
            mock_config.get.side_effect = lambda section, key, default=None: default
            mock_get_config.return_value = mock_config

            from astra.memory.store import ChromaMemoryStore
            store = ChromaMemoryStore()

            # Check default path logic
            args, kwargs = mock_super.call_args
            assert kwargs.get('persist_path') == "./data/memory"
            # Current hardcoded val
            assert kwargs.get('embedding_model') == "all-MiniLM-L6-v2"

    def test_init_config_overrides(self):
        """Test that config overrides work for path and model."""
        with patch('astra.adapters.chromadb_store.ChromaDBStore.__init__', return_value=None) as mock_super, \
             patch('astra.memory.store.get_config') as mock_get_config:

            mock_config = MagicMock()
            # Simulate config returning custom values
            def get_side_effect(section, key, default=None):
                if section == "memory" and key == "persist_path":
                    return "./custom/memory/path"
                if section == "memory" and key == "embedding_model":
                    return "custom-model"
                return default

            mock_config.get.side_effect = get_side_effect
            mock_get_config.return_value = mock_config

            from astra.memory.store import ChromaMemoryStore
            store = ChromaMemoryStore()

            args, kwargs = mock_super.call_args
            assert kwargs.get('persist_path') == "./custom/memory/path"

            # THIS ASSERTION IS EXPECTED TO FAIL CURRENTLY
            assert kwargs.get('embedding_model') == "custom-model"
