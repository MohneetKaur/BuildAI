from __future__ import annotations

import base64

from agents.base import BaseAgent
from services.asr import get_asr


class ListeningAgent(BaseAgent):
    """Captures audio chunks and optionally transcribes them via Whisper.

    Inputs (any of):
      - text: pre-transcribed text (skips ASR)
      - audio_bytes / audio_chunk_b64: raw audio (Whisper transcribes if no text)
    """

    name = "listening"

    async def run(
        self,
        *,
        audio_chunk_b64: str | None = None,
        audio_bytes: bytes | None = None,
        text: str | None = None,
    ) -> dict:
        if text:
            self.emit("done", f"Captured text input: {len(text)} chars")
            return {"audio_bytes": audio_bytes, "text_hint": text}

        # Decode base64 if provided
        if audio_chunk_b64 and not audio_bytes:
            audio_bytes = base64.b64decode(audio_chunk_b64)

        if not audio_bytes:
            self.emit("error", "No audio or text provided")
            return {"audio_bytes": None, "text_hint": None}

        # Try Whisper ASR if available
        asr = get_asr()
        if asr is None:
            self.emit("done", f"Captured audio ({len(audio_bytes)} bytes), no ASR configured")
            return {"audio_bytes": audio_bytes, "text_hint": None}

        self.emit("active", f"Transcribing {len(audio_bytes)} bytes via Whisper...")
        try:
            result = await asr.transcribe(audio_bytes, mime_type="audio/wav")
            transcribed = result["text"]
            self.emit(
                "done",
                f'Whisper: "{transcribed[:60]}{"..." if len(transcribed) > 60 else ""}" · {result["latency_ms"]}ms',
                meta={"asr_model": result["model"], "asr_latency_ms": result["latency_ms"]},
            )
            return {"audio_bytes": audio_bytes, "text_hint": transcribed}
        except Exception as exc:
            self.emit("error", f"Whisper failed: {exc}")
            return {"audio_bytes": audio_bytes, "text_hint": None}
