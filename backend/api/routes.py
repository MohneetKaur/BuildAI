from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from sse_starlette.sse import EventSourceResponse

from agents.base import utcnow
from agents.orchestrator import SPEAKER_COLORS, get_orchestrator
from api.models import (
    CreateMeetingRequest,
    CreateMeetingResponse,
    HealthResponse,
    LLMStats,
    MeetingSummary,
    SignClip,
    Speaker,
    TranscribeRequest,
)
from config import get_settings
from llm_router import get_router
from services.sign_lookup import get_sign_lookup


router = APIRouter()


# --- in-memory store ---
class _Store:
    def __init__(self) -> None:
        self.meetings: dict[str, dict] = {}

    def create(self, req: CreateMeetingRequest) -> CreateMeetingResponse:
        mid = str(uuid.uuid4())[:8]
        speakers = [
            Speaker(id=str(uuid.uuid4())[:8], name=name, color=SPEAKER_COLORS[i % len(SPEAKER_COLORS)])
            for i, name in enumerate(req.expected_speakers)
        ]
        now = utcnow()
        self.meetings[mid] = {
            "title": req.title,
            "mode": req.mode,
            "speakers": speakers,
            "transcript": [],
            "started_at": now,
            "target_language": req.target_language,
        }
        return CreateMeetingResponse(meeting_id=mid, title=req.title, mode=req.mode, started_at=now)

    def get(self, mid: str) -> dict:
        if mid not in self.meetings:
            raise HTTPException(status_code=404, detail=f"Meeting {mid} not found")
        return self.meetings[mid]


_store = _Store()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    router_ = get_router()
    active = None
    if router_._gemini_client is not None:
        active = "gemini"
    elif router_._claude_client is not None:
        active = "claude"
    return HealthResponse(
        status="ok" if router_.has_any_provider else "degraded",
        llm_provider_active=active,
        has_gemini=router_._gemini_client is not None,
        has_claude=router_._claude_client is not None,
        has_hf_token=bool(settings.hf_token),
        mock_mode=settings.use_mock_diarization or settings.use_mock_sign_lookup,
        mock_diarization=settings.use_mock_diarization,
        mock_sign_lookup=settings.use_mock_sign_lookup,
    )


@router.get("/stats", response_model=LLMStats)
async def get_llm_stats() -> LLMStats:
    return LLMStats(**get_router().stats.to_dict())


@router.post("/meetings", response_model=CreateMeetingResponse)
async def create_meeting(req: CreateMeetingRequest) -> CreateMeetingResponse:
    return _store.create(req)


@router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str) -> dict:
    m = _store.get(meeting_id)
    return {
        "meeting_id": meeting_id,
        "title": m["title"],
        "mode": m["mode"],
        "speakers": m["speakers"],
        "transcript": m["transcript"],
        "started_at": m["started_at"],
        "target_language": m.get("target_language", "en"),
    }


@router.post("/transcribe")
async def transcribe(req: TranscribeRequest) -> dict:
    """Process one segment through the agent pipeline (batch mode).
    Returns the new TranscriptSegment + agent activity events.
    """
    m = _store.get(req.meeting_id)
    orch = get_orchestrator()
    target = req.target_language or m.get("target_language", "en")
    segment, events = await orch.process_segment(
        meeting_id=req.meeting_id,
        audio_chunk_b64=req.audio_chunk_b64,
        text_hint=req.text,
        speakers=m["speakers"],
        target_language=target,
    )
    m["transcript"].append(segment)
    if segment.speaker not in m["speakers"]:
        m["speakers"].append(segment.speaker)
    return {"segment": segment, "events": events}


@router.post("/transcribe-stream")
async def transcribe_stream(req: TranscribeRequest):
    """Same as /transcribe but streams agent events live via Server-Sent Events.
    Frontend can use fetch + ReadableStream to consume — events appear as agents
    complete rather than batched at the end.
    """
    m = _store.get(req.meeting_id)
    orch = get_orchestrator()
    target = req.target_language or m.get("target_language", "en")

    async def event_generator():
        async for stream_event in orch.process_segment_streaming(
            meeting_id=req.meeting_id,
            audio_chunk_b64=req.audio_chunk_b64,
            text_hint=req.text,
            speakers=m["speakers"],
            target_language=target,
        ):
            if stream_event.type == "segment" and stream_event.segment:
                m["transcript"].append(stream_event.segment)
                if stream_event.segment.speaker not in m["speakers"]:
                    m["speakers"].append(stream_event.segment.speaker)
            yield {"event": stream_event.type, "data": stream_event.model_dump_json()}
        # final marker so frontend knows to close
        yield {"event": "done", "data": json.dumps({"ok": True})}

    return EventSourceResponse(event_generator())


@router.post("/transcribe-audio")
async def transcribe_audio(
    meeting_id: str,
    target_language: str = "en",
    text_hint: str | None = None,
    audio: UploadFile = File(...),
) -> dict:
    """Process an uploaded WAV file through the full pipeline.

    If text_hint is provided, that text is used (skipping ASR).
    Otherwise the audio is sent to Whisper for transcription, then
    pyannote runs diarization on the same audio.

    This is the bulletproof browser-mic path: MediaRecorder -> WAV -> here.
    """
    m = _store.get(meeting_id)
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    orch = get_orchestrator()
    segment, events = await orch.process_segment(
        meeting_id=meeting_id,
        audio_bytes=audio_bytes,
        text_hint=text_hint,
        speakers=m["speakers"],
        target_language=target_language,
    )
    m["transcript"].append(segment)
    if segment.speaker not in m["speakers"]:
        m["speakers"].append(segment.speaker)
    return {"segment": segment, "events": events, "audio_bytes_size": len(audio_bytes)}


@router.post("/meetings/{meeting_id}/end", response_model=MeetingSummary)
async def end_meeting(meeting_id: str) -> MeetingSummary:
    m = _store.get(meeting_id)
    duration = int((utcnow() - m["started_at"]).total_seconds())
    orch = get_orchestrator()
    return await orch.generate_summary(
        meeting_id=meeting_id,
        title=m["title"],
        transcript=m["transcript"],
        speakers=m["speakers"],
        duration_seconds=duration,
    )


@router.get("/signs/lookup")
async def lookup_signs(text: str) -> list[SignClip]:
    return get_sign_lookup().find_signs(text)


@router.get("/signs/vocabulary")
async def sign_vocabulary() -> list[str]:
    return get_sign_lookup().vocabulary()
