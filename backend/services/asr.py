"""Automatic speech recognition (ASR) service.

Uses HuggingFace Inference Providers via the official `huggingface_hub` SDK
(handles endpoint routing automatically — direct REST hits the wrong URL on
the current API). Free with the user's HF token. No Google dependency.

The first call to a cold model can take 10-30s while it loads on HF;
subsequent calls are ~1-2s for short audio.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class WhisperHFASR:
    """Whisper ASR via HuggingFace Inference Providers."""

    def __init__(
        self,
        hf_token: str,
        model: str = "openai/whisper-large-v3",
    ) -> None:
        if not hf_token:
            raise ValueError("HF_TOKEN required for Whisper ASR")
        from huggingface_hub import InferenceClient
        self.hf_token = hf_token
        self.model = model
        self.client = InferenceClient(token=hf_token)

    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/wav") -> dict[str, Any]:
        """Returns {text, model, latency_ms}. Raises on hard failure."""
        if not audio_bytes:
            raise ValueError("empty audio")

        # InferenceClient is sync — run in a thread to keep the event loop free
        return await asyncio.to_thread(self._transcribe_sync, audio_bytes)

    def _transcribe_sync(self, audio_bytes: bytes) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            result = self.client.automatic_speech_recognition(audio_bytes, model=self.model)
        except Exception as exc:
            logger.error("Whisper ASR failed: %s", exc)
            raise RuntimeError(f"Whisper ASR failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - t0) * 1000)
        # InferenceClient may return a dataclass or dict
        text = (
            getattr(result, "text", None)
            or (result.get("text") if isinstance(result, dict) else None)
            or str(result)
        ).strip()
        return {"text": text, "model": self.model, "latency_ms": latency_ms}


_asr_singleton: WhisperHFASR | None = None


def get_asr() -> WhisperHFASR | None:
    """Returns ASR client if HF_TOKEN is configured, else None."""
    global _asr_singleton
    if _asr_singleton is not None:
        return _asr_singleton
    from config import get_settings
    settings = get_settings()
    if not settings.hf_token:
        return None
    _asr_singleton = WhisperHFASR(hf_token=settings.hf_token)
    return _asr_singleton
