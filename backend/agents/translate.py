from __future__ import annotations

from agents.base import BaseAgent
from llm_router import get_router


LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "zh": "Mandarin Chinese",
    "hi": "Hindi",
    "fr": "French",
    "de": "German",
    "ar": "Arabic",
    "pt": "Portuguese",
    "ja": "Japanese",
    "ko": "Korean",
}

BASE_SYSTEM = """You are a meeting transcription assistant. Given a raw audio
transcript snippet, produce a clean, grammatically correct sentence that captures
what the speaker said. Keep it concise and faithful to the original.
Output ONLY the cleaned sentence, nothing else."""

TRANSLATE_SYSTEM = """You are a meeting transcription + translation assistant.
Given a raw English transcript snippet, produce a clean, grammatically correct
sentence translated into {language}. Keep it concise and faithful to the original.
Output ONLY the translated sentence, nothing else."""


class TranslateAgent(BaseAgent):
    """Cleans up raw ASR output and optionally translates into a target language."""

    name = "translate"

    def __init__(self) -> None:
        self._router = get_router()

    async def run(self, *, raw_text: str, target_language: str = "en") -> dict:
        """Returns {text, provider, latency_ms, was_fallback, language}."""
        if not raw_text or not raw_text.strip():
            self.emit("error", "Empty input")
            return {"text": "", "provider": None, "latency_ms": 0, "was_fallback": False, "language": target_language}

        is_translation = target_language and target_language != "en"
        language_name = LANGUAGE_NAMES.get(target_language, target_language)
        system = (
            TRANSLATE_SYSTEM.format(language=language_name) if is_translation else BASE_SYSTEM
        )

        if not self._router.has_any_provider:
            self.emit("done", "No LLM configured — passthrough", meta={"fallback": True})
            return {"text": raw_text.strip(), "provider": None, "latency_ms": 0, "was_fallback": False, "language": target_language}

        action_msg = f"Translating to {language_name}..." if is_translation else "Cleaning transcript with LLM..."
        self.emit("active", action_msg)
        try:
            resp = await self._router.generate(
                prompt=f"Raw transcript snippet:\n{raw_text}\n\n"
                + (f"Cleaned + translated to {language_name}:" if is_translation else "Cleaned sentence:"),
                system=system,
                max_tokens=300,
                temperature=0.3,
            )
            badge = f"via {resp.provider.value}" + (" (fallback)" if resp.was_fallback else "")
            done_msg = (
                f"Translated to {language_name} {badge} · {resp.latency_ms}ms"
                if is_translation
                else f"Cleaned {badge} · {resp.latency_ms}ms"
            )
            self.emit(
                "done",
                done_msg,
                meta={
                    "provider": resp.provider.value,
                    "latency_ms": resp.latency_ms,
                    "was_fallback": resp.was_fallback,
                    "tokens": resp.tokens_in + resp.tokens_out,
                    "language": target_language,
                },
            )
            return {
                "text": resp.text,
                "provider": resp.provider.value,
                "latency_ms": resp.latency_ms,
                "was_fallback": resp.was_fallback,
                "language": target_language,
            }
        except Exception as exc:
            self.emit("error", f"LLM failed: {exc} — passthrough")
            return {"text": raw_text.strip(), "provider": None, "latency_ms": 0, "was_fallback": False, "language": target_language}
