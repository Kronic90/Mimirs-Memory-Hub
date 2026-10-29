"""Wraps Mimir for the Playground chat loop.

Provides persona-aware memory context, mood tracking, neurochemistry
ticking, and periodic consolidation — all driven by the active preset.
"""
from __future__ import annotations

import re
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

# Ensure Mimir is importable
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

try:
    from vividmimir import Mimir  # pip-installed package
except ModuleNotFoundError:
    try:
        from mimir_modular import Mimir  # modular package (local dev)
    except ModuleNotFoundError:
        try:
            from Mimir import Mimir  # type: ignore  # monolith fallback
        except ModuleNotFoundError:
            # Fallback: explicit load from file path (handles case-sensitive FS quirks)
            import importlib.util as _ilu
            _mimir_file = Path(_root) / "Mimir.py"
            if not _mimir_file.exists():
                # Try lowercase on case-sensitive systems
                _mimir_file = Path(_root) / "mimir.py"
            _spec = _ilu.spec_from_file_location("Mimir", str(_mimir_file))
            _mod = _ilu.module_from_spec(_spec)
            sys.modules["Mimir"] = _mod
            _spec.loader.exec_module(_mod)
            Mimir = _mod.Mimir  # type: ignore

# ── lightweight keyword-based emotion detector ────────────────────────

# Covers all ~47 emotions presets.py's _REMEMBER_FMT advertises to the
# model, so detect_emotions() (the auto-detect fallback used when no
# explicit <remember emotion="..."> tag is present) can actually produce
# any of them rather than silently collapsing most to "neutral". Where two
# canonical emotions are near-synonyms (e.g. reflective/thoughtful/
# contemplative), keywords are kept distinct per bucket rather than
# merged, so a bucket can still win on word choice even though the
# emotions themselves are close in meaning.
_EMOTION_KEYWORDS: dict[str, list[str]] = {
    "happy":         ["happy", "glad", "great", "awesome", "wonderful", "amazing", "love it", "fantastic", "yay"],
    "joyful":        ["joyful", "joy", "overjoyed", "pure happiness"],
    "delighted":     ["delighted", "delightful", "so pleased", "charmed"],
    "excited":       ["excited", "pumped", "can't wait", "omg", "wow"],
    "enthusiastic":  ["enthusiastic", "enthusiasm", "psyched", "stoked"],
    "amused":        ["amused", "lol", "haha", "funny", "hilarious", "lmao", "laughing", "rofl"],
    "playful":       ["playful", "teasing", "joking around", "being silly", "goofing around"],
    "proud":         ["proud", "accomplished", "nailed it", "did it", "achievement"],
    "triumphant":    ["triumphant", "triumph", "victorious", "we won", "crushed it"],
    "inspired":      ["inspired", "inspired by", "spark of an idea"],
    "motivated":     ["motivated", "motivation", "determined", "driven", "let's do this"],
    "grateful":      ["thank", "thanks", "thankful", "grateful"],
    "warm":          ["warm", "sweet", "kind", "caring", "love you", "heart", "wholesome"],
    "appreciative":  ["appreciate", "appreciative", "means a lot", "grateful for you"],
    "tender":        ["tender", "tenderly", "gentle with", "soft spot for"],
    "affectionate":  ["affectionate", "affection", "cuddle", "adore you"],
    "hopeful":       ["hopeful", "hope", "hopefully", "looking forward", "optimistic", "fingers crossed"],
    "peaceful":      ["calm", "peaceful", "relaxed", "chill", "at ease"],
    "serene":        ["serene", "serenity", "still and quiet", "zen"],
    "content":       ["content", "satisfied", "comfortable with how things are"],
    "curious":       ["curious", "wonder", "how does", "what if", "why does", "interesting", "tell me"],
    "fascinated":    ["fascinated", "fascinating", "captivated", "intrigued"],
    "thoughtful":    ["thoughtful", "mulling over", "thinking it through"],
    "reflective":    ["reflective", "thinking about", "reflecting", "looking back"],
    "contemplative": ["contemplative", "contemplating", "deep in thought", "sitting with this"],
    "understanding": ["understanding", "that makes sense", "i get it", "see where you're coming from"],
    "nostalgic":     ["nostalgic", "remember when", "used to", "nostalgia", "back in", "good old", "miss the"],
    "bittersweet":   ["bittersweet", "mixed feelings", "happy and sad at the same time"],
    "wistful":       ["wistful", "longing for", "if only"],
    "sad":           ["sad", "miss you", "crying", "cried"],
    "lonely":        ["lonely", "alone", "nobody", "no one"],
    "melancholy":    ["melancholy", "melancholic", "a quiet sadness", "blue today"],
    "disappointed":  ["disappointed", "let down", "expected more", "bummer"],
    "guilty":        ["guilty", "guilt", "my fault", "shouldn't have done that"],
    "insecure":      ["insecure", "not good enough", "self-doubt", "second-guessing myself"],
    "vulnerable":    ["vulnerable", "exposed", "opening up about", "hard to admit"],
    "anxious":       ["anxious", "worried", "nervous", "panic", "stress"],
    "overwhelmed":   ["overwhelmed", "too much", "can't keep up", "drowning in", "swamped"],
    "angry":         ["angry", "furious", "pissed", "hate", "rage", "mad at"],
    "frustrated":    ["frustrated", "annoying", "annoyed", "ugh", "damn", "stupid", "broken"],
    "hurt":          ["hurt", "betrayed"],
    "confused":      ["confused", "don't understand", "lost", "what do you mean", "huh", "unclear"],
    "embarrassed":   ["embarrassed", "embarrassing", "so awkward", "cringe", "mortified"],
    "jealous":       ["jealous", "envious", "envy", "wish i had that"],
    "afraid":        ["afraid", "scared", "terrified", "frightened", "fear"],
    "resentful":     ["resentful", "resentment", "still bitter about", "can't forgive"],
}

