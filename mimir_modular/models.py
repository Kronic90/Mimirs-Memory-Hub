"""Mimir data models — Memory, Lesson, Attempt, Reminder, and more."""

from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any

from .constants import (
    INITIAL_STABILITY, FLASHBULB_STABILITY_FLOOR, FLASHBULB_VIVIDNESS_FLOOR,
    ANCHOR_STABILITY_FLOOR, ANCHOR_VIVIDNESS_FLOOR,
    GIST_AGE_THRESHOLD_DAYS, GIST_PRESERVE_WORDS,
    RECONSOLIDATION_DRIFT_RATE, DRIFT_ALERT_THRESHOLD,
    STATE_DEPENDENT_BOOST, ZEIGARNIK_BOOST,
    MIN_SPACING_DAYS, SPACING_BONUS, DIMINISHING_RATE, STABILITY_CAP,
    VISUAL_VIVID_THRESHOLD, VISUAL_GIST_THRESHOLD,
    SOLUTION_INITIAL_IMPORTANCE, SOLUTION_REUSE_BOOST,
    _DEDUP_STOP,
)
from .helpers import _emotion_to_vector, _closest_emotion, _content_words


# ═══════════════════════════════════════════════════════════════════════════
#  Memory — single episodic memory with neuroscience extensions
# ═══════════════════════════════════════════════════════════════════════════

