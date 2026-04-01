"""mimir_modular — Mimir split into composable mixins."""

from .core import Mimir
from .models import Memory, Lesson, Attempt, Reminder, ShortTermFact
from .constants import (
    EMOTION_VECTORS,
    HUGINN_PATTERN_MIN, HUGINN_OPEN_THREAD_WORDS,
    MUNINN_PRUNE_THRESHOLD, MUNINN_MERGE_THRESHOLD, MUNINN_COACTIVATION_BOOST,
    YGGDRASIL_WORD_EDGE_MIN, YGGDRASIL_WORD_EDGE_MAX,
    YGGDRASIL_TEMPORAL_DAYS, YGGDRASIL_MAX_EDGES, YGGDRASIL_BOOST,
    VOLVA_SAMPLE_PAIRS, VOLVA_INSIGHT_IMPORTANCE,
)
from .helpers import (
    _resonance_words, _extract_dates, _emotion_to_vector,
    _content_words, _overlap_ratio, _closest_emotion,
    _visual_hash, _compress_image, _decompress_image,
    _infer_arc_position,
)

__all__ = [
    "Mimir", "Memory", "Lesson", "Attempt", "Reminder", "ShortTermFact",
    "EMOTION_VECTORS",
    "_resonance_words", "_extract_dates", "_emotion_to_vector",
    "_content_words",
]
