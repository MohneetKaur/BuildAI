"""Orchestrator: coordinates all agents for a single transcription cycle.

Provides both a batch (`process_segment`) and a streaming
(`process_segment_streaming`) interface. The batch version is implemented
on top of the streaming version so logic lives in one place.
"""
from __future__ import annotations

import uuid
from typing import AsyncIterator

from agents.action import ActionAgent
from agents.base import BaseAgent, utcnow
from agents.listening import ListeningAgent
from agents.sign_out import SignOutAgent
from agents.speaker_id import SpeakerIdAgent
from agents.translate import TranslateAgent
from api.models import (
    AgentEvent,
    MeetingSummary,
    Speaker,
    StreamEvent,
    TranscriptSegment,
)
from llm_router import get_router


SPEAKER_COLORS = ["#6366f1", "#ec4899", "#22c55e", "#f59e0b", "#06b6d4", "#a855f7", "#ef4444", "#84cc16"]


class Orchestrator(BaseAgent):
    name = "orchestrator"

    def __init__(self) -> None:
        self.listening = ListeningAgent()
        self.speaker_id = SpeakerIdAgent()
        self.translate = TranslateAgent()
        self.sign_out = SignOutAgent()
        self.action = ActionAgent()
        self._router = get_router()

    async def run(self, **kwargs):  # not used directly — see methods below
        raise NotImplementedError("Use process_segment / process_segment_streaming")

    def _stream_event(self, ev: AgentEvent) -> StreamEvent:
        return StreamEvent(type="agent", timestamp=utcnow(), agent_event=ev)

    async def process_segment_streaming(
        self,
        *,
        meeting_id: str,
        audio_chunk_b64: str | None = None,
        audio_bytes: bytes | None = None,
        text_hint: str | None,
        speakers: list[Speaker],
        target_language: str = "en",
    ) -> AsyncIterator[StreamEvent]:
        """Yields StreamEvents as each agent completes its work."""
        yield self._stream_event(self.emit("active", "Coordinating agents for new segment"))

        # 1. Listening
        capture = await self.listening.run(
            audio_chunk_b64=audio_chunk_b64,
            text=text_hint,
            audio_bytes=audio_bytes,
        )
        yield self._stream_event(self.listening.emit("done", "Audio captured"))

        # 2. Speaker ID
        hint_names = [s.name for s in speakers]
        turns = await self.speaker_id.run(
            audio_bytes=capture["audio_bytes"], hint_speakers=hint_names
        )
        speaker_name = turns[0].speaker_id if turns else (hint_names[0] if hint_names else "Speaker 1")
        yield self._stream_event(self.speaker_id.emit("done", f"Speaker: {speaker_name}"))

        speaker = next((s for s in speakers if s.name == speaker_name), None)
        if not speaker:
            speaker = Speaker(
                id=str(uuid.uuid4())[:8],
                name=speaker_name,
                color=SPEAKER_COLORS[len(speakers) % len(SPEAKER_COLORS)],
            )

        # 3. Translate (cleanup + optional translation)
        raw = capture["text_hint"] or "(audio not transcribed in mock mode)"
        translation = await self.translate.run(raw_text=raw, target_language=target_language)
        cleaned = translation["text"]
        provider = translation.get("provider")
        yield self._stream_event(self.translate.emit(
            "done",
            f"Transcript cleaned via {provider or 'passthrough'}"
            + (f" → {target_language}" if target_language != "en" else ""),
            meta={
                "provider": provider,
                "latency_ms": translation["latency_ms"],
                "language": translation.get("language"),
            },
        ))

        # 4. Sign-Out
        clips = await self.sign_out.run(text=cleaned)
        yield self._stream_event(self.sign_out.emit("done", f"{len(clips)} sign clips matched"))

        # 5. Build segment + final event
        segment = TranscriptSegment(
            id=str(uuid.uuid4())[:8],
            meeting_id=meeting_id,
            speaker=speaker,
            text=cleaned,
            timestamp=utcnow(),
            sign_clip_ids=[c.id for c in clips],
            sign_clips=clips,
            confidence=turns[0].confidence if turns else 1.0,
            llm_provider=provider,
            llm_latency_ms=translation["latency_ms"],
            llm_was_fallback=translation["was_fallback"],
        )

        yield self._stream_event(self.emit("done", "Segment processed"))
        yield StreamEvent(type="segment", timestamp=utcnow(), segment=segment)

    async def process_segment(
        self,
        *,
        meeting_id: str,
        audio_chunk_b64: str | None = None,
        audio_bytes: bytes | None = None,
        text_hint: str | None,
        speakers: list[Speaker],
        target_language: str = "en",
    ) -> tuple[TranscriptSegment, list[AgentEvent]]:
        """Batch version: collects all events and returns final segment."""
        events: list[AgentEvent] = []
        segment: TranscriptSegment | None = None
        async for stream_event in self.process_segment_streaming(
            meeting_id=meeting_id,
            audio_chunk_b64=audio_chunk_b64,
            audio_bytes=audio_bytes,
            text_hint=text_hint,
            speakers=speakers,
            target_language=target_language,
        ):
            if stream_event.type == "agent" and stream_event.agent_event:
                events.append(stream_event.agent_event)
            elif stream_event.type == "segment" and stream_event.segment:
                segment = stream_event.segment
        if segment is None:
            raise RuntimeError("Streaming pipeline did not produce a segment")
        return segment, events

    async def generate_summary(
        self,
        *,
        meeting_id: str,
        title: str,
        transcript: list[TranscriptSegment],
        speakers: list[Speaker],
        duration_seconds: int,
    ) -> MeetingSummary:
        action_items = await self.action.run(transcript=transcript)
        summary_text, topics = await self._summarize(transcript)
        return MeetingSummary(
            meeting_id=meeting_id,
            title=title,
            duration_seconds=duration_seconds,
            speakers=speakers,
            summary=summary_text,
            key_topics=topics,
            action_items=action_items,
            transcript=transcript,
            generated_at=utcnow(),
        )

    async def _summarize(self, transcript: list[TranscriptSegment]) -> tuple[str, list[str]]:
        if not transcript:
            return ("No content was captured during this meeting.", [])
        if not self._router.has_any_provider:
            return (f"{len(transcript)} segments captured (LLM disabled — summary skipped).", [])

        body = "\n".join(f"{seg.speaker.name}: {seg.text}" for seg in transcript)
        try:
            data = await self._router.generate_json(
                prompt=f"Meeting transcript:\n{body}\n\nProduce summary + key topics:",
                system=(
                    "Summarize the meeting in 2-3 sentences. Then list 3-6 key topics discussed. "
                    "Return JSON: {\"summary\": str, \"topics\": [str, ...]}"
                ),
                max_tokens=512,
            )
            return (data.get("summary", ""), data.get("topics", []))
        except Exception:
            return (f"{len(transcript)} segments captured.", [])


_orch: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orch
    if _orch is None:
        _orch = Orchestrator()
    return _orch