class Memory:
    """A single memory with organic vividness decay and neuroscience layers.

    Compared to base VividnessMem Memory, Mimir's Memory adds:
    - Flashbulb encoding (_is_flashbulb) with stability + vividness floors
    - Encoding mood (_encoding_mood) for state-dependent retrieval
    - Reconsolidation drift on touch()
    - Temporal gist compression (.gist property)
    """

    __slots__ = (
        "content", "emotion", "importance", "timestamp",
        "source", "entity", "_access_count", "_last_access",
        "_stability", "why_saved",
        # Neuroscience extensions
        "original_emotion",   # immutable baseline — never drifts
        "_is_flashbulb", "_encoding_mood", "_emotion_pad",
        # Temporal / Episodic (Tulving 1972)
        "_mentioned_dates",
        # VividEmbed sync
        "_embed_uid",
        # Visual memory (Kosslyn 1980)
        "_visual_hash", "_visual_description", "_visual_dimensions",
        # Intentional reframe tracking
        "_reframed", "_reframe_reason",
        # VividnessMem-compatible fields
        "_anchor", "_cherished", "_privacy",
        "_regret", "_believed_importance", "_rescore_survived",
        # Novelty-modulated encoding
        "_novelty_score",
        # Enhanced drift tracking
        "_drift_history",
        # Narrative arc (Freytag 1863)
        "_arc_position",
    )

    def __init__(self, content: str, emotion: str = "neutral",
                 importance: int = 5, source: str = "reflection",
                 entity: str = "", why_saved: str = ""):
        self.content = content
        self.emotion = emotion
        self.importance = max(1, min(10, importance))
        self.timestamp = datetime.now().isoformat()
        self.source = source
        self.entity = entity
        self._access_count: int = 0
        self._last_access: str = self.timestamp
        self._stability: float = INITIAL_STABILITY
        self.why_saved = why_saved
        # Neuroscience
        self.original_emotion: str = emotion   # immutable baseline — never drifts
        self._is_flashbulb: bool = False
        self._encoding_mood: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._emotion_pad: tuple[float, float, float] | None = None
        # Temporal
        self._mentioned_dates: list[str] = []
        # VividEmbed sync
        self._embed_uid: str = ""
        # Visual memory (Kosslyn 1980)
        self._visual_hash: str = ""
        self._visual_description: str = ""
        self._visual_dimensions: tuple[int, int] = (0, 0)
        # VividnessMem compat
        self._anchor: bool = False
        self._cherished: bool = False
        self._privacy: str = "public"
        self._reframed: bool = False
        self._reframe_reason: str = ""
        self._regret: float = 0.0
        self._believed_importance: int = 0
        self._rescore_survived: int = 0
        # Novelty-modulated encoding
        self._novelty_score: float = 0.5  # 0 = redundant, 1 = completely novel
        # Enhanced drift tracking
        self._drift_history: list[tuple[str, str, float]] = []  # (timestamp, emotion, magnitude)
        # Narrative arc
        self._arc_position: str = ""  # setup / rising / climax / falling / resolution

    # ── Spaced-repetition touch + reconsolidation ─────────────────────
    def touch(self, current_mood: tuple[float, float, float] | None = None):
        """Record an access.  Well-spaced touches increase stability.

        If *current_mood* is provided and the memory is not a flashbulb,
        reconsolidation occurs: the memory's emotion subtly drifts toward
        the current mood context (Nader et al 2000).
        """
        now = datetime.now()
        last = datetime.fromisoformat(self._last_access)
        gap_days = (now - last).total_seconds() / 86400

        if gap_days >= MIN_SPACING_DAYS:
            effective_bonus = (
                1.0 + (SPACING_BONUS - 1.0)
                * (DIMINISHING_RATE ** self._access_count)
            )
            self._stability = min(
                self._stability * effective_bonus, STABILITY_CAP)
        self._access_count += 1
        self._last_access = now.isoformat()

        # ── Reconsolidation instability ───────────────────────────────
        if current_mood and not self._is_flashbulb:
            if self._emotion_pad is None:
                self._emotion_pad = (
                    _emotion_to_vector(self.emotion) or (0.0, 0.0, 0.0))
            self._emotion_pad = tuple(
                self._emotion_pad[i]
                + RECONSOLIDATION_DRIFT_RATE
                * (current_mood[i] - self._emotion_pad[i])
                for i in range(3)
            )
            self.emotion = _closest_emotion(self._emotion_pad)

    # ── Vividness (organic decay) ─────────────────────────────────────
    @property
    def vividness(self) -> float:
        age_days = (
            datetime.now() - datetime.fromisoformat(self.timestamp)
        ).total_seconds() / 86400
        effective_stability = self._stability
        if self._anchor:
            effective_stability = max(
                effective_stability, ANCHOR_STABILITY_FLOOR)
        if self._is_flashbulb:
            effective_stability = max(
                effective_stability, FLASHBULB_STABILITY_FLOOR)
        retention = math.exp(-age_days / max(effective_stability, 0.1))
        raw = self.importance * retention
        if self._is_flashbulb:
            return max(raw, self.importance * FLASHBULB_VIVIDNESS_FLOOR)
        if self._anchor:
            return max(raw, self.importance * ANCHOR_VIVIDNESS_FLOOR)
        return raw

    # ── Mood-adjusted vividness (state-dependent memory) ──────────────
    def mood_adjusted_vividness(
        self, mood_vector: tuple[float, float, float]
    ) -> float:
        """Vividness boosted when retrieval mood matches the memory."""
        base = self.vividness
        mem_vec = _emotion_to_vector(self.emotion)
        if not mem_vec or mood_vector == (0.0, 0.0, 0.0):
            return base

        # Standard mood congruence
        dot = sum(a * b for a, b in zip(mem_vec, mood_vector))
        congruence = max(-1.0, min(1.0, dot))
        mood_boost = 1.0 + congruence * 0.3

        # State-dependent boost (encoding-context match)
        if self._encoding_mood != (0.0, 0.0, 0.0):
            enc_dot = sum(
                a * b for a, b in zip(mood_vector, self._encoding_mood))
            enc_match = max(0.0, min(1.0, enc_dot))
            mood_boost += enc_match * STATE_DEPENDENT_BOOST

        return base * mood_boost

    # ── Temporal gist extraction ──────────────────────────────────────
    @property
    def gist(self) -> str:
        """Return the memory's content, or a compressed gist if old."""
        if self._is_flashbulb:
            return self.content
        age_days = (
            datetime.now() - datetime.fromisoformat(self.timestamp)
        ).total_seconds() / 86400
        if age_days < GIST_AGE_THRESHOLD_DAYS:
            return self.content
        words = self.content.split()
        if len(words) <= GIST_PRESERVE_WORDS:
            return self.content
        preserved = " ".join(words[:GIST_PRESERVE_WORDS])
        return f"[faded memory — {self.emotion}] {preserved}…"

    # ── Helpers ───────────────────────────────────────────────────────
    @property
    def content_words(self) -> set[str]:
        return _content_words(self.content)

    # ── Visual memory properties (Kosslyn 1980) ──────────────────────
    @property
    def has_visual(self) -> bool:
        return bool(self._visual_hash)

    @property
    def can_show(self) -> bool:
        return self.has_visual and self.vividness >= VISUAL_GIST_THRESHOLD

    @property
    def drift_magnitude(self) -> float:
        orig_pad = _emotion_to_vector(self.original_emotion)
        if orig_pad is None:
            return 0.0
        curr_pad = self._emotion_pad or orig_pad
        return math.sqrt(sum(
            (a - b) ** 2 for a, b in zip(orig_pad, curr_pad)))

    @property
    def has_drifted(self) -> bool:
        return self.drift_magnitude >= DRIFT_ALERT_THRESHOLD

    @property
    def visual_clarity(self) -> str:
        if not self.has_visual:
            return "none"
        v = self.vividness
        if v >= VISUAL_VIVID_THRESHOLD:
            return "vivid"
        elif v >= VISUAL_GIST_THRESHOLD:
            return "faded"
        return "gist_only"

    # ── Serialization ─────────────────────────────────────────────────
    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "content":       self.content,
            "emotion":       self.emotion,
            "importance":    self.importance,
            "timestamp":     self.timestamp,
            "source":        self.source,
            "entity":        self.entity,
            "access_count":  self._access_count,
            "last_access":   self._last_access,
            "stability":     self._stability,
            "why_saved":     self.why_saved,
            "original_emotion": self.original_emotion,
            "encoding_mood": list(self._encoding_mood),
            "is_flashbulb":  self._is_flashbulb,
            "emotion_pad":   list(self._emotion_pad) if self._emotion_pad else None,
        }
        if self._mentioned_dates:
            d["mentioned_dates"] = self._mentioned_dates
        if self._embed_uid:
            d["embed_uid"] = self._embed_uid
        if self._visual_hash:
            d["visual_hash"] = self._visual_hash
            d["visual_description"] = self._visual_description
            d["visual_dimensions"] = list(self._visual_dimensions)
        if self._anchor:
            d["anchor"] = True
            d["rescore_survived"] = self._rescore_survived
        if self._cherished:
            d["cherished"] = True
        if self._reframed:
            d["reframed"] = True
            d["reframe_reason"] = self._reframe_reason
        if self._privacy != "public":
            d["privacy"] = self._privacy
        regret = self._regret
        if regret > 0:
            d["regret"] = round(regret, 3)
            d["believed_importance"] = self._believed_importance
        if self._novelty_score != 0.5:
            d["novelty_score"] = round(self._novelty_score, 3)
        if self._drift_history:
            d["drift_history"] = self._drift_history
        if self._arc_position:
            d["arc_position"] = self._arc_position
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Memory":
        obj = cls.__new__(cls)
        obj.content       = d.get("content", "")
        obj.emotion       = d.get("emotion", "neutral")
        obj.importance    = max(1, min(10, d.get("importance", 5)))
        obj.timestamp     = d.get("timestamp", datetime.now().isoformat())
        obj.source        = d.get("source", "reflection")
        obj.entity        = d.get("entity", "")
        obj._access_count = d.get("access_count", 0)
        obj._last_access  = d.get("last_access", obj.timestamp)
        obj._stability    = d.get("stability", INITIAL_STABILITY)
        obj.why_saved     = d.get("why_saved", "")
        # Neuroscience
        obj.original_emotion = d.get("original_emotion", obj.emotion)
        enc = d.get("encoding_mood", [0.0, 0.0, 0.0])
        obj._encoding_mood = tuple(enc) if isinstance(enc, list) else enc
        obj._is_flashbulb  = d.get("is_flashbulb", False)
        epad = d.get("emotion_pad")
        obj._emotion_pad = tuple(epad) if epad else None
        # Temporal
        obj._mentioned_dates = d.get("mentioned_dates", [])
        # VividEmbed sync
        obj._embed_uid = d.get("embed_uid", "")
        # Visual memory
        obj._visual_hash = d.get("visual_hash", "")
        obj._visual_description = d.get("visual_description", "")
        vdim = d.get("visual_dimensions", [0, 0])
        obj._visual_dimensions = tuple(vdim) if isinstance(vdim, list) else vdim
        # VividnessMem compat
        obj._anchor            = d.get("anchor", False)
        obj._rescore_survived  = d.get("rescore_survived", 0)
        obj._cherished         = d.get("cherished", False)
        obj._reframed          = d.get("reframed", False)
        obj._reframe_reason    = d.get("reframe_reason", "")
        obj._privacy           = d.get("privacy", "public")
        obj._regret            = d.get("regret", 0.0)
        obj._believed_importance = d.get("believed_importance", 0)
        obj._novelty_score     = d.get("novelty_score", 0.5)
        obj._drift_history     = d.get("drift_history", [])
        obj._arc_position      = d.get("arc_position", "")
        return obj


