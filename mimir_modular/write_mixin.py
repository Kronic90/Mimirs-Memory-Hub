"""Mimir write mixin — remember, visual memory, mood, social, anchor/cherish, relive."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .constants import (
    NOVELTY_MAX_COMPARE, NOVELTY_HIGH_THRESHOLD, NOVELTY_LOW_THRESHOLD,
    NOVELTY_BOOST_FACTOR, NOVELTY_DECAY_FACTOR,
    _DEDUP_THRESHOLD,
    FLASHBULB_AROUSAL_THRESHOLD, FLASHBULB_IMPORTANCE_MIN,
    FLASHBULB_STABILITY_FLOOR,
    PATTERN_SEP_THRESHOLD, PATTERN_SEP_NUDGE,
    STABILITY_CAP, INITIAL_STABILITY,
    ANCHOR_STABILITY_FLOOR,
    AUTO_CONSOLIDATION_INTERVAL,
    PROSPECTIVE_IMPORTANCE_MIN,
    VISUAL_QUALITY_FADED,
)
from .helpers import (
    _emotion_to_vector, _closest_emotion,
    _content_words, _overlap_ratio, _resonance_words, _extract_dates,
    _infer_arc_position,
    _visual_hash, _compress_image, _decompress_image,
)
from .models import Memory, Reminder


class WriteMixin:
    """Mixin providing memory creation (remember, remember_visual),
    mood updates, social impressions, anchor/cherish/reframe, and relive."""

    # ──────────────────────────────────────────────────────────────────
    #  Core: remember
    # ──────────────────────────────────────────────────────────────────

    def remember(self, content: str, emotion: str = "neutral",
                 importance: int = 5, source: str = "reflection",
                 why_saved: str = "") -> Memory:
        """Store an episodic memory."""
        # Chemistry modulation
        mods = self._chemistry.get_modifiers()
        effective_importance = importance
        if mods["encoding_boost"] != 1.0:
            effective_importance = max(1, min(10, round(
                importance * mods["encoding_boost"])))

        self._chemistry.on_emotion(emotion)

        # ── Novelty detection (Ranganath & Rainer 2003) ───────────────
        new_words = _content_words(content)
        novelty = 1.0
        if self._reflections and new_words:
            recent = self._reflections[-NOVELTY_MAX_COMPARE:]
            overlaps = []
            for existing in recent:
                overlap = _overlap_ratio(new_words, existing.content_words)
                overlaps.append(overlap)
            avg_overlap = sum(overlaps) / len(overlaps)
            novelty = 1.0 - avg_overlap

            if novelty >= NOVELTY_HIGH_THRESHOLD:
                effective_importance = max(1, min(10, round(
                    effective_importance * NOVELTY_BOOST_FACTOR)))
            elif novelty <= NOVELTY_LOW_THRESHOLD:
                effective_importance = max(1, min(10, round(
                    effective_importance * NOVELTY_DECAY_FACTOR)))

        # Dedup check
        for i, existing in enumerate(self._reflections):
            if _overlap_ratio(new_words, existing.content_words) >= _DEDUP_THRESHOLD:
                merged = Memory(
                    content=content, emotion=emotion,
                    importance=max(effective_importance, existing.importance),
                    source=source, why_saved=why_saved or existing.why_saved)
                merged._access_count = existing._access_count
                merged._stability = existing._stability
                merged._last_access = existing._last_access
                merged.timestamp = existing.timestamp
                merged._encoding_mood = existing._encoding_mood or self._mood
                merged._is_flashbulb = existing._is_flashbulb
                merged._anchor = existing._anchor
                merged._cherished = existing._cherished
                merged._mentioned_dates = (
                    existing._mentioned_dates or _extract_dates(content))
                if self._embed is not None and existing._embed_uid:
                    try:
                        self._embed.remove(existing._embed_uid)
                    except Exception:
                        pass
                self._reflections[i] = merged
                self._rebuild_index()
                if self._embed is not None:
                    try:
                        entry = self._embed.add(
                            content=content, emotion=emotion,
                            importance=merged.importance,
                            stability=merged._stability)
                        merged._embed_uid = entry.uid
                    except Exception:
                        pass
                return merged

        mem = Memory(content=content, emotion=emotion,
                     importance=effective_importance, source=source,
                     why_saved=why_saved)

        mem._novelty_score = novelty
        mem._encoding_mood = self._mood

        # ── Narrative arc position (Freytag 1863) ─────────────────────
        mem._arc_position = _infer_arc_position(content, emotion)

        # ── Flashbulb detection ───────────────────────────────────────
        vec = _emotion_to_vector(emotion)
        arousal = abs(vec[1]) if vec else 0.0
        if (arousal >= FLASHBULB_AROUSAL_THRESHOLD
                and effective_importance >= FLASHBULB_IMPORTANCE_MIN):
            mem._is_flashbulb = True
            mem._stability = max(
                mem._stability, FLASHBULB_STABILITY_FLOOR)

        # Chemistry flashbulb (cortisol)
        if mods["flashbulb"] and not mem._is_flashbulb:
            mem._stability = max(mem._stability, STABILITY_CAP * 0.6)

        self._reflections.append(mem)
        self._index_memory(len(self._reflections) - 1, mem)

        # ── Hippocampal pattern separation (Yassa & Stark 2011) ───────
        new_idx = len(self._reflections) - 1
        for i, other in enumerate(self._reflections[:-1]):
            overlap = _overlap_ratio(new_words, other.content_words)
            if _DEDUP_THRESHOLD <= overlap < PATTERN_SEP_THRESHOLD:
                continue
            if overlap >= PATTERN_SEP_THRESHOLD and overlap < 1.0:
                if mem.importance >= other.importance:
                    mem._importance = min(10, mem.importance + PATTERN_SEP_NUDGE)
                    other._importance = max(1, other.importance - PATTERN_SEP_NUDGE)
                else:
                    other._importance = min(10, other.importance + PATTERN_SEP_NUDGE)
                    mem._importance = max(1, mem.importance - PATTERN_SEP_NUDGE)

        # ── Temporal date extraction (Tulving 1972) ───────────────────
        mem._mentioned_dates = _extract_dates(content)
        idx = len(self._reflections) - 1
        for ds in mem._mentioned_dates:
            if ds not in self._date_index:
                self._date_index[ds] = set()
            self._date_index[ds].add(idx)

        # ── Prospective memory (Einstein & McDaniel 1990) ─────────────
        if mem._mentioned_dates and effective_importance >= PROSPECTIVE_IMPORTANCE_MIN:
            now_date = datetime.now().date()
            for ds in mem._mentioned_dates:
                try:
                    mention_date = datetime.fromisoformat(ds).date()
                except ValueError:
                    continue
                if mention_date > now_date:
                    trigger = datetime(
                        mention_date.year, mention_date.month,
                        mention_date.day, 9, 0)
                    r = Reminder(content, trigger.isoformat())
                    self._reminders.append(r)

        # ── VividEmbed indexing ────────────────────────────────────────
        if self._embed is not None:
            try:
                entry = self._embed.add(
                    content=content, emotion=emotion,
                    importance=effective_importance,
                    stability=mem._stability)
                mem._embed_uid = entry.uid
            except Exception:
                pass

        # ── LLM-inferred relational reasoning ─────────────────────────
        if self._llm_fn and len(self._reflections) >= 5:
            self._infer_relations(len(self._reflections) - 1)

        # ── Auto-consolidation (hippocampal replay) ───────────────────
        self._memories_since_consolidation += 1
        if self._memories_since_consolidation >= AUTO_CONSOLIDATION_INTERVAL:
            self._memories_since_consolidation = 0
            self.muninn()
            self._compress_to_gist()
            self.chunk_memories()
            self._build_yggdrasil()

        return mem

    # ──────────────────────────────────────────────────────────────────
    #  Core: remember_visual (Kosslyn 1980 — Mental Imagery)
    # ──────────────────────────────────────────────────────────────────

    def remember_visual(
        self,
        image_data: bytes,
        description: str,
        emotion: str = "neutral",
        importance: int = 5,
        why_saved: str = "",
        source: str = "visual",
    ) -> Memory:
        """Store a visual memory with a compressed image attachment."""
        if not self._visual_enabled:
            return self.remember(
                content=f"[image] {description}",
                emotion=emotion, importance=importance,
                source=source, why_saved=why_saved)

        webp_bytes, dimensions = _compress_image(image_data)
        img_hash = _visual_hash(webp_bytes)
        img_path = self._visual_dir / f"{img_hash}.webp"
        if not img_path.exists():
            img_path.write_bytes(webp_bytes)

        mem = self.remember(
            content=description,
            emotion=emotion, importance=importance,
            source=source, why_saved=why_saved)

        mem._visual_hash = img_hash
        mem._visual_description = description
        mem._visual_dimensions = dimensions

        self._audit.log("visual_memory", emotion=emotion,
                        details={"hash": img_hash,
                                 "importance": importance})
        return mem

    def get_visual(self, memory: Memory) -> dict:
        """Retrieve a visual memory's image data with fading applied."""
        result: dict[str, Any] = {
            "available": False,
            "clarity": memory.visual_clarity,
            "description": memory._visual_description,
            "image_bytes": None,
            "dimensions": memory._visual_dimensions,
            "hash": memory._visual_hash,
        }

        if not memory.has_visual:
            return result

        img_path = self._visual_dir / f"{memory._visual_hash}.webp"
        if not img_path.exists():
            return result

        raw = img_path.read_bytes()
        clarity = memory.visual_clarity

        if clarity == "vivid":
            result["image_bytes"] = raw
            result["available"] = True
        elif clarity == "faded":
            result["image_bytes"] = _decompress_image(
                raw, quality=VISUAL_QUALITY_FADED)
            result["available"] = True

        return result

    def forget_visual(self, memory: Memory) -> bool:
        """Remove the visual attachment from a memory."""
        if not memory.has_visual:
            return False
        img_path = self._visual_dir / f"{memory._visual_hash}.webp"
        refs = sum(1 for m in self._reflections
                   if m._visual_hash == memory._visual_hash)
        for mlist in self._social.values():
            refs += sum(1 for m in mlist
                        if m._visual_hash == memory._visual_hash)
        if refs <= 1 and img_path.exists():
            img_path.unlink()
        memory._visual_hash = ""
        memory._visual_dimensions = (0, 0)
        return True

    # ──────────────────────────────────────────────────────────────────
    #  Core: update_mood
    # ──────────────────────────────────────────────────────────────────

    def update_mood(self, emotions: list[str]):
        """Shift mood toward given emotion labels using EMA blending."""
        if not emotions:
            return
        vectors = [_emotion_to_vector(e) for e in emotions]
        vectors = [v for v in vectors if v is not None]
        if not vectors:
            return
        avg = tuple(
            sum(v[i] for v in vectors) / len(vectors) for i in range(3))
        mods = self._chemistry.get_modifiers()
        alpha = 0.3 * mods.get("mood_decay_mult", 1.0)
        alpha = max(0.1, min(0.5, alpha))
        self._mood = tuple(
            round(self._mood[i] * (1 - alpha) + avg[i] * alpha, 4)
            for i in range(3))
        for emo in emotions:
            self._chemistry.on_emotion(emo)
        self._audit.log("mood_shift", emotion=_closest_emotion(self._mood),
                        source="conversation",
                        details={"emotions": emotions})

    # ──────────────────────────────────────────────────────────────────
    #  Social impressions
    # ──────────────────────────────────────────────────────────────────

    def add_social_impression(self, entity: str, content: str,
                              emotion: str = "neutral",
                              importance: int = 5,
                              why_saved: str = "") -> Memory:
        """Store a memory about someone."""
        mods = self._chemistry.get_modifiers()
        combined = mods["encoding_boost"] * mods.get("social_boost", 1.0)
        eff_imp = max(1, min(10, round(importance * combined)))
        self._chemistry.on_emotion(emotion)

        if entity not in self._social:
            self._social[entity] = []

        mem = Memory(content=content, emotion=emotion,
                     importance=eff_imp, source="social",
                     entity=entity, why_saved=why_saved)
        mem._encoding_mood = self._mood
        self._social[entity].append(mem)
        return mem

    # ──────────────────────────────────────────────────────────────────
    #  Anchor + cherished management
    # ──────────────────────────────────────────────────────────────────

    def promote_to_anchor(self, memory: Memory) -> bool:
        """Mark a memory as a formative anchor (resists full decay)."""
        if memory._anchor:
            return False
        all_mems = list(self._reflections)
        for mlist in self._social.values():
            all_mems.extend(mlist)
        if memory not in all_mems:
            return False
        memory._anchor = True
        memory._stability = max(memory._stability, ANCHOR_STABILITY_FLOOR)
        return True

    def cherish(self, memory: Memory) -> bool:
        """Mark a memory as a sentimental favourite."""
        if memory._cherished:
            return False
        all_mems = list(self._reflections)
        for mlist in self._social.values():
            all_mems.extend(mlist)
        if memory not in all_mems:
            return False
        memory._cherished = True
        return True

    def uncherish(self, memory: Memory) -> bool:
        """Remove the cherished mark."""
        if not memory._cherished:
            return False
        memory._cherished = False
        return True

    def reframe(self, memory: Memory, new_emotion: str,
                reason: str = "") -> bool:
        """Deliberately shift a memory's emotion (intentional reframe)."""
        all_mems = list(self._reflections)
        for mlist in self._social.values():
            all_mems.extend(mlist)
        if memory not in all_mems:
            return False
        old_emotion = memory.emotion
        new_pad = _emotion_to_vector(new_emotion)
        if new_pad is None:
            return False
        memory.emotion = new_emotion
        memory._emotion_pad = new_pad
        memory._reframed = True
        memory._reframe_reason = reason or f"reframed from {old_emotion}"
        self._audit.log(
            "intentional_reframe",
            emotion=new_emotion,
            source="reframe",
            details={
                "old_emotion": old_emotion,
                "new_emotion": new_emotion,
                "original_emotion": memory.original_emotion,
                "reason": memory._reframe_reason,
                "content_preview": memory.content[:60],
            })
        return True

    def reflect_on_cherished(self) -> list[Memory]:
        """Deliberately revisit cherished memories (photo album moment)."""
        cherished = [
            m for m in self._reflections if m._cherished]
        for mlist in self._social.values():
            cherished.extend(m for m in mlist if m._cherished)
        if not cherished:
            return []
        for mem in cherished:
            self._touch_memory(mem)
        if self._chemistry.enabled:
            self._chemistry.on_emotion("nostalgic", 0.3)
        return sorted(cherished, key=lambda m: m.vividness, reverse=True)

    def relive(self, memory: Memory) -> dict:
        """Mental Time Travel — experientially re-enter a past memory."""
        self._touch_memory(memory)

        old_mood = self._mood
        encoding_mood = memory._encoding_mood
        if encoding_mood and any(v != 0 for v in encoding_mood):
            alpha = 0.6
            self._mood = tuple(
                round(old_mood[i] * (1 - alpha) + encoding_mood[i] * alpha, 4)
                for i in range(3))

        if self._chemistry.enabled:
            emo = memory.emotion.lower()
            event_map = {
                "joy": "reward", "happiness": "reward",
                "excitement": "surprise", "surprise": "surprise",
                "love": "social_bond", "gratitude": "social_bond",
                "trust": "comfort", "nostalgia": "comfort",
                "sadness": "loss", "grief": "loss",
                "fear": "threat", "anxiety": "threat",
                "anger": "betrayal",
                "loneliness": "loneliness",
                "pride": "achievement", "satisfaction": "achievement",
            }
            event_type = event_map.get(emo)
            if event_type:
                self._chemistry.on_event(event_type, 0.4)

        try:
            idx = self._reflections.index(memory)
        except ValueError:
            idx = -1

        connected: list[Memory] = []
        if idx >= 0:
            edges = self._yggdrasil.get(idx, [])
            for target_idx, edge_type, strength in edges:
                if target_idx < len(self._reflections):
                    neighbour = self._reflections[target_idx]
                    for w in _resonance_words(neighbour.content):
                        self._priming_buffer[w] = max(
                            self._priming_buffer.get(w, 0.0),
                            strength)
                    connected.append(neighbour)

        arc = memory._arc_position or "unclassified"
        drift_info = None
        if memory.has_drifted:
            drift_info = {
                "original_emotion": memory._original_emotion,
                "current_emotion": memory.emotion,
                "magnitude": round(memory.drift_magnitude, 3),
            }

        return {
            "memory": memory,
            "gist": memory.gist,
            "emotion": memory.emotion,
            "original_emotion": memory.original_emotion,
            "encoding_mood": encoding_mood,
            "restored_mood": self._mood,
            "previous_mood": old_mood,
            "arc_position": arc,
            "is_flashbulb": memory._is_flashbulb,
            "is_cherished": memory._cherished,
            "vividness": round(memory.vividness, 3),
            "drift": drift_info,
            "connected_memories": [m.gist for m in connected],
            "connected_count": len(connected),
        }

    # ──────────────────────────────────────────────────────────────────
    #  VividEmbed advanced retrieval
    # ──────────────────────────────────────────────────────────────────

    def query_by_emotion(self, emotion: str, top_k: int = 5,
                         min_importance: int = 0) -> list[dict]:
        """Find memories by emotional similarity in PAD space."""
        if self._embed is None:
            return []
        try:
            return self._embed.query_by_emotion(
                emotion, top_k=top_k, min_importance=min_importance)
        except Exception:
            return []

    def find_contradictions(self, text: str, emotion: str = "neutral",
                            threshold: float = 0.70) -> list[dict]:
        """Find stored memories that might contradict the given text."""
        if self._embed is None:
            return []
        try:
            return self._embed.find_contradictions(
                text, emotion=emotion, threshold=threshold)
        except Exception:
            return []

    def update_importance(self, memory: Memory,
                          new_importance: int) -> bool:
        """Update a memory's importance and sync to VividEmbed."""
        memory.importance = max(1, min(10, new_importance))
        if self._embed is not None and memory._embed_uid:
            try:
                self._embed.update_importance(
                    memory._embed_uid, memory.importance)
            except Exception:
                pass
        return True
