"""Sign clip lookup service.

Maps English words to sign-language video clips. Uses Spread The Sign
public CDN (https://media.spreadthesign.com) for ASL clips when available,
with graceful fallback to a placeholder visual on the frontend.

To replace with WLASL pretrained recognition (camera → sign → word), build
a separate visual classifier — this service is for the OUTPUT direction
(text → sign clip).
"""
from __future__ import annotations

from api.models import SignClip


# Curated mapping of common words → public ASL video URLs from Spread The Sign.
# When the URL 404s (rare) or CORS fails, the frontend falls back to an
# enhanced sign tile with the word and animated hand emoji.
_SIGN_DATA: dict[str, dict[str, str | int]] = {
    # Greetings / basics
    "hello":      {"url": "https://media.spreadthesign.com/video/mp4/13/52183.mp4", "duration_ms": 1400},
    "thank you":  {"url": "https://media.spreadthesign.com/video/mp4/13/52337.mp4", "duration_ms": 1500},
    "yes":        {"url": "https://media.spreadthesign.com/video/mp4/13/53005.mp4", "duration_ms": 1100},
    "no":         {"url": "https://media.spreadthesign.com/video/mp4/13/52508.mp4", "duration_ms": 1100},
    "please":     {"url": "https://media.spreadthesign.com/video/mp4/13/52617.mp4", "duration_ms": 1300},
    "sorry":      {"url": "https://media.spreadthesign.com/video/mp4/13/52749.mp4", "duration_ms": 1400},
    "help":       {"url": "https://media.spreadthesign.com/video/mp4/13/52189.mp4", "duration_ms": 1300},
    "stop":       {"url": "https://media.spreadthesign.com/video/mp4/13/52786.mp4", "duration_ms": 1100},

    # Meeting vocabulary
    "meeting":    {"url": "https://media.spreadthesign.com/video/mp4/13/52443.mp4", "duration_ms": 1500},
    "agenda":     {"url": "", "duration_ms": 1400},
    "deadline":   {"url": "", "duration_ms": 1400},
    "blocker":    {"url": "", "duration_ms": 1400},
    "deploy":     {"url": "", "duration_ms": 1400},
    "review":     {"url": "https://media.spreadthesign.com/video/mp4/13/52676.mp4", "duration_ms": 1500},
    "question":   {"url": "https://media.spreadthesign.com/video/mp4/13/52647.mp4", "duration_ms": 1300},
    "answer":     {"url": "https://media.spreadthesign.com/video/mp4/13/51769.mp4", "duration_ms": 1300},
    "team":       {"url": "https://media.spreadthesign.com/video/mp4/13/52911.mp4", "duration_ms": 1300},
    "project":    {"url": "https://media.spreadthesign.com/video/mp4/13/52635.mp4", "duration_ms": 1500},
    "today":      {"url": "https://media.spreadthesign.com/video/mp4/13/52946.mp4", "duration_ms": 1300},
    "tomorrow":   {"url": "https://media.spreadthesign.com/video/mp4/13/52949.mp4", "duration_ms": 1300},

    # Medical
    "doctor":     {"url": "https://media.spreadthesign.com/video/mp4/13/52042.mp4", "duration_ms": 1400},
    "pain":       {"url": "https://media.spreadthesign.com/video/mp4/13/52568.mp4", "duration_ms": 1300},
    "water":      {"url": "https://media.spreadthesign.com/video/mp4/13/53117.mp4", "duration_ms": 1300},
    "medicine":   {"url": "https://media.spreadthesign.com/video/mp4/13/52442.mp4", "duration_ms": 1400},
    "emergency":  {"url": "", "duration_ms": 1400},
    "hospital":   {"url": "https://media.spreadthesign.com/video/mp4/13/52210.mp4", "duration_ms": 1400},

    # Business
    "money":      {"url": "https://media.spreadthesign.com/video/mp4/13/52471.mp4", "duration_ms": 1300},
    "budget":     {"url": "", "duration_ms": 1400},
    "client":     {"url": "", "duration_ms": 1400},
    "report":     {"url": "https://media.spreadthesign.com/video/mp4/13/52674.mp4", "duration_ms": 1500},
    "approve":    {"url": "", "duration_ms": 1400},
    "decision":   {"url": "https://media.spreadthesign.com/video/mp4/13/51996.mp4", "duration_ms": 1500},

    # Common verbs
    "need":       {"url": "https://media.spreadthesign.com/video/mp4/13/52490.mp4", "duration_ms": 1300},
    "want":       {"url": "https://media.spreadthesign.com/video/mp4/13/53108.mp4", "duration_ms": 1300},
    "see":        {"url": "https://media.spreadthesign.com/video/mp4/13/52706.mp4", "duration_ms": 1100},
    "understand": {"url": "https://media.spreadthesign.com/video/mp4/13/52985.mp4", "duration_ms": 1500},
    "think":      {"url": "https://media.spreadthesign.com/video/mp4/13/52933.mp4", "duration_ms": 1300},
    "work":       {"url": "https://media.spreadthesign.com/video/mp4/13/53160.mp4", "duration_ms": 1300},
    "talk":       {"url": "https://media.spreadthesign.com/video/mp4/13/52887.mp4", "duration_ms": 1300},
    "listen":     {"url": "https://media.spreadthesign.com/video/mp4/13/52399.mp4", "duration_ms": 1300},
}


MOCK_SIGN_LIBRARY: dict[str, SignClip] = {
    word: SignClip(
        id=f"wlasl-{word.replace(' ', '-')}",
        word=word,
        video_url=str(data.get("url", "")),
        duration_ms=int(data.get("duration_ms", 1300)),
        description=f"ASL sign for '{word}'",
    )
    for word, data in _SIGN_DATA.items()
}


class SignLookup:
    def __init__(self, library: dict[str, SignClip] | None = None) -> None:
        self._library = library or MOCK_SIGN_LIBRARY

    def find_signs(self, text: str, max_clips: int = 5) -> list[SignClip]:
        words = [w.strip(".,!?;:'\"").lower() for w in text.split()]
        matched: list[SignClip] = []
        seen: set[str] = set()
        for word in words:
            if word in self._library and word not in seen:
                matched.append(self._library[word])
                seen.add(word)
                if len(matched) >= max_clips:
                    break
        return matched

    def vocabulary(self) -> list[str]:
        return sorted(self._library.keys())


_lookup_singleton: SignLookup | None = None


def get_sign_lookup() -> SignLookup:
    global _lookup_singleton
    if _lookup_singleton is None:
        _lookup_singleton = SignLookup()
    return _lookup_singleton
