"""v1.0.5: character sheets, card import, Character.ai import, voice messages,
swipe memory undo helpers."""
import base64
import io
import json
import struct
import sys
import wave
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _png_with_chunk(keyword: bytes, payload: bytes) -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 60), (200, 100, 50)).save(b, format="PNG")
    png = b.getvalue()
    body = keyword + b"\x00" + payload
    chunk = struct.pack(">I", len(body)) + b"tEXt" + body + struct.pack(">I", zlib.crc32(b"tEXt" + body) & 0xffffffff)
    i = png.rindex(b"IEND") - 4
    return png[:i] + chunk + png[i:]


# ── character sheet prompt ─────────────────────────────────────────────
def test_prompt_uses_every_sheet_section_and_placeholders():
    from playground.character_sheet import build_character_prompt
    char = {"name": "Seraphina", "nicknames": ["Sera"], "tagline": "A forest guardian",
            "traits": ["Kind", "Witty"], "speaking_style": "Soft and slow", "likes": ["moonlight"],
            "scenario": "{{user}} wakes in {{char}}'s glade.", "user_nickname": "wanderer",
            "example_dialogue": "{{user}}: hi\n{{char}}: hello", "appearance": "Green eyes"}
    p = build_character_prompt(char, {"name": "Alex", "about": "Loves hiking"})
    for bit in ["Your name is Seraphina", "Sera", "Kind, Witty", "Soft and slow", "moonlight",
                "Alex wakes in Seraphina's glade", "call them wanderer", "Loves hiking",
                "never actually happened", "Green eyes"]:
        assert bit in p, bit
    assert "{{" not in p


def test_empty_sections_are_skipped():
    from playground.character_sheet import build_character_prompt
    p = build_character_prompt({"name": "Bob"}, {})
    assert p.strip() == "Your name is Bob."


def test_per_character_persona_override():
    from playground.character_sheet import resolve_user_persona
    g = {"name": "Alex", "about": "me"}
    assert resolve_user_persona(g, {})["name"] == "Alex"
    o = resolve_user_persona(g, {"user_persona": {"enabled": True, "name": "Captain Rhys", "about": "a pirate"}})
    assert o == {"name": "Captain Rhys", "about": "a pirate"}


# ── card import ────────────────────────────────────────────────────────
def test_v2_png_card():
    from playground.character_sheet import read_card_png, card_to_character
    card = {"spec": "chara_card_v2", "data": {"name": "Ann", "first_mes": "Hi", "mes_example": "x",
                                              "alternate_greetings": ["Yo"], "description": "d"}}
    png = _png_with_chunk(b"chara", base64.b64encode(json.dumps(card).encode()))
    f = card_to_character(read_card_png(png))
    assert (f["name"], f["greeting"], f["example_dialogue"], f["alternate_greetings"]) == ("Ann", "Hi", "x", ["Yo"])


def test_png_without_card_is_rejected():
    from playground.character_sheet import read_card_png
    with pytest.raises(ValueError):
        read_card_png(_png_with_chunk(b"Comment", b"just a picture"))


def test_cai_tools_card_maps_title_to_tagline():
    from playground.character_sheet import card_to_character
    card = {"name": "Kael", "description": "Long desc", "first_mes": "Hey", "scenario": "", "mes_example": "def",
            "personality": "Retired captain", "metadata": {"tool": {"name": "CAI Tools", "version": "2.1.0"}}}
    f = card_to_character(card)
    assert f["tagline"] == "Retired captain" and f["personality"] == "" and f["description"] == "Long desc"


# ── Character.ai chats ─────────────────────────────────────────────────
def test_tavern_jsonl():
    from playground.cai_import import parse_chat_file
    lines = [{"user_name": "You", "character_name": "Kael", "create_date": 1},
             {"name": "Kael", "is_user": False, "is_name": True, "send_date": 1, "mes": "Hello"},
             {"name": "You", "is_user": True, "is_name": True, "send_date": 1, "mes": "Hi there"}]
    r = parse_chat_file("Kael_tavern_Chat.jsonl", "\n".join(json.dumps(x) for x in lines).encode())
    assert r["char_name"] == "Kael" and [m["is_user"] for m in r["chats"][0]["messages"]] == [False, True]


