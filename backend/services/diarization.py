"""Speaker diarization service.

`MockDiarizer`: round-robins through expected speakers (no real audio analysis).
`PyannoteDiarizer`: real diarization using pyannote.audio + HF-hosted model.

Selected via USE_MOCK_DIARIZATION env flag.
"""
from __future__ import annotations

import asyncio
import io
import logging
import random
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DiarizedTurn:
    speaker_id: str
    start_seconds: float
    end_seconds: float
    confidence: float


class BaseDiarizer:
    async def diarize(self, audio_chunk: bytes | None, hint_speakers: list[str]) -> list[DiarizedTurn]:
        raise NotImplementedError


class MockDiarizer(BaseDiarizer):
    """Round-robins through hint speakers to simulate diarization."""

    def __init__(self) -> None:
        self._counter = 0

    async def diarize(self, audio_chunk: bytes | None, hint_speakers: list[str]) -> list[DiarizedTurn]:
        if not hint_speakers:
            hint_speakers = ["Speaker 1", "Speaker 2", "Speaker 3"]
        speaker = hint_speakers[self._counter % len(hint_speakers)]
        self._counter += 1
        return [
            DiarizedTurn(
                speaker_id=speaker,
                start_seconds=0.0,
                end_seconds=2.5,
                confidence=round(random.uniform(0.85, 0.99), 2),
            )
        ]


class PyannoteDiarizer(BaseDiarizer):
    """Real speaker diarization using pyannote/speaker-diarization-3.1.

    Pre-loads audio with soundfile to bypass the torchcodec/ffmpeg dependency
    that causes issues on macOS. Maps detected speaker labels (SPEAKER_00,
    SPEAKER_01, ...) to the user-provided hint speakers in first-appearance order.
    """

    def __init__(self, hf_token: str, model: str = "pyannote/speaker-diarization-3.1") -> None:
        """Loads the pyannote speaker diarization pipeline.

        On pyannote.audio 4.x, the default `speaker-diarization-3.1` model
        depends on `pyannote/speaker-diarization-community-1` (a separately
        gated repo). All three repos must have terms accepted:
          - pyannote/speaker-diarization-3.1
          - pyannote/segmentation-3.0
          - pyannote/speaker-diarization-community-1
        """
        from pyannote.audio import Pipeline
        import torch

        logger.info("Loading %s (first run downloads ~100MB)...", model)
        # pyannote 4.x renamed `use_auth_token` -> `token`
        try:
            self.pipeline = Pipeline.from_pretrained(model, token=hf_token)
        except TypeError:
            # Backwards-compat for pyannote 3.x
            self.pipeline = Pipeline.from_pretrained(model, use_auth_token=hf_token)
        # Use Apple Silicon MPS or CUDA if available
        if torch.cuda.is_available():
            self.pipeline.to(torch.device("cuda"))
            logger.info("pyannote running on CUDA")
        elif torch.backends.mps.is_available():
            # Note: pyannote sometimes has MPS issues; fall back to CPU on error
            try:
                self.pipeline.to(torch.device("mps"))
                logger.info("pyannote running on MPS (Apple Silicon)")
            except Exception:
                logger.warning("MPS load failed, using CPU")
        else:
            logger.info("pyannote running on CPU")

    async def diarize(self, audio_chunk: bytes | None, hint_speakers: list[str]) -> list[DiarizedTurn]:
        if not audio_chunk:
            logger.warning("PyannoteDiarizer called with no audio — returning empty")
            return []

        # Run sync pyannote in a thread to avoid blocking the event loop
        return await asyncio.to_thread(self._diarize_sync, audio_chunk, hint_speakers)

    def _diarize_sync(self, audio_bytes: bytes, hint_speakers: list[str]) -> list[DiarizedTurn]:
        import soundfile as sf
        import torch

        # Decode WAV bytes via soundfile (bypasses torchcodec)
        audio_buf = io.BytesIO(audio_bytes)
        try:
            waveform_np, sample_rate = sf.read(audio_buf, dtype="float32", always_2d=True)
        except Exception as exc:
            logger.error("Failed to decode audio: %s", exc)
            return []

        # Convert (samples, channels) → (channels, samples) tensor
        waveform = torch.from_numpy(waveform_np.T)

        # Run pipeline on in-memory audio (avoids torchcodec)
        result = self.pipeline({"waveform": waveform, "sample_rate": sample_rate})

        # pyannote 4.x: result is DiarizeOutput with .speaker_diarization Annotation
        # pyannote 3.x: result is the Annotation directly
        annotation = getattr(result, "speaker_diarization", result)

        # Map detected speaker labels to hint speakers in first-appearance order
        seen: dict[str, str] = {}
        turns: list[DiarizedTurn] = []
        for turn, _, label in annotation.itertracks(yield_label=True):
            if label not in seen:
                if hint_speakers:
                    seen[label] = hint_speakers[len(seen) % len(hint_speakers)]
                else:
                    seen[label] = label
            turns.append(
                DiarizedTurn(
                    speaker_id=seen[label],
                    start_seconds=float(turn.start),
                    end_seconds=float(turn.end),
                    confidence=0.92,  # pyannote doesn't expose per-turn confidence
                )
            )
        return turns


_diarizer_singleton: BaseDiarizer | None = None


def get_diarizer() -> BaseDiarizer:
    """Factory — returns mock or real based on USE_MOCK_DIARIZATION flag."""
    global _diarizer_singleton
    if _diarizer_singleton is not None:
        return _diarizer_singleton

    from config import get_settings
    settings = get_settings()

    if settings.use_mock_diarization:
        _diarizer_singleton = MockDiarizer()
    else:
        if not settings.hf_token:
            raise RuntimeError(
                "USE_MOCK_DIARIZATION=false but HF_TOKEN is not set. "
                "Get a token at https://huggingface.co/settings/tokens"
            )
        _diarizer_singleton = PyannoteDiarizer(hf_token=settings.hf_token)
    return _diarizer_singleton


def reset_diarizer() -> None:
    """Useful for tests / hot reload after settings change."""
    global _diarizer_singleton
    _diarizer_singleton = None
