"""End-to-end API tests using FastAPI TestClient.

LLM is auto-disabled (no key in env), so the system falls through
to passthrough behavior — verifying the agent pipeline still runs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "has_gemini" in body
    assert "has_claude" in body


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "SignBridge"


def test_create_meeting(client):
    r = client.post(
        "/api/meetings",
        json={"title": "Daily standup", "mode": "general", "expected_speakers": ["Sarah", "Raj"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Daily standup"
    assert "meeting_id" in body
    assert len(body["meeting_id"]) > 0


def test_full_meeting_lifecycle(client):
    create = client.post(
        "/api/meetings",
        json={"title": "Sprint planning", "expected_speakers": ["Sarah", "Raj", "Priya"]},
    ).json()
    mid = create["meeting_id"]

    # transcribe a few segments
    for text in [
        "We need to deploy the new auth service today",
        "I have a blocker with the database migration",
        "Sarah will own the deploy and Raj reviews tomorrow",
    ]:
        r = client.post("/api/transcribe", json={"meeting_id": mid, "text": text})
        assert r.status_code == 200
        seg = r.json()["segment"]
        assert seg["text"]
        assert seg["speaker"]["name"]

    # end and get summary
    r = client.post(f"/api/meetings/{mid}/end")
    assert r.status_code == 200
    summary = r.json()
    assert summary["meeting_id"] == mid
    assert len(summary["transcript"]) == 3
    assert isinstance(summary["action_items"], list)


def test_sign_lookup(client):
    """WLASL has ~1959 words — verify common content words match."""
    r = client.get("/api/signs/lookup", params={"text": "I need help today"})
    assert r.status_code == 200
    clips = r.json()
    matched_words = {c["word"] for c in clips}
    assert "help" in matched_words
    assert "today" in matched_words
    # each clip has the new WLASL fields
    for clip in clips:
        assert clip["video_type"] in ("mp4", "youtube")
        assert clip["video_url"]


def test_sign_vocabulary(client):
    """Backed by real WLASL dataset (~1959 signs)."""
    r = client.get("/api/signs/vocabulary")
    assert r.status_code == 200
    vocab = r.json()
    assert isinstance(vocab, list)
    assert len(vocab) > 1500, f"Expected ~1959 WLASL signs, got {len(vocab)}"
    assert "hello" in vocab
    assert "doctor" in vocab
    assert "today" in vocab


def test_unknown_meeting_404(client):
    r = client.get("/api/meetings/does-not-exist")
    assert r.status_code == 404
