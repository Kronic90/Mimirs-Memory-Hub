"""
Gap #9 — Vividness/fading granularity over 1-2 simulated years.

Uses FixedHarness (tests/long_term/_time_patch.py), NOT the stock
SimulationHarness, because the stock harness's TimeWarp does not reach
datetime.now()-based decay math -- see test_audit_timewarp_bug.py.

Snapshots vividness at week 1, month 1, month 3, month 6, year 1, year 2
for memories at different importance tiers, and checks:
  - low/medium importance memories show a smooth, monotonic, graduated
    decay curve (not cliff-edged).
  - cherished/anchored/flashbulb memories resist fading as designed.
  - whether the "normal" importance tier actually becomes hard-to-recall
    by year 1-2 as the README claims, or plateaus at an artificial floor.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.long_term._time_patch import FixedHarness

CHECKPOINTS_DAYS = [7, 30, 90, 180, 365, 730]


def _snapshot_curve(h, mem, label):
    curve = []
    elapsed = 0
    for target_day in CHECKPOINTS_DAYS:
        h.advance_days(target_day - elapsed)
        elapsed = target_day
        curve.append((target_day, mem.vividness))
    print(f"[{label}] " + " ".join(f"d{d}={v:.3f}" for d, v in curve))
    return curve


def test_low_importance_memory_fades_smoothly_and_substantially():
    with FixedHarness("fade_low_imp") as h:
        h.remember("Mentioned liking oat milk in coffee", emotion="neutral",
                   importance=3)
        mem = h.mem_obj()
        v0 = mem.vividness
        curve = _snapshot_curve(h, mem, "low-imp(3)/neutral")
        values = [v0] + [v for _, v in curve]
        # Monotonicity: never increases.
        for i in range(1, len(values)):
            assert values[i] <= values[i - 1] + 1e-6, (
                f"Vividness increased unexpectedly: step {i}: "
                f"{values[i-1]} -> {values[i]}")

        # FINDING: with INITIAL_STABILITY=3.0 days (vividmimir/constants.py)
        # and no spaced-repetition re-access, an importance-3 neutral
        # memory loses the overwhelming majority of its vividness in the
        # FIRST WEEK, not gradually over months as the README's "falls out
        # of recall after 3-6 months" framing implies. This is correct
        # exponential math (not a bug), but the effective human-perceived
        # curve for below-average-importance content is "vivid for ~1
        # week, then essentially gone within a month" rather than a
        # multi-month graduated fade.
        week1_drop_fraction = (v0 - curve[0][1]) / max(v0, 1e-9)
        month1_value = curve[1][1]
        print(f"[low-imp curve shape] week1_drop_fraction="
              f"{week1_drop_fraction:.3f} month1_value={month1_value:.6f}")
        assert week1_drop_fraction > 0.5, (
            "Expected to confirm the fast-initial-decay finding; if this "
            "fails, INITIAL_STABILITY or the decay formula changed")
        assert month1_value < 0.01, (
            "Expected near-zero vividness within a month for imp-3 "
            "neutral content under current INITIAL_STABILITY; if this "
            "fails the decay rate has slowed down")
        # By year 2, a low-importance, never-revisited, non-emotional
        # memory should be most of the way to "forgotten" (human-like).
        assert values[-1] < v0 * 0.4, (
            f"Low-importance memory barely faded after 2 years: "
            f"v0={v0:.3f} -> v2yr={values[-1]:.3f}")


def test_normal_vs_cherished_vs_anchor_divergence_over_2_years():
    with FixedHarness("fade_divergence") as h:
        h.remember("Normal conversational detail about weekend plans",
                   emotion="neutral", importance=4)
        normal_mem = h.mem_obj()

        h.remember("A moment I want to treasure forever",
                   emotion="content", importance=6)
        cherish_mem = h.mem_obj()
        idx = len(h.manager._mimir._reflections) - 1
        h.manager.toggle_cherish(idx)

        h.remember("A core fact about who I am",
                   emotion="neutral", importance=6)
        anchor_mem = h.mem_obj()
        idx2 = len(h.manager._mimir._reflections) - 1
        h.manager.toggle_anchor(idx2)

        n0, c0, a0 = normal_mem.vividness, cherish_mem.vividness, anchor_mem.vividness
        h.advance_days(730)
        n2, c2, a2 = normal_mem.vividness, cherish_mem.vividness, anchor_mem.vividness

        print(f"[divergence] normal {n0:.3f}->{n2:.3f} | "
              f"cherished {c0:.3f}->{c2:.3f} | anchor {a0:.3f}->{a2:.3f}")

        assert n2 < n0 * 0.5, "Normal memory should fade substantially by year 2"
        # cherish/anchor should retain much more of their original vividness
        # than the plain memory, proportionally.
        assert (c2 / c0) > (n2 / n0), (
            "Cherished memory did not retain proportionally more "
            "vividness than a normal memory over 2 years")
        assert (a2 / a0) > (n2 / n0), (
            "Anchored memory did not retain proportionally more "
            "vividness than a normal memory over 2 years")


def test_high_importance_emotional_memory_hits_permanent_flashbulb_floor():
    """Documents real behaviour: importance>=8 + high-arousal emotion
    triggers flashbulb encoding (vividmimir/write_mixin.py, gated by
    FLASHBULB_AROUSAL_THRESHOLD/FLASHBULB_IMPORTANCE_MIN in constants.py),
    which pins vividness at importance*FLASHBULB_VIVIDNESS_FLOOR (0.85)
    PERMANENTLY -- it does not continue to fade at all after hitting the
    floor, even from year 1 to year 2. This is a deliberate design choice
    (flashbulb memories resist fading, consistent with the neuroscience
    literature this project cites) but it means any memory a character
    saves with importance>=8 under a high-arousal emotion (joyful, excited,
    angry, afraid, triumphant, etc.) effectively never fades -- which is a
    large fraction of what companion/character presets are encouraged to
    save per presets.py's system-prompt guidance ('proactively mark truly
    precious... cherish=true... anchor=true').

    NOTE: deliberately uses emotion="excited" (arousal 0.8, NOT aliased by
    memory_manager.normalize_emotion) rather than "joyful". See
    test_audit_emotion_nuance.py::test_joyful_alias_breaks_flashbulb_threshold
    for the companion finding: "joyful" (an emotion the system prompt
    explicitly advertises) gets silently collapsed to "happy" before
    reaching this exact flashbulb check, and happy's arousal (0.4) falls
    BELOW FLASHBULB_AROUSAL_THRESHOLD (0.6) where joyful's own (0.6) would
    have cleared it -- so the emotion-alias bug actually flips whether a
    memory gets permanently protected from fading."""
    with FixedHarness("flashbulb_floor") as h:
        h.remember("An exciting milestone moment", emotion="excited",
                   importance=8)
        mem = h.mem_obj()
        assert mem._is_flashbulb, "Expected this memory to encode as flashbulb"
        h.advance_days(365)
        v1 = mem.vividness
        h.advance_days(365)
        v2 = mem.vividness
        print(f"[flashbulb floor] year1={v1:.4f} year2={v2:.4f} "
              f"(importance*0.85={8*0.85})")
        assert v1 == v2, (
            "Expected flashbulb floor to be a hard, non-decaying floor "
            "between year 1 and year 2 -- if this fails the floor "
            "mechanic changed and this doc-comment is stale")
        assert abs(v1 - 8 * 0.85) < 1e-6


if __name__ == "__main__":
    test_low_importance_memory_fades_smoothly_and_substantially()
    test_normal_vs_cherished_vs_anchor_divergence_over_2_years()
    test_high_importance_emotional_memory_hits_permanent_flashbulb_floor()
    print("ALL VIVIDNESS FADING AUDIT PROBES RAN")
