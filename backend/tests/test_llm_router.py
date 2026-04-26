"""Tests for LLM Router fallback behavior.

These tests do NOT call real APIs — they monkeypatch the providers
to verify routing logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_router import LLMResponse, LLMRouter, Provider, RouterStats  # noqa: E402


class _FakeGeminiOK:
    async def generate_content_async(self, *_args, **_kwargs):
        class R:
            text = "gemini response"
        return R()


class _FakeGeminiFail:
    async def generate_content_async(self, *_args, **_kwargs):
        raise RuntimeError("gemini down")


class _FakeClaudeBlock:
    type = "text"
    text = "claude response"


class _FakeClaudeMessage:
    content = [_FakeClaudeBlock()]


class _FakeClaudeOK:
    class messages:
        @staticmethod
        async def create(**_kwargs):
            return _FakeClaudeMessage()


class _FakeClaudeFail:
    class messages:
        @staticmethod
        async def create(**_kwargs):
            raise RuntimeError("claude down")


def _make_router(gemini=None, claude=None) -> LLMRouter:
    r = LLMRouter.__new__(LLMRouter)
    r.gemini_key = "x" if gemini else ""
    r.gemini_model = "gemini-2.5-flash"
    r.claude_key = "y" if claude else ""
    r.claude_model = "claude-sonnet-4-6"
    r._gemini_client = gemini
    r._claude_client = claude
    r.stats = RouterStats()
    return r


@pytest.mark.asyncio
async def test_gemini_used_when_available():
    r = _make_router(gemini=_FakeGeminiOK(), claude=_FakeClaudeOK())
    resp = await r.generate("hi")
    assert resp.provider == Provider.GEMINI
    assert resp.text == "gemini response"


@pytest.mark.asyncio
async def test_falls_back_to_claude_when_gemini_fails():
    r = _make_router(gemini=_FakeGeminiFail(), claude=_FakeClaudeOK())
    resp = await r.generate("hi")
    assert resp.provider == Provider.CLAUDE
    assert resp.text == "claude response"


@pytest.mark.asyncio
async def test_claude_used_when_no_gemini():
    r = _make_router(gemini=None, claude=_FakeClaudeOK())
    resp = await r.generate("hi")
    assert resp.provider == Provider.CLAUDE


@pytest.mark.asyncio
async def test_raises_when_both_fail():
    r = _make_router(gemini=_FakeGeminiFail(), claude=_FakeClaudeFail())
    with pytest.raises(RuntimeError, match="No LLM provider available"):
        await r.generate("hi")


@pytest.mark.asyncio
async def test_raises_when_no_providers_configured():
    r = _make_router(gemini=None, claude=None)
    with pytest.raises(RuntimeError, match="No LLM provider available"):
        await r.generate("hi")


@pytest.mark.asyncio
async def test_generate_json_strips_markdown_fences():
    class _Fake:
        async def generate_content_async(self, *_a, **_k):
            class R:
                text = '```json\n{"foo": "bar"}\n```'
            return R()

    r = _make_router(gemini=_Fake())
    data = await r.generate_json("give json")
    assert data == {"foo": "bar"}