# Pre-compiled negation pattern — catches "not", "n't", "never", "no" etc.
_NEGATION_RE = re.compile(
    r"\b(?:not|n't|never|no|neither|nor|don't|doesn't|didn't|isn't|aren't"
    r"|wasn't|weren't|won't|wouldn't|can't|couldn't|shouldn't|barely|hardly)"
    r"\s+",
    re.IGNORECASE,
)

# Normalise emotion aliases → canonical label.
#
# IMPORTANT: every key here must be a word that is NOT itself one of the
# ~47 canonical emotions the system prompts advertise to the model
# (see presets.py's _REMEMBER_FMT). The engine (vividmimir/constants.py's
# EMOTION_VECTORS) already has correct, distinct arousal/valence vectors
# for the full canonical set — aliasing one canonical emotion onto another
# (e.g. "joyful" -> "happy") silently throws that distinction away before
# it ever reaches the engine, which previously caused memories tagged with
# a high-arousal canonical emotion (e.g. "joyful", arousal 0.6) to lose
# flashbulb protection because they got rewritten to a lower-arousal one
# ("happy", arousal 0.4) before the flashbulb threshold check ever saw the
# original label. Only genuinely non-canonical, free-form synonyms a model
# might use (e.g. "cheerful", "thrilled", "scared") belong in this table.
_EMOTION_ALIASES: dict[str, str] = {
    "cheerful": "happy", "elated": "happy", "ecstatic": "happy",
    "thrilled": "excited", "amazed": "excited", "astonished": "excited",
    "worried": "anxious", "nervous": "anxious", "stressed": "anxious",
    "scared": "afraid", "terrified": "afraid", "frightened": "afraid",
    "annoyed": "frustrated", "irritated": "frustrated",
    "furious": "angry", "enraged": "angry", "livid": "angry",
    "depressed": "sad", "unhappy": "sad", "heartbroken": "sad",
    "thankful": "grateful",
    "tranquil": "peaceful", "calm": "peaceful",
    "creative": "inspired",
    "kind": "warm", "caring": "warm", "sweet": "warm", "fond": "warm",
    "bewildered": "confused", "perplexed": "confused",
    "isolated": "lonely", "abandoned": "lonely",
    "ashamed": "guilty",
    "betrayed": "hurt",
}


def normalize_emotion(emotion: str) -> str:
    """Map an emotion label to its canonical form."""
    key = emotion.lower().strip()
    return _EMOTION_ALIASES.get(key, key)


def detect_emotions(text: str, top_k: int = 3) -> list[str]:
    """Detect emotions from text via keyword matching with negation awareness."""
    lower = text.lower()
    # Build set of negated spans (keyword positions preceded by negation)
    negated_spans: set[int] = set()
    for m in _NEGATION_RE.finditer(lower):
        # Mark words in a 30-char window after the negation token
        neg_end = min(m.end() + 30, len(lower))
        negated_spans.update(range(m.start(), neg_end))

    scores: dict[str, int] = {}
    for emotion, keywords in _EMOTION_KEYWORDS.items():
        for kw in keywords:
            idx = lower.find(kw)
            while idx != -1:
                # Skip if this keyword occurrence falls within a negation window
                if idx not in negated_spans:
                    scores[emotion] = scores.get(emotion, 0) + 1
                idx = lower.find(kw, idx + 1)
    if not scores:
        return ["neutral"]
    ranked = sorted(scores, key=scores.get, reverse=True)
    return [normalize_emotion(e) for e in ranked[:top_k]]