def test_offline_html_decodes_messages_and_orders_chats():
    from urllib.parse import quote
    from playground.cai_import import parse_chat_file
    hist = {"charPic": None, "userPic": None, "history": [
        {"date": "2026-10-02T00:00:00Z", "chat": [{"isUser": True, "name": "Sam", "message": quote("newer & later")}]},
        {"date": "2026-09-01T00:00:00Z", "chat": [{"isUser": False, "name": "Kael", "message": quote("older")}]}]}
    html = "<html><script>const historyData = " + json.dumps(hist) + ";</script></html>"
    r = parse_chat_file("Kael_Offline.html", html.encode())
    assert [c["date"][:7] for c in r["chats"]] == ["2026-09", "2026-10"]
    assert r["chats"][1]["messages"][0]["text"] == "newer & later" and r["user_name"] == "Sam"


def test_memories_skip_small_talk_but_keep_moments():
    from playground.cai_import import memories_from_chats
    chat = {"date": "2026-09-01T00:00:00Z", "messages": [
        {"is_user": True, "text": "ok"}, {"is_user": False, "text": "sure"},
        {"is_user": True, "text": "My grandmother passed away last week and I miss her a lot."},
        {"is_user": False, "text": "I'm so sorry."}]}
    mems = memories_from_chats([chat], "Sam")
    assert len(mems) == 1 and "grandmother" in mems[0]["content"] and mems[0]["timestamp"].startswith("2026-09")


# ── voice messages ─────────────────────────────────────────────────────
def test_audio_converts_to_16k_mono_wav():
    pytest.importorskip("av")
    from playground.media_utils import audio_to_wav16k
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"\x00\x01" * 2 * 44100)   # 1 s stereo
    out = audio_to_wav16k(b.getvalue())
    with wave.open(io.BytesIO(out)) as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (1, 16000, 2)
        assert 15000 < w.getnframes() < 17000


def _fake_gguf(kv: dict) -> bytes:
    out = b"GGUF" + struct.pack("<I", 3) + struct.pack("<QQ", 0, len(kv))
    for k, v in kv.items():
        kb = k.encode()
        out += struct.pack("<Q", len(kb)) + kb + struct.pack("<I", 7) + struct.pack("<?", v)
    return out


def test_projector_caps_reads_audio_flag(tmp_path):
    from playground.media_utils import projector_caps
    a = tmp_path / "mmproj-a.gguf"
    a.write_bytes(_fake_gguf({"clip.has_vision_encoder": True, "clip.has_audio_encoder": True}))
    v = tmp_path / "mmproj-v.gguf"
    v.write_bytes(_fake_gguf({"clip.has_vision_encoder": True}))
    assert projector_caps(str(a)) == {"vision": True, "audio": True}
    assert projector_caps(str(v)) == {"vision": True, "audio": False}


# ── history sent to the model ──────────────────────────────────────────
def test_history_starting_with_greeting_gets_a_user_turn_first():
    from playground import server as S
    out = S._ensure_alternation([{"role": "assistant", "content": "Welcome back!", "greeting": True},
                                 {"role": "user", "content": "hi"}])
    assert [m["role"] for m in out] == ["user", "assistant", "user"]


# ── known-bug fixes ────────────────────────────────────────────────────
def test_user_real_name_merges_into_user(tmp_path):
    from vividmimir import Mimir
    m = Mimir(data_dir=str(tmp_path))
    m.remember("Scott loves trail running", emotion="happy", importance=6, source="social", entity="Scott")
    assert m.set_user_aliases(["Scott"]) == 1
    assert m.remember("He beat his 10k record", emotion="proud", source="social", entity="scott").entity == "User"
    assert "Scott" not in m._social


def test_first_affect_fade_is_capped(tmp_path):
    from datetime import datetime, timedelta
    from vividmimir import Mimir
    m = Mimir(data_dir=str(tmp_path))
    b = m.remember("A horrible argument", emotion="angry", importance=7)
    old = (datetime.now() - timedelta(days=730)).isoformat()
    b.timestamp = old; b._last_access = old; m._last_affect_fade = ""
    m.fade_affect()
    assert b._affect_intensity > 0.8          # a month's softening, not two years'


def test_anthropic_and_google_accept_images():
    import inspect
    from playground import llm_backends as L
    for c in (L.AnthropicBackend, L.GoogleBackend):
        assert "images" in inspect.signature(c.generate).parameters
