"""Wraps Mimir for the Playground chat loop.

Provides persona-aware memory context, mood tracking, neurochemistry
ticking, and periodic consolidation — all driven by the active preset.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Any

# Ensure Mimir is importable
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from Mimir import Mimir  # type: ignore

# ── lightweight keyword-based emotion detector ────────────────────────

_EMOTION_KEYWORDS: dict[str, list[str]] = {
    "happy":        ["happy", "glad", "great", "awesome", "wonderful", "amazing", "love it", "fantastic", "yay"],
    "excited":      ["excited", "thrilled", "pumped", "can't wait", "omg", "wow"],
    "grateful":     ["thank", "thanks", "grateful", "appreciate", "thankful"],
    "amused":       ["lol", "haha", "funny", "hilarious", "lmao", "laughing", "rofl"],
    "curious":      ["curious", "wonder", "how does", "what if", "why does", "interesting", "tell me"],
    "sad":          ["sad", "depressed", "unhappy", "heartbroken", "miss you", "crying", "cried"],
    "anxious":      ["anxious", "worried", "nervous", "scared", "afraid", "panic", "stress"],
    "frustrated":   ["frustrated", "annoying", "annoyed", "ugh", "damn", "stupid", "broken"],
    "angry":        ["angry", "furious", "pissed", "hate", "rage", "mad at"],
    "confused":     ["confused", "don't understand", "lost", "what do you mean", "huh", "unclear"],
    "nostalgic":    ["remember when", "used to", "nostalgia", "back in", "good old", "miss the"],
    "hopeful":      ["hope", "hopefully", "looking forward", "optimistic", "fingers crossed"],
    "proud":        ["proud", "accomplished", "nailed it", "did it", "achievement"],
    "lonely":       ["lonely", "alone", "nobody", "no one", "isolated"],
    "inspired":     ["inspired", "motivation", "inspired by", "creative", "idea"],
    "peaceful":     ["calm", "peaceful", "relaxed", "chill", "serene", "at ease"],
    "hurt":         ["hurt", "betrayed", "let down", "disappointed in"],
    "warm":         ["sweet", "kind", "caring", "love you", "heart", "wholesome"],
    "reflective":   ["thinking about", "reflecting", "looking back", "pondering"],
}


def detect_emotions(text: str, top_k: int = 3) -> list[str]:
    """Detect emotions from text via keyword matching. Returns top-k labels."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for emotion, keywords in _EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                scores[emotion] = scores.get(emotion, 0) + 1
    if not scores:
        return ["neutral"]
    ranked = sorted(scores, key=scores.get, reverse=True)
    return ranked[:top_k]


def estimate_importance(user_text: str, response_text: str) -> int:
    """Heuristic importance scoring (1-10)."""
    score = 5
    lower = user_text.lower()
    # Personal revelations
    if any(w in lower for w in ["i feel", "i love", "i hate", "my family",
                                 "my life", "i'm scared", "i'm worried"]):
        score += 2
    # Questions about the AI itself
    if any(w in lower for w in ["do you remember", "what do you think",
                                 "how do you feel"]):
        score += 1
    # Very short / trivial
    if len(user_text) < 20:
        score -= 1
    # Very long / detailed
    if len(user_text) > 300:
        score += 1
    return max(1, min(10, score))