# Phrase tiers for estimate_importance(). Kept as substring lists (not a
# full NLP model) by design, but deliberately broad — the original 7-phrase
# list only caught a narrow literal pattern ("i feel", "i love", "i hate",
# "my family", "my life", "i'm scared", "i'm worried"), so something like
# "I told him my dad passed away last year and it still hurts" scored
# identically to "Just a short hello, nothing much happened". This matters
# most for memory IMPORT (pasting old chat history from elsewhere, e.g. a
# Character.ai export) since that's the one path with no live model
# turn-by-turn judging importance — this heuristic is all it gets.
_IMPORTANCE_MAJOR_EVENT_PHRASES = [
    "passed away", "passed last", " died ", "death of", "lost my", "lost him",
    "lost her", "funeral", "diagnosed with", "diagnosis", "miscarriage",
    "divorce", "broke up with", "break up", "breakup", "assaulted", "suicide",
    "cancer", "hospitalized", "surgery", "car accident", "fired from",
    "lost my job", "lost his job", "lost her job", "eviction", "homeless",
]
_IMPORTANCE_MILESTONE_PHRASES = [
    "i feel", "i love", "i hate", "my family", "my life",
    "i'm scared", "i'm worried", "i am scared", "i am worried",
    "promoted", "promotion", "got engaged", "proposed to", "the wedding",
    "got married", "pregnant", "newborn", "graduated", "graduation",
    "moved in together", "moving to", "new job",
    "my dad", "my mom", "my mother", "my father", "my brother", "my sister",
    "my partner", "my boyfriend", "my girlfriend", "my husband", "my wife",
    "my son", "my daughter", "my grandfather", "my grandmother",
    "i'm proud", "i'm grateful", "i'm anxious", "i'm terrified",
    "i'm heartbroken", "i'm devastated", "always remember", "never forget",
    "means everything", "means so much", "changed my life",
    "biggest mistake", "proudest moment",
]
_IMPORTANCE_MINOR_DISCLOSURE_PHRASES = [
    "excited about", "nervous about", "worried about", "reminds me of",
]
# Emotions that mark a turn as emotionally loaded enough to be worth extra
# weight even when no specific phrase above matched (e.g. third-person/
# narrative-style pasted text, which won't contain first-person "i feel").
_IMPORTANCE_SIGNIFICANT_EMOTIONS = {
    "sad", "angry", "afraid", "guilty", "vulnerable", "overwhelmed", "hurt",
    "resentful", "embarrassed", "insecure", "proud", "triumphant", "joyful",
    "nostalgic", "bittersweet", "melancholy", "disappointed", "jealous",
    "grateful",
}


def estimate_importance(user_text: str, response_text: str) -> int:
    """Heuristic importance scoring (1-10)."""
    score = 5
    lower = f" {user_text.lower()} "

    if any(w in lower for w in _IMPORTANCE_MAJOR_EVENT_PHRASES):
        score += 3
    elif any(w in lower for w in _IMPORTANCE_MILESTONE_PHRASES):
        score += 2
    elif any(w in lower for w in _IMPORTANCE_MINOR_DISCLOSURE_PHRASES):
        score += 1

    # Questions about the AI itself
    if any(w in lower for w in ["do you remember", "what do you think",
                                 "how do you feel"]):
        score += 1

    # Emotional-content signal — catches significant content that doesn't
    # match a literal phrase above (e.g. pasted narrative-style text).
    detected = detect_emotions(f"{user_text} {response_text}")
    if detected and detected[0] in _IMPORTANCE_SIGNIFICANT_EMOTIONS:
        score += 2

    # Very short / trivial
    if len(user_text) < 20:
        score -= 1
    # Very long / detailed
    if len(user_text) > 300:
        score += 1
    return max(1, min(10, score))


# Pre-compiled neurochemistry event patterns (avoids per-turn keyword loops)
_NEURO_EVENT_PATTERNS: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r'\b(?:surprise|unexpected|wow|omg)\b', re.I), "surprise", 0.6),
    (re.compile(r'\b(?:conflict|argue|disagree|fight)\b', re.I), "conflict", 0.5),
    (re.compile(r'\b(?:love|care|hug|friend|together)\b', re.I), "warmth", 0.5),
    (re.compile(r'\b(?:new|novel|first\s+time|discover)\b', re.I), "novelty", 0.4),
    (re.compile(r'\b(?:solved|fixed|done|completed|success)\b', re.I), "achievement", 0.5),
    (re.compile(r'\b(?:lost|died|gone|miss|grief)\b', re.I), "loss", 0.5),
    (re.compile(r'\b(?:haha|lol|funny|joke|lmao)\b', re.I), "humor", 0.4),
]


