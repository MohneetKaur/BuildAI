"""Sign clip lookup service.

Backed by the **WLASL dataset** (Word-Level American Sign Language, Li et al. 2020):
2000 ASL glosses with multiple video instances each.

We pre-process WLASL_v0.3.json once via `scripts/build_wlasl_library.py` into
`data/wlasl_library.json` — a flat dict mapping each English gloss to:
  - a direct MP4 URL on Microsoft signschool/Azure (preferred), or
  - a YouTube embed (fallback)
plus start/end timing, signer ID, and source attribution.

This service does word-level lookup against ~1959 WLASL signs. It does NOT
perform real ASL grammar (which needs continuous sign translation models).
For sign-to-text input recognition (camera -> word), see roadmap: WLASL
pretrained classifiers exist on HuggingFace but require ~15h of integration.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from api.models import SignClip

logger = logging.getLogger(__name__)

LIBRARY_PATH = Path(__file__).resolve().parent.parent / "data" / "wlasl_library.json"


def _load_library() -> dict[str, SignClip]:
    if not LIBRARY_PATH.exists():
        logger.warning("WLASL library not found at %s — falling back to empty.", LIBRARY_PATH)
        logger.warning("Run: python scripts/build_wlasl_library.py")
        return {}
    with open(LIBRARY_PATH) as f:
        raw = json.load(f)
    library = {
        word: SignClip(
            id=entry["id"],
            word=entry["word"],
            video_url=entry["video_url"],
            duration_ms=int(entry.get("duration_ms", 1500)),
            description=entry.get("description", f"ASL sign for '{word}'"),
            video_type=entry.get("video_type", "mp4"),
            youtube_id=entry.get("youtube_id"),
            start_seconds=float(entry.get("start_seconds", 0.0) or 0.0),
            end_seconds=(float(entry["end_seconds"]) if entry.get("end_seconds") else None),
            source=entry.get("source", "wlasl"),
        )
        for word, entry in raw.items()
    }
    logger.info("Loaded WLASL library: %d signs", len(library))
    return library


WLASL_LIBRARY: dict[str, SignClip] = _load_library()


class SignLookup:
    def __init__(self, library: dict[str, SignClip] | None = None) -> None:
        self._library = library if library is not None else WLASL_LIBRARY

    def find_signs(self, text: str, max_clips: int = 6) -> list[SignClip]:
        """Word-level match: tokenize, normalize, look up in WLASL.

        Common stopwords are skipped to surface signs for content words.
        """
        words = [w.strip(".,!?;:'\"()[]").lower() for w in text.split()]
        matched: list[SignClip] = []
        seen: set[str] = set()
        for word in words:
            if not word or word in _STOPWORDS or word in seen:
                continue
            if word in self._library:
                matched.append(self._library[word])
                seen.add(word)
                if len(matched) >= max_clips:
                    break
        return matched

    def vocabulary(self) -> list[str]:
        return sorted(self._library.keys())

    def size(self) -> int:
        return len(self._library)


# Don't show signs for high-frequency function words — they clutter the UI
_STOPWORDS = {
    "a", "an", "the", "is", "am", "are", "was", "were", "be", "been", "being",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their",
    "of", "to", "in", "on", "at", "by", "for", "with", "from", "as", "into",
    "and", "or", "but", "so", "if", "then", "than",
    "do", "does", "did", "have", "has", "had",
    "this", "that", "these", "those",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    "not", "no",  # 'no' has its own sign elsewhere if needed
}


_lookup_singleton: SignLookup | None = None


def get_sign_lookup() -> SignLookup:
    global _lookup_singleton
    if _lookup_singleton is None:
        _lookup_singleton = SignLookup()
    return _lookup_singleton
