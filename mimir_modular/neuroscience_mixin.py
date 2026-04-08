"""Mimir neuroscience mixin — Huginn, Muninn, Völva, drift, gist, chunking."""

from __future__ import annotations

import random
from datetime import datetime

from .constants import (
    HUGINN_PATTERN_MIN, HUGINN_OPEN_THREAD_WORDS,
    MUNINN_PRUNE_THRESHOLD, MUNINN_MERGE_THRESHOLD, MUNINN_COACTIVATION_BOOST,
    STABILITY_CAP, _DEDUP_THRESHOLD, _DEDUP_STOP,
    GIST_AGE_THRESHOLD_DAYS, GIST_PRESERVE_WORDS,
    CHUNK_OVERLAP_THRESHOLD, CHUNK_MIN_GROUP, CHUNK_MAX_CONTENT_WORDS,
    VOLVA_SAMPLE_PAIRS, VOLVA_INSIGHT_IMPORTANCE,
    COGNITIVE_BIAS_THRESHOLD, DRIFT_ALERT_THRESHOLD,
    SEMANTIC_MIN_MENTIONS, SEMANTIC_STABILITY,
    SEMANTIC_IMPORTANCE_FLOOR, SEMANTIC_VIVIDNESS_FLOOR,
    SUMMARY_MIN_MEMORIES, SUMMARY_AGE_DAYS,
    SUMMARY_IMPORTANCE, SUMMARY_STABILITY,
    REINFORCEMENT_IMPORTANCE_MIN, REINFORCEMENT_VIVIDNESS_MAX,
    REINFORCEMENT_STABILITY_BOOST, REINFORCEMENT_MAX_PER_CYCLE,
)
from .helpers import (
    _emotion_to_vector, _content_words, _overlap_ratio, _resonance_words,
)
from .models import Memory


