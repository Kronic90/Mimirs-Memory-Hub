"""
Gap #1 — Visual memory (<remember source="visual"/> path + <showimage/>
recall) and Gap #2 — Self-identity memories (identity="true"/category="self").

Uses FixedHarness (real simulated-time decay) for the multi-month checks,
since visual_clarity/can_show are vividness-threshold-gated and the stock
SimulationHarness's TimeWarp doesn't reach that math (test_audit_timewarp_bug.py).
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

from tests.long_term._time_patch import FixedHarness

# A tiny valid PNG (1x1 red pixel) so PIL can actually decode/recompress it.
import base64
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YA"
    "AAAASUVORK5CYII="
)


def test_visual_memory_hash_stable_and_recallable_after_months():
    with FixedHarness("visual_stability") as h:
        mgr = h.manager
        result = mgr.remember_visual(
            image_bytes=_TINY_PNG,
            description="A photo the user shared of their new apartment",
            emotion="happy", importance=7,
        )
        assert result.get("visual_hash"), (
            "remember_visual did not produce a visual_hash -- visual_enabled "
            "may be False (PIL missing) or compression failed")
        h0_hash = result["visual_hash"]

        img_bytes_0 = mgr.get_visual_image(h0_hash)
        assert img_bytes_0, "Could not retrieve raw image bytes right after saving"

        h.advance_days(120)  # ~4 months

        img_bytes_later = mgr.get_visual_image(h0_hash)
        assert img_bytes_later is not None, (
            "Visual image file disappeared after 4 simulated months -- "
            "hash should remain stable and the file should persist")
        assert img_bytes_later == img_bytes_0, (
            "Stored image bytes changed over time -- hash is supposed to "
            "be a stable content identifier for the ORIGINAL file; fading "
            "is applied at display-time via get_visual(), not by mutating "
            "the stored file")

        visuals = mgr.get_visual_memories()
        assert any(v["visual_hash"] == h0_hash for v in visuals), (
            "Visual memory no longer appears in get_visual_memories() "
            "after 4 months")

        ctx = mgr.get_visual_context_block()
        print("[visual context block after 4mo]\n"
              + ctx.encode("ascii", "backslashreplace").decode("ascii"))
        assert h0_hash in ctx, (
            "Visual memory's hash is not surfaced in the context block "
            "the model uses to decide whether to <showimage/> it -- a "
            "4-month-old photo the model should still be able to "
            "reference is invisible to it")


def test_visual_clarity_degrades_then_image_becomes_unavailable():
    """Checks the fading tiers (vivid -> faded -> gone) actually trigger
    at the documented importance/time combination, using a LOW importance
    visual memory so it crosses both thresholds within 2 years."""
    with FixedHarness("visual_clarity_tiers") as h:
        mgr = h.manager
        result = mgr.remember_visual(
            image_bytes=_TINY_PNG,
            description="A casual snapshot, nothing special",
            emotion="neutral", importance=3,
        )
        img_hash = result["visual_hash"]
        mem = h.mem_obj()
        clarity_0 = mem.visual_clarity
        h.advance_days(60)
        clarity_60 = mem.visual_clarity
        h.advance_days(670)  # ~2 years total
        clarity_730 = mem.visual_clarity
        print(f"[visual clarity tiers] t0={clarity_0} t60d={clarity_60} "
              f"t2yr={clarity_730}")
        assert clarity_0 == "vivid"
        # Tiers are vivid -> faded -> gist_only (models.py:265-273); at
        # gist_only, write_mixin.get_visual() no longer returns image
        # bytes at all (only the text description survives) -- the visual
        # equivalent of "I remember there was a photo but not the details".
        assert clarity_730 == "gist_only", (
            f"Expected a low-importance visual memory to reach the "
            f"lowest clarity tier by year 2, got clarity={clarity_730}")
        visual_result = h.manager._mimir.get_visual(mem)
        print(f"[get_visual at gist_only] available={visual_result['available']}")
        assert visual_result["available"] is False, (
            "Expected image bytes to no longer be returned once a visual "
            "memory reaches gist_only clarity")


def test_identity_memories_distinct_from_about_user_and_surfaced_in_context():
    """Self-identity memories (category='self') should: (1) accumulate
    and be queryable as a consistent block distinct from memories ABOUT
    the user, (2) be counted correctly in stats()['self_count'], and
    (3) be surfaced in get_context_block's '=== WHO I AM ===' section
    regardless of conversational topic (core.py:get_self_identity /
    get_context_block)."""
    with FixedHarness("identity_memories") as h:
        mgr = h.manager
        mgr.remember(content="I tend to be curious and ask a lot of questions",
                     emotion="curious", importance=7, source="reflection",
                     category="self")
        mgr.remember(content="I value honesty above almost everything else",
                     emotion="thoughtful", importance=8, source="reflection",
                     category="self")
        mgr.remember(content="User's favorite color is teal",
                     emotion="neutral", importance=4, source="conversation")
        mgr.remember(content="User works as a nurse",
                     emotion="neutral", importance=5, source="conversation")

        stats = mgr.stats()
        print(f"[identity stats] self_count={stats.get('self_count')} "
              f"total={stats.get('total_reflections')}")
        assert stats.get("self_count") == 2, (
            f"Expected self_count==2, got {stats.get('self_count')} -- "
            f"identity memories not being counted correctly or bleeding "
            f"into the general count")

        identity_mems = mgr._mimir.get_self_identity()
        contents = {m.content for m in identity_mems}
        assert "User's favorite color is teal" not in contents, (
            "A memory ABOUT the user leaked into get_self_identity()")
        assert any("curious" in c or "honesty" in c for c in contents), (
            "Expected identity memories to be retrievable via "
            "get_self_identity()")

        # Context block should surface identity even when the current
        # conversation topic has nothing to do with it.
        ctx = mgr.get_context_block(conversation_context="What's the weather like today?")
        print("[context block w/ off-topic conversation]\n"
              + ctx[:800].encode("ascii", "backslashreplace").decode("ascii"))
        assert "WHO I AM" in ctx, (
            "Identity section did not appear in the context block even "
            "though self_count > 0 -- identity should be persistent "
            "context, not filtered by topical relevance")
        assert "honesty" in ctx or "curious" in ctx, (
            "Identity section present but neither identity memory's "
            "content actually made it into the rendered context block")


def test_identity_memories_resist_being_overwhelmed_by_volume():
    """With many more 'about the user' memories than identity memories,
    the identity block should still surface -- identity memories are
    selected by their own category, not by competing for a shared
    relevance-ranked slot (if they did compete, high memory volume could
    silently crowd identity out)."""
    with FixedHarness("identity_volume") as h:
        mgr = h.manager
        mgr.remember(content="At my core, I care deeply about creativity",
                     emotion="warm", importance=8, source="reflection",
                     category="self")
        for i in range(40):
            mgr.remember(content=f"User mentioned detail number {i} about their day",
                         emotion="neutral", importance=3,
                         source="conversation")
        stats = mgr.stats()
        assert stats.get("self_count") == 1
        ctx = mgr.get_context_block(conversation_context="random unrelated topic")
        assert "creativity" in ctx, (
            "Single identity memory got crowded out of the context block "
            "by 40 unrelated higher-recency 'about the user' memories")


if __name__ == "__main__":
    test_visual_memory_hash_stable_and_recallable_after_months()
    test_visual_clarity_degrades_then_image_becomes_unavailable()
    test_identity_memories_distinct_from_about_user_and_surfaced_in_context()
    test_identity_memories_resist_being_overwhelmed_by_volume()
    print("ALL VISUAL/IDENTITY AUDIT PROBES RAN")
