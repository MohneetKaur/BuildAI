from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class MeetingMode(str, Enum):
    GENERAL = "general"
    MEDICAL = "medical"
    LEGAL = "legal"
    EDUCATION = "education"


class CreateMeetingRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    mode: MeetingMode = MeetingMode.GENERAL
    expected_speakers: list[str] = Field(default_factory=list)
    target_language: str = "en"


class CreateMeetingResponse(BaseModel):
    meeting_id: str
    title: str
    mode: MeetingMode
    started_at: datetime


class TranscribeRequest(BaseModel):
    meeting_id: str
    audio_chunk_b64: str | None = None
    text: str | None = None  # for testing without real audio
    target_language: str = "en"  # ISO code: en, es, zh, hi, fr, de, ar, pt, ja, ko


class Speaker(BaseModel):
    id: str
    name: str
    color: str  # hex color for UI


class SignClip(BaseModel):
    id: str
    word: str
    video_url: str
    duration_ms: int
    description: str
    video_type: Literal["mp4", "youtube"] = "mp4"
    youtube_id: str | None = None
    start_seconds: float = 0.0
    end_seconds: float | None = None
    source: str = ""


class TranscriptSegment(BaseModel):
    id: str
    meeting_id: str
    speaker: Speaker
    text: str
    timestamp: datetime
    sign_clip_ids: list[str] = Field(default_factory=list)
    sign_clips: list[SignClip] = Field(default_factory=list)
    confidence: float = 1.0
    llm_provider: str | None = None  # "gemini" | "claude" | None
    llm_latency_ms: int | None = None
    llm_was_fallback: bool = False


class AgentEvent(BaseModel):
    agent: Literal["orchestrator", "listening", "speaker_id", "translate", "sign_out", "action"]
    status: Literal["thinking", "active", "done", "error"]
    message: str
    timestamp: datetime
    meta: dict | None = None


class StreamEvent(BaseModel):
    """SSE event sent during streaming transcription."""
    type: Literal["agent", "segment", "error", "done"]
    timestamp: datetime
    # Populated for type="agent":
    agent_event: AgentEvent | None = None
    # Populated for type="segment" (the final result):
    segment: TranscriptSegment | None = None
    # Populated for type="error":
    error: str | None = None


class ActionItem(BaseModel):
    id: str
    text: str
    owner: str
    deadline: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"


class MeetingSummary(BaseModel):
    meeting_id: str
    title: str
    duration_seconds: int
    speakers: list[Speaker]
    summary: str
    key_topics: list[str]
    action_items: list[ActionItem]
    transcript: list[TranscriptSegment]
    generated_at: datetime


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    llm_provider_active: str | None
    has_gemini: bool
    has_claude: bool
    has_hf_token: bool = False
    mock_mode: bool  # legacy: true if ANY mock is active
    mock_diarization: bool = True
    mock_sign_lookup: bool = True


class LLMStats(BaseModel):
    total_calls: int
    gemini_calls: int
    claude_calls: int
    fallback_count: int
    failed_calls: int
    total_latency_ms: int
    avg_latency_ms: int
    total_tokens_in: int
    total_tokens_out: int
    total_tokens: int
    last_provider: str | None
    last_call_at_ms: int
