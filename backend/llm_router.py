"""LLM Router: Gemini primary, Claude fallback.

If GEMINI_API_KEY is set and the call succeeds, returns Gemini's response.
Otherwise falls back to Anthropic Claude. Raises RuntimeError if both fail
or neither is configured.

Tracks per-provider stats: call counts, latency, fallback events, tokens.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)


class Provider(str, Enum):
    GEMINI = "gemini"
    CLAUDE = "claude"


@dataclass
class LLMResponse:
    text: str
    provider: Provider
    model: str
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    was_fallback: bool = False  # true if we fell back to Claude after Gemini failed
    raw: dict[str, Any] | None = None


@dataclass
class RouterStats:
    total_calls: int = 0
    gemini_calls: int = 0
    claude_calls: int = 0
    fallback_count: int = 0
    failed_calls: int = 0
    total_latency_ms: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    last_provider: str | None = None
    last_call_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        avg_latency = self.total_latency_ms // max(self.total_calls, 1)
        return {
            "total_calls": self.total_calls,
            "gemini_calls": self.gemini_calls,
            "claude_calls": self.claude_calls,
            "fallback_count": self.fallback_count,
            "failed_calls": self.failed_calls,
            "total_latency_ms": self.total_latency_ms,
            "avg_latency_ms": avg_latency,
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_tokens": self.total_tokens_in + self.total_tokens_out,
            "last_provider": self.last_provider,
            "last_call_at_ms": self.last_call_at_ms,
        }


class LLMRouter:
    def __init__(self) -> None:
        settings = get_settings()
        self.gemini_key = settings.gemini_api_key
        self.gemini_model = settings.gemini_model
        self.claude_key = settings.anthropic_api_key
        self.claude_model = settings.anthropic_model

        self._gemini_client = None
        self._claude_client = None
        self.stats = RouterStats()

        if self.gemini_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.gemini_key)
                self._gemini_client = genai.GenerativeModel(self.gemini_model)
                logger.info("Gemini client initialized: %s", self.gemini_model)
            except Exception as exc:
                logger.error("Failed to init Gemini: %s", exc)

        if self.claude_key:
            try:
                from anthropic import AsyncAnthropic
                self._claude_client = AsyncAnthropic(api_key=self.claude_key)
                logger.info("Claude client initialized: %s", self.claude_model)
            except Exception as exc:
                logger.error("Failed to init Claude: %s", exc)

    @property
    def has_any_provider(self) -> bool:
        return self._gemini_client is not None or self._claude_client is not None

    def _record(self, resp: LLMResponse) -> None:
        self.stats.total_calls += 1
        self.stats.total_latency_ms += resp.latency_ms
        self.stats.total_tokens_in += resp.tokens_in
        self.stats.total_tokens_out += resp.tokens_out
        self.stats.last_provider = resp.provider.value
        self.stats.last_call_at_ms = int(time.time() * 1000)
        if resp.provider == Provider.GEMINI:
            self.stats.gemini_calls += 1
        else:
            self.stats.claude_calls += 1
        if resp.was_fallback:
            self.stats.fallback_count += 1

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.4,
    ) -> LLMResponse:
        last_error: Exception | None = None
        gemini_failed = False

        if self._gemini_client is not None:
            try:
                resp = await self._gemini_generate(prompt, system, max_tokens, temperature)
                self._record(resp)
                return resp
            except Exception as exc:
                logger.warning("Gemini failed (%s) — falling back to Claude", exc)
                last_error = exc
                gemini_failed = True

        if self._claude_client is not None:
            try:
                resp = await self._claude_generate(prompt, system, max_tokens, temperature)
                resp.was_fallback = gemini_failed
                self._record(resp)
                return resp
            except Exception as exc:
                logger.error("Claude also failed: %s", exc)
                last_error = exc

        self.stats.failed_calls += 1
        raise RuntimeError(
            f"No LLM provider available. Configure GEMINI_API_KEY or ANTHROPIC_API_KEY. "
            f"Last error: {last_error}"
        )

    async def generate_json(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        full_system = (system or "") + "\n\nRespond ONLY with valid JSON. No prose, no markdown fences."
        resp = await self.generate(prompt, system=full_system, max_tokens=max_tokens, temperature=0.2)
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse JSON from %s: %s", resp.provider, text[:200])
            raise ValueError(f"LLM returned non-JSON: {exc}") from exc

    async def generate_with_meta(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.4,
    ) -> LLMResponse:
        """Returns the full LLMResponse so callers can extract provider/latency."""
        return await self.generate(prompt, system, max_tokens, temperature)

    async def _gemini_generate(
        self, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> LLMResponse:
        import google.generativeai as genai
        full_prompt = (f"{system}\n\n{prompt}" if system else prompt)
        config = genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        t0 = time.perf_counter()
        result = await self._gemini_client.generate_content_async(full_prompt, generation_config=config)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        text = (result.text or "").strip()
        usage = getattr(result, "usage_metadata", None)
        return LLMResponse(
            text=text,
            provider=Provider.GEMINI,
            model=self.gemini_model,
            latency_ms=latency_ms,
            tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) or 0,
        )

    async def _claude_generate(
        self, prompt: str, system: str | None, max_tokens: int, temperature: float
    ) -> LLMResponse:
        t0 = time.perf_counter()
        message = await self._claude_client.messages.create(
            model=self.claude_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        text = "".join(block.text for block in message.content if block.type == "text").strip()
        usage = getattr(message, "usage", None)
        return LLMResponse(
            text=text,
            provider=Provider.CLAUDE,
            model=self.claude_model,
            latency_ms=latency_ms,
            tokens_in=getattr(usage, "input_tokens", 0) or 0,
            tokens_out=getattr(usage, "output_tokens", 0) or 0,
        )


_router_singleton: LLMRouter | None = None


def get_router() -> LLMRouter:
    global _router_singleton
    if _router_singleton is None:
        _router_singleton = LLMRouter()
    return _router_singleton
