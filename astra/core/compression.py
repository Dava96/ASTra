"""
Context Compression using LLMLingua.
Optimizes context window usage by removing redundant tokens.
"""

import logging

from astra.config import get_config

logger = logging.getLogger(__name__)

class ContextCompressor:
    """
    Compresses text context using LLMLingua to fit within token limits.
    Uses a small local model to identify and remove low-entropy tokens.
    """

    def __init__(self):
        self._config = get_config()
        self._compressor = None
        self._enabled = self._config.get("context", "compression_enabled", default=False)
        self._model_name = self._config.get("context", "compression_model", default="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank")
        self._device_map = "cpu" # Force CPU for VPS compatibility unless configured otherwise

    def _load_model(self):
        """Lazy load the compression model."""
        if self._compressor:
            return

        try:
            from llmlingua import PromptCompressor
            logger.info(f"Loading LLMLingua model: {self._model_name} on {self._device_map}")
            self._compressor = PromptCompressor(
                model_name=self._model_name,
                device_map=self._device_map,
                use_auth_token=False
            )
        except ImportError:
            logger.error("LLMLingua not installed. Context compression disabled.")
            self._enabled = False
        except Exception as e:
            logger.error(f"Failed to load LLMLingua model: {e}")
            self._enabled = False

    def compress(self, context: str, target_token_count: int = 2000) -> str:
        """
        Compress the given context string to approximately the target token count.
        
        Args:
            context: The text to compress.
            target_token_count: The desired number of tokens after compression.
            
        Returns:
            The compressed string, or the original if compression fails/disabled.
        """
        if not self._enabled:
            return context

        if not context or not context.strip():
            return context

        self._load_model()

        if not self._compressor:
            return context

        try:
            # Estimate current tokens (rough char count heuristic: 1 token ~= 4 chars)
            # LLMLingua handles tokenization internally, but check if we even need to compress
            current_est_tokens = len(context) / 4
            if current_est_tokens <= target_token_count:
                return context

            logger.info(f"Compressing context from ~{int(current_est_tokens)} to {target_token_count} tokens")

            # compress_prompt returns a dictionary
            result = self._compressor.compress_prompt(
                context,
                target_token=target_token_count,
                # Heuristic parameters for code/structured text preservation
                rank_method="longllmlingua",
                context_budget="+100", # Slack
                dynamic_context_compression_ratio=0.5 # Aggressiveness
            )

            compressed_text = result['compressed_prompt']
            logger.info(f"Context compressed. New length: {len(compressed_text)}")
            return compressed_text

        except Exception as e:
            logger.warning(f"Compression failed: {e}. Returning original context.")
            return context
