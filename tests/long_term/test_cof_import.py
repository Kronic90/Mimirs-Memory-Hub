"""COF file (.cof) import: detection, the card path, memories with their
dates, emotion and importance, private memories left in the file, and the
character-manager entry point."""
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

MIMETYPE = "application/vnd.cof.character+zip"

CARD = {"spec": "chara_card_v3", "spec_version": "3.0",
        "data": {"name": "Mira Voss", "description": "A quiet cartographer.", "personality": "Patient, exact.",
                 "scenario": "A port city.", "first_mes": "You found the attic again.", "mes_example": "x",
                 "alternate_greetings": ["The lamp is still warm."], "tags": ["maps"], "extensions": {}}}

MEMORIES = {
    "ev1": {"gist": {"fr": "La premiere carte.", "en": "The first map I inked alone."},
            "when": {"date": "2019-05"}, "salience": 80,
            "felt_then": {"category": {"set": "everyday", "value": "Proud"}}},
    "ev2": {"gist": "The night the harbour flooded.", "when": {"date": "2021-11-03"}, "salience": 95,
            "felt_then": {"category": {"set": "everyday", "value": "afraid"}}},
    "ev3": {"gist": {"en": "The summer I was eight, at my grandmother's house."},
            "when": {"age": {"value": 8, "unit": "years"}}},
    "ev4": {"gist": {"en": "What I never told my brother."}, "disclosure": "secret", "salience": 90},
}


def _cof(manifest_patch=None, extra=None, first="mimetype", mimetype=MIMETYPE, compress_mimetype=False) -> bytes:
    manifest = {
        "cof": "1.2", "name": "Mira", "fictional": True, "default_preset": "main", "default_identity": "id1",
        "identities": {"id1": {"name": "Mira Voss", "default_preset": "main"}},
        "elements": {
            "personality": {"variants": {
                "p1": {"kind": "card", "language": "en", "card": "elements/personality/p1/card.json"},
                "p2": {"kind": "description", "language": "en", "text": "Mira, in plain words."}}},
            "memories": {"variants": {k: {"kind": "moment", "memory": f"elements/memories/{k}/memory.json"}
                                      for k in MEMORIES}},
        },
        "presets": {"main": {"identity": "id1", "slots": {"personality": ["p1"], "memories": list(MEMORIES)}},
                    "plain": {"identity": "id1", "extends": "main", "slots": {"personality": ["p2"]}}},
        "rights": {"permissions": {"commercialUsage": "personalNonProfit", "allowRedistribution": False}},
    }
    manifest.update(manifest_patch or {})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        info = zipfile.ZipInfo(first)
        info.compress_type = zipfile.ZIP_DEFLATED if compress_mimetype else zipfile.ZIP_STORED
        z.writestr(info, mimetype)
        z.writestr("manifest.json", json.dumps(manifest), zipfile.ZIP_DEFLATED)
        z.writestr("elements/personality/p1/card.json", json.dumps(CARD), zipfile.ZIP_DEFLATED)
        for k, v in MEMORIES.items():
            z.writestr(f"elements/memories/{k}/memory.json", json.dumps(v), zipfile.ZIP_DEFLATED)
        for path, content in (extra or {}).items():
            z.writestr(path, content)
    return buf.getvalue()


