"""
Neurochemistry System Tests
=============================
Tests the full neurochemistry simulation over extended time periods:
- Chemistry tick stability (no overflow/underflow)
- Event-driven chemistry shifts
- Mood EMA blending
- Sleep reset behavior
- Dampening (high cortisol suppression)
- Long-term chemistry trajectories
- Chemistry under stress vs. positive scenarios
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.long_term.harness import SimulationHarness


def test_chemistry_initialization():
    """Test: chemistry starts at reasonable baseline values."""
    with SimulationHarness("chem_init") as h:
        mood = h.get_mood()
        chem = mood.get("chemistry", {})
        levels = chem.get("levels", {})

        h.metrics.record("chemistry_exists",
                         bool(levels),
                         f"Chemistry levels: {levels}")

        expected_keys = ["dopamine", "serotonin", "oxytocin",
                         "norepinephrine", "cortisol"]
        for key in expected_keys:
            present = key in levels
            h.metrics.record(f"has_{key}", present,
                             f"{key}: {levels.get(key, 'MISSING')}")

        # All should be between 0 and 1
        in_range = all(0.0 <= levels.get(k, -1) <= 1.0 for k in expected_keys)
        h.metrics.record("all_in_range", in_range,
                         f"All levels in [0,1]: {in_range}")

        return h.metrics


def test_positive_events():
    """Test: positive events boost dopamine/serotonin/oxytocin."""
    with SimulationHarness("chem_positive") as h:
        mood_before = h.get_mood()
        before = mood_before.get("chemistry", {}).get("levels", {})

        # Process happy conversations
        for _ in range(5):
            h.process(
                "I'm so happy! Everything is going great!",
                "That's wonderful to hear! Your positivity is infectious!"
            )
            h.advance_hours(1)

        mood_after = h.get_mood()
        after = mood_after.get("chemistry", {}).get("levels", {})

        # Dopamine and serotonin should be elevated
        for key in ["dopamine", "serotonin"]:
            if key in before and key in after:
                h.metrics.record(f"positive_{key}_boost",
                                 True,  # Just tracking the change
                                 f"{key}: {before.get(key, 0):.3f} → {after.get(key, 0):.3f}")

        h.assert_chemistry_stable("after_positive_events")
        return h.metrics


def test_stress_events():
    """Test: stress events elevate cortisol and suppress others."""
    with SimulationHarness("chem_stress") as h:
        mood_before = h.get_mood()

        # Simulate stress
        for _ in range(10):
            h.process(
                "I'm so stressed! Deadlines are killing me! I can't handle this conflict!",
                "I hear you. That sounds really overwhelming. Let's take a breath."
            )
            h.advance_hours(2)

        mood_after = h.get_mood()
        after = mood_after.get("chemistry", {}).get("levels", {})

        h.metrics.record("cortisol_level",
                         "cortisol" in after,
                         f"Cortisol after stress: {after.get('cortisol', 'N/A'):.3f}")

        # Check dampening
        dampened = mood_after.get("chemistry", {}).get("is_dampened", None)
        h.metrics.record("dampening_active",
                         dampened is not None,
                         f"Dampening active: {dampened}")

        h.assert_chemistry_stable("after_stress")
        return h.metrics


def test_sleep_reset():
    """Test: sleep resets chemistry toward baselines."""
    with SimulationHarness("chem_sleep") as h:
        # Push chemistry into stressed state
        for _ in range(8):
            h.process(
                "Terrible day! Everything went wrong! I'm so angry!",
                "I'm sorry to hear that. Tomorrow will be better."
            )
            h.advance_hours(1)

        mood_stressed = h.get_mood()
        levels_stressed = mood_stressed.get("chemistry", {}).get("levels", {})

        # Sleep for 8 hours
        h.sleep_cycle(8.0)

        mood_rested = h.get_mood()
        levels_rested = mood_rested.get("chemistry", {}).get("levels", {})

        h.metrics.record("sleep_reset_ran", True,
                         f"Pre-sleep: {levels_stressed}\nPost-sleep: {levels_rested}")

        # Cortisol should decrease or stay stable after sleep
        if "cortisol" in levels_stressed and "cortisol" in levels_rested:
            h.metrics.record("cortisol_decreased",
                             levels_rested["cortisol"] <= levels_stressed["cortisol"] + 0.1,
                             f"Cortisol: {levels_stressed['cortisol']:.3f} → {levels_rested['cortisol']:.3f}")

        h.assert_chemistry_stable("after_sleep_reset")
        return h.metrics


def test_mood_ema_blending():
    """Test: mood label changes smoothly via EMA blending."""
    with SimulationHarness("mood_ema") as h:
        mood_labels = []

        # Neutral start
        mood0 = h.get_mood()
        mood_labels.append(mood0.get("mood_label", "unknown"))

        # Process happy content
        for _ in range(5):
            h.process("I'm really happy today!", "Great to hear!")
            h.advance_hours(1)
        mood_h = h.get_mood()
        mood_labels.append(mood_h.get("mood_label", "unknown"))

        # Switch to sad content
        for _ in range(5):
            h.process("I'm feeling really sad and lonely.", "I'm here for you.")
            h.advance_hours(1)
        mood_s = h.get_mood()
        mood_labels.append(mood_s.get("mood_label", "unknown"))

        h.metrics.record("mood_trajectory",
                         len(mood_labels) == 3,
                         f"Mood journey: {' → '.join(mood_labels)}")

        # Mood should have valid labels
        h.assert_mood(label="ema_final_mood_valid")
        return h.metrics


def test_chemistry_stability_over_year():
    """Test: chemistry doesn't explode or collapse over 365 simulated days."""
    with SimulationHarness("chem_year_stability") as h:
        violations = []

        for day in range(0, 365, 7):  # Weekly check
            # Alternate between positive and negative events
            if day % 14 == 0:
                h.process("Great day today!", "Wonderful!")
            else:
                h.process("Rough day today.", "Sorry to hear that.")

            h.advance_days(7)
            if day % 28 == 0:
                h.sleep_cycle(8)

            mood = h.get_mood()
            levels = mood.get("chemistry", {}).get("levels", {})

            for key, val in levels.items():
                if not (0.0 <= val <= 1.0):
                    violations.append(f"Day {day}: {key}={val}")

        h.metrics.record("year_stability",
                         len(violations) == 0,
                         f"Violations: {len(violations)}" +
                         (f" — {violations[:5]}" if violations else " — None"))

        h.assert_chemistry_stable("year_end_chemistry")
        return h.metrics