# ═══════════════════════════════════════════════════════════════════════════
#  Lesson — procedural memory with Zeigarnik effect
# ═══════════════════════════════════════════════════════════════════════════

class Lesson:
    """A learned procedure or skill."""

    __slots__ = (
        "id", "topic", "context_trigger", "strategy",
        "created", "importance", "_stability",
        "attempts", "consecutive_failures", "total_attempts",
        "last_attempt",
        "_source_memory_idx",
    )

    def __init__(self, topic: str, context_trigger: str = "",
                 strategy: str = "", importance: int = 5):
        self.id = str(uuid.uuid4())
        self.topic = topic
        self.context_trigger = context_trigger
        self.strategy = strategy
        self.created = datetime.now().isoformat()
        self.importance = importance
        self._stability: float = 30.0
        self.attempts: list[Attempt] = []
        self.consecutive_failures: int = 0
        self.total_attempts: int = 0
        self.last_attempt: str | None = None
        self._source_memory_idx: int = -1

    @property
    def vividness(self) -> float:
        age_days = (
            datetime.now() - datetime.fromisoformat(self.created)
        ).total_seconds() / 86400
        retention = math.exp(-age_days / max(self._stability, 0.1))
        base = self.importance * retention
        if self.consecutive_failures > 0:
            base *= (1.0 + ZEIGARNIK_BOOST)
        return base

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "context_trigger": self.context_trigger,
            "strategy": self.strategy,
            "created": self.created,
            "importance": self.importance,
            "stability": self._stability,
            "consecutive_failures": self.consecutive_failures,
            "total_attempts": self.total_attempts,
            "last_attempt": self.last_attempt,
            "attempts": [a.to_dict() for a in self.attempts],
            "source_memory_idx": self._source_memory_idx,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Lesson":
        obj = cls.__new__(cls)
        obj.id = d.get("id", str(uuid.uuid4()))
        obj.topic = d.get("topic", "")
        obj.context_trigger = d.get("context_trigger", "")
        obj.strategy = d.get("strategy", "")
        obj.created = d.get("created", datetime.now().isoformat())
        obj.importance = d.get("importance", 5)
        obj._stability = d.get("stability", 30.0)
        obj.consecutive_failures = d.get("consecutive_failures", 0)
        obj.total_attempts = d.get("total_attempts", 0)
        obj.last_attempt = d.get("last_attempt")
        obj.attempts = [
            Attempt.from_dict(a) for a in d.get("attempts", [])
        ]
        obj._source_memory_idx = d.get("source_memory_idx", -1)
        return obj


