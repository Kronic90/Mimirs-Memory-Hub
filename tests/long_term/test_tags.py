"""
Tag Parsing & Processing Tests
================================
Tests all XML tag types that the system parses from LLM responses:
- <remember> with all attributes
- <remind> (time-based and date-based)
- <social> impressions
- <task> management
- <solution> patterns
- <cherish> retroactive
- Tag stripping from display text
- Malformed tag handling
- Nested/escaped content robustness
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.long_term.harness import SimulationHarness, parse_tags, strip_tags


def test_remember_tag_basic():
    """Test: basic <remember> tag parsing."""
    with SimulationHarness("tag_remember") as h:
        text = '<remember emotion="happy" importance="8" why="test">User is happy</remember>'
        tags = parse_tags(text)

        r = tags["remember"]
        h.metrics.record("remember_count", len(r) == 1,
                         f"Found {len(r)} remember tags")
        if r:
            h.metrics.record("remember_emotion", r[0].get("emotion") == "happy",
                             f"Emotion: {r[0].get('emotion')}")
            h.metrics.record("remember_importance", r[0].get("importance") == "8",
                             f"Importance: {r[0].get('importance')}")
            h.metrics.record("remember_why", r[0].get("why") == "test",
                             f"Why: {r[0].get('why')}")
            h.metrics.record("remember_content", r[0].get("content") == "User is happy",
                             f"Content: {r[0].get('content')}")

        return h.metrics


def test_remember_tag_cherished():
    """Test: <remember> with cherish and anchor attributes."""
    with SimulationHarness("tag_cherish") as h:
        text = ('<remember emotion="overjoyed" importance="10" why="milestone" '
                'cherish="true" anchor="true">Wedding day!</remember>')
        tags = parse_tags(text)

        r = tags["remember"]
        h.metrics.record("cherish_parsed", len(r) == 1, f"Tags: {len(r)}")
        if r:
            h.metrics.record("cherish_flag", r[0].get("cherish") == "true",
                             f"Cherish: {r[0].get('cherish')}")
            h.metrics.record("anchor_flag", r[0].get("anchor") == "true",
                             f"Anchor: {r[0].get('anchor')}")

        return h.metrics


def test_multiple_remember_tags():
    """Test: multiple <remember> tags in one response."""
    with SimulationHarness("tag_multi_remember") as h:
        text = (
            'Here\'s what I noted:\n'
            '<remember emotion="happy" importance="7" why="a">Memory A</remember>\n'
            '<remember emotion="sad" importance="5" why="b">Memory B</remember>\n'
            '<remember emotion="curious" importance="6" why="c">Memory C</remember>'
        )
        tags = parse_tags(text)

        h.metrics.record("multi_remember", len(tags["remember"]) == 3,
                         f"Found {len(tags['remember'])} tags (expected 3)")

        return h.metrics


def test_remind_tag():
    """Test: <remind> tag with time-based and date-based formats."""
    with SimulationHarness("tag_remind") as h:
        # Time-based
        text1 = '<remind in="24h">Call the dentist</remind>'
        tags1 = parse_tags(text1)
        h.metrics.record("remind_timebased", len(tags1["remind"]) == 1,
                         f"Time-based: {tags1['remind']}")
        if tags1["remind"]:
            h.metrics.record("remind_content",
                             tags1["remind"][0]["content"] == "Call the dentist",
                             f"Content: {tags1['remind'][0].get('content')}")

        # Date-based
        text2 = '<remind date="2025-12-25">Christmas shopping</remind>'
        tags2 = parse_tags(text2)
        h.metrics.record("remind_datebased", len(tags2["remind"]) == 1,
                         f"Date-based: {tags2['remind']}")

        return h.metrics


def test_social_tag():
    """Test: <social> impression tag."""
    with SimulationHarness("tag_social") as h:
        text = '<social entity="Sarah" emotion="warm" importance="7">Close friend, loves hiking</social>'
        tags = parse_tags(text)

        s = tags["social"]
        h.metrics.record("social_parsed", len(s) == 1, f"Found: {len(s)}")
        if s:
            h.metrics.record("social_entity", s[0].get("entity") == "Sarah",
                             f"Entity: {s[0].get('entity')}")
            h.metrics.record("social_emotion", s[0].get("emotion") == "warm",
                             f"Emotion: {s[0].get('emotion')}")

        return h.metrics


def test_task_tag():
    """Test: <task> tag with various actions."""
    with SimulationHarness("tag_task") as h:
        # Start
        text1 = '<task action="start" priority="8" project="Work">Write report</task>'
        tags1 = parse_tags(text1)
        h.metrics.record("task_start", len(tags1["task"]) == 1,
                         f"Start: {tags1['task']}")
        if tags1["task"]:
            h.metrics.record("task_action", tags1["task"][0].get("action") == "start",
                             f"Action: {tags1['task'][0].get('action')}")
            h.metrics.record("task_project", tags1["task"][0].get("project") == "Work",
                             f"Project: {tags1['task'][0].get('project')}")

        # Complete
        text2 = '<task action="complete" id="123">Report done</task>'
        tags2 = parse_tags(text2)
        h.metrics.record("task_complete", len(tags2["task"]) == 1,
                         f"Complete: {tags2['task']}")

        # Fail
        text3 = '<task action="fail" id="456">Could not finish</task>'
        tags3 = parse_tags(text3)
        h.metrics.record("task_fail", len(tags3["task"]) == 1,
                         f"Fail: {tags3['task']}")

        return h.metrics


def test_solution_tag():
    """Test: <solution> pattern tag."""
    with SimulationHarness("tag_solution") as h:
        text = '<solution problem="slow queries" importance="8">Add database indexes on frequently filtered columns</solution>'
        tags = parse_tags(text)

        s = tags["solution"]
        h.metrics.record("solution_parsed", len(s) == 1, f"Found: {len(s)}")
        if s:
            h.metrics.record("solution_problem",
                             s[0].get("problem") == "slow queries",
                             f"Problem: {s[0].get('problem')}")
            h.metrics.record("solution_content",
                             "database indexes" in s[0].get("content", ""),
                             f"Content: {s[0].get('content')}")

        return h.metrics


def test_tag_stripping():
    """Test: tags are stripped from display text."""
    with SimulationHarness("tag_strip") as h:
        text = ('Great news! <remember emotion="happy" importance="8" why="test">'
                'User got promoted</remember> I\'m so proud of you! '
                '<remind in="24h">Follow up on celebration</remind>')

        stripped = strip_tags(text)
        h.metrics.record("strip_remember", "<remember" not in stripped,
                         f"Stripped: '{stripped[:80]}'")
        h.metrics.record("strip_remind", "<remind" not in stripped,
                         f"No remind tag in stripped text")
        h.metrics.record("strip_preserves_text", "Great news!" in stripped,
                         "Display text preserved")
        h.metrics.record("strip_preserves_text2", "proud of you" in stripped,
                         "Surrounding text preserved")

        return h.metrics


def test_mixed_tags():
    """Test: response with multiple tag types at once."""
    with SimulationHarness("tag_mixed") as h:
        text = (
            'That\'s exciting! '
            '<remember emotion="excited" importance="8" why="trip">User booked Japan trip</remember> '
            '<social entity="Sarah" emotion="excited" importance="6">Going on trip together</social> '
            '<remind in="168h">Check Japan visa requirements</remind> '
            '<task action="start" priority="5" project="Travel">Plan Japan itinerary</task>'
        )

        tags = parse_tags(text)
        h.metrics.record("mixed_remember", len(tags["remember"]) == 1)
        h.metrics.record("mixed_social", len(tags["social"]) == 1)
        h.metrics.record("mixed_remind", len(tags["remind"]) == 1)
        h.metrics.record("mixed_task", len(tags["task"]) == 1)

        stripped = strip_tags(text)
        h.metrics.record("mixed_stripped", "<" not in stripped or ">" not in stripped,
                         f"Stripped: '{stripped[:60]}'")

        return h.metrics


def test_malformed_tags():
    """Test: malformed tags don't crash the parser."""
    with SimulationHarness("tag_malformed") as h:
        malformed_cases = [
            # Unclosed tag
            '<remember emotion="happy">No closing tag',
            # Missing attributes
            '<remember>Just content</remember>',
            # Empty content
            '<remember emotion="test" importance="5" why="test"></remember>',
            # Nested incorrectly
            '<remember emotion="a"><remember emotion="b">inner</remember></remember>',
            # HTML entities
            '<remember emotion="happy" importance="5" why="test">Content with &amp; and &lt;</remember>',
            # Unicode
            '<remember emotion="happy" importance="5" why="test">Content with émojis 🎉</remember>',
            # Very long content
            '<remember emotion="happy" importance="5" why="test">' + "x" * 1000 + '</remember>',
        ]

        for i, text in enumerate(malformed_cases):
            try:
                tags = parse_tags(text)
                h.metrics.record(f"malformed_{i}_no_crash", True,
                                 f"Parsed without crash: {text[:50]}")
            except Exception as e:
                h.metrics.record(f"malformed_{i}_no_crash", False,
                                 f"CRASHED: {e}")

        return h.metrics


