"""
Gap #7 — Multi-character isolation under heavy, realistic, interleaved use.
Gap #8 — Memory import quality (the exact failure mode from the original
Yggdrasil bug report: emotion/importance inference, dedup, recall/decay
parity with organically-formed memories).

Each character in this test is its own MemoryManager instance with its own
temp profile dir (mirrors playground/server.py:625-637's `_char_memories`
dict keyed by char_id -- each entry is a distinct MemoryManager with a
distinct directory). We don't start the live server; we build the same
isolation boundary directly.
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

CHAR_NAMES = ["Aria", "Dmitri", "Sana", "Pip", "Oleander"]


# ─────────────────────── Gap #7: multi-character isolation ──────────────

def test_five_characters_full_year_no_cross_contamination():
    harnesses = {name: FixedHarness(f"multichar_{name}") for name in CHAR_NAMES}
    try:
        # Each character gets its own unique secret fact + a shared
        # real-world event told to TWO of them (the scenario the audit
        # brief specifically calls out: "two characters both told about
        # the same real-world event by the user").
        per_char_secret = {
            "Aria": "Aria, I got accepted into the astrophysics program at Caltech",
            "Dmitri": "Dmitri, I finally paid off my student loans this month",
            "Sana": "Sana, my sister is getting married in the spring",
            "Pip": "Pip, I adopted a three-legged cat named Biscuit",
            "Oleander": "Oleander, I started learning to sail this summer",
        }
        shared_event = "By the way, there was a huge earthquake near my hometown yesterday"
        shared_with = ["Aria", "Sana"]

        day = 0
        for week in range(52):
            for name, h in harnesses.items():
                h.remember(per_char_secret[name] + f" (week {week} check-in)",
                           emotion="warm", importance=6)
                if week == 10 and name in shared_with:
                    h.remember(shared_event, emotion="anxious", importance=7)
                if week % 13 == 0:
                    h.manager.sleep(hours=8)
            day += 7
            for h in harnesses.values():
                h.advance_days(7)

        # 1. Each character's own secret must be recallable from ITS OWN
        #    memory and ONLY its own.
        for name, h in harnesses.items():
            results = h.recall(per_char_secret[name].split(",")[1][:40], limit=5)
            found = any(name.split()[0] in (r.content if hasattr(r, "content") else str(r))
                        or per_char_secret[name][:20] in (r.content if hasattr(r, "content") else str(r))
                        for r in results)
            assert found, f"{name} could not recall their own secret after a year"

        # 2. No character's memory store contains another character's
        #    secret content at all (hard isolation, not just ranking).
        for name, h in harnesses.items():
            all_content = " ".join(m.content for m in h.manager._mimir._reflections)
            for other_name, other_secret in per_char_secret.items():
                if other_name == name:
                    continue
                leaked = other_secret.split(",")[0] in all_content and other_name != name
                assert other_name not in all_content or other_name in per_char_secret[name], (
                    f"{name}'s memory store contains '{other_name}' -- cross-character bleed")

        # 3. Shared real-world event: both Aria and Sana should have it;
        #    neither Dmitri, Pip, nor Oleander should.
        for name in shared_with:
            all_content = " ".join(m.content for m in harnesses[name].manager._mimir._reflections)
            assert "earthquake" in all_content, (
                f"{name} should have the shared earthquake memory but doesn't")
        for name in CHAR_NAMES:
            if name in shared_with:
                continue
            all_content = " ".join(m.content for m in harnesses[name].manager._mimir._reflections)
            assert "earthquake" not in all_content, (
                f"{name} was never told about the earthquake but has it in memory "
                f"-- cross-character leak")

        # 4. Mood/chemistry independence: push one character's chemistry
        #    hard in one direction and confirm the others are unaffected.
        harnesses["Pip"].manager.on_event("conflict", intensity=1.0)
        harnesses["Pip"].manager._tick_chemistry()
        pip_chem = harnesses["Pip"].manager.get_mood()["chemistry"]["levels"]
        other_chems = {n: h.manager.get_mood()["chemistry"]["levels"]
                       for n, h in harnesses.items() if n != "Pip"}
        print(f"[chemistry isolation] Pip (perturbed) cortisol={pip_chem['cortisol']:.3f} | "
              f"others cortisol={{n: c['cortisol'] for n, c in zip(other_chems, other_chems.values())}}")
        for name, chem in other_chems.items():
            assert chem["cortisol"] != pip_chem["cortisol"] or chem["cortisol"] == 0.3, (
                f"{name}'s chemistry moved in lockstep with Pip's -- "
                f"suggests shared/global chemistry state")

        # 5. Rapid switching: interleave single remembers across all 5 in
        #    quick succession (as a real user checking in on multiple
        #    companions would) and confirm nothing bleeds afterward.
        for i in range(20):
            name = CHAR_NAMES[i % len(CHAR_NAMES)]
            harnesses[name].remember(
                f"Quick check-in message number {i} for {name}",
                emotion="content", importance=3)
        for name, h in harnesses.items():
            all_content = " ".join(m.content for m in h.manager._mimir._reflections)
            for other in CHAR_NAMES:
                if other == name:
                    continue
                assert f"for {other}" not in all_content, (
                    f"Rapid interleaved switching caused {other}'s check-in "
                    f"to leak into {name}'s memory store")
    finally:
        for h in harnesses.values():
            h.close()
            import shutil
            shutil.rmtree(h._tmpdir, ignore_errors=True)


def test_identity_memories_do_not_bleed_between_characters():
    """Each character's self-identity ('WHO I AM') memories must stay
    distinct -- a companion app's whole pitch is each character having
    their own developing personality."""
    with FixedHarness("multichar_identity_a") as ha, \
         FixedHarness("multichar_identity_b") as hb:
        ha.manager.remember(content="I am fiercely loyal and protective of people I care about",
                            emotion="warm", importance=8, source="reflection", category="self")
        hb.manager.remember(content="I am playful and love making people laugh",
                            emotion="playful", importance=8, source="reflection", category="self")

        identity_a = {m.content for m in ha.manager._mimir.get_self_identity()}
        identity_b = {m.content for m in hb.manager._mimir.get_self_identity()}
        assert identity_a.isdisjoint(identity_b), "Identity memories bled between two separate characters"
        assert "loyal" in " ".join(identity_a)
        assert "playful" in " ".join(identity_b)
        assert "loyal" not in " ".join(identity_b)
        assert "playful" not in " ".join(identity_a)


# ─────────────────────── Gap #8: memory import quality ───────────────────

def _enrich(content: str):
    """Replicates playground/server.py:1280-1290's AI-enrichment step
    exactly, without starting the server."""
    from playground.memory_manager import detect_emotions, estimate_importance
    detected = detect_emotions(content)
    emotion = detected[0] if detected else "neutral"
    importance = estimate_importance(content, "")
    return emotion, importance


# A realistic batch of pasted "memories" like a Character.ai refugee
# might export from old chats -- third-person summaries, mixed tense,
# mixed emotional register, some trivial, some significant.
REALISTIC_IMPORT_BATCH = [
    "Talked about how nervous I was before my first day at the new job",
    "He said he was proud of me for finishing the marathon",
    "We joked around about terrible 2010s memes for an hour",
    "I told him my dad passed away last year and it still hurts",
    "Mentioned I like my coffee with oat milk, no sugar",
    "We argued about whether pineapple belongs on pizza",
    "She said she loved spending time with me and felt safe",
    "Just a short hello, nothing much happened",
    "I confided that I've been feeling really anxious about money lately",
    "We talked about building a treehouse together someday",
]


def test_import_without_enrichment_defaults_flatly():
    """Without enrich=True, import_memory uses whatever emotion/importance
    the caller passed (default neutral/5 if omitted) -- NO inference
    happens at all. Documents this so it isn't mistaken for 'the system
    infers emotion/importance from imported content' when it doesn't."""
    with FixedHarness("import_no_enrich") as h:
        mgr = h.manager
        results = []
        for content in REALISTIC_IMPORT_BATCH:
            d = mgr.import_memory(content=content)  # no emotion/importance passed
            results.append(d)
        emotions = {r.get("emotion") for r in results}
        importances = {r.get("importance") for r in results}
        print(f"[no-enrich import] distinct emotions={emotions} "
              f"distinct importances={importances}")
        assert emotions == {"neutral"}, (
            "Expected ALL unenriched imports to land as 'neutral' "
            "regardless of actual emotional content -- a grief memory "
            "('my dad passed away') and a trivial one ('just a short "
            "hello') get IDENTICAL emotion without enrich=True")
        # Importance should be ~constant (any wobble is from unrelated
        # chemistry-encoding_boost drift across the batch, NOT from
        # import_memory reading the content at all -- it has no
        # content-based importance inference without enrich=True).
        assert importances <= {5, 6}, (
            f"Unexpected importance spread without enrichment: {importances}")
        grief_result = results[3]  # "I told him my dad passed away..."
        trivial_result = results[7]  # "Just a short hello..."
        print(f"[no-enrich spot-check] grief_importance="
              f"{grief_result.get('importance')} trivial_importance="
              f"{trivial_result.get('importance')}")
        assert grief_result.get("importance") == trivial_result.get("importance"), (
            "If this fails, no-enrichment import now differentiates "
            "importance by content -- re-verify import_memory's signature")


def test_import_with_enrichment_infers_some_emotion_importance_spread():
    """With enrich=True (replicating server.py's heuristic path), check
    whether the batch actually gets a believable spread -- e.g. the grief
    memory should score meaningfully higher importance than the trivial
    'just a short hello' one, and at least some emotions should move off
    'neutral'."""
    with FixedHarness("import_with_enrich") as h:
        mgr = h.manager
        enriched = []
        for content in REALISTIC_IMPORT_BATCH:
            emotion, importance = _enrich(content)
            d = mgr.import_memory(content=content, emotion=emotion, importance=importance)
            enriched.append((content, emotion, importance))
        for content, emotion, importance in enriched:
            print(f"[enrich] emo={emotion:12s} imp={importance} | {content[:60]}")

        by_content = {c: (e, i) for c, e, i in enriched}
        grief = by_content["I told him my dad passed away last year and it still hurts"]
        trivial = by_content["Just a short hello, nothing much happened"]
        print(f"[enrich spot-check] grief={grief} trivial={trivial}")
        # FIXED: estimate_importance's keyword list used to only boost on
        # exact-ish first-person phrases ("i feel", "i love", "i hate",
        # "my family", "my life", "i'm scared", "i'm worried"), so this
        # grief sentence ("I told him my dad passed away... it still
        # hurts") matched none of them and scored the same baseline (5)
        # as a content-free greeting. The heuristic now also has a major-
        # life-event phrase tier ("passed away") and an emotion-detection
        # signal, so grief content should clearly outscore trivial text.
        assert grief[1] > trivial[1], (
            f"Regression: grief ({grief[1]}) no longer outscores a "
            f"trivial greeting ({trivial[1]}) on importance")

        emotions_seen = {e for _, e, _ in enriched}
        print(f"[enrich spread] distinct emotions across 10 varied "
              f"memories: {emotions_seen}")
        assert len(emotions_seen) > 1, (
            "detect_emotions produced 'neutral' for the ENTIRE realistic "
            "import batch -- its 19-keyword-bucket vocabulary (vs. the "
            "47 emotions the system itself advertises) may be too "
            "narrow for free-text pasted memories")


def test_imported_memories_recall_and_decay_identically_to_organic():
    """The core of the original bug report: imported memories should be
    recallable and subject to the SAME vividness/decay treatment as
    memories formed organically through remember() -- not a second-class
    citizen."""
    with FixedHarness("import_parity") as h:
        mgr = h.manager
        mgr.import_memory(
            content="Moved to a new apartment downtown last spring",
            emotion="content", importance=6, source="import")
        h.remember("Started a new job downtown last spring", emotion="content", importance=6)

        imported_mem = next(m for m in mgr._mimir._reflections if "apartment" in m.content)
        organic_mem = next(m for m in mgr._mimir._reflections if "job" in m.content)

        v0_imported, v0_organic = imported_mem.vividness, organic_mem.vividness
        h.advance_days(180)
        v180_imported, v180_organic = imported_mem.vividness, organic_mem.vividness

        print(f"[parity] imported {v0_imported:.3f}->{v180_imported:.3f} | "
              f"organic {v0_organic:.3f}->{v180_organic:.3f}")
        # Same importance/emotion -> decay curves should match closely
        # (both go through the same Memory.vividness property/formula).
        assert abs(v180_imported - v180_organic) < 0.05, (
            "Imported and organic memories with identical importance/"
            "emotion decayed differently after 180 days")

        results = mgr.recall("new apartment downtown", limit=5)
        found = any("apartment" in (r.content if hasattr(r, "content") else str(r))
                    for r in results)
        assert found, "Imported memory not recallable via normal recall() after 180 days"


def test_import_dedup_against_existing_organic_memory():
    """A pasted import that's near-duplicate of something already
    organically remembered should be recognized and skipped, not create
    a confusing duplicate (import_memory's dedup check compares against
    ALL existing reflections, organic or imported, at an 0.85 overlap
    threshold -- notably stricter than remember()'s own 0.55 merge
    threshold, which means imports are less aggressively deduped than
    live conversation)."""
    with FixedHarness("import_dedup") as h:
        mgr = h.manager
        h.remember("I got a new puppy named Rex last weekend", emotion="joyful", importance=7)
        before_count = len(mgr._mimir._reflections)
        result = mgr.import_memory(
            content="I got a new puppy named Rex last weekend",
            emotion="joyful", importance=7, source="import")
        after_count = len(mgr._mimir._reflections)
        print(f"[import dedup] before={before_count} after={after_count}")
        assert after_count == before_count, (
            "Importing an exact-duplicate of an existing organic memory "
            "created a new entry instead of being deduped")


if __name__ == "__main__":
    test_five_characters_full_year_no_cross_contamination()
    test_identity_memories_do_not_bleed_between_characters()
    test_import_without_enrichment_defaults_flatly()
    test_import_with_enrichment_infers_some_emotion_importance_spread()
    test_imported_memories_recall_and_decay_identically_to_organic()
    test_import_dedup_against_existing_organic_memory()
    print("ALL MULTICHAR/IMPORT AUDIT PROBES RAN")
