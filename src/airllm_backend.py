"""AirLLM inference backend for GarudaAI.

Allows running 70B+ parameter models on GPUs with as little as 4GB VRAM
by loading model weights layer-by-layer from SSD (disk offloading).

Install optional deps first:
    pip install garudaai[airllm]
    # or: pip install airllm bitsandbytes

IMPORTANT: Responses take 1-3 minutes per message (limited by SSD throughput).
Suitable for tasks where quality matters more than speed.
"""

import asyncio
import logging
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

# Cache loaded models to avoid reloading on every request
_model_cache: dict = {}


class AirLLMBackend:
    """Inference backend using AirLLM layer-offloading.

    Usage:
        backend = AirLLMBackend("meta-llama/Llama-3.3-70B-Instruct")
        backend.load()   # downloads and shards model on first call (~slow)
        async for chunk in backend.stream_generate(prompt):
            yield chunk
    """

    def __init__(self, hf_model_id: str, compression: str = "4bit"):
        """
        Args:
            hf_model_id: HuggingFace model ID, e.g. "meta-llama/Llama-3.3-70B-Instruct"
            compression: "4bit" (default, 3x faster) or "8bit" or None
        """
        self.hf_model_id = hf_model_id
        self.compression = compression
        self._model = None

    def is_available(self) -> bool:
        """Check if the airllm package is installed."""
        try:
            import airllm  # noqa: F401
            return True
        except ImportError:
            return False

    def load(self):
        """Load and shard the model (slow on first call, cached afterward)."""
        cache_key = f"{self.hf_model_id}:{self.compression}"
        if cache_key in _model_cache:
            self._model = _model_cache[cache_key]
            logger.info(f"AirLLM: reusing cached model {self.hf_model_id}")
            return

        if not self.is_available():
            raise ImportError(
                "airllm is not installed. Run: pip install 'garudaai[airllm]'"
            )

        try:
            from airllm import AutoModel
            logger.info(f"AirLLM: loading {self.hf_model_id} (compression={self.compression})")
            kwargs = {}
            if self.compression:
                kwargs["compression"] = self.compression
            self._model = AutoModel.from_pretrained(self.hf_model_id, **kwargs)
            _model_cache[cache_key] = self._model
            logger.info("AirLLM: model loaded and cached")
        except Exception as e:
            logger.error(f"AirLLM: failed to load model: {e}")
            raise

    def _run_inference(self, prompt: str, max_new_tokens: int) -> str:
        """Blocking inference — called in a thread."""
        if self._model is None:
            self.load()

        tokenizer = self._model.tokenizer
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            return_attention_mask=False,
            truncation=True,
            max_length=2048,
            padding=False,
        )

        try:
            import torch
            input_ids = inputs["input_ids"].cuda()
        except Exception:
            input_ids = inputs["input_ids"]

        output = self._model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            use_cache=True,
            return_dict_in_generate=True,
        )

        # Decode only the newly generated tokens (exclude the prompt)
        new_tokens = output.sequences[0][input_ids.shape[-1]:]
        return tokenizer.decode(new_tokens, skip_special_tokens=True)

    async def stream_generate(
        self,
        prompt: str,
        max_new_tokens: int = 512,
    ) -> AsyncGenerator[str, None]:
        """Run inference in a thread and yield the full response as one chunk.

        AirLLM does not support true token-level streaming because each token
        requires a full disk-offload cycle (~0.5-2 seconds). Yielding the full
        response at once is the correct UX pattern here.
        """
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, self._run_inference, prompt, max_new_tokens
            )
            yield result
        except Exception as e:
            logger.error(f"AirLLM inference error: {e}")
            yield f"Error during AirLLM inference: {e}"


def get_airllm_backend(hf_model_id: str) -> AirLLMBackend:
    """Factory: return a cached-or-new AirLLMBackend instance."""
    return AirLLMBackend(hf_model_id)
