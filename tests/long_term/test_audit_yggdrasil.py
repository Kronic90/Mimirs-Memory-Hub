"""
Gap #6 — Yggdrasil (World Tree memory graph).

Background: vividmimir/yggdrasil_mixin.py's `_build_yggdrasil()` is an
O(n^2) FULL REBUILD from scratch (entity/lexical/temporal/emotional
edges). It is NOT run on every new memory. It only runs:
  - every AUTO_CONSOLIDATION_INTERVAL=50 new memories (write_mixin.py:208-213,
    via the auto-consolidation path: muninn + compress_to_gist + chunk + build)
  - on `sleep_reset()` / `manager.sleep()` (core.py:214-225)
  - on persistence load, IF >=2 memories exist (persistence_mixin.py:386-387)
  - explicitly after `import_memory` / `import_memories_batch`
    (playground/memory_manager.py:1406,1454 -- comments there show this was
    deliberately patched in specifically because imports used to leave
    memories disconnected, matching the original Yggdrasil bug report)
  - LLM-inferred edges (_infer_relations) ARE added incrementally per new
    memory, but only when `_llm_fn` is configured (never true in the
    existing test suite -- see test_audit_treasure_dream_recall.py)

So: between full rebuilds, newly-formed memories from ordinary
conversation (not import) have ZERO structural (entity/lexical/temporal/
emotional) Yggdrasil edges -- they are graph-disconnected nodes until the
50-memory threshold or a sleep cycle. This test quantifies that window
and confirms import/sleep correctly backfill it.
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


def test_new_conversational_memories_connect_within_one_session():
    """Regression guard for the fixed bug: ordinary <remember> memories
    (the common case) used to get no Yggdrasil edges at all until 50 of
    them accumulated, a sleep cycle ran, or the app restarted. For a
    companion app where a real user might send 5-15 memorable messages
    per session, that was several real sessions before Yggdrasil
    'remembered the shape of the relationship'. Fixed via
    YGGDRASIL_EARLY_REBUILD_EVERY=10 (below YGGDRASIL_EARLY_SESSION_MAX
    memories, rebuild every 10 instead of waiting for the full
    50-memory auto-consolidation threshold) -- edges should now exist
    well within a single normal session."""
    # NOTE: memory content must be genuinely distinct per entry -- using
    # near-identical sentences (e.g. only a trailing number changed)
    # triggers the dedup/merge path in write_mixin.py (overlap>=0.55
    # collapses into ONE existing memory instead of appending), which
    # would make this test measure dedup instead of Yggdrasil lag.
    hiking_trips = [
        "Went hiking at Mount Baker and saw a bald eagle overhead",
        "Hiked the coastal trail near Big Sur with strong wind",
        "Climbed a ridge in the Rockies and got caught in hail",
        "Walked the Appalachian trail section near a waterfall",
        "Hiked through redwoods and found an old fire lookout tower",
        "Trekked up a volcano trail and saw steam vents",
        "Hiked a desert canyon trail and ran low on water",
        "Walked a snowy ridge trail and saw fresh wolf tracks",
        "Hiked along a glacier moraine with loose scree",
        "Climbed a coastal bluff trail at low tide",
    ]

    with FixedHarness("ygg_lag") as h:
        mimir = h.manager._mimir
        for trip in hiking_trips:
            h.remember(trip, emotion="warm", importance=6)
        assert len(mimir._reflections) == len(hiking_trips), (
            "Sanity check failed: memories collapsed via dedup instead "
            "of staying distinct -- adjust content")
        edge_count = sum(len(e) for e in mimir._yggdrasil.values())
        print(f"[ygg lag] after {len(hiking_trips)} distinct same-session "
              f"memories: yggdrasil edge count = {edge_count}")
        assert edge_count > 0, (
            "Regression: Yggdrasil has no edges after 10 memories again -- "
            "the early-session rebuild (YGGDRASIL_EARLY_REBUILD_EVERY) "
            "may not be firing")

        # Push past the 50-memory auto-consolidation threshold with 40
        # more genuinely distinct (low pairwise word-overlap, hand-
        # written, no shared template) memories -- a repeated template
        # with only one varying word reliably exceeds _DEDUP_THRESHOLD
        # (0.55) and collapses via the merge path instead of appending,
        # which would undercount _memories_since_consolidation (that
        # counter only increments on the fresh-append path, write_mixin.py
        # ~line 207, not on a dedup-merge return).
        fillers = [
            "Learned to bake sourdough bread after watching a tutorial",
            "Tried kayaking for the first time on the river last weekend",
            "Picked up the ukulele and learned three new chords",
            "Started a tiny terrarium with moss and pebbles",
            "Fixed a broken compass by replacing the needle",
            "Lit a lantern during the camping trip in the valley",
            "Took a pottery class and made a wobbly bowl",
            "Watched a documentary about falconry in medieval times",
            "Folded an origami crane for a friend's birthday",
            "Started beekeeping and got stung twice this month",
            "Practiced calligraphy with a new brush pen set",
            "Went snowshoeing through fresh powder near the cabin",
            "Took a welding class at the community college",
            "Spent the night stargazing with a borrowed telescope",
            "Embroidered a small patch for an old jacket",
            "Learned to juggle three tennis balls after a week of practice",
            "Shot arrows at a archery range for the first time",
            "Made a wheel of cheese from a kit at home",
            "Built a small wooden stool in woodworking class",
            "Spotted a rare woodpecker while birdwatching at dawn",
            "Went sailing on a borrowed boat during low wind",
            "Poured candles using old jars and leftover wax",
            "Watched a blacksmith forge a knife at the fair",
            "Pieced together a mosaic from broken ceramic tiles",
            "Wove a small tapestry using scraps of yarn",
            "Brewed a batch of ginger beer that turned out flat",
            "Used a map and compass to practice orienteering in the park",
            "Explored a shallow cave while spelunking with friends",
            "Read about old taxidermy techniques used in museums",
            "Blew a lopsided glass ornament at a studio class",
            "Learned marquetry by inlaying thin wood veneers",
            "Drew an old-style map for a cartography project",
            "Helped a friend with their apiculture hives in spring",
            "Tried dowsing with sticks just for fun at a fair",
            "Started quilting a blanket out of old t-shirts",
            "Whittled a small spoon out of a block of pine",
            "Trimmed a bonsai tree for the first time",
            "Made paper from pulp using an old screen frame",
            "Mixed soap using lavender oil and goat milk",
            "Visited a glass museum and sketched the exhibits",
        ]
        for filler in fillers:
            h.remember(filler, emotion="warm", importance=6)
        assert len(mimir._reflections) == 50, (
            f"Expected 50 distinct memories, got {len(mimir._reflections)} "
            f"-- dedup collapsed some of the filler batch")
        edge_count_after_50 = sum(len(e) for e in mimir._yggdrasil.values())
        print(f"[ygg lag] after 50 memories (auto-consolidation threshold "
              f"hit): yggdrasil edge count = {edge_count_after_50}")
        assert edge_count_after_50 > 0, (
            "Expected auto-consolidation at the 50-memory mark to "
            "finally build real Yggdrasil edges for lexically-similar "
            "hiking memories")


def test_sleep_cycle_immediately_backfills_yggdrasil():
    """A sleep cycle (end of session, as a real user would trigger by
    closing the app) should make the graph connected without needing 50
    memories first."""
    sci_fi_picks = [
        "Discussed Blade Runner and its themes of identity",
        "Talked about Dune and the political intrigue in it",
        "Debated whether Interstellar's ending made scientific sense",
        "Argued about the best Star Wars trilogy over dinner",
        "Watched Arrival together and discussed the language theory",
        "Compared The Matrix to older cyberpunk novels",
        "Talked about Alien and practical effects versus CGI",
        "Discussed Her and whether AI companionship felt plausible",
    ]
    with FixedHarness("ygg_sleep_backfill") as h:
        mimir = h.manager._mimir
        for pick in sci_fi_picks:
            h.remember(pick, emotion="excited", importance=6)
        assert len(mimir._reflections) == len(sci_fi_picks), (
            "Sanity check failed: memories collapsed via dedup -- adjust content")
        assert sum(len(e) for e in mimir._yggdrasil.values()) == 0
        h.manager.sleep(hours=8)
        edge_count = sum(len(e) for e in mimir._yggdrasil.values())
        print(f"[ygg sleep backfill] edges after sleep() with only 8 "
              f"memories = {edge_count}")
        assert edge_count > 0, (
            "sleep_reset() should call _build_yggdrasil() -- see "
            "core.py sleep_reset() -- even well under the 50-memory "
            "auto-consolidation threshold")


def test_imported_memories_get_connected_not_orphaned():
    """Direct regression test for the original bug report: 'Yggdrasil
    had 160 memories, imported memories did not show up.' Confirms
    import_memory/import_memories_batch's explicit post-import
    _build_yggdrasil() call (memory_manager.py:1406,1454) actually
    connects a freshly-imported memory to thematically related
    EXISTING ones, including when the existing memories arrived via
    ordinary remember() and are themselves still pre-consolidation
    (i.e. import must trigger a full rebuild, not just graph-append the
    new node)."""
    board_game_chats = [
        "Talked about favorite board games, Catan came up first",
        "Mentioned loving Ticket to Ride during a rainy weekend",
        "Discussed strategy games like Terraforming Mars",
        "Brought up Pandemic as a favorite cooperative game",
        "Talked about trying a new board game cafe downtown",
    ]
    with FixedHarness("ygg_import") as h:
        mgr = h.manager
        mimir = mgr._mimir
        for chat in board_game_chats:
            h.remember(chat, emotion="playful", importance=5)
        assert len(mimir._reflections) == len(board_game_chats), (
            "Sanity check failed: board-game memories collapsed via dedup")
        assert sum(len(e) for e in mimir._yggdrasil.values()) == 0, (
            "Sanity check: pre-import graph should still be empty "
            "(under the 50-memory/no-sleep threshold)")

        import_result = mgr.import_memory(
            content="Also mentioned loving board games, especially Settlers of Catan",
            emotion="playful", importance=5, source="import",
            why_saved="imported from old chat export",
        )
        assert import_result, "import_memory returned falsy"

        edge_count = sum(len(e) for e in mimir._yggdrasil.values())
        print(f"[ygg import] edge count immediately after single import "
              f"= {edge_count}")
        assert edge_count > 0, (
            "Importing one memory should trigger an immediate Yggdrasil "
            "rebuild connecting it (and backfilling the pre-existing "
            "board-game memories) -- if this is 0, the original bug "
            "report's failure mode has regressed")

        imported_idx = len(mimir._reflections) - 1
        imported_edges = mimir._yggdrasil.get(imported_idx, [])
        print(f"[ygg import] imported memory's own edges: {imported_edges}")
        assert imported_edges, (
            "The imported memory itself has zero graph edges -- it is "
            "connected to the overall rebuild but still an orphan node, "
            "exactly the reported failure mode")


def test_imported_memories_are_recallable_and_feed_dream():
    """Second half of the regression: the bug report also said 'dreams
    gave nothing' and (implicitly) that imports were otherwise invisible
    to the system. Confirms an imported memory is recallable like an
    organic one, AND eligible to participate in volva_dream (it must not
    be excluded by source-type filtering -- volva_dream excludes source
    in ('huginn','volva','semantic','summary'), 'import' is not in that
    exclusion list)."""
    with FixedHarness("ygg_import_dream") as h:
        mgr = h.manager
        mimir = mgr._mimir
        mgr.import_memory(
            content="Learned to love rock climbing during a trip to Yosemite",
            emotion="excited", importance=6, source="import",
        )
        for i in range(3):
            h.remember(f"Mentioned wanting to go climbing again, visit {i}",
                       emotion="excited", importance=5)

        results = mgr.recall("rock climbing Yosemite", limit=5)
        found = any("climbing" in (r.content if hasattr(r, "content") else str(r))
                    for r in results)
        print(f"[ygg import recall] found imported memory via recall: {found}")
        assert found, "Imported memory is not recallable via normal recall()"

        dreams = mimir.volva_dream(n_samples=40)
        print(f"[ygg import dream] dreams generated: {[d.content for d in dreams]}")
        climbing_dreams = [d for d in dreams if "climb" in d.content.lower()]
        if not dreams:
            print("[ygg import dream] NOTE: no insights this run (random "
                  "sampling) -- source-type exclusion check done "
                  "structurally below instead")
        # Structural guarantee regardless of this run's random sampling:
        imported_mem = next(m for m in mimir._reflections if "Yosemite" in m.content)
        assert imported_mem.source not in ("huginn", "volva", "semantic", "summary"), (
            "Imported memory's source would exclude it from volva_dream's "
            "candidate pool")


def test_yggdrasil_roots_and_traversal_after_rebuild():
    """Sanity check on the graph-query helpers (roots/branches/traverse)
    once the graph is actually built, since these back the Yggdrasil UI
    panel the bug report referenced."""
    with FixedHarness("ygg_traverse") as h:
        mgr = h.manager
        mimir = mgr._mimir
        h.remember("A foundational memory about who I am", importance=9,
                   emotion="proud")
        idx = len(mimir._reflections) - 1
        mgr.toggle_anchor(idx)
        identity_chats = [
            "Talked about how I value honesty in every relationship",
            "Explained that curiosity drives most of what I do",
            "Reflected on why creativity matters so much to me",
            "Discussed how patience shapes the way I respond",
            "Shared that empathy guides my sense of identity",
            "Considered how growth defines who I am becoming",
        ]
        for chat in identity_chats:
            h.remember(chat, emotion="thoughtful", importance=5)
        assert len(mimir._reflections) == 1 + len(identity_chats), (
            "Sanity check failed: identity memories collapsed via dedup")
        mgr.sleep(hours=8)  # force a rebuild

        roots = mimir.yggdrasil_roots()
        print(f"[ygg roots] {len(roots)} roots found")
        assert roots, "Expected at least the anchored memory as a root"
        assert any(r._anchor for r in roots)

        branches = mimir.yggdrasil_branches(roots[0])
        print(f"[ygg branches] {len(branches)} branches from top root")
        traverse = mimir.yggdrasil_traverse(roots[0], depth=2)
        print(f"[ygg traverse depth=2] {len(traverse)} reachable nodes")
        # Traversal at depth 2 should reach at least as many nodes as a
        # single hop (branches).
        assert len(traverse) >= len(branches)


if __name__ == "__main__":
    test_new_conversational_memories_connect_within_one_session()
    test_sleep_cycle_immediately_backfills_yggdrasil()
    test_imported_memories_get_connected_not_orphaned()
    test_imported_memories_are_recallable_and_feed_dream()
    test_yggdrasil_roots_and_traversal_after_rebuild()
    print("ALL YGGDRASIL AUDIT PROBES RAN")
