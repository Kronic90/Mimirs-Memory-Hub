"""
AUDIT FINDING — TimeWarp does not reach the engine's decay math
=================================================================
`SimulationHarness.clock.patched()` (tests/long_term/harness.py) only
monkeypatches `time.time`. The entire vividmimir engine computes memory
age via `datetime.now()` (vividmimir/models.py:76,154-156,228; core.py;
write_mixin.py; neuroscience_mixin.py; yggdrasil_mixin.py; llm_mixin.py),
which that patch never touches.

Net effect: every existing test in tests/long_term/ that calls
`harness.advance_days(N)` and then inspects `.vividness`, stability,
consolidation cadence, gist compression, or Yggdrasil temporal edges is
advancing a clock the engine never looks at. Only neurochemistry/mood
(playground/memory_manager.py, which uses `time.time()` directly) is
genuinely affected by TimeWarp.

This file proves the gap exists, and shows why the existing
`test_vividness_decay` test in test_memory_lifecycle.py (assertion
`v90 <= v0`, note the `<=`) still shows green: v90 == v0 under the bug,
which trivially satisfies `<=`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.long_term.harness import SimulationHarness
from tests.long_term._time_patch import FixedHarness


def test_timewarp_now_affects_vividness():
    """Regression guard for the fixed bug: advancing the harness clock
    400 simulated days should meaningfully lower vividness (stability=3.0
    days means near-total decay by day 400 absent a floor), because
    Memory.vividness now reads the patched datetime.now(), not the real
    one. NOTE: the read of .vividness itself must happen inside
    `with h.clock.patched():` -- reading it unpatched computes age
    against the REAL wall clock (which barely moves between v0 and v400
    in test execution), making v0 and v400 look identical regardless of
    whether advance_days() worked. That accidentally made the original
    version of this test "pass" for the wrong reason in both the broken
    and fixed states."""
    with SimulationHarness("timewarp_bug_probe") as h:
        h.remember("I adopted a cat named Whiskers", emotion="content",
                   importance=5)
        mem = h.manager._mimir._reflections[-1]
        with h.clock.patched():
            v0 = mem.vividness
        h.advance_days(400)
        with h.clock.patched():
            v400 = mem.vividness

        assert v400 < v0 - 1e-6, (
            f"Regression: vividness did not decay after advance_days(400) "
            f"(v0={v0} v400={v400}) -- TimeWarp may no longer be reaching "
            f"the engine's datetime.now() calls"
        )
        print(f"[FIXED] v0={v0} v400(sim)={v400} "
              f"(harness.advance_days(400) now correctly ages the memory)")


def test_SimulationHarness_now_produces_real_decay():
    """Regression guard for the fixed bug: replays
    test_memory_lifecycle.test_vividness_decay's exact assertion shape
    (`v90 <= v0`) which used to pass even when nothing decayed at all --
    i.e. the existing regression test couldn't distinguish 'decay works'
    from 'decay is completely broken', because plain SimulationHarness's
    TimeWarp only patched time.time(), never datetime.now() (which is
    what the engine actually reads). TimeWarp.patched() now patches both,
    so SimulationHarness itself (not just the audit's separate
    FixedHarness) should produce real decay."""
    with SimulationHarness("timewarp_weak_assertion") as h:
        h.remember("first memory of the test", importance=5)
        mimir = h.manager._mimir
        with h.clock.patched():
            v0 = mimir._reflections[0].vividness
        h.advance_days(30)
        h.advance_days(60)
        with h.clock.patched():
            v90 = mimir._reflections[0].vividness
        assert v90 < v0, (
            "Regression: SimulationHarness's advance_days() no longer "
            "produces real decay -- TimeWarp.patched() may have stopped "
            "patching datetime.now() across the engine submodules again."
        )


def test_FixedHarness_patches_datetime_now_correctly():
    """Sanity-check for the audit's own corrected harness (_time_patch.py):
    with BOTH time.time() and datetime.now() patched, vividness actually
    decays as simulated days advance. Used as the foundation for the
    gap-9 (vividness/fading granularity) tests in
    test_audit_vividness_fading_2yr.py."""
    with FixedHarness("timewarp_fix_probe") as h:
        h.remember("a forgettable low-importance detail", emotion="neutral",
                   importance=3)
        mem = h.mem_obj()
        v0 = mem.vividness
        h.advance_days(60)
        v60 = mem.vividness
        assert v60 < v0, (
            f"FixedHarness should produce real decay: v0={v0} v60={v60}"
        )
        print(f"[FixedHarness OK] v0={v0:.4f} v60={v60:.4f}")


def test_chemistry_IS_correctly_timewarped_for_contrast():
    """Contrast case: memory_manager's neurochemistry tick uses
    time.time() directly (playground/memory_manager.py _tick_chemistry),
    so TimeWarp DOES correctly affect chemistry/mood decay even though it
    does not affect core vividness. Confirms the bug is module-scoped, not
    a total harness failure."""
    with SimulationHarness("timewarp_chemistry_contrast") as h:
        with h.clock.patched():
            # Perturb away from homeostatic baseline first -- ticking while
            # already at baseline has nothing to decay, which is not a bug.
            h.manager.on_event("conflict", intensity=0.9)
            h.manager._tick_chemistry()
            before = h.manager.get_mood()["chemistry"]["levels"].copy()
        h.advance_hours(6)
        with h.clock.patched():
            h.manager._tick_chemistry()
            after = h.manager.get_mood()["chemistry"]["levels"].copy()
        changed = any(
            abs(before[k] - after[k]) > 1e-9 for k in before)
        assert changed, (
            "Expected chemistry levels to shift after a 6h simulated gap "
            "(time.time()-based tick) -- if this fails, chemistry's "
            "time.time() dependency may have been removed/changed."
        )


if __name__ == "__main__":
    test_timewarp_now_affects_vividness()
    test_SimulationHarness_now_produces_real_decay()
    test_FixedHarness_patches_datetime_now_correctly()
    test_chemistry_IS_correctly_timewarped_for_contrast()
    print("ALL TIMEWARP AUDIT PROBES RAN")