class NeuroscienceMixin:
    """Mixin providing neuroscience mechanisms: Huginn, Muninn, Völva,
    drift detection, gist compression, and memory chunking."""

    # ══════════════════════════════════════════════════════════════════
    #  Reconsolidation drift detection (mechanism #16)
    # ══════════════════════════════════════════════════════════════════

    def detect_drift(self, include_reframed: bool = False) -> list[Memory]:
        """Return memories whose emotion has drifted significantly."""
        drifted = [
            m for m in self._reflections
            if m.has_drifted
            and m.source not in ("huginn", "volva")
            and (include_reframed or not m._reframed)]
        drifted.sort(key=lambda m: m.drift_magnitude, reverse=True)
        for m in drifted:
            self._audit.log(
                "reconsolidation_drift",
                emotion=m.emotion,
                source="drift_monitor",
                details={
                    "original_emotion": m.original_emotion,
                    "current_emotion": m.emotion,
                    "drift_magnitude": round(m.drift_magnitude, 3),
                    "content_preview": m.content[:60],
                })
        return drifted

    def drift_analysis(self) -> dict:
        """Enhanced drift detection — deeper pattern analysis."""
        drifted = self.detect_drift(include_reframed=True)

        # ── Drift direction analysis ──────────────────────────────────
        directions: list[dict] = []
        for m in drifted:
            orig = _emotion_to_vector(m.original_emotion)
            curr = m._emotion_pad
            if not orig or not curr:
                continue
            deltas = {
                "pleasure": curr[0] - orig[0],
                "arousal": curr[1] - orig[1],
                "dominance": curr[2] - orig[2],
            }
            primary = max(deltas, key=lambda k: abs(deltas[k]))
            directions.append({
                "memory": m.content[:60],
                "original": m.original_emotion,
                "current": m.emotion,
                "magnitude": round(m.drift_magnitude, 3),
                "primary_axis": primary,
                "delta": {k: round(v, 3) for k, v in deltas.items()},
                "reframed": m._reframed,
            })

        # ── Cognitive bias detection ──────────────────────────────────
        biases: list[dict] = []

        if len(drifted) >= 3:
            neg_drift = sum(
                1 for d in directions
                if d["delta"]["pleasure"] < -0.1)
            if neg_drift / len(drifted) >= COGNITIVE_BIAS_THRESHOLD:
                biases.append({
                    "type": "negativity_drift",
                    "description": (
                        f"{neg_drift}/{len(drifted)} memories drifting "
                        f"toward negative — possible negativity bias"),
                    "severity": round(neg_drift / len(drifted), 2),
                })

        if len(drifted) >= 3:
            pos_drift = sum(
                1 for d in directions
                if d["delta"]["pleasure"] > 0.1)
            if pos_drift / len(drifted) >= COGNITIVE_BIAS_THRESHOLD:
                biases.append({
                    "type": "positivity_fixation",
                    "description": (
                        f"{pos_drift}/{len(drifted)} memories drifting "
                        f"toward positive — possible rose-tinting"),
                    "severity": round(pos_drift / len(drifted), 2),
                })

        if len(drifted) >= 3:
            arousal_up = sum(
                1 for d in directions
                if d["delta"]["arousal"] > 0.1)
            if arousal_up / len(drifted) >= COGNITIVE_BIAS_THRESHOLD:
                biases.append({
                    "type": "arousal_escalation",
                    "description": (
                        f"{arousal_up}/{len(drifted)} memories gaining "
                        f"arousal — emotional amplification pattern"),
                    "severity": round(arousal_up / len(drifted), 2),
                })

        all_mems = [m for m in self._reflections
                    if m.source not in ("huginn", "volva")]
        if len(all_mems) >= 5:
            pleasures = []
            for m in all_mems:
                v = _emotion_to_vector(m.emotion)
                if v:
                    pleasures.append(v[0])
            if pleasures:
                pos_count = sum(1 for p in pleasures if p > 0.2)
                neg_count = sum(1 for p in pleasures if p < -0.2)
                total = len(pleasures)
                if pos_count / total >= COGNITIVE_BIAS_THRESHOLD:
                    biases.append({
                        "type": "positive_tunnel",
                        "description": (
                            f"{pos_count}/{total} memories are positive-valence "
                            f"— may be neglecting negative experiences"),
                        "severity": round(pos_count / total, 2),
                    })
                elif neg_count / total >= COGNITIVE_BIAS_THRESHOLD:
                    biases.append({
                        "type": "negative_tunnel",
                        "description": (
                            f"{neg_count}/{total} memories are negative-valence "
                            f"— may be neglecting positive experiences"),
                        "severity": round(neg_count / total, 2),
                    })

        for b in biases:
            self._audit.log(
                "cognitive_bias_detected",
                source="drift_analysis",
                details=b)

        return {
            "drifted": drifted,
            "directions": directions,
            "cognitive_biases": biases,
            "total_memories": len(self._reflections),
            "drift_rate": (
                round(len(drifted) / max(len(self._reflections), 1), 3)),
        }

    # ══════════════════════════════════════════════════════════════════
    #  Huginn — Thought (pattern detection, mechanism #11)
    # ══════════════════════════════════════════════════════════════════

    def huginn(self) -> list[Memory]:
        """Odin's raven of Thought — scans all memories for emergent
        patterns and generates insight memories."""
        insights: list[Memory] = []

        # ── 1. Entity sentiment arcs ──────────────────────────────────
        for entity, mems in self._social.items():
            if len(mems) < HUGINN_PATTERN_MIN:
                continue
            sorted_mems = sorted(mems, key=lambda m: m.timestamp)
            pleasures = []
            for m in sorted_mems:
                vec = _emotion_to_vector(m.emotion)
                if vec:
                    pleasures.append(vec[0])
            if len(pleasures) < HUGINN_PATTERN_MIN:
                continue
            mid = len(pleasures) // 2
            first_avg = sum(pleasures[:mid]) / max(mid, 1)
            second_avg = sum(pleasures[mid:]) / max(len(pleasures) - mid, 1)
            delta = second_avg - first_avg
            if abs(delta) < 0.15:
                continue
            direction = "warming" if delta > 0 else "cooling"
            early_emo = sorted_mems[0].emotion
            recent_emo = sorted_mems[-1].emotion
            content = (
                f"My relationship with {entity} has been {direction} — "
                f"early on I felt {early_emo}, more recently {recent_emo}")
            if not any(entity in m.content and "relationship" in m.content
                       for m in self._reflections if m.source == "huginn"):
                mem = self.remember(
                    content, emotion="reflective",
                    importance=6, source="huginn",
                    why_saved="pattern detected by Huginn")
                insights.append(mem)

        # ── 2. Recurring theme clusters ───────────────────────────────
        word_mems: dict[str, list[int]] = {}
        for i, m in enumerate(self._reflections):
            if m.source in ("huginn", "volva"):
                continue
            for w in m.content_words:
                if len(w) >= 4:
                    if w not in word_mems:
                        word_mems[w] = []
                    word_mems[w].append(i)
        for word, indices in word_mems.items():
            if len(indices) < HUGINN_PATTERN_MIN:
                continue
            mems_for_word = [self._reflections[i] for i in indices]
            emotions = [m.emotion for m in mems_for_word]
            emotion_counts: dict[str, int] = {}
            for e in emotions:
                emotion_counts[e] = emotion_counts.get(e, 0) + 1
            dominant = max(emotion_counts, key=emotion_counts.get)
            content = (
                f"I notice '{word}' comes up often in my memories "
                f"(mentioned {len(indices)} times) — the feeling is "
                f"usually {dominant}")
            if not any(f"'{word}'" in m.content
                       for m in self._reflections if m.source == "huginn"):
                mem = self.remember(
                    content, emotion="thoughtful",
                    importance=4, source="huginn",
                    why_saved="recurring theme detected by Huginn")
                insights.append(mem)

        # ── 3. Open threads (unresolved intentions) ───────────────────
        for i, m in enumerate(self._reflections):
            if m.source in ("huginn", "volva"):
                continue
            words = set(m.content.lower().split())
            if not words & HUGINN_OPEN_THREAD_WORDS:
                continue
            m_words = m.content_words
            resolved = False
            for j in range(i + 1, len(self._reflections)):
                later = self._reflections[j]
                if later.source in ("huginn", "volva"):
                    continue
                overlap = _overlap_ratio(m_words, later.content_words)
                if overlap >= 0.3:
                    resolved = True
                    break
            if not resolved and m.vividness > 0.05:
                age_days = (
                    datetime.now()
                    - datetime.fromisoformat(m.timestamp)
                ).total_seconds() / 86400
                if age_days > 3:
                    content = (
                        f"Unresolved thread: '{m.content[:80]}' "
                        f"— this has been on my mind for "
                        f"{int(age_days)} days")
                    if not any(m.content[:40] in mem.content
                               for mem in self._reflections
                               if mem.source == "huginn"):
                        mem = self.remember(
                            content, emotion="thoughtful",
                            importance=5, source="huginn",
                            why_saved="open thread detected by Huginn")
                        insights.append(mem)

        # ── 4. Reconsolidation drift alerts ────────────────────────
        drifted = self.detect_drift()
        for m in drifted:
            content = (
                f"Drift alert: my memory of '{m.content[:60]}' "
                f"was originally {m.original_emotion} but now "
                f"feels {m.emotion} (drift: {m.drift_magnitude:.2f})")
            if not any(m.content[:40] in mem.content
                       for mem in self._reflections
                       if mem.source == "huginn"):
                mem = self.remember(
                    content, emotion="thoughtful",
                    importance=4, source="huginn",
                    why_saved="reconsolidation drift detected by Huginn")
                insights.append(mem)

        # ── 5. Semantic memory crystallization (Tulving 1972) ─────
        # Scan episodic memories for recurring factual content that
        # should graduate into durable semantic knowledge — like how the
        # hippocampus transfers repeated patterns to the neocortex.
        semantic_insights = self._crystallize_semantic_memories()
        insights.extend(semantic_insights)

        # ── 6. Retrieval-augmented reinforcement (slow-wave replay) ──
        # Identify important memories that are fading and refresh their
        # stability — mimics hippocampal replay during slow-wave sleep.
        reinforced = self._reinforce_fading_memories()
        if reinforced:
            self._audit.log("huginn_reinforcement",
                            details={"reinforced": reinforced})

        return insights

    # ══════════════════════════════════════════════════════════════════
    #  Semantic Memory Crystallization (Tulving 1972 — episodic→semantic)
    # ══════════════════════════════════════════════════════════════════

    def _crystallize_semantic_memories(self) -> list[Memory]:
        """Extract recurring factual content from episodic memories and
        crystallize it into durable semantic memories.

        This models the real neuroscience process where repeated episodic
        experiences gradually distill into semantic knowledge stored in the
        neocortex.  Semantic memories live in the same store as episodic
        ones but get near-permanent stability and a high vividness floor.
        """
        crystallized: list[Memory] = []

        # Collect significant phrases from episodic memories
        # (skip insight/dream/chunk/existing semantic memories)
        _skip_sources = {"huginn", "volva", "chunk", "semantic", "summary"}
        episodic = [
            m for m in self._reflections if m.source not in _skip_sources]
        if len(episodic) < SEMANTIC_MIN_MENTIONS:
            return crystallized

        # Build entity→content fragments index for fact extraction
        # Focus on memories with entities (named people, places, projects)
        entity_facts: dict[str, list[str]] = {}
        for m in episodic:
            if not m.entity:
                continue
            ent = m.entity.lower()
            if ent not in entity_facts:
                entity_facts[ent] = []
            entity_facts[ent].append(m.content)

        # Also track frequently repeated short phrases (3-5 word n-grams)
        from collections import Counter
        ngram_counts: Counter = Counter()
        for m in episodic:
            words = m.content.lower().split()
            for n in range(3, 6):
                for i in range(len(words) - n + 1):
                    gram = " ".join(words[i:i + n])
                    # Skip grams that are mostly stopwords
                    meaningful = sum(
                        1 for w in words[i:i + n]
                        if len(w) >= 4 and w not in _DEDUP_STOP)
                    if meaningful >= 2:
                        ngram_counts[gram] += 1

        # Existing semantic content (dedup)
        existing_semantic = {
            m.content for m in self._reflections
            if m.source == "semantic"}

        # Crystallize entity-linked facts that appear across
        # multiple episodic memories
        for entity, contents in entity_facts.items():
            if len(contents) < SEMANTIC_MIN_MENTIONS:
                continue

            # Find the most representative content fragment
            # (the one with highest word overlap with others)
            best_content = contents[0]
            best_overlap = 0.0
            content_word_sets = [
                set(_content_words(c)) for c in contents]
            for i, c in enumerate(contents):
                avg_overlap = sum(
                    len(content_word_sets[i] & content_word_sets[j])
                    / max(len(content_word_sets[i] | content_word_sets[j]), 1)
                    for j in range(len(contents)) if j != i
                ) / max(len(contents) - 1, 1)
                if avg_overlap > best_overlap:
                    best_overlap = avg_overlap
                    best_content = c

            semantic_content = (
                f"[semantic — {entity}] {best_content[:200]}")
            if semantic_content not in existing_semantic:
                mem = Memory(
                    content=semantic_content,
                    emotion="neutral",
                    importance=max(SEMANTIC_IMPORTANCE_FLOOR, 7),
                    source="semantic",
                    entity=entity,
                    why_saved=(
                        f"crystallized from {len(contents)} episodic "
                        f"memories about {entity}"),
                )
                mem._stability = SEMANTIC_STABILITY
                mem._encoding_mood = self._mood
                self._reflections.append(mem)
                if self._embed is not None:
                    try:
                        entry = self._embed.add(
                            content=mem.content,
                            emotion="neutral",
                            importance=mem.importance,
                            stability=mem._stability)
                        mem._embed_uid = entry.uid
                    except Exception:
                        pass
                crystallized.append(mem)
                existing_semantic.add(semantic_content)

        # Crystallize frequently repeated phrases (entity-free facts)
        for gram, count in ngram_counts.most_common(20):
            if count < SEMANTIC_MIN_MENTIONS:
                break
            # Don't duplicate existing semantic knowledge
            if any(gram in sc for sc in existing_semantic):
                continue
            semantic_content = (
                f"[semantic — recurring fact] {gram} "
                f"(mentioned {count} times)")
            mem = Memory(
                content=semantic_content,
                emotion="neutral",
                importance=SEMANTIC_IMPORTANCE_FLOOR,
                source="semantic",
                why_saved=(
                    f"crystallized from {count} repetitions "
                    f"during consolidation"),
            )
            mem._stability = SEMANTIC_STABILITY
            mem._encoding_mood = self._mood
            self._reflections.append(mem)
            if self._embed is not None:
                try:
                    entry = self._embed.add(
                        content=mem.content,
                        emotion="neutral",
                        importance=mem.importance,
                        stability=mem._stability)
                    mem._embed_uid = entry.uid
                except Exception:
                    pass
            crystallized.append(mem)
            existing_semantic.add(semantic_content)

        if crystallized:
            self._audit.log("semantic_crystallization",
                            details={"crystallized": len(crystallized)})

        return crystallized

    # ══════════════════════════════════════════════════════════════════
    #  Retrieval-Augmented Reinforcement (slow-wave hippocampal replay)
    # ══════════════════════════════════════════════════════════════════

    def _reinforce_fading_memories(self) -> int:
        """During consolidation, find high-importance memories that are
        fading and boost their stability — like the hippocampus replaying
        important traces during slow-wave sleep.

        This prevents the "forgot my job title after 3 months" problem
        by giving important memories a periodic refresh cycle.
        """
        candidates = []
        for m in self._reflections:
            if m._is_flashbulb or m._cherished or m._anchor:
                continue  # already protected
            if m.source in ("huginn", "volva"):
                continue  # insights don't need reinforcement
            if m.importance < REINFORCEMENT_IMPORTANCE_MIN:
                continue
            vivid = m.vividness
            # Only reinforce memories that are genuinely fading
            if vivid <= REINFORCEMENT_VIVIDNESS_MAX * m.importance:
                candidates.append((vivid, m))

        # Sort by vividness ascending — reinforce the most faded first
        candidates.sort(key=lambda x: x[0])
        reinforced = 0
        for _, m in candidates[:REINFORCEMENT_MAX_PER_CYCLE]:
            old_stability = m._stability
            m._stability = min(
                m._stability * REINFORCEMENT_STABILITY_BOOST,
                STABILITY_CAP)
            reinforced += 1

        return reinforced

    # ══════════════════════════════════════════════════════════════════
    #  Muninn — Memory (consolidation daemon, mechanism #12)
    # ══════════════════════════════════════════════════════════════════

    def muninn(self) -> dict:
        """Odin's raven of Memory — consolidation daemon."""
        merged = 0
        pruned = 0
        strengthened = 0

        # ── 1. Merge near-duplicates ──────────────────────────────────
        to_remove: set[int] = set()
        n = len(self._reflections)
        for i in range(n):
            if i in to_remove:
                continue
            mi = self._reflections[i]
            wi = mi.content_words
            if not wi:
                continue
            for j in range(i + 1, n):
                if j in to_remove:
                    continue
                mj = self._reflections[j]
                overlap = _overlap_ratio(wi, mj.content_words)
                if overlap >= MUNINN_MERGE_THRESHOLD:
                    keeper, donor = (mi, mj) if len(mi.content) >= len(mj.content) else (mj, mi)
                    keeper.importance = max(keeper.importance, donor.importance)
                    keeper._stability = max(
                        keeper._stability, donor._stability)
                    keeper._access_count += donor._access_count
                    if donor._is_flashbulb:
                        keeper._is_flashbulb = True
                    if donor._cherished:
                        keeper._cherished = True
                    if donor._anchor:
                        keeper._anchor = True
                    if donor.entity and not keeper.entity:
                        keeper.entity = donor.entity
                    if self._embed and donor._embed_uid:
                        try:
                            self._embed.remove(donor._embed_uid)
                        except Exception:
                            pass
                    to_remove.add(j if keeper is mi else i)
                    merged += 1

        # ── 2. Prune dead memories (archive to attic) ─────────────────
        for i in range(n):
            if i in to_remove:
                continue
            m = self._reflections[i]
            if (m.vividness < MUNINN_PRUNE_THRESHOLD
                    and not m._is_flashbulb
                    and not m._anchor
                    and not m._cherished
                    and m.source not in (
                        "huginn", "volva", "semantic", "summary")):
                if self._embed and m._embed_uid:
                    try:
                        self._embed.remove(m._embed_uid)
                    except Exception:
                        pass
                # Archive to attic instead of permanent deletion
                self._attic.append(m)
                to_remove.add(i)
                pruned += 1

        if to_remove:
            self._reflections = [
                m for i, m in enumerate(self._reflections)
                if i not in to_remove]
            self._rebuild_index()

        # ── 3. Strengthen co-activated pairs ──────────────────────────
        day_groups: dict[str, list[Memory]] = {}
        for m in self._reflections:
            day = m.timestamp[:10]
            if day not in day_groups:
                day_groups[day] = []
            day_groups[day].append(m)

        for day, group in day_groups.items():
            if len(group) >= 2:
                for m in group:
                    m._stability = min(
                        m._stability * MUNINN_COACTIVATION_BOOST,
                        STABILITY_CAP)
                    strengthened += 1

        self._audit.log("muninn_consolidation",
                        details={"merged": merged, "pruned": pruned,
                                 "strengthened": strengthened})

        # ── 4. Hierarchical summarization (hippocampal replay) ────────
        # Group old episodic memories by week and produce durable summary
        # memories — like how the hippocampus replays episode clusters
        # into compressed schemas for neocortical storage.
        summarized = self._produce_weekly_summaries()

        return {"merged": merged, "pruned": pruned,
                "strengthened": strengthened,
                "summarized": summarized}

    # ══════════════════════════════════════════════════════════════════
    #  Hierarchical Summarization (hippocampal schema compression)
    # ══════════════════════════════════════════════════════════════════

    def _produce_weekly_summaries(self) -> int:
        """Produce weekly summary memories from clusters of old episodic
        memories — models hippocampal replay compressing episodes into
        durable schemas.

        Summary memories are stored as source='summary' with high
        stability, and participate in normal recall and Yggdrasil graph
        connections.
        """
        now = datetime.now()
        _skip_sources = {
            "huginn", "volva", "chunk", "semantic", "summary"}

        # Group episodic memories by ISO week
        week_groups: dict[str, list[Memory]] = {}
        for m in self._reflections:
            if m.source in _skip_sources:
                continue
            try:
                ts = datetime.fromisoformat(m.timestamp)
            except Exception:
                continue
            age_days = (now - ts).total_seconds() / 86400
            if age_days < SUMMARY_AGE_DAYS:
                continue  # too recent to summarize
            # ISO year-week key
            iso_year, iso_week, _ = ts.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
            if week_key not in week_groups:
                week_groups[week_key] = []
            week_groups[week_key].append(m)

        # Existing summary weeks (dedup)
        existing_weeks = set()
        for m in self._reflections:
            if m.source == "summary" and m.content.startswith("[summary — "):
                # Extract week key from content
                try:
                    wk = m.content.split("]")[0].replace("[summary — ", "")
                    existing_weeks.add(wk)
                except Exception:
                    pass

        summaries_created = 0
        for week_key, mems in sorted(week_groups.items()):
            if week_key in existing_weeks:
                continue
            if len(mems) < SUMMARY_MIN_MEMORIES:
                continue

            # Build summary: dominant emotions, entities, top themes
            emotion_counts: dict[str, int] = {}
            entities_seen: set[str] = set()
            all_content_words: list[str] = []
            max_importance = 0
            for m in mems:
                emotion_counts[m.emotion] = (
                    emotion_counts.get(m.emotion, 0) + 1)
                if m.entity:
                    entities_seen.add(m.entity)
                all_content_words.extend(
                    w for w in m.content_words if len(w) >= 4)
                max_importance = max(max_importance, m.importance)

            dominant_emotion = max(
                emotion_counts, key=emotion_counts.get)

            # Top theme words by frequency
            from collections import Counter
            word_freq = Counter(all_content_words)
            top_themes = [w for w, _ in word_freq.most_common(8)]
            themes_str = ", ".join(top_themes) if top_themes else "various"
            entities_str = (
                ", ".join(sorted(entities_seen)[:5])
                if entities_seen else "no specific entities"
            )

            content = (
                f"[summary — {week_key}] "
                f"{len(mems)} memories: "
                f"themes — {themes_str}; "
                f"entities — {entities_str}; "
                f"dominant feeling — {dominant_emotion}")

            mem = Memory(
                content=content,
                emotion=dominant_emotion,
                importance=max(SUMMARY_IMPORTANCE, min(max_importance, 8)),
                source="summary",
                why_saved=(
                    f"weekly summary of {len(mems)} memories "
                    f"from {week_key}"),
            )
            mem._stability = SUMMARY_STABILITY
            mem._encoding_mood = self._mood
            self._reflections.append(mem)

            if self._embed is not None:
                try:
                    entry = self._embed.add(
                        content=mem.content,
                        emotion=dominant_emotion,
                        importance=mem.importance,
                        stability=mem._stability)
                    mem._embed_uid = entry.uid
                except Exception:
                    pass

            summaries_created += 1

        if summaries_created:
            self._audit.log("muninn_summarization",
                            details={"summaries": summaries_created})

        return summaries_created

    # ══════════════════════════════════════════════════════════════════
    #  Gist Compression (Reyna & Brainerd 1995)
    # ══════════════════════════════════════════════════════════════════

    def _compress_to_gist(self) -> int:
        """Compress old, low-importance memories to gist form."""
        now = datetime.now()
        compressed = 0
        for m in self._reflections:
            if m._is_flashbulb or m._anchor or m._cherished:
                continue
            if m.source in ("huginn", "volva", "semantic", "summary"):
                continue
            try:
                age_days = (
                    now - datetime.fromisoformat(m.timestamp)
                ).total_seconds() / 86400
            except Exception:
                continue
            if age_days < GIST_AGE_THRESHOLD_DAYS:
                continue
            words = m.content.split()
            if len(words) <= GIST_PRESERVE_WORDS:
                continue
            preserved = " ".join(words[:GIST_PRESERVE_WORDS])
            m.content = f"[gist — {m.emotion}] {preserved}…"
            m._content_words = None
            compressed += 1
        if compressed:
            self._rebuild_index()
        return compressed

    # ══════════════════════════════════════════════════════════════════
    #  Memory Chunking (Miller 1956 — 7±2 capacity)
    # ══════════════════════════════════════════════════════════════════

    def chunk_memories(self) -> int:
        """Fuse clusters of related memories into richer composite chunks."""
        n = len(self._reflections)
        if n < CHUNK_MIN_GROUP:
            return 0

        word_sets = [m.content_words for m in self._reflections]
        adjacency: dict[int, set[int]] = {i: set() for i in range(n)}
        for i in range(n):
            if not word_sets[i]:
                continue
            mi = self._reflections[i]
            if mi.source in ("huginn", "volva", "chunk", "semantic", "summary"):
                continue
            for j in range(i + 1, n):
                if not word_sets[j]:
                    continue
                mj = self._reflections[j]
                if mj.source in ("huginn", "volva", "chunk", "semantic", "summary"):
                    continue
                overlap = _overlap_ratio(word_sets[i], word_sets[j])
                if CHUNK_OVERLAP_THRESHOLD <= overlap < _DEDUP_THRESHOLD:
                    adjacency[i].add(j)
                    adjacency[j].add(i)

        used: set[int] = set()
        clusters: list[list[int]] = []

        nodes_by_degree = sorted(
            adjacency.keys(),
            key=lambda x: len(adjacency[x]),
            reverse=True)

        for seed in nodes_by_degree:
            if seed in used:
                continue
            if len(adjacency[seed]) < CHUNK_MIN_GROUP - 1:
                continue
            cluster = {seed}
            for neighbor in adjacency[seed]:
                if neighbor not in used:
                    cluster.add(neighbor)
            if len(cluster) >= CHUNK_MIN_GROUP:
                clusters.append(sorted(cluster))
                used |= cluster

        chunks_created = 0
        to_remove: set[int] = set()

        for cluster in clusters:
            mems = [self._reflections[i] for i in cluster]

            all_words: list[str] = []
            seen_words: set[str] = set()
            for m in sorted(mems, key=lambda x: x.importance, reverse=True):
                for w in m.content.split():
                    lw = w.lower().strip(".,!?;:'\"")
                    if lw not in seen_words and lw not in _DEDUP_STOP:
                        all_words.append(w)
                        seen_words.add(lw)
                    if len(all_words) >= CHUNK_MAX_CONTENT_WORDS:
                        break

            emotion_counts: dict[str, int] = {}
            for m in mems:
                emotion_counts[m.emotion] = emotion_counts.get(m.emotion, 0) + 1
            dominant_emotion = max(emotion_counts, key=emotion_counts.get)

            entity = ""
            for m in sorted(mems, key=lambda x: x.importance, reverse=True):
                if m.entity:
                    entity = m.entity
                    break

            chunk_content = " ".join(all_words)
            max_imp = max(m.importance for m in mems)
            max_stab = max(m._stability for m in mems)

            chunk_mem = Memory(
                content=f"[chunk: {len(mems)} memories] {chunk_content}",
                emotion=dominant_emotion,
                importance=min(10, max_imp + 1),
                source="chunk",
                entity=entity,
                why_saved=f"chunked from {len(mems)} related memories")
            chunk_mem._stability = min(max_stab * 1.2, STABILITY_CAP)
            chunk_mem._encoding_mood = self._mood

            if any(m._is_flashbulb for m in mems):
                chunk_mem._is_flashbulb = True
            if any(m._cherished for m in mems):
                chunk_mem._cherished = True
            if any(m._anchor for m in mems):
                chunk_mem._anchor = True

            self._reflections.append(chunk_mem)

            for i in cluster:
                m = self._reflections[i]
                if not (m._is_flashbulb or m._anchor or m._cherished):
                    if self._embed and m._embed_uid:
                        try:
                            self._embed.remove(m._embed_uid)
                        except Exception:
                            pass
                    to_remove.add(i)

            if self._embed is not None:
                try:
                    entry = self._embed.add(
                        content=chunk_mem.content,
                        emotion=dominant_emotion,
                        importance=chunk_mem.importance,
                        stability=chunk_mem._stability)
                    chunk_mem._embed_uid = entry.uid
                except Exception:
                    pass

            chunks_created += 1

        if to_remove:
            self._reflections = [
                m for i, m in enumerate(self._reflections)
                if i not in to_remove]
            self._rebuild_index()

        if chunks_created:
            self._audit.log("chunk_memories",
                            details={"chunks_created": chunks_created,
                                     "memories_absorbed": len(to_remove)})

        return chunks_created

    # ══════════════════════════════════════════════════════════════════
    #  Völva's Vision — Dream Synthesis (mechanism #14)
    # ══════════════════════════════════════════════════════════════════

    def volva_dream(self, n_samples: int | None = None) -> list[Memory]:
        """The Völva's trance — dream synthesis during rest."""
        n = n_samples or VOLVA_SAMPLE_PAIRS
        if len(self._reflections) < 4:
            return []

        real_mems = [
            m for m in self._reflections
            if m.source not in (
                "huginn", "volva", "semantic", "summary")]
        if len(real_mems) < 4:
            return []

        insights: list[Memory] = []
        seen_pairs: set[tuple[str, str]] = set()

        for _ in range(n):
            a, b = random.sample(real_mems, 2)
            pair_key = tuple(sorted([a.timestamp, b.timestamp]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            a_words = a.content_words
            b_words = b.content_words
            shared = a_words & b_words

            # ── Emotional arc: same topic, different emotions ─────────
            if (shared and len(shared) >= 2
                    and a.emotion != b.emotion):
                earlier, later = (
                    (a, b) if a.timestamp <= b.timestamp else (b, a))
                bridge_words = ", ".join(sorted(shared)[:3])
                content = (
                    f"Dream insight: regarding '{bridge_words}', "
                    f"my feeling shifted from {earlier.emotion} to "
                    f"{later.emotion} over time")
                if not any(bridge_words in m.content
                           for m in self._reflections
                           if m.source == "volva"):
                    mem = self.remember(
                        content, emotion="reflective",
                        importance=VOLVA_INSIGHT_IMPORTANCE,
                        source="volva",
                        why_saved="dream synthesis by Völva")
                    insights.append(mem)
                continue

            # ── Theme bridge: distant memories with hidden thread ─────
            if shared and len(shared) >= 3:
                age_a = (datetime.now()
                         - datetime.fromisoformat(a.timestamp)
                         ).total_seconds() / 86400
                age_b = (datetime.now()
                         - datetime.fromisoformat(b.timestamp)
                         ).total_seconds() / 86400
                if abs(age_a - age_b) > 30:
                    bridge = ", ".join(sorted(shared)[:4])
                    content = (
                        f"Dream insight: a thread connects two distant "
                        f"memories through '{bridge}' — perhaps there's "
                        f"a deeper pattern here")
                    if not any(bridge in m.content
                               for m in self._reflections
                               if m.source == "volva"):
                        mem = self.remember(
                            content, emotion="contemplative",
                            importance=VOLVA_INSIGHT_IMPORTANCE,
                            source="volva",
                            why_saved="dream synthesis by Völva")
                        insights.append(mem)
                continue

            # ── Temporal cluster: events on the same day ──────────────
            if a.timestamp[:10] == b.timestamp[:10]:
                day = a.timestamp[:10]
                same_day = [
                    m for m in real_mems if m.timestamp[:10] == day]
                if len(same_day) >= 3:
                    emotions = set(m.emotion for m in same_day)
                    content = (
                        f"Dream insight: a lot happened on {day} — "
                        f"I felt {', '.join(sorted(emotions))}. "
                        f"That was a significant day.")
                    if not any(day in m.content
                               for m in self._reflections
                               if m.source == "volva"):
                        mem = self.remember(
                            content, emotion="nostalgic",
                            importance=VOLVA_INSIGHT_IMPORTANCE,
                            source="volva",
                            why_saved="dream synthesis by Völva")
                        insights.append(mem)

        self._audit.log("volva_dream",
                        details={"insights_generated": len(insights)})
        return insights
