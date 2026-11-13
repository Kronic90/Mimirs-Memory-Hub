"""
Organic memory additions (Nov 2026):

1. Memory updating -- reconsolidation on prediction error. Only when the
   MODEL says something changed (updates="..."); the old memory becomes
   "how things used to be", it is never erased.
2. Fading Affect Bias -- during sleep, emotional charge softens with real
   elapsed time, unpleasant faster than pleasant; facts untouched.
3. Tip of the tongue -- faded-but-cued memories come back as gist without
   specifics unless the conversation supplies them; effortful <recall>
   brings them back and strengthens them.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from playground.memory_manager import MemoryManager  # noqa: E402
from vividmimir.helpers import _emotion_to_vector  # noqa: E402


def _mgr(tmp_path, name="p"):
    return MemoryManager(profile_dir=tmp_path / name, chemistry=True)


def _find(m, needle):
    return next(r for r in m._mimir._reflections if needle in r.content)


def _age(mem, days):
    ts = (datetime.now() - timedelta(days=days)).isoformat()
    mem.timestamp = ts
    mem._last_access = ts


# ── 1. memory updating ──────────────────────────────────────────────────

def test_model_marked_update_supersedes_old_memory(tmp_path):
    m = _mgr(tmp_path)
    m.remember("User lives in Manchester with his cat Milo", importance=7)
    m.remember("User has moved to Leeds for a new job", importance=7,
               updates="lives in Manchester")
    old, new = _find(m, "Manchester"), _find(m, "Leeds")
    assert old._superseded_by.startswith("User has moved to Leeds")
    assert new._supersedes.startswith("User lives in Manchester")
    # current version wins in recall, the past isn't erased
    top = m._mimir.recall("where does the user live now, which city", limit=2, touch=False)
    assert top and top[0] is new
    assert any(r is old for r in m._mimir._reflections)


def test_outdated_memory_is_labelled_in_context(tmp_path):
    m = _mgr(tmp_path)
    m.remember("User lives in Manchester with his cat Milo", importance=7)
    m.remember("User has moved to Leeds for a new job", importance=7,
               updates="lives in Manchester")
    block = m.get_context_block(conversation_context="Manchester Milo cat")
    if "Manchester" in block:
        line = next(l for l in block.splitlines() if "Manchester" in l)
        assert "used to be true" in line and "Leeds" in line


def test_unclear_update_reference_changes_nothing(tmp_path):
    m = _mgr(tmp_path)
    m.remember("User lives in Manchester with his cat Milo", importance=7)
    m.remember("User started a pottery class", importance=5,
               updates="loves skydiving")
    assert not any(r._superseded_by for r in m._mimir._reflections)


def test_near_duplicate_update_revises_in_place_and_keeps_history(tmp_path):
    m = _mgr(tmp_path)
    m.remember("User's favourite colour is blue", importance=6)
    m.remember("User's favourite colour is green", importance=6,
               updates="favourite colour is blue")
    refs = [r for r in m._mimir._reflections if "colour" in r.content]
    current = [r for r in refs if not r._superseded_by]
    assert len(current) == 1 and "green" in current[0].content
    assert "blue" in (current[0]._supersedes
                      or next((r.content for r in refs if r._superseded_by), ""))


def test_social_impression_update_and_persistence(tmp_path):
    m = _mgr(tmp_path)
    m.add_social("User", "User doesn't like coffee at all", importance=6)
    m.add_social("User", "User has started drinking coffee every morning",
                 importance=6, updates="doesn't like coffee")
    m.save()
    m2 = _mgr(tmp_path)
    old = _find(m2, "doesn't like coffee")
    assert old._superseded_by
    block = m2.get_context_block(entity="User")
    imp = block.split("=== MY IMPRESSIONS OF USER ===")[1].split("===")[0]
    first = [l for l in imp.splitlines() if l.startswith("—")][0]
    assert "every morning" in first          # current impression listed first


# ── 2. fading affect bias ───────────────────────────────────────────────

def test_negative_affect_fades_faster_than_positive(tmp_path):
    m = _mgr(tmp_path)
    m.remember("We had a horrible argument about the holiday plans",
               emotion="angry", importance=6)
    m.remember("We laughed all night at the comedy show",
               emotion="joyful", importance=6)
    bad, good = _find(m, "argument"), _find(m, "comedy")
    for mem in (bad, good):
        _age(mem, 200)
    content_before = (bad.content, bad.importance, bad.emotion,
                      good.content, good.importance, good.emotion)

    assert m._mimir.fade_affect() >= 2
    assert bad._affect_intensity < good._affect_intensity < 1.0   # the sting fades faster
    # what was felt, what happened and how much it mattered are untouched
    assert (bad.content, bad.importance, bad.emotion,
            good.content, good.importance, good.emotion) == content_before
    line = m._mimir._recollect(bad)
    assert "angry" in line and ("softened" in line or "faintly" in line)


def test_affect_fading_is_elapsed_time_based_and_keeps_a_residual(tmp_path):
    from vividmimir.constants import FAB_RESIDUAL
    m = _mgr(tmp_path)
    m.remember("The day my grandad passed away", emotion="sad", importance=8)
    mem = _find(m, "grandad")
    _age(mem, 3650)
    m._mimir.fade_affect()
    first = mem._affect_intensity
    assert first >= FAB_RESIDUAL - 1e-9 and mem.emotion == "sad"   # still felt
    m._mimir.fade_affect()                                          # no time passed
    assert abs(mem._affect_intensity - first) < 1e-6


def test_faded_feeling_pulls_on_mood_less(tmp_path):
    m = _mgr(tmp_path)
    m.remember("We had a horrible argument about the holiday plans",
               emotion="angry", importance=6)
    mem = _find(m, "argument")
    angry_mood = _emotion_to_vector("angry")
    before = mem.mood_adjusted_vividness(angry_mood) / mem.vividness
    mem._affect_intensity = 0.4
    after = mem.mood_adjusted_vividness(angry_mood) / mem.vividness
    assert 1.0 <= after < before


def test_last_affect_fade_persists(tmp_path):
    m = _mgr(tmp_path)
    m.remember("A small thing", importance=5)
    m._mimir.fade_affect()
    stamp = m._mimir._last_affect_fade
    m.save()
    assert _mgr(tmp_path)._mimir._last_affect_fade == stamp


# ── 3. tip of the tongue ────────────────────────────────────────────────

def _hazy_dog(m):
    m.remember("User's dog is called Rex and he turned 4 in March", importance=5)
    mem = _find(m, "Rex")
    _age(mem, 400)
    return mem


def test_faded_memory_comes_back_as_gist_without_specifics(tmp_path):
    m = _mgr(tmp_path)
    mem = _hazy_dog(m)
    assert mem.is_hazy
    text = m._mimir._hazy_gist(mem, "tell me about the dog")
    assert "dog" in text and "Rex" not in text and "4" not in text and "…" in text


def test_cue_supplies_the_missing_detail_recognition(tmp_path):
    m = _mgr(tmp_path)
    mem = _hazy_dog(m)
    text = m._mimir._hazy_gist(mem, "do you remember rex?")
    assert "Rex" in text


def test_cherished_memories_never_go_hazy(tmp_path):
    m = _mgr(tmp_path)
    mem = _hazy_dog(m)
    m._mimir.cherish(mem)
    assert not mem.is_hazy


def test_effortful_recall_brings_it_back_and_strengthens_it(tmp_path):
    m = _mgr(tmp_path)
    mem = _hazy_dog(m)
    stab = mem._stability
    assert m.request_deep_remember("what is the dog called")
    assert mem._stability > stab
    block = m.get_context_block(conversation_context="hmm")
    assert "comes back to you" in block and "Rex" in block


def test_hazy_hint_shown_only_when_something_is_hazy(tmp_path):
    m = _mgr(tmp_path)
    m.remember("User's dog is called Rex and he turned 4 in March", importance=5)
    assert "Hazy memories" not in m.get_context_block(conversation_context="dog Rex")