class MemoryManager:
    """Full-featured wrapper around Mimir for the playground."""

    # Number of turns between automatic consolidation
    _CONSOLIDATION_INTERVAL = 25
    _HUGINN_INTERVAL = 10
    _VOLVA_INTERVAL = 30   # Völva dream synthesis every 30 turns

    def __init__(self, profile_dir: str | Path, chemistry: bool = True,
                 llm_fn=None):
        self._dir = Path(profile_dir) / "mimir_data"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._mimir = Mimir(
            data_dir=str(self._dir),
            chemistry=chemistry,
            llm_fn=llm_fn,
        )
        self._turn_count = 0
        self._last_chemistry_tick = time.time()

    # ── store ─────────────────────────────────────────────────────────

    def remember(self, content: str, emotion: str = "neutral",
                 importance: int = 5, source: str = "playground",
                 why_saved: str = "") -> dict:
        mem = self._mimir.remember(
            content=content, emotion=emotion,
            importance=importance, source=source,
            why_saved=why_saved,
        )
        return mem.to_dict()

    def remember_exchange(self, user_msg: str, assistant_msg: str,
                          emotion: str = "neutral",
                          importance: int = 5) -> dict:
        """Store a user<>assistant exchange as a single memory."""
        summary = f"User said: {user_msg[:200]}"
        if len(assistant_msg) > 300:
            assistant_brief = assistant_msg[:300] + "..."
        else:
            assistant_brief = assistant_msg
        summary += f"\nI responded: {assistant_brief}"
        return self.remember(
            content=summary, emotion=emotion,
            importance=importance, source="conversation",
            why_saved="conversation exchange",
        )

    # ── mood & neurochemistry ─────────────────────────────────────────

    def update_mood(self, emotions: list[str]) -> None:
        """Shift mood toward the given emotion labels (EMA blending).
        Also ticks neurochemistry based on elapsed time."""
        self._mimir.update_mood(emotions)
        self._tick_chemistry()

    def _tick_chemistry(self) -> None:
        """Tick neurochemistry based on real elapsed time."""
        now = time.time()
        dt_minutes = (now - self._last_chemistry_tick) / 60.0
        self._last_chemistry_tick = now
        if dt_minutes > 0.1:  # at least 6 seconds
            try:
                self._mimir.chemistry.tick(dt_minutes)
            except Exception:
                pass

    def on_event(self, event_type: str, intensity: float = 0.7) -> None:
        """Register a neurochemistry event (surprise, conflict, warmth, etc.)."""
        try:
            self._mimir.chemistry.on_event(event_type, intensity)
        except Exception:
            pass

    def get_mood(self) -> dict:
        """Return current mood state with label, PAD vector, and chemistry."""
        result = {
            "mood_label": self._mimir.mood_label,
            "mood_pad": list(self._mimir.mood),
            "session_count": self._mimir.session_count,
        }
        try:
            result["chemistry"] = {
                "levels": self._mimir.chemistry.levels,
                "baselines": self._mimir.chemistry.baselines,
                "description": self._mimir.chemistry.describe(),
                "is_dampened": self._mimir.is_dampened,
                "modifiers": self._mimir.chemistry.get_modifiers(),
            }
        except Exception:
            result["chemistry"] = None
        return result

    # ── LLM-driven memory curation ────────────────────────────────────

    async def llm_curate_memory(
        self,
        user_msg: str,
        assistant_msg: str,
        backend,
    ) -> dict | None:
        """Ask the active LLM to decide whether an exchange is worth
        remembering and how to tag it.

        Returns a dict::

            {
                "should_remember": bool,
                "emotion":         str,   # one of the known emotion labels
                "importance":      int,   # 1–10
                "reason":          str,   # brief rationale
            }

        Returns ``None`` on any error (caller should fall back to
        heuristics in that case).
        """
        prompt = (
            "You are a memory curator for an AI with persistent memory.\n"
            "Decide whether this conversation exchange is worth remembering"
            " long-term.\n\n"
            f"User: {user_msg[:400]}\n"
            f"Assistant: {assistant_msg[:400]}\n\n"
            "Reply ONLY with valid JSON (no other text):\n"
            '{"should_remember": true, "emotion": "curious",'
            ' "importance": 7, "reason": "User revealed a personal goal"}\n\n'
            "Available emotions: neutral, happy, sad, curious, anxious,"
            " excited, grateful, frustrated, angry, amused, confused,"
            " nostalgic, hopeful, proud, lonely, inspired, peaceful,"
            " hurt, warm, reflective\n"
            "Importance scale: 1 (trivial) to 10 (deeply significant).\n"
            "Set should_remember to false for purely factual Q&A exchanges"
            " or identical repetitions."
        )
        try:
            import json as _json
            import re as _re

            messages = [{"role": "user", "content": prompt}]
            result = ""
            async for token in backend.generate(
                messages=messages,
                system_prompt="",
                temperature=0.1,
                max_tokens=80,
                model="",
            ):
                result += token

            # Extract the first JSON object from the response
            m = _re.search(r"\{.*?\}", result, _re.DOTALL)
            if not m:
                return None
            data = _json.loads(m.group())

            # Normalise / validate
            valid_emotions = set(_EMOTION_KEYWORDS.keys()) | {"neutral"}
            emotion = data.get("emotion", "neutral")
            if emotion not in valid_emotions:
                emotion = "neutral"
            importance = int(data.get("importance", 5))
            importance = max(1, min(10, importance))

            return {
                "should_remember": bool(data.get("should_remember", True)),
                "emotion": emotion,
                "importance": importance,
                "reason": str(data.get("reason", ""))[:200],
            }
        except Exception:
            return None

    # ── per-turn processing (called after each chat exchange) ─────────

    def process_turn(self, user_msg: str, assistant_msg: str,
                     preset: dict,
                     curation: dict | None = None,
                     skip_save: bool = False) -> dict:
        """Full post-turn processing: detect emotion, update mood,
        tick chemistry, and periodically consolidate.

        Memory saving is handled by the caller (server.py parses
        model-authored <remember> tags). Pass skip_save=True to
        suppress the legacy auto-save path entirely.

        If *curation* is provided it still overrides the emotion/importance
        used for mood-update purposes (e.g. from reflect/edit_memories).

        Returns dict with emotion, importance, mood info."""
        combined_text = user_msg + " " + assistant_msg

        if curation is not None:
            primary_emotion = curation.get("emotion", "neutral")
            importance = curation.get("importance", 5)
            emotions = [primary_emotion]
            should_remember = curation.get("should_remember", True) and not skip_save
        else:
            emotions = detect_emotions(combined_text)
            primary_emotion = emotions[0]
            importance = estimate_importance(user_msg, assistant_msg)
            emotion_weight = preset.get("emotion_weight", 0.5)
            if primary_emotion not in ("neutral", "reflective", "thoughtful"):
                importance = min(10, int(importance + emotion_weight * 2))
            should_remember = not skip_save

        if should_remember:
            why = curation.get("reason", "conversation exchange") if curation else "conversation exchange"
            mem_content = f"User said: {user_msg[:200]}"
            if len(assistant_msg) > 300:
                assistant_brief = assistant_msg[:300] + "..."
            else:
                assistant_brief = assistant_msg
            mem_content += f"\nI responded: {assistant_brief}"
            self.remember(
                content=mem_content,
                emotion=primary_emotion,
                importance=importance,
                source="conversation",
                why_saved=why,
            )

        # Update mood (also ticks chemistry internally)
        self.update_mood(emotions)

        # Detect neurochemistry events from content
        lower = combined_text.lower()
        if any(w in lower for w in ["surprise", "unexpected", "wow", "omg"]):
            self.on_event("surprise", 0.6)
        if any(w in lower for w in ["conflict", "argue", "disagree", "fight"]):
            self.on_event("conflict", 0.5)
        if any(w in lower for w in ["love", "care", "hug", "friend", "together"]):
            self.on_event("warmth", 0.5)
        if any(w in lower for w in ["new", "novel", "first time", "discover"]):
            self.on_event("novelty", 0.4)
        if any(w in lower for w in ["solved", "fixed", "done", "completed", "success"]):
            self.on_event("achievement", 0.5)
        if any(w in lower for w in ["lost", "died", "gone", "miss", "grief"]):
            self.on_event("loss", 0.5)
        if any(w in lower for w in ["haha", "lol", "funny", "joke", "lmao"]):
            self.on_event("humor", 0.4)

        # Increment turn counter
        self._turn_count += 1

        # Periodic consolidation (muninn)
        consolidated = None
        if self._turn_count % self._CONSOLIDATION_INTERVAL == 0:
            try:
                consolidated = self._mimir.muninn()
            except Exception:
                pass

        # Run huginn every 10 turns for pattern detection
        insights = None
        if self._turn_count % 10 == 0:
            try:
                self._mimir.huginn()
            except Exception:
                pass

        # Run Völva dream synthesis every 30 turns (organic cross-memory insight)
        if self._turn_count % self._VOLVA_INTERVAL == 0:
            try:
                self._mimir.volva_dream()
            except Exception:
                pass

        self.save()

        return {
            "emotion": primary_emotion,
            "emotions": emotions,
            "importance": importance,
            "mood_label": self._mimir.mood_label,
            "mood_pad": list(self._mimir.mood),
            "consolidated": consolidated,
        }

    # ── preset-aware context building ─────────────────────────────────

    def get_context_for_preset(self, preset: dict,
                               conversation_context: str = "",
                               entity: str = "") -> str:
        """Build memory context tailored to the active preset type."""
        preset_label = preset.get("label", "").lower()

        # All presets get the core context block from Mimir
        # (includes mood, active memories, lessons, reminders, temporal,
        #  neurochemistry, drift alerts, resonant memories, insights)
        context = self._mimir.get_context_block(
            current_entity=entity,
            conversation_context=conversation_context,
        )

        extra_parts: list[str] = []

        # Agent / Assistant: add task & project context
        if preset.get("task_priority"):
            overview = self._mimir.get_project_overview()
            if overview.get("tasks_active", 0) > 0:
                extra_parts.append("=== ACTIVE TASKS ===")
                for desc in overview["active_task_descriptions"]:
                    extra_parts.append(f"- {desc}")
                extra_parts.append(
                    f"({overview['tasks_completed']} completed, "
                    f"{overview['tasks_failed']} failed, "
                    f"{overview['solutions_stored']} solutions stored)")
                extra_parts.append("")

            # Include solution patterns for agent
            if conversation_context:
                solutions = self._mimir.find_solutions(
                    conversation_context, top_k=2)
                if solutions:
                    extra_parts.append("=== RELEVANT SOLUTIONS ===")
                    for s in solutions:
                        extra_parts.append(
                            f"- Problem: {s.problem[:80]}")
                        extra_parts.append(
                            f"  Solution: {s.solution[:120]}")
                    extra_parts.append("")

        # Character: add extra emotional depth
        if preset_label == "character":
            # Surface cherished memories via reflect_on_cherished
            try:
                cherished = self._mimir.reflect_on_cherished()
                if cherished:
                    extra_parts.append("=== CHERISHED MEMORIES ===")
                    for m in cherished[:3]:
                        extra_parts.append(f"- {m.gist} ({m.emotion})")
                    extra_parts.append("")
            except Exception:
                pass

            # Extra drift awareness for deep immersion
            try:
                drifted = self._mimir.detect_drift()
                if drifted:
                    extra_parts.append("=== EMOTIONAL GROWTH ===")
                    for m in drifted[:2]:
                        extra_parts.append(
                            f"- '{m.gist[:50]}': was {m.original_emotion} "
                            f"-> now {m.emotion}")
                    extra_parts.append("")
            except Exception:
                pass

        # Assistant: add short-term facts
        if preset_label == "assistant":
            try:
                facts = self._mimir.get_facts()
                if facts:
                    extra_parts.append("=== SHORT-TERM FACTS ===")
                    for f in facts[:10]:
                        extra_parts.append(
                            f"- {f.entity}: {f.attribute} = {f.value}")
                    extra_parts.append("")
            except Exception:
                pass

        if extra_parts:
            context += "\n" + "\n".join(extra_parts)

        return context

    # ── retrieve ──────────────────────────────────────────────────────

    def recall(self, context: str, limit: int = 10) -> list[dict]:
        memories = self._mimir.recall(context, limit=limit)
        return [m.to_dict() for m in memories]

    def get_context_block(self, entity: str = "",
                          conversation_context: str = "") -> str:
        return self._mimir.get_context_block(
            current_entity=entity,
            conversation_context=conversation_context,
        )

    # ── lifecycle ─────────────────────────────────────────────────────

    def save(self) -> None:
        self._mimir.save()

    def sleep(self, hours: float = 8.0) -> None:
        self._mimir.sleep_reset(hours)
        # Also enrich the Yggdrasil graph if LLM is available
        try:
            self._mimir.enrich_yggdrasil(batch_size=10)
        except Exception:
            pass
        self._mimir.save()

    def bump_session(self) -> int:
        return self._mimir.bump_session()

    # ── consolidation & insights ──────────────────────────────────────

    def run_consolidation(self) -> dict:
        """Run Muninn consolidation daemon."""
        try:
            return self._mimir.muninn()
        except Exception as e:
            return {"error": str(e)}

    def run_huginn(self) -> list[dict]:
        """Run Huginn pattern detection."""
        try:
            insights = self._mimir.huginn()
            return [m.to_dict() for m in insights]
        except Exception as e:
            return [{"error": str(e)}]

    def run_dream(self) -> list[dict]:
        """Run Volva dream synthesis."""
        try:
            dreams = self._mimir.volva_dream()
            return [m.to_dict() for m in dreams]
        except Exception as e:
            return [{"error": str(e)}]

    # ── diagnostics ───────────────────────────────────────────────────

    def stats(self) -> dict:
        s = self._mimir.stats()
        s["turn_count"] = self._turn_count
        return s

    def emotion_distribution(self) -> dict:
        return self._mimir.emotion_distribution()

    def neurochemistry_snapshot(self) -> dict:
        return self._mimir.neurochemistry_snapshot()

    # ── social ────────────────────────────────────────────────────────

    def add_social(self, entity: str, content: str,
                   emotion: str = "neutral", importance: int = 5,
                   why_saved: str = "") -> dict:
        mem = self._mimir.add_social_impression(
            entity=entity, content=content, emotion=emotion,
            importance=importance, why_saved=why_saved,
        )
        return mem.to_dict()

    def get_social_impressions(self, entity: str = "") -> list[dict]:
        """Return social impressions, optionally filtered by entity."""
        social = self._mimir.social_impressions  # dict: entity -> [Memory]
        results = []
        for ent, mems in social.items():
            if entity and ent.lower() != entity.lower():
                continue
            for m in mems:
                d = m.to_dict()
                d["entity_key"] = ent
                results.append(d)
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return results

    # ── facts ─────────────────────────────────────────────────────────

    def add_fact(self, entity: str, attribute: str, value: str) -> dict:
        f = self._mimir.add_fact(entity, attribute, value)
        return f.to_dict()

    def get_facts(self, entity: str = "") -> list[dict]:
        facts = self._mimir.get_facts(entity)
        return [f.to_dict() for f in facts]

    # ── tasks ─────────────────────────────────────────────────────────

    def start_task(self, description: str, priority: int = 5,
                   project: str = "") -> dict:
        t = self._mimir.start_task(description, priority=priority, project=project)
        return {"task_id": t.task_id, "description": t.description,
                "priority": t.priority, "status": t.status}

    def complete_task(self, task_id: str, outcome: str = "") -> bool:
        return self._mimir.complete_task(task_id, outcome)

    def get_active_tasks(self) -> list[dict]:
        tasks = self._mimir.get_active_tasks()
        return [{"task_id": t.task_id, "description": t.description,
                 "priority": t.priority, "status": t.status} for t in tasks]

    # ── lessons ───────────────────────────────────────────────────────

    def get_active_lessons(self) -> list[dict]:
        lessons = self._mimir.get_active_lessons()
        return [{"id": l.id, "topic": l.topic, "strategy": l.strategy,
                 "importance": l.importance,
                 "failures": l.consecutive_failures} for l in lessons]

    def add_lesson(self, topic: str, context_trigger: str,
                   strategy: str, importance: int = 5) -> dict:
        """Add a lesson derived from experience."""
        lesson = self._mimir.add_lesson(
            topic=topic,
            context_trigger=context_trigger,
            strategy=strategy,
            importance=importance,
        )
        return {"id": lesson.id, "topic": lesson.topic,
                "context_trigger": lesson.context_trigger,
                "strategy": lesson.strategy,
                "importance": lesson.importance,
                "failures": lesson.consecutive_failures}

    def record_outcome(self, lesson_id: str, action: str,
                       result: str, diagnosis: str = "") -> bool:
        """Record an attempt outcome against a lesson."""
        try:
            self._mimir.record_outcome(lesson_id, action, result, diagnosis)
            self.save()
            return True
        except Exception:
            return False

    # ── reminders ────────────────────────────────────────────────────

    def set_reminder(self, text: str, hours: float = 24.0) -> dict:
        """Create a timed reminder."""
        reminder = self._mimir.set_reminder(text, hours)
        return {"text": reminder.text,
                "trigger_at": reminder.trigger_at,
                "created": reminder.created,
                "fired": reminder.fired}

    def get_reminders(self, include_fired: bool = False) -> list[dict]:
        """Return pending (and optionally fired) reminders."""
        all_reminders = self._mimir._reminders
        result = []
        for r in all_reminders:
            if r.fired and not include_fired:
                continue
            result.append({"text": r.text,
                           "trigger_at": r.trigger_at,
                           "created": r.created,
                           "fired": r.fired,
                           "is_due": r.is_due})
        return result

    # ── advanced memory ops ───────────────────────────────────────────

    def reframe_memory(self, index: int, new_emotion: str,
                       reason: str = "") -> dict | None:
        """Intentionally reframe a memory's emotion — logged to audit."""
        refs = self._mimir._reflections
        if index < 0 or index >= len(refs):
            return None
        mem = refs[index]
        self._mimir.reframe(mem, new_emotion, reason)
        self.save()
        return mem.to_dict()

    def relive_memory(self, index: int) -> dict | None:
        """Mental Time Travel: touch memory, shift mood, fire spreading activation."""
        refs = self._mimir._reflections
        if index < 0 or index >= len(refs):
            return None
        mem = refs[index]
        try:
            result = self._mimir.relive(mem)
            return result
        except Exception:
            return {"memory": mem.to_dict()}

    def enrich_yggdrasil(self, batch_size: int = 20) -> dict:
        """Run LLM-inferred graph enrichment on recent memories."""
        try:
            added = self._mimir.enrich_yggdrasil(batch_size)
            return {"edges_added": added}
        except Exception as e:
            return {"error": str(e)}

    async def reflect(self, backend) -> dict:
        """Ask the LLM to reflect on its memories and store insights."""
        try:
            # Build a compact snapshot of recent memories for the LLM
            recent = self._mimir._reflections[-20:]
            mem_lines = "\n".join(
                f"- [{m.emotion}, imp={m.importance}] {m.gist}"
                for m in recent
            )
            stats = self._mimir.stats()
            prompt = (
                "You are an AI reviewing your own long-term memory.\n"
                f"You have {stats.get('total_reflections', 0)} memories stored.\n"
                f"Current mood: {self._mimir.mood_label}\n\n"
                "Recent memories:\n"
                f"{mem_lines}\n\n"
                "Reflect on 2-3 meaningful patterns, themes, or gaps you notice "
                "in your memory. What does this tell you about your ongoing "
                "experiences and growth? Be concise and genuine."
            )
            messages = [{"role": "user", "content": prompt}]
            result = ""
            async for token in backend.generate(
                messages=messages,
                system_prompt="",
                temperature=0.7,
                max_tokens=300,
                model="",
            ):
                result += token

            if result.strip():
                # Store reflection as a Huginn insight
                mem = self._mimir.remember(
                    content=f"[self-reflection] {result.strip()}",
                    emotion="reflective",
                    importance=6,
                    source="huginn",
                    why_saved="periodic LLM self-reflection",
                )
                self.save()
                return {"reflection": result.strip(),
                        "stored": True}
            return {"reflection": "", "stored": False}
        except Exception as e:
            return {"error": str(e)}

    async def edit_memories(self, backend, instruction: str = "") -> dict:
        """LLM-driven bulk memory curation: promote, demote, forget, update."""
        try:
            # Build a numbered list of recent memories
            recent = self._mimir._reflections[-20:]
            mem_lines = "\n".join(
                f"[{i}] emotion={m.emotion}, imp={m.importance}, "
                f"src={m.source}: {m.gist}"
                for i, m in enumerate(recent)
            )
            if not instruction:
                instruction = (
                    "Review these memories and organically curate them. "
                    "Forget trivial ones, promote important ones, update "
                    "emotions where they've shifted."
                )
            prompt = (
                f"You are curating your own memory store.\n\n"
                f"Instruction: {instruction}\n\n"
                f"Memories (indices 0-{len(recent)-1}):\n{mem_lines}\n\n"
                "Reply ONLY with a JSON array of operations:\n"
                '[{"op": "FORGET", "idx": 2}, {"op": "PROMOTE", "idx": 5}, '
                '{"op": "DEMOTE", "idx": 1}, '
                '{"op": "UPDATE", "idx": 3, "emotion": "nostalgic", '
                '"importance": 8}]\n'
                "Valid ops: FORGET, PROMOTE (importance+2), DEMOTE (importance-2), UPDATE.\n"
                "Only include memories that genuinely need changing. "
                "Return [] if nothing needs changing."
            )
            import json as _json
            import re as _re
            messages = [{"role": "user", "content": prompt}]
            result = ""
            async for token in backend.generate(
                messages=messages,
                system_prompt="",
                temperature=0.1,
                max_tokens=400,
                model="",
            ):
                result += token

            m = _re.search(r"\[.*?\]", result, _re.DOTALL)
            if not m:
                return {"promoted": 0, "demoted": 0, "forgotten": 0, "updated": 0}
            ops = _json.loads(m.group())

            counts = {"promoted": 0, "demoted": 0, "forgotten": 0, "updated": 0}
            base = len(self._mimir._reflections) - len(recent)
            to_forget_real = []

            for op in ops:
                idx = op.get("idx")
                if idx is None or not isinstance(idx, int):
                    continue
                real_idx = base + idx
                if real_idx < 0 or real_idx >= len(self._mimir._reflections):
                    continue
                mem = self._mimir._reflections[real_idx]
                # Never touch protected memories
                if mem._is_flashbulb or mem._anchor or mem._cherished:
                    continue
                op_type = op.get("op", "").upper()
                if op_type == "FORGET":
                    to_forget_real.append(real_idx)
                    counts["forgotten"] += 1
                elif op_type == "PROMOTE":
                    mem._importance = min(10, mem.importance + 2)
                    counts["promoted"] += 1
                elif op_type == "DEMOTE":
                    mem._importance = max(1, mem.importance - 2)
                    counts["demoted"] += 1
                elif op_type == "UPDATE":
                    if "emotion" in op:
                        mem.emotion = str(op["emotion"])
                    if "importance" in op:
                        mem._importance = max(1, min(10, int(op["importance"])))
                    counts["updated"] += 1

            # Remove forgotten in reverse order to preserve indices
            for real_idx in sorted(to_forget_real, reverse=True):
                self._mimir._reflections.pop(real_idx)

            if any(counts.values()):
                self.save()

            return counts
        except Exception as e:
            return {"error": str(e)}

    # ── browse / edit / delete ────────────────────────────────────

    def browse_memories(self, offset: int = 0, limit: int = 50,
                        sort: str = "recent",
                        emotion_filter: str = "",
                        source_filter: str = "",
                        min_importance: int = 0) -> dict:
        """Return a paginated slice of all memories for the browser UI."""
        mems = list(self._mimir._reflections)

        # filters
        if emotion_filter:
            ef = emotion_filter.lower()
            mems = [m for m in mems if m.emotion.lower() == ef]
        if source_filter:
            sf = source_filter.lower()
            mems = [m for m in mems if m.source.lower() == sf]
        if min_importance > 0:
            mems = [m for m in mems if m.importance >= min_importance]

        # sort
        if sort == "recent":
            mems.sort(key=lambda m: m.timestamp, reverse=True)
        elif sort == "oldest":
            mems.sort(key=lambda m: m.timestamp)
        elif sort == "importance":
            mems.sort(key=lambda m: m.importance, reverse=True)
        elif sort == "vividness":
            mems.sort(key=lambda m: getattr(m, '_stability', 0), reverse=True)

        total = len(mems)
        page = mems[offset:offset + limit]

        # Build index map so we can address them for edit/delete
        all_refs = self._mimir._reflections
        results = []
        for m in page:
            d = m.to_dict()
            try:
                d["_index"] = all_refs.index(m)
            except ValueError:
                d["_index"] = -1
            d["cherished"] = getattr(m, '_cherished', False)
            d["anchor"] = getattr(m, '_anchor', False)
            d["vividness"] = round(getattr(m, '_stability', 0), 2)
            results.append(d)

        return {"total": total, "offset": offset, "limit": limit,
                "memories": results}

    def delete_memory(self, index: int) -> bool:
        """Remove a memory by its index in _reflections."""
        refs = self._mimir._reflections
        if 0 <= index < len(refs):
            refs.pop(index)
            self.save()
            return True
        return False

    def update_memory(self, index: int, changes: dict) -> dict | None:
        """Edit a memory's mutable fields (importance, emotion).
        Emotion changes go through mimir.reframe() so they're audit-logged."""
        refs = self._mimir._reflections
        if index < 0 or index >= len(refs):
            return None
        mem = refs[index]
        if "importance" in changes:
            mem._importance = max(1, min(10, int(changes["importance"])))
        if "emotion" in changes:
            new_emotion = str(changes["emotion"])
            reason = changes.get("reason", "user edit")
            try:
                self._mimir.reframe(mem, new_emotion, reason)
            except Exception:
                mem.emotion = new_emotion  # graceful fallback
        self.save()
        return mem.to_dict()

    def toggle_cherish(self, index: int) -> bool | None:
        """Toggle cherished status on a memory."""
        refs = self._mimir._reflections
        if index < 0 or index >= len(refs):
            return None
        mem = refs[index]
        if mem._cherished:
            self._mimir.uncherish(mem)
        else:
            self._mimir.cherish(mem)
        self.save()
        return mem._cherished

    def toggle_anchor(self, index: int) -> bool | None:
        """Toggle anchor status on a memory (uses promote_to_anchor for proper floors)."""
        refs = self._mimir._reflections
        if index < 0 or index >= len(refs):
            return None
        mem = refs[index]
        if mem._anchor:
            mem._anchor = False  # demote
        else:
            try:
                self._mimir.promote_to_anchor(mem)
            except Exception:
                mem._anchor = True
                mem._stability = max(mem._stability, 90.0)
        self.save()
        return mem._anchor

    def export_all(self) -> list[dict]:
        """Export every memory as a list of dicts."""
        return [m.to_dict() for m in self._mimir._reflections]

    def get_unique_emotions(self) -> list[str]:
        """Return sorted list of unique emotion labels in the store."""
        return sorted({m.emotion for m in self._mimir._reflections})

    def get_unique_sources(self) -> list[str]:
        """Return sorted list of unique source labels in the store."""
        return sorted({m.source for m in self._mimir._reflections})

    # ── visualization ─────────────────────────────────────────────────

    def get_graph(self) -> dict:
        """Return all memories with vividness, types, and edges for visualization."""
        mimir = self._mimir
        reflections = mimir.self_reflections
        nodes = []
        for i, m in enumerate(reflections):
            node = {
                "id": i,
                "content": m.content[:120],
                "emotion": m.emotion,
                "importance": m.importance,
                "vividness": round(m.vividness, 3),
                "timestamp": m.timestamp,
                "source": m.source,
                "is_flashbulb": m._is_flashbulb,
                "is_anchor": m._anchor,
                "is_cherished": getattr(m, "_cherished", False),
                "entity": m.entity or "",
                "stability": round(m._stability, 1),
                "access_count": m._access_count,
            }
            nodes.append(node)

        edges = []
        for src_idx, targets in mimir._yggdrasil.items():
            if src_idx >= len(reflections):
                continue
            for target_idx, edge_type, strength in targets:
                if target_idx >= len(reflections):
                    continue
                if src_idx < target_idx:  # avoid duplicates
                    edges.append({
                        "source": src_idx,
                        "target": target_idx,
                        "type": edge_type,
                        "strength": round(strength, 3),
                    })

        # Lessons as separate node type
        lessons = []
        for ls in mimir._lessons:
            lessons.append({
                "id": f"L-{ls.id[:8]}",
                "topic": ls.topic,
                "strategy": ls.strategy[:80],
                "importance": ls.importance,
                "vividness": round(ls.vividness, 3),
                "failures": ls.consecutive_failures,
                "source_idx": ls._source_memory_idx,
            })

        # Tasks
        tasks = []
        for t in mimir._project_tasks:
            tasks.append({
                "task_id": t.task_id,
                "description": t.description[:80],
                "priority": t.priority,
                "status": t.status,
            })

        return {
            "nodes": nodes,
            "edges": edges,
            "lessons": lessons,
            "tasks": tasks,
            "total": len(reflections),
        }

    # ── import ────────────────────────────────────────────────────────

    def import_memory(self, content: str, emotion: str = "neutral",
                      importance: int = 5, source: str = "import",
                      why_saved: str = "imported from external system",
                      timestamp: str = "") -> dict:
        """Import a memory and let Mimir fully index it."""
        mem = self._mimir.remember(
            content=content, emotion=emotion,
            importance=importance, source=source,
            why_saved=why_saved,
        )
        if timestamp:
            mem.timestamp = timestamp
        return mem.to_dict()
