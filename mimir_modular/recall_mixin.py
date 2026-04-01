"""Mimir recall mixin — hybrid retrieval, resonance, temporal navigation."""

from __future__ import annotations

import math
import random
from datetime import datetime

from .constants import (
    _W_KEYWORD, _W_SEMANTIC, _W_VIVIDNESS, _W_MOOD, _W_RECENCY,
    _RECENCY_HALF_LIFE_DAYS,
    PRIMING_BOOST, PRIMING_DECAY,
    SPREADING_ACTIVATION_THRESHOLD, SPREADING_ACTIVATION_MAX_DISCOVER,
    MOOD_GATE_DISTANCE, MOOD_GATE_KEEP_MIN,
    INTERFERENCE_THRESHOLD, INTERFERENCE_PENALTY, INITIAL_STABILITY,
    INVOLUNTARY_RECALL_PROB,
    TEMPORAL_PROXIMITY_BOOST, TEMPORAL_SALIENCE_BOOST,
    TEMPORAL_LOOKAHEAD_DAYS, TEMPORAL_LOOKBEHIND_DAYS,
    VISUAL_BOOST,
)
from .helpers import (
    _emotion_to_vector, _closest_emotion,
    _content_words, _resonance_words, _extract_dates,
)
from .models import Memory, ShortTermFact, Lesson


