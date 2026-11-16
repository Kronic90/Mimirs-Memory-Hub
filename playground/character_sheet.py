"""Character sheets: turning a character (and the user's persona) into the
prompt the model sees, plus reading character cards from other apps.

Kept separate from server.py so single chat, multi-chat and imports all
describe a character the same way.
"""
from __future__ import annotations

import base64
import json
import re
import struct
import zlib

# Sheet fields, in the order they're presented to the model.
# (old characters only have name/description/personality/system_prompt --
#  every other field is optional and simply skipped when empty)
LIST_FIELDS = ("nicknames", "traits", "likes", "dislikes")


def _as_list(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        v = re.split(r"[,\n]", v)
    return [str(x).strip() for x in v if str(x).strip()]


def _fill(text: str, char_name: str, user_name: str) -> str:
    """SillyTavern-style placeholders: {{char}} / {{user}} (any case, and
    the old <BOT>/<USER> spellings)."""
    if not text:
        return ""
    text = re.sub(r"\{\{\s*char\s*\}\}|<BOT>", char_name or "the character", text, flags=re.I)
    text = re.sub(r"\{\{\s*user\s*\}\}|<USER>", user_name or "the user", text, flags=re.I)
    return text.strip()


def resolve_user_persona(cfg_persona: dict | None, char: dict | None) -> dict:
    """Who the user is in this chat: the character's own override if it has
    one, otherwise the global persona from Settings."""
    base = dict(cfg_persona or {})
    if char:
        override = char.get("user_persona") or {}
        if override.get("enabled") and (override.get("name") or override.get("about")):
            base = {"name": override.get("name") or base.get("name", ""),
                    "about": override.get("about") or ""}
    return {"name": (base.get("name") or "").strip(),
            "about": (base.get("about") or "").strip()}


def build_character_prompt(char: dict, persona: dict | None = None,
                           display_name: str = "") -> str:
    """The character part of the system prompt, written as plain sections
    a model can follow. Empty fields are skipped entirely."""
    persona = persona or {}
    name = display_name or char.get("name") or "the character"
    user_name = persona.get("name") or ""
    f = lambda key: _fill(char.get(key, ""), name, user_name)  # noqa: E731

    out: list[str] = [f"Your name is {name}."]
    nick = _as_list(char.get("nicknames"))
    if nick:
        out[0] += f" People also call you {', '.join(nick)}."
    if char.get("tagline"):
        out.append(f("tagline"))

    who = [x for x in (f("description"), f("backstory")) if x]
    appearance = f("appearance")
    if who or appearance:
        sec = ["## Who you are"] + who
        if appearance:
            sec.append(f"Appearance: {appearance}")
        out.append("\n".join(sec))

    traits = _as_list(char.get("traits"))
    pers = [f"Traits: {', '.join(traits)}."] if traits else []
    if f("personality"):
        pers.append(f("personality"))
    if f("speaking_style"):
        pers.append(f"How you talk: {f('speaking_style')}")
    likes, dislikes = _as_list(char.get("likes")), _as_list(char.get("dislikes"))
    if likes:
        pers.append(f"You love: {', '.join(likes)}.")
    if dislikes:
        pers.append(f"You can't stand: {', '.join(dislikes)}.")
    if f("quirks"):
        pers.append(f"Quirks & habits: {f('quirks')}")
    if pers:
        out.append("## Personality\n" + "\n".join(pers))

    if f("scenario"):
        out.append("## The situation\n" + f("scenario"))

    about_user = []
    if user_name:
        call = (char.get("user_nickname") or "").strip()
        about_user.append(f"Their name is {user_name}."
                          + (f" You usually call them {call}." if call else ""))
    elif (char.get("user_nickname") or "").strip():
        about_user.append(f"You usually call them {char['user_nickname'].strip()}.")
    if persona.get("about"):
        about_user.append(_fill(persona["about"], name, user_name))
    if f("relationship"):
        about_user.append(f"Your relationship: {f('relationship')}")
    if about_user:
        out.append("## The person you're talking to\n" + "\n".join(about_user))

    if f("example_dialogue"):
        out.append("## Example of how you talk (style only — this never actually happened)\n"
                   + f("example_dialogue"))
    if f("system_prompt"):
        out.append(f("system_prompt"))
    return "\n\n".join(out)


def build_user_prompt(persona: dict) -> str:
    """For chats with no character: just who the user is."""
    if not persona or not (persona.get("name") or persona.get("about")):
        return ""
    lines = ["## The person you're talking to"]
    if persona.get("name"):
        lines.append(f"Their name is {persona['name']}.")
    if persona.get("about"):
        lines.append(persona["about"])
    return "\n".join(lines)


# ── Character cards from other apps ─────────────────────────────────────

def _png_text_chunks(data: bytes) -> dict[str, str]:
    """tEXt / zTXt / iTXt chunks of a PNG, keyword -> text."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Not a PNG file")
    pos, out = 8, {}
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        try:
            if ctype == b"tEXt":
                k, _, v = body.partition(b"\x00")
                out[k.decode("latin-1")] = v.decode("latin-1")
            elif ctype == b"zTXt":
                k, _, rest = body.partition(b"\x00")
                out[k.decode("latin-1")] = zlib.decompress(rest[1:]).decode("latin-1")
            elif ctype == b"iTXt":
                k, _, rest = body.partition(b"\x00")
                comp, _method = rest[0], rest[1]
                _lang, _, rest = rest[2:].partition(b"\x00")
                _tk, _, text = rest.partition(b"\x00")
                out[k.decode("latin-1")] = (zlib.decompress(text) if comp else text).decode("utf-8")
        except Exception:
            continue
        if ctype == b"IEND":
            break
    return out


def read_card_png(data: bytes) -> dict:
    """Character data embedded in a SillyTavern / TavernAI / Chub card PNG
    (V3 'ccv3' preferred, else V2/V1 'chara'). Raises ValueError if none."""
    chunks = _png_text_chunks(data)
    for key in ("ccv3", "chara"):
        if key in chunks:
            raw = chunks[key].strip()
            try:
                return json.loads(base64.b64decode(raw).decode("utf-8"))
            except Exception:
                try:
                    return json.loads(raw)
                except Exception:
                    continue
    raise ValueError("This PNG doesn't contain character data (no 'chara' or 'ccv3' block)")


def card_to_character(card: dict) -> dict:
    """Map a Tavern V1/V2/V3 card (or a plain JSON character) onto sheet
    fields. Keeps the original under _original."""
    d = card.get("data") if isinstance(card.get("data"), dict) else card
    name = d.get("name") or d.get("char_name") or "Imported Character"
    alts = d.get("alternate_greetings") or []
    out = {
        "name": name,
        "description": d.get("description") or d.get("char_persona") or "",
        "personality": d.get("personality") or "",
        "scenario": d.get("scenario") or d.get("world_scenario") or "",
        "greeting": d.get("first_mes") or d.get("char_greeting") or d.get("greeting") or "",
        "alternate_greetings": [a for a in alts if isinstance(a, str)],
        "example_dialogue": d.get("mes_example") or d.get("example_dialogue") or "",
        "system_prompt": d.get("system_prompt") or "",
        "tagline": (d.get("creator_notes") or "").strip().split("\n")[0][:140]
                   if d.get("creator_notes") else "",
        "nicknames": _as_list(d.get("nickname")) if d.get("nickname") else [],
        "_original": card,
    }
    tags = d.get("tags")
    if isinstance(tags, list):
        out["tags"] = [str(t) for t in tags][:20]
    # Character.ai (via CAI Tools) puts the short "title" in `personality`
    # and the definition in mes_example.
    from playground.cai_import import is_cai_character
    if is_cai_character(d):
        out["tagline"] = (d.get("personality") or "").strip()[:140]
        out["personality"] = ""
        out["description"] = d.get("char_persona") or d.get("description") or ""
        out["greeting"] = d.get("char_greeting") or d.get("first_mes") or ""
        out["example_dialogue"] = d.get("mes_example") or d.get("example_dialogue") or ""
        out["_cai"] = True
    return out
