"""Tests for SSE streaming, multi-language, and audio upload endpoints."""
from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _make_meeting(client) -> str:
    r = client.post(
        "/api/meetings",
        json={"title": "Stream test", "expected_speakers": ["Alice", "Bob"]},
    )
    return r.json()["meeting_id"]


def test_sse_stream_endpoint_responds(client):
    """Streaming endpoint should accept the request and produce SSE-formatted output.

    (Real LLM calls inside TestClient are racy with httpx streaming; the
    full event flow is exercised by the browser. Here we just verify the
    endpoint is wired up correctly and starts emitting events.)
    """
    mid = _make_meeting(client)
    with client.stream(
        "POST",
        "/api/transcribe-stream",
        json={"meeting_id": mid, "text": "hello team"},
    ) as r:
        assert r.status_code == 200
        # consume at least one chunk to confirm the stream starts
        first_chunk = next(r.iter_bytes(), b"")
        assert first_chunk, "Stream produced no bytes"
        # SSE format: should contain "event:" or "data:" markers
        text = first_chunk.decode("utf-8", errors="replace")
        assert "event:" in text or "data:" in text, f"Not SSE-formatted: {text[:100]}"


def test_target_language_field_round_trips(client):
    """Multi-language: target_language passed through to translate agent."""
    mid = _make_meeting(client)
    r = client.post(
        "/api/transcribe",
        json={"meeting_id": mid, "text": "hello", "target_language": "es"},
    )
    assert r.status_code == 200
    body = r.json()
    # Even without an LLM key configured in tests, pipeline should complete
    assert "segment" in body
    assert body["segment"]["text"]


def test_transcribe_audio_endpoint_accepts_wav(client):
    """The /transcribe-audio endpoint accepts a multipart file upload."""
    mid = _make_meeting(client)

    # Generate a tiny silent WAV (1 second, 16kHz mono)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    buf.seek(0)

    r = client.post(
        "/api/transcribe-audio",
        params={"meeting_id": mid, "text_hint": "hello world", "target_language": "en"},
        files={"audio": ("test.wav", buf, "audio/wav")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["audio_bytes_size"] > 0
    assert body["segment"]["text"]


def test_segment_includes_sign_clips_with_video_urls(client):
    """TranscriptSegment should include full sign_clips (with video URLs)."""
    mid = _make_meeting(client)
    r = client.post(
        "/api/transcribe",
        json={"meeting_id": mid, "text": "I need help today please"},
    )
    body = r.json()
    clips = body["segment"]["sign_clips"]
    assert isinstance(clips, list)
    assert len(clips) > 0
    for clip in clips:
        assert "id" in clip
        assert "word" in clip
        assert "video_url" in clip
        assert "duration_ms" in clip
    # at least one of these common words should be matched
    matched_words = {c["word"] for c in clips}
    assert matched_words & {"need", "help", "today", "please"}