# ═══════════════════════════════════════════════════════════════════════════
#  Attempt — outcome of a lesson application
# ═══════════════════════════════════════════════════════════════════════════

class Attempt:
    __slots__ = ("action", "result", "diagnosis", "timestamp")

    def __init__(self, action: str, result: str, diagnosis: str = ""):
        self.action = action
        self.result = result
        self.diagnosis = diagnosis
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "result": self.result,
            "diagnosis": self.diagnosis,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Attempt":
        obj = cls.__new__(cls)
        obj.action = d.get("action", "")
        obj.result = d.get("result", "")
        obj.diagnosis = d.get("diagnosis", "")
        obj.timestamp = d.get("timestamp", datetime.now().isoformat())
        return obj


# ═══════════════════════════════════════════════════════════════════════════
#  Reminder — time-triggered notification
# ═══════════════════════════════════════════════════════════════════════════

class Reminder:
    __slots__ = ("text", "trigger_at", "created", "fired")

    def __init__(self, text: str, trigger_at: str):
        self.text = text
        self.trigger_at = trigger_at
        self.created = datetime.now().isoformat()
        self.fired = False

    @property
    def is_due(self) -> bool:
        return (not self.fired
                and datetime.now() >= datetime.fromisoformat(self.trigger_at))

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "trigger_at": self.trigger_at,
            "created": self.created,
            "fired": self.fired,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Reminder":
        obj = cls.__new__(cls)
        obj.text = d.get("text", "")
        obj.trigger_at = d.get("trigger_at", datetime.now().isoformat())
        obj.created = d.get("created", datetime.now().isoformat())
        obj.fired = d.get("fired", False)
        return obj


