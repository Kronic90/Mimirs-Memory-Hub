"""
Gap #10 — Emotional nuance across the full 46/47-emotion vector set.

presets.py's _REMEMBER_FMT advertises 47 distinct emotions to the model
("Available emotions: neutral, happy, joyful, delighted, ... resentful").
vividmimir/constants.py's EMOTION_VECTORS dict has a distinct PAD vector
for every single one of them -- the *engine* supports full granularity.

playground/memory_manager.py's normalize_emotion() -- called on every
<remember emotion="..."> before it reaches the engine -- used to run the
label through _EMOTION_ALIASES first, and that table silently collapsed
14 of the 47 advertised emotions onto a different canonical label (e.g.
joyful->happy, disappointed->hurt, afraid->anxious), which fed directly
into mood (core.py update_mood), Yggdrasil emotional edges, and the
flashbulb-encoding arousal check in write_mixin.py (threshold 0.6) -- so
the collapse could flip whether a memory got permanently protected from
fading.

FIXED: _EMOTION_ALIASES now only maps genuinely non-canonical free-form
synonyms (e.g. "cheerful", "scared") onto a canonical label -- no key in
the table is itself one of the 47 advertised emotions any more, so none
of them get silently rewritten to a different canonical emotion. The
tests below now guard against this regressing back.
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
from playground.memory_manager import normalize_emotion
from vividmimir.constants import EMOTION_VECTORS

# The exact "Available emotions" list from presets.py's _REMEMBER_FMT.
ADVERTISED_EMOTIONS = [
    "neutral", "happy", "joyful", "delighted", "excited", "enthusiastic",
    "amused", "playful", "proud", "triumphant", "inspired", "motivated",
    "grateful", "warm", "appreciative", "tender", "affectionate",
    "hopeful", "peaceful", "serene", "content", "curious", "fascinated",
    "thoughtful", "reflective", "contemplative", "understanding",
    "nostalgic", "bittersweet", "wistful", "sad", "lonely", "melancholy",
    "disappointed", "guilty", "insecure", "vulnerable", "anxious",
    "overwhelmed", "angry", "frustrated", "hurt", "confused",
    "embarrassed", "jealous", "afraid", "resentful",
]


def test_all_advertised_emotions_have_engine_vectors():
    """Sanity check: the engine itself (EMOTION_VECTORS) supports every
    emotion the system prompt advertises -- so any collapsing happens
    purely in memory_manager's alias layer, not from missing engine
    support."""
    missing = [e for e in ADVERTISED_EMOTIONS if e not in EMOTION_VECTORS]
    print(f"[engine vector coverage] {len(ADVERTISED_EMOTIONS)} advertised, "
          f"{len(missing)} missing from EMOTION_VECTORS: {missing}")
    assert not missing, (
        f"Engine is missing PAD vectors for advertised emotions: {missing}")


def test_normalize_emotion_no_longer_collapses_advertised_emotions():
    """Regression guard for the fixed bug: none of the 47 advertised
    emotions should get remapped onto a different canonical label any
    more -- only genuinely non-canonical free-form synonyms (not in this
    list at all) are allowed to alias."""
    collapsed = {}
    for e in ADVERTISED_EMOTIONS:
        norm = normalize_emotion(e)
        if norm != e:
            collapsed[e] = norm
    print(f"[collapse census] {len(collapsed)}/{len(ADVERTISED_EMOTIONS)} "
          f"advertised emotions collapsed: {collapsed}")
    assert len(collapsed) == 0, (
        f"Regression: {collapsed} advertised emotions are being silently "
        "remapped onto a different canonical label again.")


def test_disappointed_and_hurt_are_semantically_different_and_no_longer_merged():
    """disappointed (low arousal, mild negative) and hurt (higher arousal,
    sharper negative) are two distinct emotions a user/character would
    clearly distinguish ('I'm a little disappointed' vs 'that really
    hurt'). They used to get merged by normalize_emotion, making two
    memories the model deliberately tagged differently indistinguishable
    in storage, mood computation, and Yggdrasil emotional-edge grouping --
    now fixed, each keeps its own label."""
    assert EMOTION_VECTORS["disappointed"] != EMOTION_VECTORS["hurt"]
    disappointed_arousal = EMOTION_VECTORS["disappointed"][1]
    hurt_arousal = EMOTION_VECTORS["hurt"][1]
    print(f"[PAD mismatch] disappointed arousal={disappointed_arousal} "
          f"hurt arousal={hurt_arousal}")
    assert normalize_emotion("disappointed") == "disappointed", (
        "Regression: disappointed is being merged into another label again")
    assert normalize_emotion("hurt") == "hurt"


def test_joyful_alias_no_longer_breaks_flashbulb_threshold():
    """Regression guard for the fixed bug: a memory tagged emotion="joyful"
    (explicitly advertised, importance 8, arousal 0.6 which meets
    FLASHBULB_AROUSAL_THRESHOLD=0.6 on its own vector) used to fail to
    encode as a protected flashbulb memory, because normalize_emotion()
    silently rewrote it to "happy" (arousal 0.4) BEFORE the flashbulb
    check in write_mixin.py ever saw the original label -- now it keeps
    its own label and correctly triggers flashbulb protection, same as
    the "excited" control case."""
    with FixedHarness("joyful_alias_bug") as h:
        h.remember("Celebrated getting the promotion at work today",
                   emotion="joyful", importance=8)
        joyful_mem = h.mem_obj()

        # Deliberately unrelated content (near-zero word overlap with the
        # memory above) so the dedup/pattern-separation merge path in
        # write_mixin.py (which copies _is_flashbulb from an existing
        # similar memory instead of recomputing it) cannot confound the
        # comparison -- each memory must go through fresh flashbulb
        # detection independently.
        h.remember("Finally finished building the treehouse in the yard",
                   emotion="excited", importance=8)
        excited_mem = h.mem_obj()

        print(f"[alias flashbulb flip] stored emotion for 'joyful' input="
              f"'{joyful_mem.emotion}' is_flashbulb={joyful_mem._is_flashbulb} "
              f"| stored emotion for 'excited' input="
              f"'{excited_mem.emotion}' is_flashbulb={excited_mem._is_flashbulb}")

        assert joyful_mem.emotion == "joyful", (
            "Regression: normalize_emotion is collapsing joyful->happy again")
        assert joyful_mem._is_flashbulb is True, (
            "Regression: a joyful/importance-8 memory no longer gets "
            "flashbulb protection")
        assert excited_mem._is_flashbulb is True, (
            "Control case failed -- excited/importance-8 should trigger "
            "flashbulb; something else changed (threshold constants?)")


def test_detect_emotions_now_covers_full_advertised_vocabulary():
    """Regression guard for the fixed gap: detect_emotions() (the
    auto-detector used for e.g. think-model fallback memory extraction)
    used to only have keyword buckets for 19 of the 47 advertised
    emotions, so text clearly expressing e.g. serene/triumphant/
    bittersweet/resentful fell back to 'neutral'. _EMOTION_KEYWORDS now
    has a bucket for all 47 -- spot-check a sample of the previously-
    missing ones actually gets detected as themselves."""
    from playground.memory_manager import detect_emotions
    samples = {
        "I feel so serene and at peace sitting by the lake": "serene",
        "We finally won the championship, what a triumph": "triumphant",
        "Looking at our old photos is bittersweet": "bittersweet",
        "I still feel resentful about how that went": "resentful",
    }
    results = {}
    for text, expected in samples.items():
        detected = detect_emotions(text)
        results[expected] = detected
        assert expected in detected, (
            f"Regression: {text!r} no longer detects as including "
            f"{expected!r} (got {detected})")
    print(f"[detect_emotions coverage] {results}")


if __name__ == "__main__":
    test_all_advertised_emotions_have_engine_vectors()
    test_normalize_emotion_no_longer_collapses_advertised_emotions()
    test_disappointed_and_hurt_are_semantically_different_and_no_longer_merged()
    test_joyful_alias_no_longer_breaks_flashbulb_threshold()
    test_detect_emotions_now_covers_full_advertised_vocabulary()
    print("ALL EMOTION NUANCE AUDIT PROBES RAN")
