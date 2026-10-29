"""
Gap #3 — Treasure tag (<treasure query="..."/>, retroactive cherish/anchor).
Gap #4 — <dream/> and <self_reflect/>: content quality + rate limiting.
Gap #5 — Deep Recall (<recall query="..."/>): full detail, next-turn timing.

Treasure resolution now goes through MemoryManager.resolve_treasure_query(),
which playground/server.py's websocket handlers call directly (it used to be
inline top-1-recall-no-threshold logic duplicated at two call sites; it's now
a single method with a minimum lexical-overlap confidence gate). We call that
same method here rather than starting the live server, per "test the engine
directly".

Dream (volva_dream) is NOT LLM-based -- it's a template generator keyed off
word-overlap between randomly sampled memory pairs (neuroscience_mixin.py
volva_dream(), ~line 892). Self-reflect (llm_mixin.py reflect()) IS genuinely
LLM-based but requires `_llm_fn` to be wired -- the existing suite never sets
it, so that whole code path has zero existing coverage. We supply a stub
llm_fn here to actually exercise it.
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


def _server_style_treasure(mgr, query: str, anchor: bool = False) -> bool:
    """Exact replica of what playground/server.py's websocket handlers do
    for a <treasure query="..."/> tag: resolve via
    MemoryManager.resolve_treasure_query() (confidence-gated), then
    toggle cherish/anchor on whatever it resolves to, if anything."""
    idx = mgr.resolve_treasure_query(query)
    if idx is None:
        return False
    m = mgr._mimir._reflections[idx]
    changed = False
    if not getattr(m, "_cherished", False):
        mgr.toggle_cherish(idx)
        changed = True
    if anchor and not getattr(m, "_anchor", False):
        mgr.toggle_anchor(idx)
        changed = True
    return changed or True


# ─────────────────────────── Gap #3: Treasure ───────────────────────────

def test_treasure_happy_path_finds_and_marks_correct_memory():
    with FixedHarness("treasure_happy") as h:
        mgr = h.manager
        mgr.remember(content="We went to the beach last summer and watched the sunset",
                     emotion="warm", importance=6)
        mgr.remember(content="User's favorite programming language is Python",
                     emotion="neutral", importance=4)
        ok = _server_style_treasure(mgr, "the sunset at the beach")
        assert ok
        target = [m for m in mgr._mimir._reflections if "sunset" in m.content][0]
        assert target._cherished is True


def test_treasure_ambiguous_candidates_picks_best_not_arbitrary():
    """Several memories plausibly match a vague query -- verify the
    resolved target is the best lexical/semantic match, not just
    whichever happened to be remembered first/last (recency bias) or
    something unrelated."""
    with FixedHarness("treasure_ambiguous") as h:
        mgr = h.manager
        mgr.remember(content="My grandmother's birthday party was last March, "
                              "we had cake and she told old stories",
                     emotion="warm", importance=7)
        mgr.remember(content="My coworker's birthday party was last week, "
                              "just pizza at the office",
                     emotion="content", importance=3)
        mgr.remember(content="I mentioned once that birthdays aren't a big "
                              "deal to me personally",
                     emotion="neutral", importance=2)
        ok = _server_style_treasure(mgr, "grandmother's birthday party with cake and stories")
        assert ok
        cherished = [m for m in mgr._mimir._reflections if m._cherished]
        assert len(cherished) == 1
        print(f"[ambiguous treasure] matched: {cherished[0].content!r}")
        assert "grandmother" in cherished[0].content, (
            f"Treasure matched the WRONG candidate among 3 similar "
            f"'birthday party' memories: got {cherished[0].content!r}")


def test_treasure_weak_query_no_longer_cherishes_top1_without_threshold():
    """Regression guard for the fixed bug: the resolution logic used to
    have no minimum-confidence threshold, so a query with no good match
    in the memory store still cherished whatever recall() ranked #1,
    silently mis-tagging an unrelated memory as precious.
    resolve_treasure_query() now requires a minimum lexical overlap
    (0.1 Jaccard, same bar used elsewhere for attic rediscovery) before
    accepting a match, so a genuinely unrelated query should resolve to
    nothing instead."""
    with FixedHarness("treasure_no_threshold") as h:
        mgr = h.manager
        mgr.remember(content="User asked how to reset a router",
                     emotion="neutral", importance=3)
        ok = _server_style_treasure(mgr, "the time we went skydiving in New Zealand")
        cherished = [m for m in mgr._mimir._reflections if m._cherished]
        print(f"[weak-query treasure] resolved={ok} cherished_count={len(cherished)} "
              f"content={[m.content for m in cherished]}")
        assert not ok and len(cherished) == 0, (
            "Regression: an unrelated memory ('reset a router') got "
            "cherished again for a completely unrelated query "
            "('skydiving in New Zealand') -- the confidence threshold "
            "in resolve_treasure_query() may not be firing")


# ─────────────────────────── Gap #4: Dream / Self-reflect ───────────────

def test_dream_rate_limiting_blocks_back_to_back_then_allows_after_cooldown():
    with FixedHarness("dream_cooldown") as h:
        mimir = h.manager._mimir
        for i in range(6):
            h.remember(f"memory number {i} about daily life", importance=4)
        first = mimir.trigger_dream()
        second_immediate = mimir.trigger_dream()
        assert first is True
        assert second_immediate is False, (
            "Back-to-back <dream/> calls should be throttled "
            "(DREAM_COOLDOWN_SECONDS=1800)")
        h.advance_days(0.02)  # ~29 minutes, still inside cooldown
        still_blocked = mimir.trigger_dream()
        assert still_blocked is False, "Cooldown released too early"
        h.advance_days(0.01)  # push total past 1800s
        released = mimir.trigger_dream()
        assert released is True, (
            "Dream should be callable again after the cooldown window "
            "fully elapses -- if this fails the cooldown may be blocking "
            "legitimate use indefinitely")


def test_dream_theme_bridge_and_emotional_arc_embed_real_content_words():
    """Heuristic structural check (NOT an LLM judge -- volva_dream is
    template-based, not generative, so this checks the template's own
    relevance logic rather than judging prose quality). Forces exactly
    2 real memories so volva_dream's random.sample(real_mems, 2) is
    deterministic, and picks content that should trigger the
    'theme bridge' template (shared words, >30 days apart): confirms the
    generated insight actually embeds the shared vocabulary rather than
    being generic."""
    with FixedHarness("dream_quality_theme") as h:
        mimir = h.manager._mimir
        h.remember("I started learning guitar and it is really fun to practice",
                   emotion="curious", importance=5)
        h.advance_days(45)
        h.remember("Thinking back on how guitar practice has become part of my routine",
                   emotion="reflective", importance=5)
        # volva_dream() requires >=4 real memories before it samples any
        # pairs at all (neuroscience_mixin.py: `if len(real_mems) < 4:
        # return []`) -- pad with unrelated filler so the guitar pair is
        # eligible to be sampled; n_samples high enough that random
        # sampling reliably includes the guitar/guitar pair at least once
        # out of C(4,2)=6 possible pairs.
        h.remember("Bought new running shoes", emotion="content", importance=2)
        h.remember("Watched a documentary about deep sea creatures",
                   emotion="fascinated", importance=2)

        # volva_dream() picks its pair via random.sample(real_mems, 2) --
        # with 4 candidates and only a couple of eligible pairs actually
        # triggering a template, relying on chance made this test flaky.
        # Force the sampler to always return the two guitar memories so
        # the theme-bridge/emotional-arc branch is deterministically
        # exercised (this does not change volva_dream's selection LOGIC,
        # only which pair luck would have picked anyway on enough tries).
        real_mems = [m for m in mimir._reflections
                     if m.source not in ("huginn", "volva", "semantic", "summary")]
        guitar_pair = [m for m in real_mems if "guitar" in m.content.lower()]
        assert len(guitar_pair) == 2

        import random as _random_mod
        original_sample = _random_mod.sample

        def _forced_sample(population, k):
            # volva_dream() has exactly one random.sample(real_mems, 2)
            # call site -- force it to always return the guitar pair.
            if k == 2:
                return guitar_pair
            return original_sample(population, k)

        _random_mod.sample = _forced_sample
        try:
            dreams = mimir.volva_dream(n_samples=3)
        finally:
            _random_mod.sample = original_sample
        print(f"[theme-bridge dream insights] {[d.content for d in dreams]}")
        assert dreams, "Expected a theme-bridge insight from 2 guitar-themed, 45-day-apart memories"
        assert any("guitar" in d.content.lower() for d in dreams), (
            "Theme-bridge dream insight did not embed the actual shared "
            "theme word from the source memories")


def test_dream_temporal_cluster_template_now_embeds_real_content():
    """Regression guard for the fixed bug: unlike the theme-bridge/
    emotional-arc templates (which embed real shared vocabulary -- see
    the sibling test above), the 'temporal cluster' dream template
    (neuroscience_mixin.py volva_dream, the
    `if a.timestamp[:10] == b.timestamp[:10]` branch) used to produce a
    CONTENT-FREE sentence: it named the date and listed the emotions
    present that day, but never referenced what actually happened --
    'a lot happened on DATE -- I felt neutral, peaceful, proud. That was
    a significant day,' regardless of what the memories actually were.
    It now pulls a short snippet from each same-day memory into the
    sentence, so it should name real things that happened."""
    with FixedHarness("dream_quality_temporal") as h:
        mimir = h.manager._mimir
        # >= 4 real memories required before volva_dream samples any
        # pairs at all (neuroscience_mixin.py: `if len(real_mems) < 4:
        # return []`), and all same-day with low pairwise word overlap
        # so the emotional-arc/theme-bridge branches (which need shared
        # content words) don't preempt the temporal-cluster branch.
        h.remember("Practiced guitar for an hour", emotion="proud", importance=4)
        h.remember("Had tacos for lunch", emotion="content", importance=2)
        h.remember("Fixed a leaky faucet in the bathroom", emotion="neutral", importance=2)
        h.remember("Watched an old movie before bed", emotion="peaceful", importance=2)
        dreams = mimir.volva_dream(n_samples=30)
        temporal = [d for d in dreams if "a lot happened on" in d.content]
        print(f"[temporal-cluster dream insights] {[d.content for d in temporal]}")
        assert temporal, (
            "temporal-cluster branch did not fire -- increase n_samples "
            "or check volva_dream()'s branch ordering")
        content_words = {"guitar", "tacos", "faucet", "bathroom", "lunch", "movie"}
        for d in temporal:
            words = set(d.content.lower().replace(",", " ").split())
            has_real_content = bool(words & content_words)
            print(f"[temporal cluster insight] {d.content!r} "
                  f"references_actual_content={has_real_content}")
            assert has_real_content, (
                "Regression: the temporal-cluster dream is content-free "
                "again -- it should name real things from the same-day "
                "memories, not just the date and emotion list")


def test_self_reflect_requires_llm_and_produces_memory_specific_content():
    """reflect() (llm_mixin.py) is genuinely LLM-based and requires
    _llm_fn. Confirms: (a) it's a no-op without one (silent, not an
    error -- matches docstring), (b) with a stub LLM it actually receives
    this character's real stats/memory content in the prompt (not
    boilerplate), and (c) the resulting reflection is stored as a
    category='self' memory."""
    with FixedHarness("self_reflect_noop") as h:
        mimir = h.manager._mimir
        h.remember("Test memory", importance=5)
        result_no_llm = mimir.trigger_self_reflect()
        assert result_no_llm is None, (
            "Without an LLM configured, trigger_self_reflect should "
            "silently no-op, not raise or fabricate content")

    captured_prompts = []

    def stub_llm(prompt: str) -> str:
        captured_prompts.append(prompt)
        return "I notice I've been consistently curious about astronomy lately."

    with FixedHarness("self_reflect_with_llm", llm_fn=stub_llm) as h:
        mimir = h.manager._mimir
        h.remember("Asked the user about their favorite constellation",
                   emotion="curious", importance=6)
        h.remember("Learned the user grew up stargazing with their dad",
                   emotion="nostalgic", importance=7)
        before_count = len(mimir._reflections)
        reflection = mimir.trigger_self_reflect()
        after_count = len(mimir._reflections)

        assert reflection, "Expected reflect() to return the stub's content"
        assert captured_prompts, "LLM was never actually called"
        prompt_text = captured_prompts[0]
        assert "constellation" in prompt_text or "stargazing" in prompt_text, (
            "The reflection prompt did not actually include this "
            "character's real recent memory content -- would produce "
            "boilerplate reflections regardless of character history")
        assert after_count == before_count + 1, (
            "Expected the reflection to be stored as a new memory")
        new_mem = mimir._reflections[-1]
        assert new_mem._category == "self", (
            "Self-reflection should be stored with category='self', "
            "same as identity memories")
        assert new_mem.source == "huginn"

        # Rate limiting: immediate second call should no-op.
        immediate = mimir.trigger_self_reflect()
        assert immediate is None, "self_reflect should be rate-limited (900s cooldown)"


# ─────────────────────────── Gap #5: Deep Recall ────────────────────────

def test_deep_recall_surfaces_full_snapshot_on_next_turn_only():
    with FixedHarness("deep_recall_timing") as h:
        mgr = h.manager
        snapshot = [
            {"role": "user", "content": "Tell me about quantum entanglement in detail"},
            {"role": "assistant", "content": "Quantum entanglement is when two "
                                              "particles become correlated such "
                                              "that measuring one instantly "
                                              "affects the other, regardless of "
                                              "distance..."},
        ]
        mgr.remember(content="Explained quantum entanglement to the user in depth",
                     emotion="curious", importance=6,
                     conversation_snapshot=snapshot)

        # Same-turn: request_deep_remember resolves, but should NOT yet
        # appear in a context block built before the "next" call.
        resolved = mgr.request_deep_remember("quantum entanglement explanation")
        assert resolved is True, "Deep recall failed to match the snapshot-bearing memory"

        ctx_1 = mgr.get_context_block()
        assert "DEEP RECALL" in ctx_1, (
            "Deep Recall section did not appear on the very next "
            "get_context_block() call after resolving")
        assert "correlated" in ctx_1 or "entangle" in ctx_1.lower(), (
            "Deep Recall section appeared but did not contain the FULL "
            "original snapshot detail")

        ctx_2 = mgr.get_context_block()
        assert "DEEP RECALL" not in ctx_2, (
            "Deep Recall section persisted into a SECOND context block "
            "instead of being consumed once -- would keep re-injecting "
            "old conversation detail turn after turn")


def test_deep_recall_no_match_returns_false_cleanly():
    with FixedHarness("deep_recall_no_match") as h:
        mgr = h.manager
        mgr.remember(content="A memory with no conversation snapshot attached",
                     emotion="neutral", importance=4)
        resolved = mgr.request_deep_remember("something completely unrelated")
        assert resolved is False


if __name__ == "__main__":
    test_treasure_happy_path_finds_and_marks_correct_memory()
    test_treasure_ambiguous_candidates_picks_best_not_arbitrary()
    test_treasure_weak_query_no_longer_cherishes_top1_without_threshold()
    test_dream_rate_limiting_blocks_back_to_back_then_allows_after_cooldown()
    test_dream_theme_bridge_and_emotional_arc_embed_real_content_words()
    test_dream_temporal_cluster_template_now_embeds_real_content()
    test_self_reflect_requires_llm_and_produces_memory_specific_content()
    test_deep_recall_surfaces_full_snapshot_on_next_turn_only()
    test_deep_recall_no_match_returns_false_cleanly()
    print("ALL TREASURE/DREAM/RECALL AUDIT PROBES RAN")