# ── detection ──────────────────────────────────────────
def test_is_cof_reads_the_first_entry_only():
    from playground.cof_import import is_cof
    assert is_cof(_cof())
    assert not is_cof(_cof(mimetype="application/epub+zip"))
    assert not is_cof(_cof(first="manifest.txt"))
    assert not is_cof(_cof(compress_mimetype=True))     # the format requires it stored
    assert not is_cof(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    assert not is_cof(json.dumps(CARD).encode())


# ── reading ──────────────────────────────────────────
def test_card_and_memories_map_onto_mimir_fields():
    from playground.cof_import import read_cof
    r = read_cof(_cof())
    assert r["name"] == "Mira Voss" and r["preset"] == "main"
    assert r["card"]["data"]["first_mes"] == "You found the attic again."
    by_text = {m["content"]: m for m in r["memories"]}
    first = by_text["The first map I inked alone."]            # English picked from the language map
    assert first["timestamp"] == "2019-05-01T00:00:00"         # partial date: first day
    assert (first["importance"], first["emotion"]) == (8, "proud")
    flood = by_text["The night the harbour flooded."]
    assert (flood["timestamp"], flood["importance"], flood["emotion"]) == ("2021-11-03T00:00:00", 10, "afraid")
    childhood = by_text["The summer I was eight, at my grandmother's house."]
    # an age and no date, and nothing in the file ties an age to a date: no date is made up
    assert (childhood["timestamp"], childhood["importance"], childhood["emotion"]) == ("", 5, "neutral")
    assert childhood["why_saved"].endswith("happened at age 8 (the file gives no date)")
    assert r["permissions"]["allowRedistribution"] is False
    assert r["real_person"] is False


def test_a_memory_with_an_age_and_no_date_stays_undated_even_when_the_file_could_anchor_it(monkeypatch):
    import sys
    from playground.cof_import import read_cof
    here = sys.modules[__name__]
    anchored = dict(MEMORIES)
    # one memory ties an age to a date: a birth year could be worked out, and must not be used for dates
    anchored["ev2"] = {**MEMORIES["ev2"], "when": {"date": "2021-11-03", "age": {"value": 30, "unit": "years"}}}
    anchored["ev5"] = {"gist": {"en": "The years at the survey office."},
                       "when": {"from": {"age": {"value": 22, "unit": "years"}}, "to": {"age": {"value": 26, "unit": "years"}}}}
    anchored["ev3"] = {**MEMORIES["ev3"], "when": {"age": {"value": 8, "unit": "years"}, "approx": True}}
    monkeypatch.setattr(here, "MEMORIES", anchored)
    r = read_cof(_cof())
    # life order: by age, a dated memory placed by the age the anchor gives it
    assert [m["content"][:14] for m in r["memories"]] == ["The summer I w", "The years at t", "The first map ", "The night the "]
    childhood, office, first_map, flood = r["memories"]
    assert childhood["timestamp"] == "" and childhood["why_saved"].endswith("happened at about age 8 (the file gives no date)")
    assert office["timestamp"] == "" and office["why_saved"].endswith("happened at age 22 (the file gives no date)")
    # a date written in the file is kept as it is
    assert flood["timestamp"] == "2021-11-03T00:00:00" and flood["why_saved"] == "imported from a COF file"
    assert first_map["timestamp"] == "2019-05-01T00:00:00"


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
PICTURE = {
    "elements": {"appearance": {"variants": {"a1": {"kind": "face", "images": ["img-a1"]}}},
                 "personality": {"variants": {"p1": {"kind": "card", "language": "en",
                                                     "card": "elements/personality/p1/card.json"}}},
                 "memories": {"variants": {}}},
    "presets": {"main": {"identity": "id1", "slots": {"personality": ["p1"], "appearance": ["a1"]}},
                "other": {"identity": "id1", "slots": {"personality": ["p1"]}}},
    "assets": [{"id": "img-a1", "path": "elements/appearance/a1/face.png"},
               {"id": "thumbnail", "path": "Thumbnails/thumbnail.png", "role": "derived", "source": "img-a1"}],
}


def test_the_picture_is_shown_only_for_its_preset_and_with_consent_for_a_real_person():
    from playground.cof_import import read_cof
    extra = {"Thumbnails/thumbnail.png": PNG}
    assert read_cof(_cof(PICTURE, extra))["avatar_png"] == PNG
    # the preset being read does not apply the variant the thumbnail was made from
    other = {**PICTURE, "identities": {"id1": {"name": "Mira Voss", "default_preset": "other"}}}
    assert read_cof(_cof(other, extra))["avatar_png"] is None
    # an undeclared thumbnail is nobody's picture
    assert read_cof(_cof({**PICTURE, "assets": []}, extra))["avatar_png"] is None
    # a real person, or a file that does not say: no picture without consent that covers images
    real = read_cof(_cof({**PICTURE, "fictional": False}, extra))
    assert real["real_person"] and real["avatar_png"] is None and real["consent_scope"] == []
    assert read_cof(_cof({**PICTURE, "fictional": "unknown"}, extra))["real_person"]
    talk = {"permissions": {}, "consent": {"scope": ["conversational-persona"]}}
    assert read_cof(_cof({**PICTURE, "fictional": False, "rights": talk}, extra))["avatar_png"] is None
    seen = {"permissions": {}, "consent": {"scope": ["likeness-image"]}}
    assert read_cof(_cof({**PICTURE, "fictional": False, "rights": seen}, extra))["avatar_png"] == PNG
    expired = {"permissions": {}, "consent": {"scope": ["likeness-image"], "expires": "2020-01-01"}}
    assert read_cof(_cof({**PICTURE, "fictional": False, "rights": expired}, extra))["avatar_png"] is None


def test_secret_memories_stay_in_the_file_unless_asked_for():
    from playground.cof_import import read_cof
    r = read_cof(_cof())
    assert r["skipped_secret"] == 1
    assert all("never told" not in m["content"] for m in r["memories"])
    r = read_cof(_cof(), include_secret=True)
    assert r["skipped_secret"] == 0 and any("never told" in m["content"] for m in r["memories"])


def test_free_text_personality_and_inherited_memories():
    from playground.cof_import import read_cof
    patch = {"identities": {"id1": {"name": "Mira Voss", "default_preset": "plain"}}}
    r = read_cof(_cof(patch))
    assert r["card"] is None and r["description"] == "Mira, in plain words."
    assert len(r["memories"]) == 3                               # inherited from the preset it extends
    assert r["greeting"] == ""
    patch["presets"] = {"main": {"identity": "id1", "slots": {"personality": ["p1"]},
                                 "prompts": {"greeting": {"fr": "Vous revoila.", "en": "You again."}}},
                        "plain": {"identity": "id1", "extends": "main", "slots": {"personality": ["p2"]}}}
    assert read_cof(_cof(patch))["greeting"] == "You again."     # the nearest inherited greeting, in English


def test_refuses_what_it_cannot_read_safely():
    from playground.cof_import import read_cof
    with pytest.raises(ValueError):
        read_cof(json.dumps(CARD).encode())
    with pytest.raises(ValueError, match="newer"):
        read_cof(_cof({"cof": "2.0"}))
    with pytest.raises(ValueError, match="unsafe"):
        read_cof(_cof(extra={"../escape.txt": "x"}))
    with pytest.raises(ValueError, match="no preset"):
        read_cof(_cof({"presets": {}}))


# ── into the app ─────────────────────────────────────────
@pytest.fixture
def characters(tmp_path, monkeypatch):
    from playground import character_manager
    monkeypatch.setattr(character_manager, "_DATA_DIR", tmp_path)
    return character_manager.CharacterManager()


def test_character_manager_imports_a_cof(characters):
    char, parsed = characters.import_cof(_cof())
    assert char["name"] == "Mira Voss" and char["_source"] == "cof"
    assert char["greeting"] == "You found the attic again."
    assert len(parsed["memories"]) == 3
    # the ordinary "Import card" entry point accepts the same file
    again = characters.import_card_bytes("mira.cof", _cof())
    assert again["name"] == "Mira Voss" and again["id"] != char["id"]


def test_imported_memories_keep_their_dates_and_are_recalled(tmp_path):
    from playground.cof_import import read_cof
    from playground.memory_manager import MemoryManager
    mem = MemoryManager(profile_dir=tmp_path / "p", chemistry=True)
    for m in read_cof(_cof())["memories"]:
        assert mem.import_memory(m["content"], m["emotion"], m["importance"], "import",
                                 m["why_saved"], m["timestamp"])
    stored = {m["content"]: m for m in mem.export_all()}
    assert stored["The night the harbour flooded."]["timestamp"].startswith("2021-11-03")
    assert stored["The first map I inked alone."]["timestamp"].startswith("2019-05-01")
    assert mem.recall("harbour flooded")