# ═══════════════════════════════════════════════════════════════════════════
#  ShortTermFact — volatile factual memory with aggressive decay
# ═══════════════════════════════════════════════════════════════════════════

class ShortTermFact:
    """A volatile fact (e.g. 'Scott's monitor is 27 inches')."""

    __slots__ = ("entity", "attribute", "value", "timestamp")

    _HALF_LIFE_HOURS = 12.0

    def __init__(self, entity: str, attribute: str, value: str):
        self.entity = entity
        self.attribute = attribute
        self.value = value
        self.timestamp = datetime.now().isoformat()

    @property
    def vividness(self) -> float:
        age_hours = (
            datetime.now() - datetime.fromisoformat(self.timestamp)
        ).total_seconds() / 3600
        return math.exp(-0.693 * age_hours / self._HALF_LIFE_HOURS)

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "attribute": self.attribute,
            "value": self.value,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ShortTermFact":
        obj = cls.__new__(cls)
        obj.entity = d.get("entity", "")
        obj.attribute = d.get("attribute", "")
        obj.value = d.get("value", "")
        obj.timestamp = d.get("timestamp", datetime.now().isoformat())
        return obj


# ═══════════════════════════════════════════════════════════════════════════
#  NullChemistry — no-op fallback when VividnessMem is not installed
# ═══════════════════════════════════════════════════════════════════════════

class _NullChemistry:
    """Minimal no-op chemistry for standalone operation."""
    enabled = False
    _dampening_active = False
    _dampening_turns_left = 0

    def tick(self, dt_minutes: float | None = None): pass
    def on_emotion(self, emotion: str, intensity: float = 0.7): pass
    def on_event(self, event_type: str, intensity: float = 0.7): pass
    def cognitive_override(self, emotion: str, intensity: float = 0.7): pass
    def request_dampening(self, turns: int = 5, intensity: float = 0.3): pass
    def end_dampening(self): pass
    def tick_dampening(self): pass
    def sleep_reset(self, hours: float = 8.0): pass
    def describe(self) -> str: return "(chemistry not installed)"
    def to_dict(self) -> dict: return {}
    @classmethod
    def from_dict(cls, d: dict) -> "_NullChemistry": return cls()
    @property
    def is_dampened(self) -> bool: return False
    @property
    def levels(self) -> dict:
        return {"dopamine": 0.5, "cortisol": 0.3, "serotonin": 0.6,
                "oxytocin": 0.4, "norepinephrine": 0.5}
    @property
    def baselines(self) -> dict:
        return {"dopamine": 0.5, "cortisol": 0.3, "serotonin": 0.6,
                "oxytocin": 0.4, "norepinephrine": 0.5}

    def get_modifiers(self) -> dict:
        return {
            "encoding_boost": 1.0, "attention_width": 1.0,
            "mood_decay_mult": 1.0, "mood_influence_mult": 1.0,
            "social_boost": 1.0, "warmth_nudge_mult": 1.0,
            "consolidation_bonus": 1.0, "flashbulb": False,
            "yerkes_dodson": 1.0,
        }


# ═══════════════════════════════════════════════════════════════════════════
#  NullAuditLog — no-op fallback when VividnessMem is not installed
# ═══════════════════════════════════════════════════════════════════════════

class _NullAuditLog:
    """Minimal no-op audit log for standalone operation."""
    def log(self, event_type: str, emotion: str = "",
            source: str = "", details: dict | None = None): pass
    def get_recent(self, n: int = 20) -> list[dict]: return []
    def query_by_type(self, event_type: str, n: int = 10) -> list[dict]: return []
    def describe_recent(self, n: int = 5) -> str: return ""
    def load_recent_from_disk(self, n: int = 50): pass


# ═══════════════════════════════════════════════════════════════════════════
#  Task / Project branch — project management with organic memory properties
# ═══════════════════════════════════════════════════════════════════════════