class RecallMixin:
    """Mixin providing hybrid retrieval, resonance, spreading-activation
    priming, temporal navigation, and related recall helpers."""

    # ──────────────────────────────────────────────────────────────────
    #  Internal: touch memory + sync VividEmbed
    # ──────────────────────────────────────────────────────────────────

    def _touch_memory(self, mem: Memory):
        """Touch a memory and propagate to VividEmbed if uid is set."""
        mem.touch(current_mood=self._mood)
        if self._embed is not None and mem._embed_uid:
            try:
                self._embed.touch(mem._embed_uid)
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────────
    #  Core: get_active_self + spreading activation
    # ──────────────────────────────────────────────────────────────────

    def get_active_self(self, context: str = "") -> list[Memory]:
        """Return the most vivid self-memories, mood-weighted."""
        self._chemistry.tick()

        mods = self._chemistry.get_modifiers()
        limit = max(3, round(
            self.ACTIVE_SELF_LIMIT * mods.get("attention_width", 1.0)))

        if context:
            ctx_words = _resonance_words(context)
            ctx_primed = {
                w for w in ctx_words if w in self._priming_buffer}

            def _score(mem: Memory) -> float:
                base = mem.mood_adjusted_vividness(self._mood)
                mem_words = _resonance_words(
                    f"{mem.content} {mem.emotion}")
                overlap = len(ctx_words & mem_words)
                relevance = 1.0 + min(
                    overlap / max(len(ctx_words), 1), 1.0)
                primed_hits = sum(
                    self._priming_buffer.get(w, 0.0)
                    for w in mem_words if w in self._priming_buffer)
                return base * relevance + primed_hits * 0.1

            ranked = sorted(self._reflections, key=_score, reverse=True)
        else:
            ranked = sorted(
                self._reflections,
                key=lambda m: m.mood_adjusted_vividness(self._mood),
                reverse=True)

        active = ranked[:limit]

        # ── Spreading activation: populate priming buffer ─────────────
        for mem in active:
            for w in _resonance_words(f"{mem.content} {mem.emotion}"):
                if len(w) >= 4:
                    self._priming_buffer[w] = (
                        self._priming_buffer.get(w, 0.0) + PRIMING_BOOST)

        # Touch relevant memories
        if context:
            ctx_words = _resonance_words(context)
            for mem in active:
                mem_words = _resonance_words(
                    f"{mem.content} {mem.emotion}")
                if ctx_words & mem_words:
                    self._touch_memory(mem)
        else:
            for mem in active:
                self._touch_memory(mem)

        return active

    # ──────────────────────────────────────────────────────────────────
    #  Core: decay_priming
    # ──────────────────────────────────────────────────────────────────

    def decay_priming(self):
        """Decay the spreading-activation priming buffer."""
        dead = []
        for w in self._priming_buffer:
            self._priming_buffer[w] *= PRIMING_DECAY
            if self._priming_buffer[w] < 0.01:
                dead.append(w)
        for w in dead:
            del self._priming_buffer[w]

    # ──────────────────────────────────────────────────────────────────
    #  Core: recall (hybrid retrieval bridge)
    # ──────────────────────────────────────────────────────────────────

    def recall(self, context: str, limit: int | None = None,
               mood: tuple[float, float, float] | None = None) -> list[Memory]:
        """Hybrid retrieval: BM25 keyword + VividEmbed semantic + spreading
        activation + contextual gating → composite re-rank."""
        k = limit or self.RECALL_LIMIT
        current_mood = mood or self._mood

        if not context or not self._reflections:
            return []

        query_words = _resonance_words(context)
        if not query_words:
            return []

        # ── Stage 1a: BM25 keyword search ─────────────────────────────
        bm25 = self._bm25_scores(query_words)
        max_bm25 = max(bm25.values()) if bm25 else 1.0
        bm25_norm = (
            {idx: s / max_bm25 for idx, s in bm25.items()}
            if max_bm25 > 0 else {}
        )

        bm25_top = sorted(
            bm25.items(), key=lambda x: x[1], reverse=True)[:2 * k]
        candidates: dict[int, dict] = {}
        for idx, _ in bm25_top:
            candidates[idx] = {
                "bm25": bm25_norm.get(idx, 0.0), "semantic": 0.0}

        # ── Stage 1a½: Date-index lookup ──────────────────────────────
        query_dates = _extract_dates(context)
        for ds in query_dates:
            for idx in self._date_index.get(ds, set()):
                if idx not in candidates:
                    candidates[idx] = {
                        "bm25": bm25_norm.get(idx, 0.0),
                        "semantic": 0.0,
                    }

        # ── Stage 1b: VividEmbed semantic search ──────────────────────
        if self._embed is not None:
            try:
                embed_results = self._embed.query(
                    context, top_k=2 * k,
                    mood=_closest_emotion(current_mood))
                for r in embed_results:
                    content = r.get("content", "")
                    score = r.get("score", 0.0)
                    for idx, mem in enumerate(self._reflections):
                        if mem.content == content:
                            if idx not in candidates:
                                candidates[idx] = {
                                    "bm25": bm25_norm.get(idx, 0.0),
                                    "semantic": 0.0,
                                }
                            candidates[idx]["semantic"] = max(
                                candidates[idx]["semantic"], score)
                            break
            except Exception:
                pass

        # Normalize semantic scores to [0, 1]
        max_sem = max(
            (c["semantic"] for c in candidates.values()), default=1.0)
        if max_sem > 0:
            for c in candidates.values():
                c["semantic"] /= max_sem

        if not candidates:
            return []

        # ── Stage 1c: Spreading Activation (Collins & Loftus 1975) ────
        seed_indices = set(candidates.keys())
        activation = self._spreading_activation(seed_indices)

        discovered = [
            (act, idx) for idx, act in activation.items()
            if idx not in seed_indices
            and act >= SPREADING_ACTIVATION_THRESHOLD
            and idx < len(self._reflections)
        ]
        discovered.sort(key=lambda x: x[0], reverse=True)
        for act, idx in discovered[:SPREADING_ACTIVATION_MAX_DISCOVER]:
            candidates[idx] = {
                "bm25": bm25_norm.get(idx, 0.0),
                "semantic": 0.0,
            }

        # ── Stage 1d: Contextual Pre-filtering ────────────────────────
        if current_mood != (0.0, 0.0, 0.0):
            gated: list[tuple[float, int]] = []
            for idx in list(candidates.keys()):
                mem = self._reflections[idx]
                enc_mood = mem._encoding_mood or (0.0, 0.0, 0.0)
                if enc_mood == (0.0, 0.0, 0.0):
                    gated.append((0.0, idx))
                    continue
                dist = math.sqrt(sum(
                    (a - b) ** 2 for a, b in zip(current_mood, enc_mood)))
                gated.append((dist, idx))

            gated.sort(key=lambda x: x[0])
            kept: set[int] = set()
            for dist, idx in gated:
                mem = self._reflections[idx]
                if (dist <= MOOD_GATE_DISTANCE
                        or mem._is_flashbulb or mem._anchor
                        or mem._cherished
                        or len(kept) < MOOD_GATE_KEEP_MIN):
                    kept.add(idx)
            candidates = {
                idx: sig for idx, sig in candidates.items()
                if idx in kept}

        if not candidates:
            return []

        # ── Stage 2: Composite re-rank ────────────────────────────────
        now = datetime.now()
        scored: list[tuple[float, int]] = []

        _salient = self._temporally_salient_indices()

        for idx, signals in candidates.items():
            mem = self._reflections[idx]

            s_keyword = signals["bm25"]
            s_semantic = signals["semantic"]
            s_vividness = mem.vividness / 10.0

            mem_vec = _emotion_to_vector(mem.emotion)
            if mem_vec and current_mood != (0.0, 0.0, 0.0):
                dot = sum(a * b for a, b in zip(mem_vec, current_mood))
                s_mood = (dot + 1.0) / 2.0
            else:
                s_mood = 0.5

            age_days = (
                now - datetime.fromisoformat(mem.timestamp)
            ).total_seconds() / 86400
            s_recency = math.exp(
                -0.693 * age_days / _RECENCY_HALF_LIFE_DAYS)

            composite = (
                _W_KEYWORD   * s_keyword
                + _W_SEMANTIC  * s_semantic
                + _W_VIVIDNESS * s_vividness
                + _W_MOOD      * s_mood
                + _W_RECENCY   * s_recency
            )

            if mem._cherished:
                composite *= 1.1

            mem_words = _resonance_words(
                f"{mem.content} {mem.emotion}")
            primed = sum(
                self._priming_buffer.get(w, 0.0) for w in mem_words)
            if primed > 0:
                composite += primed * 0.02

            if query_dates and mem._mentioned_dates:
                date_overlap = set(query_dates) & set(mem._mentioned_dates)
                if date_overlap:
                    composite += TEMPORAL_PROXIMITY_BOOST * len(date_overlap)

            if idx in _salient:
                composite += TEMPORAL_SALIENCE_BOOST

            if mem.has_visual:
                composite += VISUAL_BOOST

            act_level = activation.get(idx, 0.0)
            if act_level > 0 and idx not in seed_indices:
                composite += act_level * 0.15
            elif act_level > 1.0:
                composite += (act_level - 1.0) * 0.05

            scored.append((composite, idx))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._reflections[idx] for _, idx in scored[:k]]

    # ──────────────────────────────────────────────────────────────────
    #  Core: recall_unified (cross-type retrieval)
    # ──────────────────────────────────────────────────────────────────

    def recall_unified(self, context: str, limit: int = 8
                       ) -> dict[str, list]:
        """Cross-type retrieval bridging episodic, semantic, and procedural stores."""
        if not context:
            return {"reflections": [], "impressions": [],
                    "facts": [], "lessons": []}

        query_words = _content_words(context.lower())
        if not query_words:
            return {"reflections": [], "impressions": [],
                    "facts": [], "lessons": []}

        per_type = max(2, limit // 3)

        reflections = self.recall(context, limit=per_type)

        # ── Social impressions (keyword + vividness) ──────────────────
        imp_scored: list[tuple[float, Memory]] = []
        for entity, mems in self._social.items():
            for m in mems:
                overlap = _overlap_ratio(query_words, m.content_words)
                if overlap > 0.05:
                    score = overlap * 0.6 + (m.vividness / 10.0) * 0.4
                    imp_scored.append((score, m))
        imp_scored.sort(key=lambda x: x[0], reverse=True)
        impressions = [m for _, m in imp_scored[:per_type]]

        # ── Facts ─────────────────────────────────────────────────────
        fact_scored: list[tuple[float, ShortTermFact]] = []
        for f in self._facts:
            if f.vividness < 0.1:
                continue
            fact_text = f"{f.entity} {f.attribute} {f.value}".lower()
            fact_words = _content_words(fact_text)
            overlap = _overlap_ratio(query_words, fact_words)
            if overlap > 0.05:
                score = overlap * 0.5 + f.vividness * 0.5
                fact_scored.append((score, f))
        fact_scored.sort(key=lambda x: x[0], reverse=True)
        facts = [f for _, f in fact_scored[:per_type]]

        # ── Lessons ───────────────────────────────────────────────────
        lesson_scored: list[tuple[float, Lesson]] = []
        for ls in self._lessons:
            ls_text = f"{ls.topic} {ls.strategy} {ls.context_trigger}".lower()
            ls_words = _content_words(ls_text)
            overlap = _overlap_ratio(query_words, ls_words)
            if overlap > 0.05:
                score = overlap * 0.5 + (ls.vividness / 10.0) * 0.5
                lesson_scored.append((score, ls))
        lesson_scored.sort(key=lambda x: x[0], reverse=True)
        lessons = [ls for _, ls in lesson_scored[:per_type]]

        return {
            "reflections": reflections,
            "impressions": impressions,
            "facts": facts,
            "lessons": lessons,
        }

    # ──────────────────────────────────────────────────────────────────
    #  Core: resonate (hybrid recall + neuroscience)
    # ──────────────────────────────────────────────────────────────────

    def resonate(self, context: str, limit: int | None = None) -> list[Memory]:
        """Find old faded memories resonating with current context."""
        hard_cap = max(limit or self.RESONANCE_LIMIT, 8)
        if not context or not self._reflections:
            return []

        recalled = self.recall(
            context, limit=max(hard_cap * 2, self.RECALL_LIMIT))

        resonant = recalled[:hard_cap]
        active_ids = {id(m) for m in resonant}

        # ── Retrieval-induced forgetting ──────────────────────────────
        if resonant:
            retrieved_words = set()
            for mem in resonant:
                retrieved_words |= _resonance_words(mem.content)
            for ref in self._reflections:
                if id(ref) in active_ids:
                    continue
                ref_words = _resonance_words(ref.content)
                if not ref_words:
                    continue
                overlap = (
                    len(retrieved_words & ref_words) / len(ref_words))
                if overlap >= INTERFERENCE_THRESHOLD:
                    ref._stability = max(
                        INITIAL_STABILITY * 0.5,
                        ref._stability * (1.0 - INTERFERENCE_PENALTY))

        # ── Involuntary / Proustian recall ────────────────────────────
        if (len(self._reflections) > 3
                and random.random() < INVOLUNTARY_RECALL_PROB):
            candidate = random.choice(self._reflections)
            if id(candidate) not in active_ids:
                resonant.append(candidate)

        for r in resonant:
            self._touch_memory(r)

        return resonant

    # ──────────────────────────────────────────────────────────────────
    #  Core: recall_period (temporal navigation)
    # ──────────────────────────────────────────────────────────────────

    def recall_period(self, start: str | datetime, end: str | datetime,
                      limit: int = 20) -> list[Memory]:
        """Retrieve memories from a time window (Tulving 1972)."""
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)

        start_d = start.date() if hasattr(start, 'date') else start
        end_d = end.date() if hasattr(end, 'date') else end

        hits: set[int] = set()

        for i, mem in enumerate(self._reflections):
            ts = datetime.fromisoformat(mem.timestamp).date()
            if start_d <= ts <= end_d:
                hits.add(i)

        for ds, indices in self._date_index.items():
            try:
                d = datetime.fromisoformat(ds).date()
            except ValueError:
                continue
            if start_d <= d <= end_d:
                hits |= indices

        ordered = sorted(hits, key=lambda i: self._reflections[i].timestamp)
        return [self._reflections[i] for i in ordered[:limit]]

    # ──────────────────────────────────────────────────────────────────
    #  Temporal awareness — proactive time-based surfacing
    # ──────────────────────────────────────────────────────────────────

    def get_temporal_context(
        self,
        now: datetime | None = None,
        lookahead: int | None = None,
        lookbehind: int | None = None,
    ) -> dict[str, list[tuple[str, Memory]]]:
        """Proactive temporal awareness — returns memories about *now*."""
        ref = (now or datetime.now()).date()
        ahead = lookahead if lookahead is not None else TEMPORAL_LOOKAHEAD_DAYS
        behind = lookbehind if lookbehind is not None else TEMPORAL_LOOKBEHIND_DAYS

        today_bucket:    list[tuple[str, Memory]] = []
        upcoming_bucket: list[tuple[str, Memory]] = []
        recent_bucket:   list[tuple[str, Memory]] = []

        for ds, indices in self._date_index.items():
            try:
                d = datetime.fromisoformat(ds).date()
            except ValueError:
                continue
            delta = (d - ref).days
            for idx in indices:
                if idx >= len(self._reflections):
                    continue
                mem = self._reflections[idx]
                pair = (ds, mem)
                if delta == 0:
                    today_bucket.append(pair)
                elif 1 <= delta <= ahead:
                    upcoming_bucket.append(pair)
                elif -behind <= delta < 0:
                    recent_bucket.append(pair)

        upcoming_bucket.sort(key=lambda p: p[0])
        recent_bucket.sort(key=lambda p: p[0], reverse=True)

        return {
            "today": today_bucket,
            "upcoming": upcoming_bucket,
            "recent": recent_bucket,
        }

    def _temporally_salient_indices(self) -> set[int]:
        """Return indices of memories with dates near today."""
        ref = datetime.now().date()
        salient: set[int] = set()
        for ds, indices in self._date_index.items():
            try:
                d = datetime.fromisoformat(ds).date()
            except ValueError:
                continue
            delta_abs = abs((d - ref).days)
            if delta_abs <= max(TEMPORAL_LOOKAHEAD_DAYS,
                                TEMPORAL_LOOKBEHIND_DAYS):
                salient |= indices
        return salient