class MemoryManager:
    """Full-featured wrapper around Mimir for the playground."""

    # Number of turns between automatic consolidation
    _CONSOLIDATION_INTERVAL = 25
    _HUGINN_INTERVAL = 10
    _VOLVA_INTERVAL = 30   # Völva dream synthesis every 30 turns
    _HUGINN_MEMORY_INTERVAL = 15   # Run Huginn every N new memories
    _REFLECT_MEMORY_INTERVAL = 50  # Run reflect every N new memories
    _WAKE_THRESHOLD_SECONDS = 1800  # 30 min gap triggers wake-up cycle

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
        self._memories_since_huginn = 0
        self._memories_since_reflect = 0
        self._last_chemistry_tick = time.time()
        self._wake_log: list[str] = []  # populated by wake_up() for UI notification
        self._stats_cache: dict | None = None
        self._stats_cache_time: float = 0.0
        self._STATS_TTL = 60.0  # seconds

        # Check if a wake-up cycle is needed
        self._session_file = self._dir / "_last_session.txt"
        self._check_startup_wake()

    # ── startup wake cycle ──────────────────────────────────────────

    def _check_startup_wake(self):
        """Auto-run sleep/dream on startup if enough time has passed."""
        now = time.time()
        last_session_time = 0.0
        try:
            if self._session_file.exists():
                last_session_time = float(self._session_file.read_text().strip())
        except (ValueError, OSError):
            pass

        # Write current time as latest session
        try:
            self._session_file.write_text(str(now))
        except OSError:
            pass

        gap = now - last_session_time
        if last_session_time > 0 and gap >= self._WAKE_THRESHOLD_SECONDS:
            self._run_wake_up(gap)

    def _run_wake_up(self, gap_seconds: float):
        """Execute the full wake-up consolidation cycle."""
        hours = min(gap_seconds / 3600, 24)
        log = self._wake_log
        try:
            log.append("Running sleep consolidation...")
            self._mimir.sleep_reset(hours=hours)
            log.append(f"Sleep cycle complete ({hours:.1f}h gap)")
        except Exception as e:
            log.append(f"Sleep cycle error: {e}")

        try:
            log.append("Running Huginn pattern detection...")
            insights = self._mimir.huginn()
            log.append(f"Huginn found {len(insights)} insight(s)")
        except Exception as e:
            log.append(f"Huginn error: {e}")

        try:
            log.append("Running Völva dream synthesis...")
            dreams = self._mimir.volva_dream()
            log.append(f"Völva synthesised {len(dreams)} dream(s)")
        except Exception as e:
            log.append(f"Völva error: {e}")

        try:
            self._mimir.save()
            log.append("Memories consolidated and saved")
        except Exception:
            pass

    def get_wake_log(self) -> list[str]:
        """Return (and clear) the wake-up log for UI notification."""
        log = list(self._wake_log)
        self._wake_log.clear()
        return log

    # ── store ─────────────────────────────────────────────────────────

    def _remember_obj(self, content: str, emotion: str = "neutral",
                       importance: int = 5, source: str = "playground",
                       why_saved: str = "",
                       conversation_snapshot: list[dict] | None = None,
                       category: str = "", entity: str = ""):
        """Like remember(), but returns the live Memory object rather than
        a dict snapshot — for internal callers that need to mutate the
        memory right after creation."""
        emotion = normalize_emotion(emotion)
        mem = self._mimir.remember(
            content=content, emotion=emotion,
            importance=importance, source=source,
            why_saved=why_saved,
            conversation_snapshot=conversation_snapshot,
            category=category, entity=entity,
        )
        self._invalidate_stats_cache()
        return mem

    def remember(self, content: str, emotion: str = "neutral",
                 importance: int = 5, source: str = "playground",
                 why_saved: str = "",
                 conversation_snapshot: list[dict] | None = None,
                 category: str = "", entity: str = "") -> dict:
        return self._remember_obj(
            content, emotion, importance, source,
            why_saved, conversation_snapshot, category, entity,
        ).to_dict()

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
        if dt_minutes > 0.016:  # ~1 second minimum
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
            # No automatic entity-linking here deliberately -- which
            # person (if any) a memory is about is the model's own choice
            # via <remember entity="Name">, never inferred from a name
            # merely appearing in the message.
            self._remember_obj(
                content=mem_content,
                emotion=primary_emotion,
                importance=importance,
                source="conversation",
                why_saved=why,
            )

        # Update mood (also ticks chemistry internally)
        self.update_mood(emotions)

        # Detect neurochemistry events from content (compiled patterns)
        lower = combined_text.lower()
        for pattern, event_type, intensity in _NEURO_EVENT_PATTERNS:
            if pattern.search(lower):
                self.on_event(event_type, intensity)

        # Increment turn counter & memory counters
        self._turn_count += 1
        if should_remember:
            self._memories_since_huginn += 1
            self._memories_since_reflect += 1

        # Periodic consolidation (muninn)
        consolidated = None
        if self._turn_count % self._CONSOLIDATION_INTERVAL == 0:
            try:
                consolidated = self._mimir.muninn()
            except Exception:
                pass

        # Run huginn: every 10 turns OR every _HUGINN_MEMORY_INTERVAL new memories
        if (self._turn_count % self._HUGINN_INTERVAL == 0 or
                self._memories_since_huginn >= self._HUGINN_MEMORY_INTERVAL):
            try:
                self._mimir.huginn()
                self._memories_since_huginn = 0
            except Exception:
                pass

        # Run Völva dream synthesis every 30 turns
        if self._turn_count % self._VOLVA_INTERVAL == 0:
            try:
                self._mimir.volva_dream()
            except Exception:
                pass

        # Auto-reflect every _REFLECT_MEMORY_INTERVAL new memories
        if self._memories_since_reflect >= self._REFLECT_MEMORY_INTERVAL:
            try:
                self._mimir.reflect()
                self._memories_since_reflect = 0
            except Exception:
                pass

        # Update last session timestamp
        try:
            self._session_file.write_text(str(time.time()))
        except OSError:
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
                               entity: str = "",
                               interaction_gap_seconds: float | None = None) -> str:
        """Build memory context tailored to the active preset type."""
        preset_label = preset.get("label", "").lower()

        # All presets get the core context block from Mimir
        # (includes mood, active memories, lessons, reminders, temporal,
        #  neurochemistry, drift alerts, resonant memories, insights)
        context = self._mimir.get_context_block(
            current_entity=entity,
            conversation_context=conversation_context,
            interaction_gap_seconds=interaction_gap_seconds,
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
                            f"- Problem: {s.problem_signature[:80]}")
                        extra_parts.append(
                            f"  Solution: {s.solution[:120]}")
                    extra_parts.append("")

        # Character / Writer: add extra emotional depth
        if preset_label in ("character", "writer"):
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

        # Visual memories — always include so model can recall images
        try:
            vis_block = self.get_visual_context_block()
            if vis_block:
                extra_parts.append(vis_block)
        except Exception:
            pass

        if extra_parts:
            context += "\n" + "\n".join(extra_parts)

        return context

    # ── retrieve ──────────────────────────────────────────────────────

    def recall(self, context: str, limit: int = 10) -> list[dict]:
        memories = self._mimir.recall(context, limit=limit)
        return [m.to_dict() for m in memories]

    def recall_for_display(self, context: str, limit: int = 5) -> list[dict]:
        """Lean recall for the live in-chat memory activity strip.

        Memory.to_dict() doesn't include vividness (it's a computed
        property, not a stored field) — this builds a small dict per
        memory that does, mirroring how get_graph() builds its node dicts.
        """
        memories = self._mimir.recall(context, limit=limit)
        return [
            {
                "content": m.gist[:200],
                "emotion": m.emotion,
                "importance": m.importance,
                "vividness": round(m.vividness, 2),
                "is_flashbulb": m._is_flashbulb,
                "category": m._category or "",
            }
            for m in memories
        ]

    def request_deep_remember(self, query: str) -> bool:
        """Resolve a <deep_remember query="..."/> tag against snapshot-bearing
        memories; on a match, the full snapshot surfaces in the next
        get_context_block() call. Returns False if nothing matched."""
        return self._mimir.request_deep_remember(query)

    def trigger_dream(self) -> bool:
        """Resolve a <dream/> tag — runs the consolidation cycle (Huginn +
        Völva + sleep_reset). Rate-limited; returns False if on cooldown."""
        return self._mimir.trigger_dream()

    def trigger_self_reflect(self) -> str | None:
        """Resolve a <self_reflect/> tag — genuine LLM self-analysis, stored
        as a memory. Rate-limited; returns None if on cooldown or no LLM
        callback is configured."""
        return self._mimir.trigger_self_reflect()

    def record_interaction(self) -> float | None:
        """Call once per real user turn. Returns seconds since the previous
        recorded interaction (None on the very first interaction ever)."""
        return self._mimir.record_interaction()

    def get_context_block(self, entity: str = "",
                          conversation_context: str = "",
                          interaction_gap_seconds: float | None = None) -> str:
        return self._mimir.get_context_block(
            current_entity=entity,
            conversation_context=conversation_context,
            interaction_gap_seconds=interaction_gap_seconds,
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
        self._invalidate_stats_cache()
        self._mimir.save()

    def bump_session(self) -> int:
        return self._mimir.bump_session()

    # ── consolidation & insights ──────────────────────────────────────

    def run_consolidation(self) -> dict:
        """Run Muninn consolidation daemon."""
        try:
            result = self._mimir.muninn()
            self._invalidate_stats_cache()
            return result
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

    def _invalidate_stats_cache(self):
        """Clear cached stats so next call recalculates."""
        self._stats_cache = None

    def stats(self) -> dict:
        now = time.time()
        if (self._stats_cache is not None
                and now - self._stats_cache_time < self._STATS_TTL):
            return self._stats_cache
        s = self._mimir.stats()
        s["turn_count"] = self._turn_count
        self._stats_cache = s
        self._stats_cache_time = now
        return s

    def emotion_distribution(self) -> dict:
        return self._mimir.emotion_distribution()

    def neurochemistry_snapshot(self) -> dict:
        return self._mimir.neurochemistry_snapshot()

    # ── social ────────────────────────────────────────────────────────

    def add_social(self, entity: str, content: str,
                   emotion: str = "neutral", importance: int = 5,
                   why_saved: str = "",
                   conversation_snapshot: list[dict] | None = None) -> dict:
        mem = self._mimir.add_social_impression(
            entity=entity, content=content, emotion=emotion,
            importance=importance, why_saved=why_saved,
            conversation_snapshot=conversation_snapshot,
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

    # Matches mimir_modular.constants._DEDUP_THRESHOLD (kept local rather than
    # imported since Mimir may be backed by the vividmimir package, the local
    # mimir_modular dev package, or the legacy Mimir.py monolith).
    _TASK_DEDUP_THRESHOLD = 0.55
    _TASK_DEDUP_STOP = {"the", "a", "an", "to", "of", "and", "in", "on",
                        "for", "with", "is", "are", "was", "were"}

    def has_similar_active_task(self, description: str,
                                 project: str = "") -> dict | None:
        """Return an existing active task dict if one closely matches the
        given description in the same project, else None. Used to avoid
        spawning duplicate tasks when the model repeats itself across turns."""
        proj = project or self._mimir._active_project
        new_words = set(description.lower().split()) - self._TASK_DEDUP_STOP
        if not new_words:
            return None
        for t in self._mimir.get_active_tasks():
            if t.project != proj:
                continue
            existing_words = set(t.description.lower().split()) - self._TASK_DEDUP_STOP
            if not existing_words:
                continue
            overlap = len(new_words & existing_words) / len(new_words | existing_words)
            if overlap >= self._TASK_DEDUP_THRESHOLD:
                return {"task_id": t.task_id, "description": t.description,
                        "priority": t.priority, "status": t.status}
        return None

    def complete_task(self, task_id: str, outcome: str = "") -> bool:
        return self._mimir.complete_task(task_id, outcome)

    def fail_task(self, task_id: str, reason: str = "") -> bool:
        return self._mimir.fail_task(task_id, reason)

    def delete_task(self, task_id: str) -> bool:
        return self._mimir.delete_task(task_id)

    def get_active_tasks(self) -> list[dict]:
        tasks = self._mimir.get_active_tasks()
        return [{"task_id": t.task_id, "description": t.description,
                 "priority": t.priority, "status": t.status} for t in tasks]

    def get_all_tasks(self) -> list[dict]:
        return [{"task_id": t.task_id, "description": t.description,
                 "priority": t.priority, "status": t.status,
                 "project": t.project,
                 "created_at": t.created_at,
                 "completed_at": t.completed_at,
                 "outcome": t.outcome}
                for t in self._mimir._project_tasks]

    def set_active_project(self, name: str) -> str:
        return self._mimir.set_active_project(name)

    def get_project_overview(self) -> dict:
        return self._mimir.get_project_overview()

    def record_solution(self, problem: str, solution: str,
                        importance: int = 5) -> dict:
        s = self._mimir.record_solution(problem, solution, importance)
        return {"problem": s.problem_signature, "solution": s.solution,
                "importance": s.importance, "reuse_count": s.times_applied}

    def find_solutions(self, problem: str, top_k: int = 3) -> list[dict]:
        results = self._mimir.find_solutions(problem, top_k)
        return [{"problem": s.problem_signature, "solution": s.solution,
                 "importance": s.importance, "reuse_count": s.times_applied}
                for s in results]

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

    # ── visual memory ─────────────────────────────────────────────────

    def remember_visual(self, image_bytes: bytes, description: str,
                        emotion: str = "neutral", importance: int = 5,
                        why_saved: str = "visual memory") -> dict:
        """Store an image + description as a visual memory."""
        mem = self._mimir.remember_visual(
            image_data=image_bytes,
            description=description,
            emotion=emotion,
            importance=importance,
            source="visual",
            why_saved=why_saved,
        )
        d = mem.to_dict()
        if mem.has_visual:
            d["visual_hash"] = mem._visual_hash
            d["visual_description"] = mem._visual_description
        return d

    def get_visual_memories(self) -> list[dict]:
        """Return all memories that have an attached image."""
        result = []
        for m in self._mimir._reflections:
            if m.has_visual:
                d = m.to_dict()
                d["visual_hash"] = m._visual_hash
                d["visual_description"] = m._visual_description
                d["visual_clarity"] = m.visual_clarity
                result.append(d)
        result.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return result

    def get_visual_image(self, hash_val: str) -> bytes | None:
        """Return raw WebP bytes for a stored visual memory."""
        try:
            img_path = self._dir / "visual" / f"{hash_val}.webp"
            if img_path.is_file():
                return img_path.read_bytes()
        except Exception:
            pass
        return None

    def get_visual_context_block(self) -> str:
        """Return a context block listing visual memories with their hashes
        so the model can reference them via <showimage hash="..."/>."""
        mems = [m for m in self._mimir._reflections if m.has_visual and m.can_show]
        if not mems:
            return ""
        try:
            from vividmimir import Mimir as _Mimir
        except ModuleNotFoundError:
            try:
                from mimir_modular import Mimir as _Mimir
            except ModuleNotFoundError:
                from Mimir import Mimir as _Mimir  # type: ignore
        vivid = sorted(mems,
                       key=lambda m: m.mood_adjusted_vividness(self._mimir._mood),
                       reverse=True)[:8]
        lines = ["=== VISUAL MEMORIES (write <showimage hash=\"HASH\"/> to show the user) ==="]
        for m in vivid:
            tag = "[vivid]" if m.visual_clarity == "vivid" else "[fading]"
            lines.append(f"— hash:{m._visual_hash} | {m._visual_description[:80]} {tag}")
        lines.append("")
        return "\n".join(lines)

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

    async def reflect(self, backend, model: str = "") -> dict:
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
                model=model,
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

    async def edit_memories(self, backend, instruction: str = "",
                            model: str = "") -> dict:
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
                model=model,
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
                    mem.importance = min(10, mem.importance + 2)
                    counts["promoted"] += 1
                elif op_type == "DEMOTE":
                    mem.importance = max(1, mem.importance - 2)
                    counts["demoted"] += 1
                elif op_type == "UPDATE":
                    if "emotion" in op:
                        mem.emotion = str(op["emotion"])
                    if "importance" in op:
                        mem.importance = max(1, min(10, int(op["importance"])))
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
            self._invalidate_stats_cache()
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
            mem._believed_importance = max(1, min(10, int(changes["importance"])))
        if "emotion" in changes:
            new_emotion = str(changes["emotion"])
            reason = changes.get("reason", "user edit")
            try:
                self._mimir.reframe(mem, new_emotion, reason)
            except Exception:
                mem.emotion = new_emotion  # graceful fallback
        self.save()
        return mem.to_dict()

    def resolve_treasure_query(self, query: str, min_confidence: float = 0.1) -> int | None:
        """Find the reflection index a <treasure query="..."/> tag refers to.

        Uses recall()'s top result, but — unlike a bare recall — requires a
        minimum lexical overlap between the query and the candidate's own
        content before accepting it. Without this, a <treasure> query with
        no good match in the store (a mis-phrased or hallucinated query)
        would otherwise silently cherish/anchor whatever recall ranked #1,
        with no indication to the user that the "wrong" memory got marked
        precious. 0.1 matches the existing confidence bar used for attic
        rediscovery-by-query (core.py's recall_from_attic).
        """
        if not query:
            return None
        matches = self._mimir.recall(query, limit=1)
        if not matches:
            return None
        target = matches[0]
        try:
            from vividmimir.helpers import _content_words, _overlap_ratio
        except ImportError:
            from mimir_modular.helpers import _content_words, _overlap_ratio
        query_words = _content_words(query.lower())
        overlap = _overlap_ratio(query_words, target.content_words)
        if overlap < min_confidence:
            return None
        for idx, m in enumerate(self._mimir._reflections):
            if m is target:
                return idx
        return None

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
                "is_self": getattr(m, "_category", "") == "self",
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

        # Social impressions — merge into nodes so they appear on the graph
        social_nodes = []
        for entity, memories in mimir._social.items():
            for sm in memories:
                social_nodes.append({
                    "id": len(nodes) + len(social_nodes),
                    "content": sm.content[:120],
                    "emotion": sm.emotion,
                    "importance": sm.importance,
                    "vividness": round(sm.vividness, 3),
                    "timestamp": sm.timestamp,
                    "source": "social",
                    "is_flashbulb": getattr(sm, "_is_flashbulb", False),
                    "is_anchor": getattr(sm, "_anchor", False),
                    "is_cherished": getattr(sm, "_cherished", False),
                    "entity": entity,
                    "stability": round(getattr(sm, "_stability", 50.0), 1),
                    "access_count": getattr(sm, "_access_count", 0),
                })
        all_nodes = nodes + social_nodes

        return {
            "nodes": all_nodes,
            "edges": edges,
            "lessons": lessons,
            "tasks": tasks,
            "total": len(all_nodes),
        }

    # ── import ────────────────────────────────────────────────────────

    def save_import_backup(self, filename: str, raw_content: str) -> str:
        """Archive the untouched original file/text an import came from,
        before any of it gets reshaped into Mimir's own memory format.
        External systems (Character.ai exports, etc.) don't have Mimir's
        fields (importance, stability, cherish/anchor, entity, ...) -- the
        import process has to make judgment calls to fill those in, so the
        original is kept as-is, permanently, in case that interpretation
        is ever wrong and the source is needed again."""
        backup_dir = self._dir.parent / "import_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename).name or "import"
        ts = time.strftime("%Y%m%d_%H%M%S")
        dest = backup_dir / f"{ts}_{safe_name}"
        # Avoid collisions if multiple files land in the same second
        n = 1
        while dest.exists():
            dest = backup_dir / f"{ts}_{n}_{safe_name}"
            n += 1
        dest.write_text(raw_content, encoding="utf-8")
        return str(dest)

    def import_memory(self, content: str, emotion: str = "neutral",
                      importance: int = 5, source: str = "import",
                      why_saved: str = "imported from external system",
                      timestamp: str = "") -> dict:
        """Import a memory with dedup check and emotion normalization."""
        emotion = normalize_emotion(emotion)
        # Dedup check: skip near-identical memories
        try:
            from vividmimir.helpers import _content_words, _overlap_ratio
        except ImportError:
            from mimir_modular.helpers import _content_words, _overlap_ratio
        new_words = _content_words(content.lower())
        if new_words:
            for existing in self._mimir._reflections:
                if _overlap_ratio(new_words, existing.content_words) >= 0.85:
                    # Very similar memory already exists — return existing
                    return existing.to_dict()
        mem = self._mimir.remember(
            content=content, emotion=emotion,
            importance=importance, source=source,
            why_saved=why_saved,
        )
        if timestamp:
            mem.timestamp = timestamp
        # Imports are infrequent/bulk, unlike live remember() calls, so it's
        # worth eagerly rebuilding Yggdrasil here rather than waiting for the
        # next auto-consolidation interval — otherwise an imported memory can
        # sit as a disconnected node with no graph edges for a long time.
        self._mimir._build_yggdrasil()
        self._invalidate_stats_cache()
        return mem.to_dict()

    def import_memories_batch(self, memories: list[dict]) -> dict:
        """Batch import: accepts a list of memory dicts, deduplicates, returns summary."""
        imported = 0
        skipped = 0
        for m in memories:
            content = m.get("content", "").strip()
            if not content:
                skipped += 1
                continue
            emotion = normalize_emotion(m.get("emotion", "neutral"))
            importance = max(1, min(10, int(m.get("importance", 5))))
            source = m.get("source", "import")
            why_saved = m.get("why_saved", "batch import")
            timestamp = m.get("timestamp", "")

            # Dedup check
            try:
                from vividmimir.helpers import _content_words, _overlap_ratio
            except ImportError:
                from mimir_modular.helpers import _content_words, _overlap_ratio
            new_words = _content_words(content.lower())
            is_dup = False
            if new_words:
                for existing in self._mimir._reflections:
                    if _overlap_ratio(new_words, existing.content_words) >= 0.85:
                        is_dup = True
                        break
            if is_dup:
                skipped += 1
                continue

            mem = self._mimir.remember(
                content=content, emotion=emotion,
                importance=importance, source=source,
                why_saved=why_saved,
            )
            if timestamp:
                mem.timestamp = timestamp
            imported += 1

        if imported > 0:
            # One rebuild after the whole batch, not per-item — a batch import
            # can add dozens of memories at once, well under the auto-rebuild
            # interval, so without this they'd sit disconnected in the graph.
            self._mimir._build_yggdrasil()
            self._invalidate_stats_cache()
            self.save()
        return {"imported": imported, "skipped": skipped, "total": len(memories)}

    # ── Relationship Strength ─────────────────────────────────────────

    def get_relationship_strength(self, entity: str = "") -> dict | list[dict]:
        return self._mimir.relationship_strength(entity)

    # ── Topic Clusters ────────────────────────────────────────────────

    def get_topic_clusters(self) -> list[dict]:
        return self._mimir.get_topic_clusters()

    # ── Emotional Trajectory ──────────────────────────────────────────

    def get_emotional_trajectory(self, window_days: int = 30) -> dict:
        return self._mimir.emotional_trajectory(window_days)

    # ── Forgotten Memory Recovery ─────────────────────────────────────

    def get_dormant_memories(self, limit: int = 20) -> list[dict]:
        return self._mimir.get_dormant_memories(limit)

    def get_attic_memories(self, limit: int = 50) -> list[dict]:
        return self._mimir.get_attic_memories(limit)

    def rediscover_memory(self, query: str = "", attic_index: int = -1) -> dict | None:
        mem = self._mimir.rediscover(query=query, attic_index=attic_index)
        return mem.to_dict() if mem else None

    def nudge_dormant_memory(self, index: int) -> dict | None:
        mem = self._mimir.nudge_dormant(index)
        return mem.to_dict() if mem else None
