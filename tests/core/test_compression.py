from unittest.mock import patch

import pytest

from astra.core.compression import ContextCompressor


@pytest.fixture
def mock_compressor_cls():
    # Patch where the class is defined (llmlingua) not where it is used,
    # because it is imported inside the function.
    # However, since we want to intercept the import, we can patch sys.modules or just patch llmlingua directly
    # if we assume it can be imported.
    # A safer way relies on the fact that when `from llmlingua import PromptCompressor` runs, it looks up in llmlingua.
    # So we patch 'llmlingua.PromptCompressor'.
    with patch("llmlingua.PromptCompressor") as mock:
        yield mock


def test_compressor_disabled_by_default():
    """Test that compressor does nothing if disabled in config."""
    # Mock config to be disabled
    with patch("astra.core.compression.get_config") as mock_conf:
        mock_conf.return_value.get.return_value = False

        compressor = ContextCompressor()
        text = "Some long text " * 100
        result = compressor.compress(text)
        assert result == text


def test_compressor_lazy_load(mock_compressor_cls):
    """Test that model is loaded only on first compress call."""
    with patch("astra.core.compression.get_config") as mock_conf:
        # Enable compression
        mock_conf.return_value.get.side_effect = (
            lambda section, key, default=None: True if key == "compression_enabled" else default
        )

        compressor = ContextCompressor()
        # Init shouldn't load
        mock_compressor_cls.assert_not_called()

        # Compress should load
        compressor.compress("test")
        mock_compressor_cls.assert_called_once()


def test_compress_logic(mock_compressor_cls):
    """Test standard compression flow."""
    with patch("astra.core.compression.get_config") as mock_conf:
        mock_conf.return_value.get.side_effect = (
            lambda section, key, default=None: True if key == "compression_enabled" else default
        )

        mock_instance = mock_compressor_cls.return_value
        mock_instance.compress_prompt.return_value = {"compressed_prompt": "CompText"}

        compressor = ContextCompressor()
        long_text = "Original " * 100
        result = compressor.compress(long_text, target_token_count=50)

        assert result == "CompText"
        mock_instance.compress_prompt.assert_called()


def test_graceful_failure(mock_compressor_cls):
    """Test fallback to original text on error."""
    with patch("astra.core.compression.get_config") as mock_conf:
        mock_conf.return_value.get.side_effect = (
            lambda section, key, default=None: True if key == "compression_enabled" else default
        )

        mock_instance = mock_compressor_cls.return_value
        mock_instance.compress_prompt.side_effect = Exception("Model Error")

        compressor = ContextCompressor()
        long_text = "Original " * 100
        result = compressor.compress(long_text, target_token_count=10)

        assert result == long_text
