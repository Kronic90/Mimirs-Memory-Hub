"""
Regression tests for the November 2026 bug sweep.

Each test pins a bug that shipped and was confirmed by reproduction:
  - imported "...Z" / epoch timestamps broke recall for the whole profile
  - deleting a memory left the keyword index / graph pointing at the
    wrong memories, and deleted social impressions came back on restart
  - editing importance in the Memory browser did nothing
  - <remember cherish="true"> merged into an older duplicate cherished the
    wrong memory (or un-cherished the right one)
  - recall_unified() raised NameError
  - the display-only recall double-touched memories every turn
  - an unreadable reflections.json was silently overwritten with nothing
  - importance="high" / "8/10" from a model raised and lost the turn
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

from playground.memory_manager import MemoryManager, coerce_importance  # noqa: E402
from vividmimir.helpers import _normalize_timestamp  # noqa: E402


def _mgr(tmp_path, name="p"):
    return MemoryManager(profile_dir=tmp_path / name, chemistry=True)


# ── timestamps ──────────────────────────────────────────────────────────

def test_normalize_timestamp_shapes():
    assert "+" not in _normalize_timestamp("2024-03-01T10:00:00.000Z")
    assert not _normalize_timestamp("2024-03-01T10:00:00Z").endswith("Z")
    assert _normalize_timestamp(1709287200).startswith("2024-03-0")
    assert _normalize_timestamp(1709287200000).startswith("2024-03-0")   # ms
    assert _normalize_timestamp("1709287200").startswith("2024-03-0")
    assert _normalize_timestamp("not a date", "FALLBACK") == "FALLBACK"
    assert _normalize_timestamp("", "F") == "F"


def test_import_with_utc_and_epoch_timestamps_keeps_recall_working(tmp_path):
    m = _mgr(tmp_path)
    m.import_memory("My cat Biscuit loves sunbeams", timestamp="2024-03-01T10:00:00Z")
    m.import_memories_batch([{"content": "My brother Tom lives in Leeds",
                              "timestamp": 1700000000000}])
    assert m.recall("Biscuit cat")
    assert m.recall("brother Tom")
    assert m.get_context_block()


def test_profile_saved_with_aware_timestamp_heals_on_load(tmp_path):
    m = _mgr(tmp_path)
    m.remember("Grandma's garden had sunflowers", importance=7)
    m._mimir._reflections[0].timestamp = "2024-03-01T10:00:00+00:00"  # as old imports saved it
    m.save()
    m2 = _mgr(tmp_path)
    assert m2.recall("garden sunflowers")
    assert "+" not in m2._mimir._reflections[0].timestamp


# ── delete ──────────────────────────────────────────────────────────────

def test_delete_keeps_keyword_index_and_graph_aligned(tmp_path):
    m = _mgr(tmp_path)
    for t in ["Tomatoes in the greenhouse grew huge", "Pizza argument about pineapple",
              "Saturn rings through the telescope", "Greenhouse tomatoes got blight",
              "Telescope trip to see Saturn again"]:
        m.remember(t, importance=6)
    eng = m._mimir
    eng._build_yggdrasil()

    def edges():
        return {(eng._reflections[s].content, eng._reflections[t].content)
                for s, es in eng._yggdrasil.items() for t, _e, _w in es}

    before = edges()
    victim = eng._reflections[1].content
    assert m.delete_memory(1)
    assert edges() == {e for e in before if victim not in e}
    hits = eng._bm25_scores({"saturn"})
    assert len(hits) == 2
    assert all("Saturn" in eng._reflections[i].content for i in hits)


def test_deleted_social_impression_stays_deleted_after_restart(tmp_path):
    m = _mgr(tmp_path)
    m.add_social("User", "User is afraid of spiders", importance=5)
    m.remember("Unrelated note about the weather", importance=5)
    idx = next(i for i, r in enumerate(m._mimir._reflections) if "spiders" in r.content)
    m.delete_memory(idx)
    m.save()
    m2 = _mgr(tmp_path)
    assert not any("spiders" in r.content for r in m2._mimir._reflections)
    assert not m2.get_social_impressions("User")


# ── edit / cherish ──────────────────────────────────────────────────────

def test_importance_edit_changes_importance(tmp_path):
    m = _mgr(tmp_path)
    m.remember("We argued about pineapple on pizza", importance=4)
    out = m.update_memory(0, {"importance": 10})
    assert out["importance"] == 10
    assert m._mimir._reflections[0].importance == 10


def test_cherish_on_merged_memory_hits_the_right_memory(tmp_path):
    m = _mgr(tmp_path)
    m.remember("Our first date was at the little Italian place by the river", importance=8)
    m.remember("I like rainy days", importance=4)
    m.toggle_cherish(0)
    m.remember("Our first date was at the little Italian place by the river!",
               importance=8, cherish=True)
    refs = m._mimir._reflections
    assert all(r._cherished for r in refs if "Italian" in r.content)
    assert not any(r._cherished for r in refs if "rainy" in r.content)


# ── recall ──────────────────────────────────────────────────────────────

def test_recall_unified_with_social_memories(tmp_path):
    m = _mgr(tmp_path)
    m.add_social("User", "User adores Italian food", importance=6)
    out = m._mimir.recall_unified("Italian food", limit=6)
    assert out["impressions"]


def test_display_recall_has_no_side_effects(tmp_path):
    m = _mgr(tmp_path)
    m.remember("Our first date was at the little Italian place by the river", importance=8)
    refs = m._mimir._reflections
    before = [(r._access_count, r.emotion, r._last_access) for r in refs]
    m.recall_for_display("Italian date river", 5)
    assert [(r._access_count, r.emotion, r._last_access) for r in refs] == before


# ── persistence safety ──────────────────────────────────────────────────

def test_unreadable_reflections_file_is_backed_up(tmp_path):
    m = _mgr(tmp_path)
    m.remember("Something precious", importance=9)
    m.save()
    data_dir = Path(m._mimir._data_dir)
    (data_dir / "reflections.json").write_text("{ not json", encoding="utf-8")
    _mgr(tmp_path)
    backups = list(data_dir.glob("reflections.unreadable-*.json"))
    assert len(backups) == 1
    assert "not json" in backups[0].read_text(encoding="utf-8")


# ── model-written importance ────────────────────────────────────────────

def test_coerce_importance_handles_model_output():
    assert coerce_importance("high") == 8
    assert coerce_importance("7.5") in (7, 8)
    assert coerce_importance("8/10") == 8
    assert coerce_importance("9 out of 10") == 9
    assert coerce_importance("80%") == 8
    assert coerce_importance("") == 5
    assert coerce_importance(None) == 5
    assert coerce_importance("banana") == 5
    assert coerce_importance(42) == 10
    assert coerce_importance(-3) == 1


# ── import freshness (Ebbinghaus savings) ───────────────────────────────

def test_old_import_keeps_its_date_but_arrives_recallable(tmp_path):
    from datetime import datetime, timedelta
    m = _mgr(tmp_path)
    two_years_ago = (datetime.now() - timedelta(days=730)).isoformat()
    m.import_memory("We stayed up all night talking about the stars", importance=6,
                    timestamp=two_years_ago)
    mem = m._mimir._reflections[0]
    assert mem.timestamp.startswith(two_years_ago[:10])          # real date kept
    assert 0.6 * mem.importance < mem.vividness < mem.importance  # fresh-ish, not new
    assert m.recall("stars all night")
    assert "year" in m._mimir._memory_age_str(mem)                # context says "past"
    # survives a save/load round trip
    m.save()
    again = _mgr(tmp_path)._mimir._reflections[0]
    assert again._decay_from and again.vividness > 0.6 * again.importance


def test_recent_import_is_not_aged_beyond_its_true_age(tmp_path):
    from datetime import datetime, timedelta
    m = _mgr(tmp_path)
    m.import_memory("Had pancakes this morning", importance=5,
                    timestamp=(datetime.now() - timedelta(days=1)).isoformat())
    mem = m._mimir._reflections[0]
    assert mem._decay_age_days() < 1.1