def test_process_turn_with_tags():
    """Test: process_turn correctly handles tagged responses."""
    with SimulationHarness("tag_process_turn") as h:
        result = h.process(
            "I just adopted a puppy named Biscuit!",
            "How wonderful! Puppies bring so much joy! "
            "<remember emotion=\"happy\" importance=\"8\" why=\"new pet\">"
            "User adopted a puppy named Biscuit</remember>"
        )

        h.metrics.record("process_turn_result",
                         result is not None and "emotion" in result,
                         f"Result keys: {list(result.keys()) if result else 'None'}")

        # Memory should be stored via process_turn
        h.assert_recall("puppy named Biscuit", "Biscuit",
                        label="tag_creates_memory")

        return h.metrics


# ═══════════════════════════════════════════════════════════════
#  Collect all tests
# ═══════════════════════════════════════════════════════════════

ALL_TAG_TESTS = [
    ("Remember Tag Basic", test_remember_tag_basic),
    ("Remember Tag Cherished", test_remember_tag_cherished),
    ("Multiple Remember Tags", test_multiple_remember_tags),
    ("Remind Tag", test_remind_tag),
    ("Social Tag", test_social_tag),
    ("Task Tag", test_task_tag),
    ("Solution Tag", test_solution_tag),
    ("Tag Stripping", test_tag_stripping),
    ("Mixed Tags", test_mixed_tags),
    ("Malformed Tags", test_malformed_tags),
    ("Process Turn with Tags", test_process_turn_with_tags),
]
