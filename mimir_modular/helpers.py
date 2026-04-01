"""Mimir helper functions — top-level utilities used across all modules."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timedelta

from .constants import (
    EMOTION_VECTORS, _DEDUP_STOP, _ARC_KEYWORDS,
    _MONTH_MAP, _WEEKDAY_MAP,
    VISUAL_QUALITY_FULL, VISUAL_MAX_EDGE,
    _PIL_Image,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _emotion_to_vector(emotion: str) -> tuple[float, float, float] | None:
    """Map an emotion label to its PAD vector, or None if unknown."""
    if not emotion:
        return None
    key = emotion.lower().strip()
    if key in EMOTION_VECTORS:
        return EMOTION_VECTORS[key]
    for k, v in EMOTION_VECTORS.items():
        if key.startswith(k) or k.startswith(key):
            return v
    return None


def _closest_emotion(pad: tuple[float, float, float]) -> str:
    """Find the EMOTION_VECTORS label nearest to a PAD vector."""
    best, best_dist = "neutral", float("inf")
    for label, vec in EMOTION_VECTORS.items():
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(pad, vec)))
        if dist < best_dist:
            best_dist = dist
            best = label
    return best


def _content_words(text: str) -> set[str]:
    """Extract meaningful non-stop words from text."""
    return set(text.lower().split()) - _DEDUP_STOP


def _overlap_ratio(a: set[str], b: set[str]) -> float:
    """Jaccard similarity."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _resonance_words(text: str) -> set[str]:
    """Extract resonance-quality words (>= 3 chars, non-stop)."""
    return {
        w for w in re.sub(r'[^a-z0-9\s]', '', text.lower()).split()
        if len(w) >= 3 and w not in _DEDUP_STOP
    }


def _extract_dates(text: str, reference: datetime | None = None
                   ) -> list[str]:
    """Extract date references from natural text → list of ISO date strings.

    Handles:
      - ISO:       2024-03-15
      - US slash:  03/15/2024, 3/15/24
      - Written:   March 15, 2024 / March 15th / 15th March 2024
      - Relative:  tomorrow, yesterday, next Tuesday, last Monday
    """
    ref = (reference or datetime.now()).date()
    found: set[str] = set()

    # Pattern 1: ISO  YYYY-MM-DD
    for m in re.finditer(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', text):
        try:
            d = datetime(int(m.group(1)), int(m.group(2)),
                         int(m.group(3))).date()
            found.add(d.isoformat())
        except ValueError:
            pass

    # Pattern 2: US slash  M/D/YYYY or M/D/YY
    for m in re.finditer(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b', text):
        yr = int(m.group(3))
        if yr < 100:
            yr += 2000
        try:
            d = datetime(yr, int(m.group(1)), int(m.group(2))).date()
            found.add(d.isoformat())
        except ValueError:
            pass

    # Pattern 3: Written  "March 15, 2024" / "March 15th" / "15th March 2024"
    month_pat = '|'.join(_MONTH_MAP.keys())
    # Month Day[suffix][, Year]
    for m in re.finditer(
            rf'\b({month_pat})\s+(\d{{1,2}})(?:st|nd|rd|th)?'
            rf'(?:\s*,?\s*(\d{{4}}))?\b',
            text, re.IGNORECASE):
        mo = _MONTH_MAP.get(m.group(1).lower())
        day = int(m.group(2))
        yr = int(m.group(3)) if m.group(3) else ref.year
        if mo:
            try:
                d = datetime(yr, mo, day).date()
                found.add(d.isoformat())
            except ValueError:
                pass
    # Day Month[, Year]
    for m in re.finditer(
            rf'\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_pat})'
            rf'(?:\s*,?\s*(\d{{4}}))?\b',
            text, re.IGNORECASE):
        mo = _MONTH_MAP.get(m.group(2).lower())
        day = int(m.group(1))
        yr = int(m.group(3)) if m.group(3) else ref.year
        if mo:
            try:
                d = datetime(yr, mo, day).date()
                found.add(d.isoformat())
            except ValueError:
                pass

    # Pattern 4: Relative days
    lower = text.lower()
    if "tomorrow" in lower:
        found.add((ref + timedelta(days=1)).isoformat())
    if "yesterday" in lower:
        found.add((ref - timedelta(days=1)).isoformat())

    # "next <weekday>" / "last <weekday>"
    for m in re.finditer(
            r'\b(next|last)\s+(monday|tuesday|wednesday|thursday'
            r'|friday|saturday|sunday)\b',
            text, re.IGNORECASE):
        direction = m.group(1).lower()
        target_wd = _WEEKDAY_MAP[m.group(2).lower()]
        current_wd = ref.weekday()
        if direction == "next":
            delta = (target_wd - current_wd) % 7
            if delta == 0:
                delta = 7
        else:  # last
            delta = -((current_wd - target_wd) % 7)
            if delta == 0:
                delta = -7
        found.add((ref + timedelta(days=delta)).isoformat())

    return sorted(found)


# ═══════════════════════════════════════════════════════════════════════════
#  Visual memory helpers — content-addressable image store
# ═══════════════════════════════════════════════════════════════════════════

def _visual_hash(data: bytes) -> str:
    """SHA-256 content hash for an image (hex, first 32 chars)."""
    return hashlib.sha256(data).hexdigest()[:32]


def _compress_image(data: bytes, quality: int = VISUAL_QUALITY_FULL,
                    max_edge: int = VISUAL_MAX_EDGE) -> tuple[bytes, tuple[int, int]]:
    """Compress raw image bytes → WebP, return (webp_bytes, (w, h)).

    Resizes if either dimension exceeds *max_edge*, preserving aspect ratio.
    Requires Pillow; raises RuntimeError if not installed.
    """
    if _PIL_Image is None:
        raise RuntimeError("Pillow is required for visual memory: pip install Pillow")
    import io
    img = _PIL_Image.open(io.BytesIO(data))
    img = img.convert("RGB")  # strip alpha for consistent hashing
    # Resize if needed
    w, h = img.size
    if max(w, h) > max_edge:
        scale = max_edge / max(w, h)
        w, h = int(w * scale), int(h * scale)
        img = img.resize((w, h), _PIL_Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality)
    return buf.getvalue(), (w, h)


def _decompress_image(data: bytes, quality: int | None = None) -> bytes:
    """Re-encode stored WebP at a different quality (for faded recall).

    If *quality* is None, returns the original bytes untouched.
    """
    if quality is None or _PIL_Image is None:
        return data
    import io
    img = _PIL_Image.open(io.BytesIO(data))
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality)
    return buf.getvalue()


def _infer_arc_position(content: str, emotion: str) -> str:
    """Infer narrative arc position from content keywords + arousal level."""
    lower = content.lower()
    scores: dict[str, int] = {}
    for pos, keywords in _ARC_KEYWORDS.items():
        scores[pos] = sum(1 for kw in keywords if kw in lower)
    # Arousal biases: high arousal → climax, low → resolution
    vec = _emotion_to_vector(emotion)
    if vec:
        if abs(vec[1]) >= 0.6:
            scores["climax"] = scores.get("climax", 0) + 2
        elif abs(vec[1]) <= 0.2:
            scores["resolution"] = scores.get("resolution", 0) + 1
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "rising"  # default to rising
