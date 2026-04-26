"""Build a sign-language library from the WLASL dataset.

WLASL (Word-Level American Sign Language) is the de-facto research dataset
for ASL recognition (Li et al., 2020). 2000 glosses (words) × ~10 video
instances per word from various ASL teaching sources.

Source priority (preferring direct, embeddable, fast-loading URLs):
  1. signschool  -> direct MP4 on Microsoft Azure blob storage (fastest)
  2. youtube      -> iframe embed (works cross-origin)
  3. (nothing)    -> word excluded

Output: data/wlasl_library.json with the structure expected by sign_lookup.py.
Run: python scripts/build_wlasl_library.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "WLASL_v0.3.json"
OUTPUT = ROOT / "data" / "wlasl_library.json"


YOUTUBE_ID_RE = re.compile(r"(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})")


def youtube_id(url: str) -> str | None:
    m = YOUTUBE_ID_RE.search(url)
    return m.group(1) if m else None


def pick_best_video(instances: list[dict]) -> dict | None:
    """Prefer signschool (direct MP4) > YouTube > nothing."""
    signschool = None
    youtube = None
    for inst in instances:
        if inst.get("source") == "signschool" and "blob.core.windows.net" in inst.get("url", ""):
            if signschool is None:
                signschool = inst
        elif "youtube.com" in inst.get("url", "") or "youtu.be" in inst.get("url", ""):
            if youtube is None:
                youtube = inst
    return signschool or youtube


def to_seconds(frame: int, fps: int) -> float:
    if frame < 0 or fps <= 0:
        return 0.0
    return round(frame / fps, 2)


def build_entry(gloss: str, instance: dict) -> dict | None:
    url = instance["url"]
    fps = instance.get("fps", 25)
    start_seconds = to_seconds(instance.get("frame_start", 1) or 1, fps)
    end_seconds = to_seconds(instance.get("frame_end", -1) or -1, fps)

    if "blob.core.windows.net" in url:
        return {
            "id": f"wlasl-{gloss}",
            "word": gloss,
            "video_type": "mp4",
            "video_url": url,
            "youtube_id": None,
            "start_seconds": start_seconds,
            "end_seconds": end_seconds if end_seconds > 0 else None,
            "duration_ms": int((end_seconds - start_seconds) * 1000) if end_seconds > 0 else 1500,
            "source": instance.get("source", ""),
            "signer_id": instance.get("signer_id"),
            "description": f"ASL sign for '{gloss}' (WLASL · {instance.get('source', 'unknown')})",
        }
    yid = youtube_id(url)
    if yid:
        return {
            "id": f"wlasl-{gloss}",
            "word": gloss,
            "video_type": "youtube",
            "video_url": url,
            "youtube_id": yid,
            "start_seconds": start_seconds,
            "end_seconds": end_seconds if end_seconds > 0 else None,
            "duration_ms": int((end_seconds - start_seconds) * 1000) if end_seconds > 0 else 2000,
            "source": instance.get("source", ""),
            "signer_id": instance.get("signer_id"),
            "description": f"ASL sign for '{gloss}' (WLASL · {instance.get('source', 'unknown')})",
        }
    return None


def main() -> int:
    if not SOURCE.exists():
        print(f"ERROR: {SOURCE} not found. Run the curl download step first.")
        return 1

    with open(SOURCE) as f:
        wlasl = json.load(f)

    library: dict[str, dict] = {}
    counts = {"mp4": 0, "youtube": 0, "skipped": 0}

    for sign in wlasl:
        gloss = sign["gloss"].lower().strip()
        instance = pick_best_video(sign["instances"])
        if not instance:
            counts["skipped"] += 1
            continue
        entry = build_entry(gloss, instance)
        if not entry:
            counts["skipped"] += 1
            continue
        library[gloss] = entry
        counts[entry["video_type"]] += 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(library, f, indent=2, ensure_ascii=False)

    print(f"WLASL library written to {OUTPUT.relative_to(ROOT)}")
    print(f"  Total entries: {len(library)}")
    print(f"  Direct MP4 (signschool): {counts['mp4']}")
    print(f"  YouTube embeds: {counts['youtube']}")
    print(f"  Skipped (no usable URL): {counts['skipped']}")
    print(f"  File size: {OUTPUT.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
