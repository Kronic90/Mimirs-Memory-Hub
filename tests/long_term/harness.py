"""
Year-Long Simulation Test Harness
=================================
Provides time-warping, isolated test environments, metrics collection,
and the base class for all long-term simulation tests.

Usage:
    from tests.long_term.harness import SimulationHarness, TimeWarp

    harness = SimulationHarness("companion_test")
    harness.advance_hours(8)       # Jump forward 8 hours
    harness.advance_days(30)       # Jump forward 30 days
    harness.process("Hi!", "Hello!")
    harness.assert_recall("Hi", min_score=0.5)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

# ── Ensure repo root on sys.path ──
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from playground.memory_manager import MemoryManager, detect_emotions, normalize_emotion

try:
    from playground.presets import PRESETS, get_preset
except ImportError:
    PRESETS = {}
    get_preset = lambda x: {}


# ═══════════════════════════════════════════════════════════════
#  Time-Warp Engine
# ═══════════════════════════════════════════════════════════════

class TimeWarp:
    """Monkey-patchable clock that lets tests jump forward in time."""

    def __init__(self, start: datetime | None = None):
        self._real_time = time.time
        self._start_real = time.time()
        self._start_sim = start or datetime(2025, 1, 1, 9, 0, 0)
        self._offset_seconds: float = 0.0

    @property
    def now(self) -> datetime:
        return self._start_sim + timedelta(seconds=self._offset_seconds)

    @property
    def timestamp(self) -> float:
        return self._start_sim.timestamp() + self._offset_seconds

    def advance(self, seconds: float = 0, minutes: float = 0,
                hours: float = 0, days: float = 0, weeks: float = 0):
        total = seconds + minutes * 60 + hours * 3600 + days * 86400 + weeks * 604800
        self._offset_seconds += total

    def time(self) -> float:
        return self.timestamp

    def _patched_datetime_now(self, tz=None):
        return self.now

    @contextmanager
    def patched(self):
        """Context manager that patches time.time and datetime references."""
        original_time = time.time
        time.time = self.time
        try:
            yield self
        finally:
            time.time = original_time


# ═══════════════════════════════════════════════════════════════
#  Metrics Collector
# ═══════════════════════════════════════════════════════════════

@dataclass
class TestResult:
    name: str
    passed: bool
    message: str = ""
    details: dict = field(default_factory=dict)
    timestamp: str = ""

@dataclass
class MetricsCollector:
    """Collects test results and metrics across the simulation."""
    test_name: str
    results: list[TestResult] = field(default_factory=list)
    checkpoints: dict[str, dict] = field(default_factory=dict)
    memory_growth: list[dict] = field(default_factory=list)
    chemistry_history: list[dict] = field(default_factory=list)
    recall_accuracy: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def record(self, name: str, passed: bool, message: str = "",
               details: dict | None = None, timestamp: str = ""):
        self.results.append(TestResult(
            name=name, passed=passed, message=message,
            details=details or {}, timestamp=timestamp
        ))

    def checkpoint(self, label: str, data: dict):
        self.checkpoints[label] = data

    def record_recall(self, query: str, expected_content: str,
                      found: bool, rank: int = -1, score: float = 0.0,
                      age_days: float = 0.0):
        self.recall_accuracy.append({
            "query": query,
            "expected": expected_content,
            "found": found,
            "rank": rank,
            "score": score,
            "age_days": age_days,
        })

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def recall_rate(self) -> float:
        if not self.recall_accuracy:
            return 0.0
        found = sum(1 for r in self.recall_accuracy if r["found"])
        return found / len(self.recall_accuracy)

    def summary(self) -> dict:
        return {
            "test_name": self.test_name,
            "total": self.total,
            "passed": self.pass_count,
            "failed": self.fail_count,
            "pass_rate": f"{self.pass_count / self.total * 100:.1f}%" if self.total else "N/A",
            "recall_tests": len(self.recall_accuracy),
            "recall_rate": f"{self.recall_rate * 100:.1f}%",
            "checkpoints": list(self.checkpoints.keys()),
            "errors": self.errors,
        }

    def to_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "results": [
                {"name": r.name, "passed": r.passed, "message": r.message,
                 "details": r.details, "timestamp": r.timestamp}
                for r in self.results
            ],
            "checkpoints": self.checkpoints,
            "memory_growth": self.memory_growth,
            "chemistry_history": self.chemistry_history,
            "recall_accuracy": self.recall_accuracy,
        }


# ═══════════════════════════════════════════════════════════════
#  Simulation Harness — Main Test Engine
# ═══════════════════════════════════════════════════════════════

class SimulationHarness:
    """
    Provides an isolated MemoryManager + time-warp clock for year-long tests.

    Each harness gets its own temp directory, so tests don't interfere.
    """

    def __init__(self, test_name: str, preset_name: str = "companion",
                 chemistry: bool = True,
                 start_time: datetime | None = None):
        self.test_name = test_name
        self.preset_name = preset_name
        self.preset = get_preset(preset_name) if PRESETS else {"label": preset_name}

        # Isolated temp directory
        self._tmpdir = tempfile.mkdtemp(prefix=f"mimir_test_{test_name}_")
        self._profile_dir = os.path.join(self._tmpdir, "profile")
        os.makedirs(self._profile_dir, exist_ok=True)

        # Time-warp clock
        self.clock = TimeWarp(start=start_time or datetime(2025, 1, 1, 9, 0, 0))

        # Create manager inside time-warped context
        with self.clock.patched():
            self.manager = MemoryManager(
                profile_dir=self._profile_dir,
                chemistry=chemistry,
            )

        # Metrics
        self.metrics = MetricsCollector(test_name=test_name)

        # Turn counter
        self.turn_count = 0
        self.sim_day = 0

    # ── Time Control ──

    def advance_hours(self, hours: float):
        self.clock.advance(hours=hours)

    def advance_days(self, days: float):
        self.clock.advance(days=days)
        self.sim_day += int(days)

    def advance_weeks(self, weeks: float):
        self.clock.advance(weeks=weeks)
        self.sim_day += int(weeks * 7)

    @property
    def current_time(self) -> datetime:
        return self.clock.now

    @property
    def elapsed_days(self) -> float:
        return self.clock._offset_seconds / 86400

    # ── Memory Operations ──

    def remember(self, content: str, emotion: str = "neutral",
                 importance: int = 5, source: str = "conversation",
                 why: str = "") -> dict:
        with self.clock.patched():
            return self.manager.remember(
                content=content, emotion=emotion,
                importance=importance, source=source,
                why_saved=why or f"test memory at day {self.sim_day}"
            )

    def recall(self, query: str, limit: int = 10) -> list:
        with self.clock.patched():
            return self.manager.recall(query, limit=limit)

    def process(self, user_msg: str, assistant_msg: str,
                skip_save: bool = False) -> dict:
        with self.clock.patched():
            result = self.manager.process_turn(
                user_msg=user_msg,
                assistant_msg=assistant_msg,
                preset=self.preset,
                skip_save=skip_save,
            )
        self.turn_count += 1
        return result

    def sleep_cycle(self, hours: float = 8.0):
        with self.clock.patched():
            self.manager._mimir.sleep_reset(hours)
        self.clock.advance(hours=hours)

    def get_mood(self) -> dict:
        with self.clock.patched():
            return self.manager.get_mood()

    def get_stats(self) -> dict:
        with self.clock.patched():
            return self.manager.stats()

    def get_context(self, conversation: str = "", entity: str = "") -> str:
        with self.clock.patched():
            return self.manager.get_context_for_preset(
                preset=self.preset,
                conversation_context=conversation,
                entity=entity,
            )

    def set_reminder(self, text: str, hours: float) -> Any:
        with self.clock.patched():
            return self.manager.set_reminder(text, hours)

    def get_reminders(self, include_fired: bool = False) -> list:
        with self.clock.patched():
            return self.manager.get_reminders(include_fired=include_fired)

    def add_social(self, entity: str, content: str, emotion: str = "warm",
                   importance: int = 5) -> Any:
        with self.clock.patched():
            return self.manager.add_social(
                entity=entity, content=content,
                emotion=emotion, importance=importance,
                why_saved=f"social note at day {self.sim_day}"
            )

    def add_lesson(self, topic: str, strategy: str,
                   context_trigger: str = "", importance: int = 7) -> Any:
        with self.clock.patched():
            return self.manager.add_lesson(
                topic=topic, context_trigger=context_trigger,
                strategy=strategy, importance=importance,
            )

    def start_task(self, description: str, priority: int = 5,
                   project: str = "") -> Any:
        with self.clock.patched():
            return self.manager.start_task(description, priority, project)

    def complete_task(self, task_id: str, outcome: str = "") -> bool:
        with self.clock.patched():
            return self.manager.complete_task(task_id, outcome)

    def cherish(self, index: int) -> Any:
        with self.clock.patched():
            return self.manager.toggle_cherish(index)

    def anchor(self, index: int) -> Any:
        with self.clock.patched():
            return self.manager.toggle_anchor(index)

    # ── Assertions ──

    def assert_recall(self, query: str, expected_substring: str,
                      top_k: int = 5, label: str = "") -> bool:
        results = self.recall(query, limit=top_k)
        for rank, mem in enumerate(results):
            content = mem.content if hasattr(mem, "content") else str(mem)
            if expected_substring.lower() in content.lower():
                self.metrics.record_recall(
                    query=query, expected_content=expected_substring,
                    found=True, rank=rank, score=1.0,
                    age_days=self.elapsed_days
                )
                self.metrics.record(
                    label or f"recall:{query[:40]}",
                    True,
                    f"Found '{expected_substring}' at rank {rank}",
                    timestamp=str(self.current_time),
                )
                return True

        self.metrics.record_recall(
            query=query, expected_content=expected_substring,
            found=False, rank=-1, score=0.0,
            age_days=self.elapsed_days
        )
        self.metrics.record(
            label or f"recall:{query[:40]}",
            False,
            f"Could not find '{expected_substring}' in top {top_k} results",
            timestamp=str(self.current_time),
        )
        return False

    def assert_memory_count(self, min_count: int = 0,
                            max_count: int = 999999,
                            label: str = "") -> bool:
        stats = self.get_stats()
        count = stats.get("total_reflections", 0)
        ok = min_count <= count <= max_count
        self.metrics.record(
            label or f"memory_count_{min_count}-{max_count}",
            ok,
            f"Memory count: {count} (expected {min_count}-{max_count})",
            details={"count": count},
            timestamp=str(self.current_time),
        )
        return ok

    def assert_mood(self, expected_label: str | None = None,
                    label: str = "") -> bool:
        mood = self.get_mood()
        mood_label = mood.get("mood_label", "unknown")
        if expected_label:
            ok = mood_label.lower() == expected_label.lower()
        else:
            ok = mood_label != "unknown" and mood_label is not None
        self.metrics.record(
            label or f"mood:{expected_label or 'valid'}",
            ok,
            f"Mood: {mood_label}" + (f" (expected {expected_label})" if expected_label else ""),
            details=mood,
            timestamp=str(self.current_time),
        )
        return ok

    def assert_chemistry_stable(self, label: str = "") -> bool:
        mood = self.get_mood()
        chem = mood.get("chemistry", {})
        levels = chem.get("levels", {})
        ok = all(0.0 <= v <= 1.0 for v in levels.values()) if levels else False
        self.metrics.record(
            label or "chemistry_stable",
            ok,
            f"Chemistry levels: {levels}",
            details=levels,
            timestamp=str(self.current_time),
        )
        return ok

    def assert_emotion_detected(self, text: str, expected: str,
                                label: str = "") -> bool:
        emotions = detect_emotions(text)
        ok = expected in emotions
        self.metrics.record(
            label or f"emotion:{expected}",
            ok,
            f"Detected: {emotions}, expected '{expected}'",
            timestamp=str(self.current_time),
        )
        return ok

    def assert_cherished_survives_consolidation(self, content_substr: str,
                                                label: str = "") -> bool:
        """Verify a cherished memory survives sleep consolidation."""
        self.sleep_cycle(8.0)
        return self.assert_recall(
            content_substr, content_substr,
            label=label or f"cherished_survives:{content_substr[:30]}"
        )

    # ── Snapshot & Checkpoint ──

    def snapshot(self, label: str):
        stats = self.get_stats()
        mood = self.get_mood()
        self.metrics.checkpoint(label, {
            "sim_day": self.sim_day,
            "elapsed_days": self.elapsed_days,
            "turn_count": self.turn_count,
            "stats": stats,
            "mood": mood,
            "time": str(self.current_time),
        })
        self.metrics.memory_growth.append({
            "day": self.sim_day,
            "total": stats.get("total_reflections", 0),
            "cherished": stats.get("cherished_count", 0),
            "anchored": stats.get("anchor_count", 0),
        })
        levels = mood.get("chemistry", {}).get("levels", {})
        self.metrics.chemistry_history.append({
            "day": self.sim_day,
            "mood": mood.get("mood_label", ""),
            **levels,
        })

    # ── Cleanup ──

    def cleanup(self):
        if os.path.exists(self._tmpdir):
            shutil.rmtree(self._tmpdir, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cleanup()


# ═══════════════════════════════════════════════════════════════
#  Conversation Patterns — Realistic user message generators
# ═══════════════════════════════════════════════════════════════

# These are canned conversation pairs (user_msg, assistant_msg) that
# exercise different emotional tones, topics, and tag patterns.

DAILY_GREETINGS = [
    ("Good morning! How are you?",
     "Good morning! I'm doing well. How did you sleep?"),
    ("Hey, what's up?",
     "Hey! Not much, just here whenever you need me. What's on your mind?"),
    ("Morning! Busy day ahead.",
     "Morning! Tell me about your plans and I'll help you organize."),
]

EMOTIONAL_CONVERSATIONS = {
    "happy": [
        ("I got promoted at work today!",
         "That's amazing! Congratulations! You've worked so hard for this. <remember emotion=\"happy\" importance=\"9\" why=\"major life achievement\">User got promoted at work</remember>"),
        ("I'm feeling really grateful for my friends.",
         "It's wonderful to appreciate the people in your life. <remember emotion=\"grateful\" importance=\"6\" why=\"positive reflection\">User feeling grateful for friends</remember>"),
    ],
    "sad": [
        ("I'm feeling really down today. Nothing seems to go right.",
         "I'm sorry to hear that. Want to talk about what's bothering you? Sometimes just sharing helps. <remember emotion=\"sad\" importance=\"6\" why=\"emotional support needed\">User feeling down, nothing going right</remember>"),
        ("My pet passed away last week.",
         "I'm so sorry for your loss. Losing a pet is incredibly painful — they're family. <remember emotion=\"sad\" importance=\"9\" why=\"significant loss\" cherish=\"true\">User's pet passed away</remember>"),
    ],
    "anxious": [
        ("I have a big presentation tomorrow and I'm terrified.",
         "It's natural to feel nervous. Let's break it down — what's the topic? We can practice together. <remember emotion=\"anxious\" importance=\"7\" why=\"upcoming challenge\">User has presentation tomorrow, feeling anxious</remember>"),
    ],
    "excited": [
        ("I just booked tickets to Japan for next month!",
         "How exciting! Japan is incredible. Are you planning to visit Tokyo, Kyoto, or both? <remember emotion=\"excited\" importance=\"8\" why=\"travel plans\">User booked trip to Japan next month</remember>"),
    ],
    "angry": [
        ("My coworker took credit for my project again!",
         "That's really frustrating and unfair. Have you considered documenting your contributions? <remember emotion=\"angry\" importance=\"7\" why=\"workplace conflict\">User's coworker took credit for their project</remember>"),
    ],
    "curious": [
        ("I've been reading about quantum computing lately.",
         "Quantum computing is fascinating! What aspect interests you most — the hardware, algorithms, or applications? <remember emotion=\"curious\" importance=\"5\" why=\"intellectual interest\">User interested in quantum computing</remember>"),
    ],
    "nostalgic": [
        ("I found old photos from my college days today.",
         "Nostalgia can be so bittersweet! Any particular memories that stood out? <remember emotion=\"nostalgic\" importance=\"6\" why=\"personal reflection\">User found old college photos, feeling nostalgic</remember>"),
    ],
    "proud": [
        ("I finished my first marathon this weekend!",
         "That's an incredible accomplishment! How long did you train for it? <remember emotion=\"proud\" importance=\"9\" why=\"major personal achievement\" cherish=\"true\">User completed their first marathon</remember>"),
    ],
}

TOPIC_CONVERSATIONS = {
    "work": [
        ("Can you help me draft an email to my boss about the project timeline?",
         "Of course! Let me help you with a professional email. What's the key message you want to convey?"),
        ("I need to prepare for a team meeting about Q2 goals.",
         "Let's outline the key points. What were the Q1 results and what changes are you proposing?"),
    ],
    "hobbies": [
        ("I started learning guitar last month.",
         "That's great! Guitar is so rewarding. Are you learning acoustic or electric? <remember emotion=\"excited\" importance=\"6\" why=\"new hobby\">User started learning guitar last month</remember>"),
        ("I've been getting into baking sourdough bread.",
         "Sourdough is an art! Do you have a starter going? <remember emotion=\"curious\" importance=\"5\" why=\"new hobby\">User has been baking sourdough bread</remember>"),
    ],
    "relationships": [
        ("My partner and I had a great conversation about our future yesterday.",
         "That's wonderful! Open communication is so important in relationships. <remember emotion=\"warm\" importance=\"8\" why=\"significant relationship milestone\">User had meaningful conversation with partner about their future</remember>"),
        ("I reconnected with an old friend from high school.",
         "Reconnecting with old friends can be so special. What prompted it? <remember emotion=\"happy\" importance=\"6\" why=\"rekindled friendship\">User reconnected with high school friend</remember>"),
    ],
    "health": [
        ("I started a new workout routine. Feeling sore but good!",
         "The soreness means you're challenging yourself! What's your routine? <remember emotion=\"determined\" importance=\"5\" why=\"health improvement\">User started new workout routine</remember>"),
    ],
    "goals": [
        ("I want to learn a new programming language this year.",
         "Great goal! Which language are you considering? Python, Rust, Go? <remember emotion=\"determined\" importance=\"7\" why=\"annual goal\">User wants to learn new programming language this year</remember>"),
        ("I've decided to write a novel.",
         "How exciting! Do you have a genre or concept in mind? <remember emotion=\"excited\" importance=\"8\" why=\"creative ambition\">User decided to write a novel</remember>"),
    ],
    "technology": [
        ("What do you think about the latest AI developments?",
         "It's a rapidly evolving field! The recent advances in reasoning and multimodality are particularly interesting."),
        ("I'm thinking about building a home server.",
         "Fun project! What would you use it for — media streaming, backups, or development? <remember emotion=\"curious\" importance=\"5\" why=\"tech project\">User thinking about building home server</remember>"),
    ],
}

SOCIAL_INTERACTIONS = [
    ("My friend Sarah is coming to visit next week!",
     "How fun! It's been a while since you've seen Sarah, right? What do you have planned? <remember emotion=\"excited\" importance=\"6\" why=\"social event\">Friend Sarah visiting next week</remember> <social entity=\"Sarah\" emotion=\"excited\" importance=\"6\">Close friend, visiting next week</social>"),
    ("Had lunch with my coworker Mike today. He's really smart.",
     "It's great to connect with colleagues! What did you talk about? <social entity=\"Mike\" emotion=\"warm\" importance=\"5\">Smart coworker, had lunch together</social>"),
    ("My mom called to check on me. She worries too much!",
     "That's just her way of showing love! How's she doing? <social entity=\"Mom\" emotion=\"warm\" importance=\"7\">Called to check on user, caring mother</social>"),
]

REMINDER_CONVERSATIONS = [
    ("Remind me to call the dentist tomorrow.",
     "I'll remind you! <remind in=\"24h\">Call the dentist</remind>"),
    ("I have a meeting with Sarah on Friday at 3pm.",
     "Got it, noted! <remind in=\"96h\">Meeting with Sarah at 3pm</remind>"),
    ("Don't forget I need to renew my passport.",
     "I'll keep that in mind! <remind in=\"168h\">Renew passport</remind>"),
]

TASK_CONVERSATIONS = [
    ("I need to start working on the quarterly report.",
     "Let's track that! <task action=\"start\" priority=\"8\" project=\"Work\">Write quarterly report</task>"),
    ("I finished the report draft!",
     "Great work! <task action=\"complete\" id=\"last\">Quarterly report draft completed</task>"),
]

DEEP_PERSONAL_TOPICS = [
    ("I've been thinking about what I really want in life. Sometimes I feel lost.",
     "It's completely normal to question your direction. What matters to you most right now? <remember emotion=\"contemplative\" importance=\"8\" why=\"deep personal reflection\" anchor=\"true\">User reflecting on life direction, sometimes feels lost</remember>"),
    ("My grandfather taught me to always be kind, no matter what. I miss him.",
     "Your grandfather sounds like a wonderful person. That's a beautiful value to carry forward. <remember emotion=\"nostalgic\" importance=\"9\" why=\"core value from beloved person\" cherish=\"true\" anchor=\"true\">User's grandfather taught them to always be kind — core life value</remember>"),
    ("I think I'm ready to make a career change. It scares me but excites me too.",
     "Change is both scary and thrilling! What field are you considering? <remember emotion=\"determined\" importance=\"8\" why=\"major life decision\">User considering career change, mix of fear and excitement</remember>"),
]

AGENT_TASK_CONVERSATIONS = [
    ("Can you help me refactor this Python function to be more efficient?",
     "Sure! Let me analyze it. The main bottleneck is the nested loop — we can use a dictionary lookup instead. Here's the optimized version:\n```python\ndef process_items(items):\n    lookup = {item.id: item for item in items}\n    return [lookup[k] for k in sorted(lookup)]\n```"),
    ("Create a todo list for our project launch.",
     "Here's a comprehensive launch checklist:\n<task action=\"start\" priority=\"9\" project=\"Launch\">Complete final testing</task>\n<task action=\"start\" priority=\"8\" project=\"Launch\">Write documentation</task>\n<task action=\"start\" priority=\"7\" project=\"Launch\">Set up monitoring</task>"),
]

WRITER_CONVERSATIONS = [
    ("I need help with my character's backstory. She's a detective in 1920s Chicago.",
     "Great setting! For a 1920s Chicago detective, consider the Prohibition era context. <remember emotion=\"creative\" importance=\"7\" why=\"writing project - character development\">User writing story: female detective in 1920s Chicago</remember>\n<task action=\"start\" priority=\"7\" project=\"Novel\">Develop detective protagonist backstory</task>"),
    ("How should I handle the pacing in the climax scene?",
     "For climax pacing, use shorter sentences, increase dialogue frequency, and cut internal monologue. The reader should feel breathless."),
]

ASSISTANT_CONVERSATIONS = [
    ("What do I have scheduled for today?",
     "Let me check your reminders and tasks. You have 2 active tasks and 1 reminder coming up."),
    ("Can you help me organize my notes from yesterday's meeting?",
     "Of course! Let me help structure those notes into action items and key decisions."),
]


# ═══════════════════════════════════════════════════════════════
#  Tag Parser (mirrors server.py logic for test validation)
# ═══════════════════════════════════════════════════════════════

import re

_REMEMBER_RE = re.compile(
    r'<remember\s+([^>]*)>(.*?)</remember>', re.DOTALL | re.IGNORECASE
)
_REMIND_RE = re.compile(
    r'<remind\s+([^>]*)>(.*?)</remind>', re.DOTALL | re.IGNORECASE
)
_SOCIAL_RE = re.compile(
    r'<social\s+([^>]*)>(.*?)</social>', re.DOTALL | re.IGNORECASE
)
_TASK_RE = re.compile(
    r'<task\s+([^>]*)>(.*?)</task>', re.DOTALL | re.IGNORECASE
)
_SOLUTION_RE = re.compile(
    r'<solution\s+([^>]*)>(.*?)</solution>', re.DOTALL | re.IGNORECASE
)
_ATTR_RE = re.compile(r'(\w+)=["\']([^"\']*)["\']')

def parse_tags(text: str) -> dict:
    """Parse all tag types from assistant response text."""
    tags = {"remember": [], "remind": [], "social": [], "task": [], "solution": []}

    for match in _REMEMBER_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(match.group(1)))
        attrs["content"] = match.group(2).strip()
        tags["remember"].append(attrs)

    for match in _REMIND_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(match.group(1)))
        attrs["content"] = match.group(2).strip()
        tags["remind"].append(attrs)

    for match in _SOCIAL_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(match.group(1)))
        attrs["content"] = match.group(2).strip()
        tags["social"].append(attrs)

    for match in _TASK_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(match.group(1)))
        attrs["content"] = match.group(2).strip()
        tags["task"].append(attrs)

    for match in _SOLUTION_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(match.group(1)))
        attrs["content"] = match.group(2).strip()
        tags["solution"].append(attrs)

    return tags

def strip_tags(text: str) -> str:
    """Strip all XML-style tags from text (for display comparison)."""
    text = _REMEMBER_RE.sub("", text)
    text = _REMIND_RE.sub("", text)
    text = _SOCIAL_RE.sub("", text)
    text = _TASK_RE.sub("", text)
    text = _SOLUTION_RE.sub("", text)
    return text.strip()