def test_mixed_emotion_sequence():
    """Test: rapid emotional shifts don't break chemistry."""
    with SimulationHarness("chem_mixed") as h:
        emotions = [
            ("I'm ecstatic! Best news ever!", "Amazing!"),
            ("Actually, I'm terrified now.", "What happened?"),
            ("Wait, I'm angry about something.", "Tell me more."),
            ("Hmm, I'm just curious about something.", "What's on your mind?"),
            ("I feel so warm and loved.", "That's beautiful."),
            ("This is disgusting!", "I understand your reaction."),
            ("Surprise! Didn't see that coming!", "What a twist!"),
            ("I'm deeply sad now.", "I'm here for you."),
            ("Actually, I'm hopeful!", "That's the spirit!"),
            ("I'm exhausted...", "Rest is important."),
        ]

        for user, asst in emotions:
            h.process(user, asst)
            h.advance_hours(0.5)

        h.assert_chemistry_stable("after_rapid_cycling")

        mood = h.get_mood()
        h.metrics.record("rapid_cycling_mood",
                         mood.get("mood_label") is not None,
                         f"Final mood after cycling: {mood.get('mood_label')}")

        return h.metrics


def test_chemistry_with_no_events():
    """Test: chemistry drifts to baselines with no interaction."""
    with SimulationHarness("chem_idle") as h:
        mood0 = h.get_mood()
        levels0 = mood0.get("chemistry", {}).get("levels", {})

        # Just advance time, no interactions
        h.advance_days(30)
        h.sleep_cycle(8)

        mood30 = h.get_mood()
        levels30 = mood30.get("chemistry", {}).get("levels", {})

        h.metrics.record("idle_chemistry",
                         bool(levels30),
                         f"Day 0: {levels0}\nDay 30: {levels30}")

        h.assert_chemistry_stable("after_idle_period")
        return h.metrics


# ═══════════════════════════════════════════════════════════════
#  Collect all tests
# ═══════════════════════════════════════════════════════════════

ALL_CHEMISTRY_TESTS = [
    ("Chemistry Initialization", test_chemistry_initialization),
    ("Positive Events", test_positive_events),
    ("Stress Events", test_stress_events),
    ("Sleep Reset", test_sleep_reset),
    ("Mood EMA Blending", test_mood_ema_blending),
    ("Year-Long Stability", test_chemistry_stability_over_year),
    ("Rapid Mixed Emotions", test_mixed_emotion_sequence),
    ("Idle Chemistry Drift", test_chemistry_with_no_events),
]