class TaskRecord:
    """A single task within a project."""
    __slots__ = ("task_id", "description", "status", "priority",
                 "created_at", "completed_at", "outcome",
                 "parent_id", "project", "tags",
                 "_memory_indices")

    def __init__(self, description: str, project: str = "",
                 priority: int = 5, parent_id: str = "",
                 tags: list[str] | None = None):
        self.task_id = uuid.uuid4().hex[:12]
        self.description = description
        self.status = "active"
        self.priority = max(1, min(10, priority))
        self.created_at = datetime.now().isoformat()
        self.completed_at = ""
        self.outcome = ""
        self.parent_id = parent_id
        self.project = project
        self.tags = tags or []
        self._memory_indices: list[int] = []

    def complete(self, outcome: str = ""):
        self.status = "completed"
        self.completed_at = datetime.now().isoformat()
        self.outcome = outcome

    def fail(self, reason: str = ""):
        self.status = "failed"
        self.completed_at = datetime.now().isoformat()
        self.outcome = reason

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__slots__}
        d["memory_indices"] = d.pop("_memory_indices", [])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TaskRecord":
        obj = cls.__new__(cls)
        for k in cls.__slots__:
            if k == "_memory_indices":
                continue
            setattr(obj, k, d.get(k, "" if k != "tags" else []))
        obj.priority = max(1, min(10, int(obj.priority or 5)))
        obj._memory_indices = d.get("memory_indices", [])
        return obj


class ActionRecord:
    """A single action taken on a task."""
    __slots__ = ("task_id", "action", "result", "error",
                 "fix", "timestamp", "importance")

    def __init__(self, task_id: str, action: str, result: str = "success",
                 error: str = "", fix: str = "", importance: int = 5):
        self.task_id = task_id
        self.action = action
        self.result = result
        self.error = error
        self.fix = fix
        self.timestamp = datetime.now().isoformat()
        self.importance = max(1, min(10, importance))

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}

    @classmethod
    def from_dict(cls, d: dict) -> "ActionRecord":
        obj = cls.__new__(cls)
        for k in cls.__slots__:
            setattr(obj, k, d.get(k, ""))
        obj.importance = max(1, min(10, int(obj.importance or 5)))
        return obj


class SolutionPattern:
    """A reusable problem→solution pattern with spaced-repetition decay."""
    __slots__ = ("problem_signature", "failed_approaches", "solution",
                 "context_tags", "times_applied", "importance",
                 "timestamp", "_stability")

    def __init__(self, problem: str, solution: str,
                 failed_approaches: list[str] | None = None,
                 tags: list[str] | None = None,
                 importance: int = SOLUTION_INITIAL_IMPORTANCE):
        self.problem_signature = problem
        self.solution = solution
        self.failed_approaches = failed_approaches or []
        self.context_tags = tags or []
        self.times_applied = 0
        self.importance = max(1, min(10, importance))
        self.timestamp = datetime.now().isoformat()
        self._stability = 30.0

    def apply(self):
        self.times_applied += 1
        self.importance = min(10, self.importance
                              + min(3, round(SOLUTION_REUSE_BOOST
                                             * self.times_applied)))
        self._stability = min(STABILITY_CAP, self._stability * 1.5)

    @property
    def vividness(self) -> float:
        age = (datetime.now()
               - datetime.fromisoformat(self.timestamp)).total_seconds() / 86400
        return self.importance * math.exp(-age / max(self._stability, 0.1))

    @property
    def search_text(self) -> str:
        return " ".join([self.problem_signature, self.solution]
                        + self.failed_approaches + self.context_tags)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}

    @classmethod
    def from_dict(cls, d: dict) -> "SolutionPattern":
        obj = cls.__new__(cls)
        for k in cls.__slots__:
            default = [] if k in ("failed_approaches", "context_tags") else ""
            setattr(obj, k, d.get(k, default))
        obj.importance = max(1, min(10, int(obj.importance or 8)))
        obj._stability = float(obj._stability or 30.0)
        obj.times_applied = int(obj.times_applied or 0)
        return obj


class ArtifactRecord:
    """A tracked artifact within a project."""
    __slots__ = ("name", "artifact_type", "description", "importance",
                 "dependencies", "current_state", "last_updated")

    def __init__(self, name: str, artifact_type: str = "file",
                 description: str = "", importance: int = 5,
                 dependencies: list[str] | None = None):
        self.name = name
        self.artifact_type = artifact_type
        self.description = description
        self.importance = max(1, min(10, importance))
        self.dependencies = dependencies or []
        self.current_state = "active"
        self.last_updated = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}

    @classmethod
    def from_dict(cls, d: dict) -> "ArtifactRecord":
        obj = cls.__new__(cls)
        for k in cls.__slots__:
            default = [] if k == "dependencies" else ""
            setattr(obj, k, d.get(k, default))
        obj.importance = max(1, min(10, int(obj.importance or 5)))
        return obj
