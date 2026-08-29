# Mimir — The Ultimate Memory Architecture
# Copyright (c) 2026 Kronic90. All rights reserved.
# Licensed under PolyForm Noncommercial 1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/

"""VividMimir — install via ``pip install vividmimir``.

Organic episodic memory for AI companions — 21 neuroscience mechanisms,
neurochemistry engine, Yggdrasil memory graph, and hybrid retrieval.
"""

__version__ = "2.0.0"

from .core import Mimir
from .models import (
    Memory, Lesson, Attempt, Reminder, ShortTermFact,
    TaskRecord, ActionRecord, SolutionPattern, ArtifactRecord,
)
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
    "TaskRecord", "ActionRecord", "SolutionPattern", "ArtifactRecord",
    "EMOTION_VECTORS",
    "_resonance_words", "_extract_dates", "_emotion_to_vector",
    "_content_words",
]
