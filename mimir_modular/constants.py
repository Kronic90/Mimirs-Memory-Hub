"""Mimir constants, engine imports, and tuning parameters.

All neuroscience mechanism constants, emotion vectors, and optional
engine imports live here so every other module can import from one place.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import random
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

# ── Engine imports (pip first → local fallback → None) ────────────────────

_NeuroChemistry = None
try:
    from vividnessmem.vividnessmem import NeuroChemistry as _NeuroChemistry
except ImportError:
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from VividnessMem import NeuroChemistry as _NeuroChemistry
    except ImportError:
        pass

_EmotionalAuditLog = None
try:
    from vividnessmem.vividnessmem import EmotionalAuditLog as _EmotionalAuditLog
except ImportError:
    try:
        from VividnessMem import EmotionalAuditLog as _EmotionalAuditLog
    except ImportError:
        pass

_VividEmbed = None
try:
    from vividembed import VividEmbed as _VividEmbed
except ImportError:
    try:
        from VividEmbed import VividEmbed as _VividEmbed
    except ImportError:
        pass

# ── Visual memory (Pillow — optional) ─────────────────────────────────────
_PIL_Image = None
try:
    from PIL import Image as _PIL_Image
except ImportError:
    pass

# ── Encryption at rest (optional) ─────────────────────────────────────────
_Fernet = None
_PBKDF2 = None
_crypto_hashes = None
try:
    from cryptography.fernet import Fernet as _Fernet
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC as _PBKDF2
    from cryptography.hazmat.primitives import hashes as _crypto_hashes
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════════════════════
#  Emotion → PAD vector mapping (Pleasure-Arousal-Dominance)
# ═══════════════════════════════════════════════════════════════════════════

EMOTION_VECTORS: dict[str, tuple[float, float, float]] = {
    # positive-calm
    "content":      ( 0.7, -0.3,  0.3),
    "peaceful":     ( 0.8, -0.5,  0.4),
    "serene":       ( 0.8, -0.6,  0.3),
    "grateful":     ( 0.8,  0.1,  0.4),
    "appreciative": ( 0.7,  0.0,  0.3),
    "hopeful":      ( 0.6,  0.2,  0.3),
    "warm":         ( 0.7,  0.1,  0.3),
    "tender":       ( 0.6, -0.1,  0.0),
    "affectionate": ( 0.7,  0.2,  0.2),
    # positive-active
    "happy":        ( 0.8,  0.4,  0.5),
    "joyful":       ( 0.9,  0.6,  0.5),
    "excited":      ( 0.7,  0.8,  0.5),
    "enthusiastic": ( 0.7,  0.7,  0.5),
    "proud":        ( 0.7,  0.4,  0.7),
    "amused":       ( 0.6,  0.5,  0.4),
    "playful":      ( 0.7,  0.6,  0.4),
    "inspired":     ( 0.7,  0.5,  0.5),
    "curious":      ( 0.5,  0.6,  0.3),
    "fascinated":   ( 0.6,  0.6,  0.3),
    "motivated":    ( 0.6,  0.5,  0.6),
    "triumphant":   ( 0.8,  0.6,  0.8),
    "delighted":    ( 0.9,  0.5,  0.5),
    # neutral / reflective
    "neutral":      ( 0.0,  0.0,  0.0),
    "thoughtful":   ( 0.2,  0.1,  0.3),
    "reflective":   ( 0.2, -0.1,  0.2),
    "contemplative":( 0.2, -0.2,  0.2),
    "nostalgic":    ( 0.3, -0.1,  0.1),
    "bittersweet":  ( 0.1,  0.0,  0.0),
    "wistful":      ( 0.1, -0.2,  0.0),
    "understanding":( 0.4,  0.0,  0.4),
    # negative-low arousal
    "sad":          (-0.6, -0.3, -0.3),
    "lonely":       (-0.7, -0.4, -0.5),
    "melancholy":   (-0.5, -0.4, -0.2),
    "disappointed": (-0.5, -0.2, -0.3),
    "guilty":       (-0.5,  0.1, -0.6),
    "insecure":     (-0.4,  0.2, -0.5),
    "vulnerable":   (-0.3,  0.1, -0.5),
    # negative-high arousal
    "anxious":      (-0.5,  0.7, -0.4),
    "frustrated":   (-0.5,  0.6, -0.2),
    "angry":        (-0.7,  0.8,  0.2),
    "hurt":         (-0.6,  0.3, -0.5),
    "confused":     (-0.3,  0.4, -0.3),
    "overwhelmed":  (-0.4,  0.7, -0.5),
    "embarrassed":  (-0.5,  0.5, -0.6),
    "jealous":      (-0.6,  0.6, -0.2),
    "afraid":       (-0.7,  0.8, -0.6),
    "resentful":    (-0.6,  0.5, -0.1),
}


# ═══════════════════════════════════════════════════════════════════════════
#  Constants — Neuroscience mechanisms
# ═══════════════════════════════════════════════════════════════════════════

# ── 1. Flashbulb memory ───────────────────────────────────────────────────
FLASHBULB_STABILITY_FLOOR  = 120.0
FLASHBULB_AROUSAL_THRESHOLD = 0.6
FLASHBULB_IMPORTANCE_MIN   = 8
FLASHBULB_VIVIDNESS_FLOOR  = 0.85

# ── 2. Reconsolidation ───────────────────────────────────────────────────
RECONSOLIDATION_DRIFT_RATE = 0.05
DRIFT_ALERT_THRESHOLD      = 0.4

# ── 3. State-dependent memory ────────────────────────────────────────────
STATE_DEPENDENT_BOOST      = 0.3

# ── 4. Spreading activation ──────────────────────────────────────────────
PRIMING_BOOST              = 1.5
PRIMING_DECAY              = 0.8

# ── 5. Retrieval-induced forgetting ──────────────────────────────────────
INTERFERENCE_THRESHOLD     = 0.7
INTERFERENCE_PENALTY       = 0.15

# ── 6. Zeigarnik effect ──────────────────────────────────────────────────
ZEIGARNIK_BOOST            = 0.5

# ── 7. Involuntary / Proustian recall ────────────────────────────────────
INVOLUNTARY_RECALL_PROB    = 0.05

# ── 8. Temporal gist extraction ──────────────────────────────────────────
GIST_AGE_THRESHOLD_DAYS    = 90
GIST_PRESERVE_WORDS        = 15

# ── Spaced-repetition (mirrored from VividnessMem) ───────────────────────
INITIAL_STABILITY  = 3.0
SPACING_BONUS      = 1.8
MIN_SPACING_DAYS   = 0.5
STABILITY_CAP      = 180.0
DIMINISHING_RATE   = 0.85

# ── Anchors ──────────────────────────────────────────────────────────────
ANCHOR_STABILITY_FLOOR  = 90.0
ANCHOR_VIVIDNESS_FLOOR  = 0.30

# ── Dedup ────────────────────────────────────────────────────────────────
_DEDUP_THRESHOLD = 0.55
_DEDUP_STOP = frozenset({
    "the", "a", "an", "is", "was", "are", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "and", "but", "or",
    "not", "so", "yet", "both", "either", "neither", "each", "every",
    "all", "any", "few", "more", "most", "other", "some", "such", "no",
    "only", "own", "same", "than", "too", "very", "just", "of", "at",
    "by", "for", "with", "about", "against", "between", "through",
    "during", "before", "after", "above", "below", "to", "from", "up",
    "down", "in", "out", "on", "off", "over", "under", "again", "then",
    "here", "there", "when", "where", "why", "how", "this", "that",
    "these", "those", "i", "me", "my", "myself", "we", "our", "you",
    "your", "he", "him", "his", "she", "her", "it", "its", "they",
    "them", "their", "what", "which", "who", "whom",
})

# ── Hybrid retrieval bridge ──────────────────────────────────────────────
RECALL_LIMIT               = 10
_RECENCY_HALF_LIFE_DAYS    = 5.0

# Composite re-rank weights (must sum to 1.0)
_W_KEYWORD   = 0.30
_W_SEMANTIC  = 0.30
_W_VIVIDNESS = 0.20
_W_MOOD      = 0.10
_W_RECENCY   = 0.10

# ── 9. Temporal / Episodic memory (Tulving 1972) ─────────────────────────
TEMPORAL_PROXIMITY_DAYS    = 3.0
TEMPORAL_PROXIMITY_BOOST   = 0.08
PROSPECTIVE_IMPORTANCE_MIN = 4

TEMPORAL_LOOKAHEAD_DAYS    = 7
TEMPORAL_LOOKBEHIND_DAYS   = 2
TEMPORAL_SALIENCE_BOOST    = 0.12

# ── 10. Visual memory (Kosslyn 1980 — Mental Imagery) ────────────────────
VISUAL_MAX_EDGE            = 1920
VISUAL_QUALITY_FULL        = 80
VISUAL_QUALITY_FADED       = 30
VISUAL_VIVID_THRESHOLD     = 0.7
VISUAL_GIST_THRESHOLD      = 0.3
VISUAL_BOOST               = 0.05

# ── 11. Huginn — Thought (pattern detection) ─────────────────────────────
HUGINN_PATTERN_MIN         = 3
HUGINN_OPEN_THREAD_WORDS   = frozenset({
    "should", "need", "want", "plan", "going", "hope",
    "intend", "must", "will", "trying",
})

# ── 12. Muninn — Memory (consolidation) ──────────────────────────────────
MUNINN_PRUNE_THRESHOLD     = 0.01
MUNINN_MERGE_THRESHOLD     = 0.40
MUNINN_COACTIVATION_BOOST  = 1.05

# ── 13. Yggdrasil — World Tree (memory graph) ────────────────────────────
YGGDRASIL_WORD_EDGE_MIN    = 0.20
YGGDRASIL_WORD_EDGE_MAX    = 0.55
YGGDRASIL_TEMPORAL_DAYS    = 3.0
YGGDRASIL_MAX_EDGES        = 8
YGGDRASIL_BOOST            = 0.03

# ── 13b. Spreading Activation (Collins & Loftus 1975) ────────────────────
SPREADING_ACTIVATION_HOPS       = 3
SPREADING_ACTIVATION_DECAY      = 0.5
SPREADING_ACTIVATION_THRESHOLD  = 0.08
SPREADING_ACTIVATION_MAX_DISCOVER = 10

# ── 19. Contextual Pre-filtering (state-dependent access gating) ─────────
MOOD_GATE_DISTANCE        = 1.4
MOOD_GATE_KEEP_MIN        = 20

# ── 20. Auto-Consolidation (hippocampal replay interval) ─────────────────
AUTO_CONSOLIDATION_INTERVAL = 50

# ── 21. Memory Chunking (Miller 1956 — 7±2) ─────────────────────────────
CHUNK_OVERLAP_THRESHOLD   = 0.30
CHUNK_MIN_GROUP           = 3
CHUNK_MAX_CONTENT_WORDS   = 120

# ── 14. Völva's Vision — Dream synthesis ─────────────────────────────────
VOLVA_SAMPLE_PAIRS         = 10
VOLVA_INSIGHT_IMPORTANCE   = 5

# ── 15. Novelty-modulated encoding (Ranganath & Rainer 2003) ─────────────
NOVELTY_MAX_COMPARE        = 20
NOVELTY_HIGH_THRESHOLD     = 0.85
NOVELTY_LOW_THRESHOLD      = 0.40
NOVELTY_BOOST_FACTOR       = 1.3
NOVELTY_DECAY_FACTOR       = 0.85

# ── 16. Enhanced drift analysis ──────────────────────────────────────────
DRIFT_VELOCITY_WINDOW      = 5
COGNITIVE_BIAS_THRESHOLD   = 0.75

# ── 17. Hippocampal Pattern Separation (Yassa & Stark 2011) ──────────────
PATTERN_SEP_THRESHOLD      = 0.80
PATTERN_SEP_NUDGE          = 1

# ── 18. Narrative Arc Tracking ───────────────────────────────────────────
ARC_POSITIONS = ("setup", "rising", "climax", "falling", "resolution")
_ARC_KEYWORDS: dict[str, list[str]] = {
    "setup":      ["beginning", "started", "first", "new", "introduce", "meet"],
    "rising":     ["growing", "building", "developing", "learning", "discovering"],
    "climax":     ["breakthrough", "crisis", "turning", "realized", "moment", "peak",
                   "confronted", "decided", "revelation", "changed"],
    "falling":    ["after", "settled", "processing", "reflecting", "consequence"],
    "resolution": ["resolved", "concluded", "peace", "accepted", "closure",
                   "understood", "finally", "lesson"],
}

# ── Task / Project branch ────────────────────────────────────────────────
PROJECT_DECAY_ACTIVE_DAYS  = 7
PROJECT_DECAY_COOLING_DAYS = 30
PROJECT_DECAY_COLD_MULT    = 6.0
SOLUTION_INITIAL_IMPORTANCE = 8
SOLUTION_REUSE_BOOST       = 0.3

# ── LLM integration ─────────────────────────────────────────────────────
LLMCallable = Callable[[list[dict[str, str]]], str]

# Month lookup for date extraction
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}

_WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# ═══════════════════════════════════════════════════════════════════════
#  Long-Term Memory Improvements (v0.7.0)
# ═══════════════════════════════════════════════════════════════════════

# ── 22. Importance-based decay floors ────────────────────────────────────
# High-importance memories never drop below a vividness floor, mirroring
# strong synaptic consolidation in real neurons.  Importance 7-8 gets a
# modest floor; 9-10 gets a higher one (below flashbulb, above anchor).
IMPORTANCE_FLOOR_THRESHOLD  = 7          # importance >= this gets a floor
IMPORTANCE_FLOOR_LOW        = 0.15       # floor multiplier for imp 7-8
IMPORTANCE_FLOOR_HIGH       = 0.40       # floor multiplier for imp 9-10

# ── 23. Semantic memory crystallization (Huginn stage 5) ─────────────────
# During consolidation, Huginn detects facts mentioned across multiple
# episodic memories and crystallizes them into durable semantic memories.
# Models the episodic→semantic transition of real memory (Tulving 1972).
SEMANTIC_MIN_MENTIONS       = 3          # times a fact-phrase must recur
SEMANTIC_STABILITY          = 150.0      # near-permanent stability (days)
SEMANTIC_IMPORTANCE_FLOOR   = 7          # minimum importance for semantic mems
SEMANTIC_VIVIDNESS_FLOOR    = 0.50       # semantic mems never fade below this

# ── 24. Hierarchical summarization (Muninn stage 4) ──────────────────────
# During consolidation, Muninn produces weekly gist-summaries from clusters
# of same-week episodic memories, like hippocampal replay compressing
# episodes into schemas.
SUMMARY_MIN_MEMORIES        = 4          # min memories in a week to summarize
SUMMARY_AGE_DAYS            = 14         # only summarize weeks older than this
SUMMARY_IMPORTANCE          = 6          # importance of summary memories
SUMMARY_STABILITY           = 90.0       # summaries last a long time

# ── 25. Retrieval-augmented reinforcement (Huginn stage 6) ───────────────
# During consolidation, Huginn scans for high-importance memories that are
# fading and refreshes their stability — like the hippocampus replaying
# important traces during slow-wave sleep.
REINFORCEMENT_IMPORTANCE_MIN = 6         # only reinforce memories imp >= this
REINFORCEMENT_VIVIDNESS_MAX  = 0.40      # only reinforce if vividness <= this
REINFORCEMENT_STABILITY_BOOST = 1.5      # multiply stability by this
REINFORCEMENT_MAX_PER_CYCLE  = 10        # cap per consolidation cycle

# ── 26. Entity-anchored recall (recall enhancement) ──────────────────────
# When a query contains a recognized entity name, boost entity-edge
# activation in spreading activation and add direct entity lookups.
ENTITY_RECALL_BOOST         = 0.15       # bonus added per entity-matched mem

# ── 27. Query-adaptive signal weighting ──────────────────────────────────
# When the system detects a factual/entity query vs emotional/thematic
# query, shift the composite re-rank weights accordingly.
# Factual queries: boost BM25 + vividness, reduce mood weight
# Emotional queries: boost semantic + mood, reduce keyword weight
_W_KEYWORD_FACTUAL   = 0.40
_W_SEMANTIC_FACTUAL  = 0.20
_W_VIVIDNESS_FACTUAL = 0.25
_W_MOOD_FACTUAL      = 0.05
_W_RECENCY_FACTUAL   = 0.10

_W_KEYWORD_EMOTIONAL  = 0.20
_W_SEMANTIC_EMOTIONAL = 0.35
_W_VIVIDNESS_EMOTIONAL = 0.15
_W_MOOD_EMOTIONAL     = 0.20
_W_RECENCY_EMOTIONAL  = 0.10

# Factual query indicators (entity names, "what is", "who", numbers, etc.)
_FACTUAL_QUERY_WORDS = frozenset({
    "what", "who", "which", "where", "when", "name", "called",
    "job", "work", "title", "birthday", "age", "live", "address",
    "number", "email", "phone", "project", "company",
})

# Emotional query indicators
_EMOTIONAL_QUERY_WORDS = frozenset({
    "feel", "feeling", "felt", "emotion", "mood", "happy", "sad",
    "angry", "afraid", "anxious", "stressed", "excited", "love",
    "hate", "miss", "worry", "scared", "lonely", "grateful",
})
