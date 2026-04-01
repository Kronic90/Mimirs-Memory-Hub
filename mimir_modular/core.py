"""Mimir core — composes all mixins into the final Mimir class."""

from __future__ import annotations

import base64
import hashlib
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .constants import (
    _NeuroChemistry, _EmotionalAuditLog, _VividEmbed, _PIL_Image,
    _Fernet, _PBKDF2, _crypto_hashes,
    STABILITY_CAP, LLMCallable,
)
from .helpers import (
    _emotion_to_vector, _closest_emotion,
    _resonance_words, _extract_dates,
)
from .models import (
    Memory, Lesson, Attempt, Reminder, ShortTermFact,
    _NullChemistry, _NullAuditLog,
    TaskRecord, ActionRecord, SolutionPattern, ArtifactRecord,
)

from .neuroscience_mixin import NeuroscienceMixin
from .yggdrasil_mixin import YggdrasilMixin
from .recall_mixin import RecallMixin
from .write_mixin import WriteMixin
from .tasks_mixin import TasksMixin
from .llm_mixin import LLMMixin
from .persistence_mixin import PersistenceMixin


class Mimir(
    NeuroscienceMixin,
    YggdrasilMixin,
    RecallMixin,
    WriteMixin,
    TasksMixin,
    LLMMixin,
    PersistenceMixin,
):
    """The Ultimate Memory Architecture — modular edition.

    Orchestrates VividnessMem's neurochemistry engine and VividEmbed's
    semantic retrieval layer, then adds twenty-one neuroscience mechanisms.

    This class composes all functionality via mixins:
    - NeuroscienceMixin  — Huginn, Muninn, Völva, drift, gist, chunking
    - YggdrasilMixin     — World Tree memory graph
    - RecallMixin        — hybrid retrieval, resonance, temporal recall
    - WriteMixin         — remember, visual memory, mood, social, cherish
    - TasksMixin         — project/task/solution/artifact management
    - LLMMixin           — query decomposition, agentic ops, reflection
    - PersistenceMixin   — save/load, encryption, migration
    """

    ACTIVE_SELF_LIMIT = 10
    RESONANCE_LIMIT   = 5
    RECALL_LIMIT      = 10

    def __init__(self, data_dir: str | Path = "mimir_data",
                 embed_model: str | None = None,
                 chemistry: bool = True,
                 visual: bool = True,
                 encryption_key: str | None = None,
                 llm_fn: LLMCallable | None = None):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # ── Encryption at rest ────────────────────────────────────────
        self._fernet = None
        if encryption_key and _Fernet is not None and _PBKDF2 is not None:
            salt = hashlib.sha256(
                str(data_dir).encode()).digest()[:16]
            kdf = _PBKDF2(
                algorithm=_crypto_hashes.SHA256(), length=32,
                salt=salt, iterations=600_000)
            key = base64.urlsafe_b64encode(
                kdf.derive(encryption_key.encode()))
            self._fernet = _Fernet(key)

        # ── Optional LLM integration ─────────────────────────────────
        self._llm_fn: LLMCallable | None = llm_fn

        # ── Core state ────────────────────────────────────────────────
        self._reflections: list[Memory] = []
        self._social: dict[str, list[Memory]] = {}
        self._lessons: list[Lesson] = []
        self._reminders: list[Reminder] = []
        self._facts: list[ShortTermFact] = []
        self._mood: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._priming_buffer: dict[str, float] = {}

        # ── Task / Project branch ─────────────────────────────────────
        self._active_project: str = ""
        self._project_tasks: list[TaskRecord] = []
        self._project_actions: list[ActionRecord] = []
        self._solutions: list[SolutionPattern] = []
        self._artifacts: list[ArtifactRecord] = []

        # ── LLM-inferred relational edges ─────────────────────────────
        self._inferred_edges: dict[tuple[int, int], float] = {}

        # ── Visual memory (Kosslyn 1980) ──────────────────────────────
        self._visual_enabled = visual and _PIL_Image is not None
        self._visual_dir = self._data_dir / "visual"
        if self._visual_enabled:
            self._visual_dir.mkdir(parents=True, exist_ok=True)

        # ── Word index for fast lexical retrieval ─────────────────────
        self._word_index: dict[str, set[int]] = {}

        # ── Date index for temporal retrieval (Tulving 1972) ──────────
        self._date_index: dict[str, set[int]] = {}

        # ── Session tracking ──────────────────────────────────────────
        self._session_count: int = 0

        # ── Auto-consolidation counter ────────────────────────────────
        self._memories_since_consolidation: int = 0

        # ── Yggdrasil — memory graph (World Tree) ────────────────────
        self._yggdrasil: dict[int, list[tuple[int, str, float]]] = {}

        # ── Chemistry engine (VividnessMem) ───────────────────────────
        if chemistry and _NeuroChemistry is not None:
            self._chemistry = _NeuroChemistry(enabled=True)
        else:
            self._chemistry = _NullChemistry()

        # ── Emotional audit log (VividnessMem) ────────────────────────
        if _EmotionalAuditLog is not None:
            self._audit = _EmotionalAuditLog(self._data_dir)
            self._audit.load_recent_from_disk()
        else:
            self._audit = _NullAuditLog()

        # ── Embedding engine (VividEmbed) ─────────────────────────────
        self._embed = None
        if _VividEmbed is not None:
            try:
                embed_dir = str(self._data_dir / "embed")
                if embed_model:
                    self._embed = _VividEmbed(
                        persist_dir=embed_dir, model_name=embed_model)
                else:
                    self._embed = _VividEmbed(persist_dir=embed_dir)
            except Exception:
                self._embed = None

        # ── Load persisted data ───────────────────────────────────────
        self._load()

    # ──────────────────────────────────────────────────────────────────
    #  Properties
    # ──────────────────────────────────────────────────────────────────

    @property
    def self_reflections(self) -> list[Memory]:
        return self._reflections

    @property
    def social_impressions(self) -> dict[str, list[Memory]]:
        return self._social

    @property
    def mood(self) -> tuple[float, float, float]:
        return self._mood

    @property
    def mood_label(self) -> str:
        return _closest_emotion(self._mood)

    @property
    def chemistry(self):
        return self._chemistry

    @property
    def session_count(self) -> int:
        return self._session_count

    def bump_session(self) -> int:
        """Increment session counter.  Returns the new count."""
        self._session_count += 1
        return self._session_count

    @property
    def visual_enabled(self) -> bool:
        return self._visual_enabled

    # ──────────────────────────────────────────────────────────────────
    #  Sleep / reset
    # ──────────────────────────────────────────────────────────────────

    def sleep_reset(self, hours: float = 8.0):
        """Between-session neurochemistry reset + god-tier consolidation."""
        self._chemistry.sleep_reset(hours)
        self._audit.log("sleep_reset", details={"hours": hours})

        muninn_stats = self.muninn()
        gist_count = self._compress_to_gist()
        chunk_count = self.chunk_memories()
        huginn_insights = self.huginn()
        volva_insights = self.volva_dream()

        self._build_yggdrasil()
        self._memories_since_consolidation = 0

    # ──────────────────────────────────────────────────────────────────
    #  Emotional pipeline — full NeuroChemistry integration
    # ──────────────────────────────────────────────────────────────────

    def on_event(self, event_type: str, intensity: float = 0.7):
        """Signal a life event to the neurochemistry engine."""
        self._chemistry.on_event(event_type, intensity)
        self._audit.log("event", source=event_type,
                        details={"intensity": intensity})

    def request_dampening(self, turns: int = 5, intensity: float = 0.3):
        """Activate emotional dampening (protective self-regulation)."""
        self._chemistry.request_dampening(turns, intensity)
        self._audit.log("dampening_activated",
                        details={"turns": turns, "intensity": intensity})

    def end_dampening(self):
        """Manually end emotional dampening early."""
        self._chemistry.end_dampening()
        self._audit.log("dampening_ended")

    def tick_dampening(self):
        """Advance dampening by one conversation turn."""
        self._chemistry.tick_dampening()

    def cognitive_override(self, emotion: str, intensity: float = 0.7):
        """Apply a deliberate cognitive reappraisal."""
        self._chemistry.cognitive_override(emotion, intensity)
        self._audit.log("cognitive_override", emotion=emotion,
                        details={"intensity": intensity})

    @property
    def is_dampened(self) -> bool:
        """Whether emotional dampening is currently active."""
        return getattr(self._chemistry, 'is_dampened', False)

    @property
    def audit_log(self):
        """Direct access to the emotional audit log."""
        return self._audit

    # ──────────────────────────────────────────────────────────────────
    #  Lessons (procedural memory)
    # ──────────────────────────────────────────────────────────────────

    def add_lesson(self, topic: str, context_trigger: str = "",
                   strategy: str = "", importance: int = 5,
                   source_memory_idx: int = -1) -> Lesson:
        """Record a learned procedure or skill."""
        lesson = Lesson(topic, context_trigger, strategy, importance)
        lesson._source_memory_idx = source_memory_idx
        self._lessons.append(lesson)
        return lesson

    def record_outcome(self, lesson_id: str, action: str, result: str,
                       diagnosis: str = ""):
        """Log the outcome of applying a lesson."""
        lesson = next(
            (l for l in self._lessons if l.id == lesson_id), None)
        if not lesson:
            return
        attempt = Attempt(action, result, diagnosis)
        lesson.attempts.append(attempt)
        lesson.total_attempts += 1
        lesson.last_attempt = datetime.now().isoformat()
        if result == "failure":
            lesson.consecutive_failures += 1
        else:
            lesson.consecutive_failures = 0
            idx = lesson._source_memory_idx
            if 0 <= idx < len(self._reflections):
                mem = self._reflections[idx]
                mem._stability = min(
                    STABILITY_CAP, mem._stability * 1.15)

    def get_active_lessons(self) -> list[Lesson]:
        """Return lessons sorted by vividness (Zeigarnik-boosted)."""
        return sorted(
            self._lessons, key=lambda l: l.vividness, reverse=True)

    @property
    def lessons(self) -> list[Lesson]:
        """Public accessor for the lessons list."""
        return self._lessons

    def retrieve_lessons(self, query: str,
                         limit: int = 10) -> list[tuple[Lesson, float]]:
        """BM25-lite keyword search over lessons."""
        if not self._lessons:
            return []

        q_tokens = set(query.lower().split())
        if not q_tokens:
            return []

        scored: list[tuple[Lesson, float]] = []
        for lesson in self._lessons:
            text = (f"{lesson.topic} {lesson.context_trigger} "
                    f"{lesson.strategy}").lower()
            doc_tokens = set(text.split())
            if not doc_tokens:
                continue
            overlap = q_tokens & doc_tokens
            if not overlap:
                continue
            tf = len(overlap) / len(q_tokens)
            score = tf * (0.5 + 0.5 * min(lesson.vividness / 10.0, 1.0))
            scored.append((lesson, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    # ──────────────────────────────────────────────────────────────────
    #  Reminders
    # ──────────────────────────────────────────────────────────────────

    def set_reminder(self, text: str, hours: float = 1.0) -> Reminder:
        """Create a time-triggered reminder."""
        trigger = datetime.now() + timedelta(hours=hours)
        reminder = Reminder(text, trigger.isoformat())
        self._reminders.append(reminder)
        return reminder

    def get_due_reminders(self) -> list[Reminder]:
        """Return all reminders that have triggered but not yet fired."""
        due = [r for r in self._reminders if r.is_due]
        for r in due:
            r.fired = True
        return due

    # ──────────────────────────────────────────────────────────────────
    #  Short-term facts
    # ──────────────────────────────────────────────────────────────────

    def add_fact(self, entity: str, attribute: str,
                 value: str) -> ShortTermFact:
        """Store a volatile fact (aggressive 12h decay)."""
        for i, f in enumerate(self._facts):
            if f.entity == entity and f.attribute == attribute:
                self._facts[i] = ShortTermFact(entity, attribute, value)
                return self._facts[i]
        fact = ShortTermFact(entity, attribute, value)
        self._facts.append(fact)
        return fact

    def get_facts(self, entity: str = "") -> list[ShortTermFact]:
        """Return still-vivid facts, optionally filtered by entity."""
        alive = [f for f in self._facts if f.vividness > 0.1]
        if entity:
            alive = [f for f in alive if f.entity == entity]
        return alive

    # ──────────────────────────────────────────────────────────────────
    #  Context block
    # ──────────────────────────────────────────────────────────────────

    def get_context_block(self, current_entity: str = "",
                          conversation_context: str = "") -> str:
        """Build a full memory context block for injection into a prompt."""
        lines: list[str] = []

        label = self.mood_label
        if label != "neutral":
            lines.append(f"(Feeling: {label})")
            lines.append("")

        active = self.get_active_self(context=conversation_context)
        fg_count = max(3, len(active) // 2)
        foreground = active[:fg_count]
        background = active[fg_count:]

        if foreground:
            lines.append("=== THINGS ON MY MIND ===")
            for m in foreground:
                lines.append(
                    f"— {m.gist} ({m.emotion})")
            lines.append("")

        if background:
            lines.append("=== BACKGROUND KNOWLEDGE ===")
            for m in background:
                content = m.gist
                if len(content) > 80:
                    cut = content[:80].rfind(" ")
                    content = content[:max(cut, 30)] + "…"
                lines.append(f"· {content} [{m.emotion}]")
            lines.append("")

        if current_entity:
            impressions = self._social.get(current_entity, [])
            if impressions:
                vivid = sorted(
                    impressions,
                    key=lambda m: m.mood_adjusted_vividness(self._mood),
                    reverse=True)[:5]
                lines.append(
                    f"=== MY IMPRESSIONS OF "
                    f"{current_entity.upper()} ===")
                for m in vivid:
                    lines.append(
                        f"— {m.content} ({m.emotion})")
                lines.append("")

        active_lessons = self.get_active_lessons()[:3]
        if active_lessons:
            lines.append("=== THINGS I'M LEARNING ===")
            for l in active_lessons:
                status = (
                    f"[{l.consecutive_failures} failures]"
                    if l.consecutive_failures > 0 else "[OK]")
                lines.append(
                    f"— {l.topic}: {l.strategy} {status}")
            lines.append("")

        due = self.get_due_reminders()
        if due:
            lines.append("=== REMINDERS (just triggered) ===")
            for r in due:
                lines.append(f"— {r.text}")
            lines.append("")

        temporal = self.get_temporal_context()
        if temporal["today"]:
            lines.append("=== HAPPENING TODAY ===")
            seen: set[int] = set()
            for ds, mem in temporal["today"]:
                mid = id(mem)
                if mid not in seen:
                    seen.add(mid)
                    lines.append(f"— {mem.gist} ({mem.emotion})")
            lines.append("")
        if temporal["upcoming"]:
            lines.append("=== COMING UP ===")
            seen = set()
            for ds, mem in temporal["upcoming"]:
                mid = id(mem)
                if mid not in seen:
                    seen.add(mid)
                    try:
                        d = datetime.fromisoformat(ds).date()
                        delta = (d - datetime.now().date()).days
                        when = (f"in {delta} day{'s' if delta != 1 else ''}"
                                if delta > 0 else "soon")
                    except ValueError:
                        when = "soon"
                    lines.append(f"— {mem.gist} [{when}] ({mem.emotion})")
            lines.append("")
        if temporal["recent"]:
            lines.append("=== JUST HAPPENED ===")
            seen = set()
            for ds, mem in temporal["recent"]:
                mid = id(mem)
                if mid not in seen:
                    seen.add(mid)
                    try:
                        d = datetime.fromisoformat(ds).date()
                        delta = (datetime.now().date() - d).days
                        when = (f"{delta} day{'s' if delta != 1 else ''} ago"
                                if delta > 0 else "recently")
                    except ValueError:
                        when = "recently"
                    lines.append(f"— {mem.gist} [{when}] ({mem.emotion})")
            lines.append("")

        visual_mems = [m for m in self._reflections
                       if m.has_visual and m.can_show]
        if visual_mems:
            vivid_vis = sorted(
                visual_mems,
                key=lambda m: m.mood_adjusted_vividness(self._mood),
                reverse=True)[:5]
            lines.append("=== IMAGES I REMEMBER ===")
            for m in vivid_vis:
                clarity = m.visual_clarity
                tag = "[vivid]" if clarity == "vivid" else "[fading]"
                lines.append(
                    f"— {m._visual_description} {tag} ({m.emotion})")
            lines.append("")

        drifted = [m for m in self._reflections if m.has_drifted]
        if drifted:
            top_drifted = sorted(
                drifted, key=lambda m: m.drift_magnitude,
                reverse=True)[:3]
            lines.append("=== DRIFT MONITOR ===")
            for m in top_drifted:
                lines.append(
                    f"— '{m.gist[:50]}' was {m.original_emotion} "
                    f"-> now {m.emotion} "
                    f"(drift: {m.drift_magnitude:.2f})")
            lines.append("")

        if conversation_context:
            resonant = self.resonate(conversation_context)
            if resonant:
                lines.append(
                    "=== SOMETHING THIS REMINDS ME OF ===")
                for m in resonant[:3]:
                    lines.append(
                        f"— {m.gist} ({m.emotion})")
                lines.append("")

        if self._chemistry.enabled:
            lines.append(f"=== NEUROCHEMISTRY ===")
            lines.append(self._chemistry.describe())
            if self.is_dampened:
                lines.append("  [shield] Emotional dampening active")
            lines.append("")

        audit_summary = self._audit.describe_recent(5)
        if audit_summary:
            lines.append("=== EMOTIONAL AUDIT ===")
            lines.append(audit_summary)
            lines.append("")

        insight_mems = [
            m for m in self._reflections
            if m.source in ("huginn", "volva") and m.vividness > 0.3]
        if insight_mems:
            recent_insights = sorted(
                insight_mems, key=lambda m: m.timestamp,
                reverse=True)[:3]
            lines.append("=== INSIGHTS (Huginn & Völva) ===")
            for m in recent_insights:
                tag = "thought" if m.source == "huginn" else "dream"
                lines.append(f"— [{tag}] {m.gist}")
            lines.append("")

        return "\n".join(lines) if lines else ""

    # ──────────────────────────────────────────────────────────────────
    #  Visualization
    # ──────────────────────────────────────────────────────────────────

    def memory_timeline(self) -> list[dict]:
        """Build a timeline of memories for visualization."""
        return [
            {
                "timestamp": m.timestamp,
                "importance": m.importance,
                "emotion": m.emotion,
                "vividness": round(m.vividness, 3),
                "is_flashbulb": m._is_flashbulb,
                "is_cherished": m._cherished,
                "arc_position": m._arc_position,
                "gist": m.gist,
            }
            for m in sorted(self._reflections, key=lambda m: m.timestamp)
        ]

    def emotion_distribution(self) -> dict[str, int]:
        """Count memories by emotion for visualization."""
        dist: dict[str, int] = {}
        for m in self._reflections:
            dist[m.emotion] = dist.get(m.emotion, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def importance_histogram(self) -> dict[int, int]:
        """Distribution of memories by importance level (1-10)."""
        hist: dict[int, int] = {i: 0 for i in range(1, 11)}
        for m in self._reflections:
            level = max(1, min(10, m.importance))
            hist[level] += 1
        return hist

    def arc_distribution(self) -> dict[str, int]:
        """Distribution of memories across narrative arc positions."""
        dist: dict[str, int] = {}
        for m in self._reflections:
            pos = m._arc_position or "unclassified"
            dist[pos] = dist.get(pos, 0) + 1
        return dist

    def drift_report(self) -> list[dict]:
        """Memories that have emotionally drifted, with magnitude."""
        return [
            {
                "gist": m.gist,
                "original_emotion": m._original_emotion,
                "current_emotion": m.emotion,
                "drift_magnitude": round(m.drift_magnitude, 3),
                "timestamp": m.timestamp,
            }
            for m in self._reflections
            if m.has_drifted
        ]

    def neurochemistry_snapshot(self) -> dict:
        """Current neurochemistry state for visualization."""
        if not self._chemistry.enabled:
            return {"enabled": False}
        try:
            return self._chemistry.to_dict()
        except Exception:
            return {"enabled": True, "error": "cannot serialize"}

    def yggdrasil_graph(self) -> dict[str, list[str]]:
        """Export the Yggdrasil graph as adjacency list for visualization."""
        graph: dict[str, list[str]] = {}
        n = len(self._reflections)
        for idx, neighbors in self._yggdrasil.items():
            if idx < n:
                key = self._reflections[idx].gist
                connected = [
                    self._reflections[j].gist
                    for j, _, _ in neighbors if j < n]
                graph[key] = connected
        return graph

    def viz_summary(self) -> dict:
        """All-in-one visualization payload."""
        return {
            "timeline": self.memory_timeline(),
            "emotions": self.emotion_distribution(),
            "importance": self.importance_histogram(),
            "arcs": self.arc_distribution(),
            "drift": self.drift_report(),
            "chemistry": self.neurochemistry_snapshot(),
            "yggdrasil_edges": sum(
                len(e) for e in self._yggdrasil.values()),
            "project": self.get_project_overview(),
        }

    # ──────────────────────────────────────────────────────────────────
    #  Stats
    # ──────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Summary of the memory system's state."""
        return {
            "total_reflections": len(self._reflections),
            "flashbulb_count": sum(
                1 for m in self._reflections if m._is_flashbulb),
            "anchor_count": sum(
                1 for m in self._reflections if m._anchor),
            "cherished_count": sum(
                1 for m in self._reflections if m._cherished),
            "embed_synced": sum(
                1 for m in self._reflections if m._embed_uid),
            "social_entities": list(self._social.keys()),
            "total_social": sum(
                len(v) for v in self._social.values()),
            "total_lessons": len(self._lessons),
            "unresolved_lessons": sum(
                1 for l in self._lessons
                if l.consecutive_failures > 0),
            "total_reminders": len(self._reminders),
            "pending_reminders": sum(
                1 for r in self._reminders if not r.fired),
            "priming_buffer_size": len(self._priming_buffer),
            "mood": self.mood_label,
            "chemistry_active": self._chemistry.enabled,
            "embed_active": self._embed is not None,
            "dampening_active": self.is_dampened,
            "audit_events": len(self._audit.get_recent(100)),
            "dated_memories": sum(
                1 for m in self._reflections if m._mentioned_dates),
            "unique_dates_indexed": len(self._date_index),
            "visual_memories": sum(
                1 for m in self._reflections if m.has_visual),
            "visual_enabled": self._visual_enabled,
            "huginn_insights": sum(
                1 for m in self._reflections if m.source == "huginn"),
            "volva_insights": sum(
                1 for m in self._reflections if m.source == "volva"),
            "yggdrasil_edges": sum(
                len(e) for e in self._yggdrasil.values()),
            "yggdrasil_roots": len(self.yggdrasil_roots()),
            "yggdrasil_inferred_edges": len(self._inferred_edges) // 2,
            "yggdrasil_edge_types": self._yggdrasil_edge_type_counts(),
            "drifted_memories": sum(
                1 for m in self._reflections if m.has_drifted),
            "max_drift": max(
                (m.drift_magnitude for m in self._reflections),
                default=0.0),
            "avg_novelty": round(
                sum(m._novelty_score for m in self._reflections)
                / max(len(self._reflections), 1), 3),
            "total_facts": len(self._facts),
            "live_facts": sum(1 for f in self._facts if f.vividness > 0.1),
            "active_project": self._active_project,
            "total_tasks": len(self._project_tasks),
            "active_tasks": sum(
                1 for t in self._project_tasks if t.status == "active"),
            "completed_tasks": sum(
                1 for t in self._project_tasks if t.status == "completed"),
            "total_actions": len(self._project_actions),
            "total_solutions": len(self._solutions),
            "total_artifacts": len(self._artifacts),
            "arc_positions": self.arc_distribution(),
            "gist_memories": sum(
                1 for m in self._reflections
                if m.content.startswith("[gist")),
            "chunk_memories": sum(
                1 for m in self._reflections if m.source == "chunk"),
            "memories_since_consolidation": self._memories_since_consolidation,
            "encryption_active": self._fernet is not None,
            "llm_active": self._llm_fn is not None,
        }

    # ──────────────────────────────────────────────────────────────────
    #  Internal: Yggdrasil edge type summary
    # ──────────────────────────────────────────────────────────────────

    def _yggdrasil_edge_type_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for edges in self._yggdrasil.values():
            for _, edge_type, _ in edges:
                counts[edge_type] = counts.get(edge_type, 0) + 1
        return counts

    # ──────────────────────────────────────────────────────────────────
    #  Internal: word index for fast retrieval
    # ──────────────────────────────────────────────────────────────────

    def _rebuild_index(self):
        self._word_index = {}
        self._date_index = {}
        for i, mem in enumerate(self._reflections):
            self._index_memory(i, mem)

    def _index_memory(self, idx: int, mem: Memory):
        for w in _resonance_words(f"{mem.content} {mem.emotion}"):
            if w not in self._word_index:
                self._word_index[w] = set()
            self._word_index[w].add(idx)
        for ds in mem._mentioned_dates:
            if ds not in self._date_index:
                self._date_index[ds] = set()
            self._date_index[ds].add(idx)

    def _candidate_indices(self, query_words: set[str]) -> set[int]:
        indices: set[int] = set()
        for w in query_words:
            indices |= self._word_index.get(w, set())
            if len(w) >= 5:
                prefix = w[:5]
                for iw, idxs in self._word_index.items():
                    if iw.startswith(prefix):
                        indices |= idxs
        return indices

    def _bm25_scores(self, query_words: set[str]) -> dict[int, float]:
        """BM25-style keyword scores using IDF weighting."""
        N = len(self._reflections)
        if N == 0 or not query_words:
            return {}

        scores: dict[int, float] = {}
        for word in query_words:
            matching = self._word_index.get(word, set())
            if not matching:
                if len(word) >= 5:
                    prefix = word[:5]
                    matching = set()
                    for iw, idxs in self._word_index.items():
                        if iw.startswith(prefix):
                            matching |= idxs
                if not matching:
                    continue

            df = len(matching)
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)

            for idx in matching:
                if idx < N:
                    scores[idx] = scores.get(idx, 0.0) + idf

        return scores
