"""Import from a COF file (.cof).

COF (Character Open File, github.com/yannsouetre/cof) is an open ZIP
container for one character: the first entry is `mimetype`, the second is
`manifest.json`, then the character's elements. Two things in it map
straight onto Mimir:

  * the personality -- a complete Character Card V3 (read by the same
    card path as SillyTavern cards), or free text;
  * the memories -- each one has a short text (`gist`), when it happened,
    how it felt and how much it matters, which is what a Mimir memory
    holds. They arrive as the character's memories, in life order, dated
    when the file gives a date.

A COF memory often says an age ("at eight") and no date, and the format
has no birth date on purpose. Such a memory is imported undated, with the
age kept in `why_saved`: no date is estimated.

Read as the format's minimal reader does: default character, default
preset, what that preset applies. Memories the character would rather not
tell (`disclosure: secret`) stay in the file unless asked for. The picture
is the file's thumbnail, only when it shows the preset being read and, for
a real person, when the file's consent record covers images. Other images,
voice, the psyche graph and usage rights are not imported; the rights are
returned so the UI can show them.

Standard library only; nothing here is executed, only read.
"""
from __future__ import annotations

import io
import json
import re
import statistics
import zipfile
from datetime import date

MIMETYPE = "application/vnd.cof.character+zip"
THUMBNAIL = "Thumbnails/thumbnail.png"

# A .cof is a few megabytes of media at most for our purposes; refuse zip bombs.
MAX_ENTRIES = 4000
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_JSON_BYTES = 8 * 1024 * 1024
_SAFE_PATH = re.compile(r"^(?!/)(?!.*\.\.)[A-Za-z0-9._/-]+\Z")
_PARTIAL_DATE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")


def is_cof(data: bytes) -> bool:
    """True when the bytes start like a COF file: a ZIP whose first entry
    is `mimetype`, stored, holding the exact media type."""
    if len(data) < 38 + len(MIMETYPE) or data[:4] != b"PK\x03\x04":
        return False
    if data[8:10] != b"\x00\x00" or data[30:38] != b"mimetype":
        return False
    start = 38 + int.from_bytes(data[28:30], "little")
    return data[start:start + len(MIMETYPE)] == MIMETYPE.encode("ascii")


def _text(value, language: str) -> str:
    """A COF text is either a string or a map of language -> string."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in (language, "en"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
        for v in value.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def _point(when) -> dict:
    """The point in time a memory starts at: `when` itself, or its `from`."""
    if not isinstance(when, dict):
        return {}
    if "age" not in when and "date" not in when and isinstance(when.get("from"), dict):
        return when["from"]
    return when


def _date_parts(when):
    """(year, 'YYYY-MM-DD') of a memory's date, or None. A partial date
    (year, or year and month) is taken at its first day."""
    value = _point(when).get("date")
    m = _PARTIAL_DATE.match(value.strip()) if isinstance(value, str) else None
    if not m:
        return None
    return int(m.group(1)), f"{m.group(1)}-{m.group(2) or '01'}-{m.group(3) or '01'}"


def _age_years(when):
    """Age of the character at a memory, in years, or None. COF writes
    {"value": 8, "unit": "years"} (months are allowed for the very young)."""
    age = _point(when).get("age")
    unit = "years"
    if isinstance(age, dict):
        age, unit = age.get("value"), age.get("unit", "years")
    if isinstance(age, bool) or not isinstance(age, (int, float)) or age < 0:
        return None
    return age / 12 if unit == "months" else age


def _date_memories(memories: list) -> list:
    """Order memories as a life (by age, then by date) and give a timestamp
    to those the file dates. A memory with an age and no date stays undated:
    Mimir's own memory system reads timestamps, so none is estimated. Ages
    and dates found together only help place dated memories in life order.
    `memories` items carry the private keys _age, _date and _approx."""
    births = [m["_date"][0] - m["_age"] for m in memories if m["_date"] and m["_age"] is not None]
    birth = statistics.median(births) if births else None

    def order(m):
        if m["_age"] is not None:
            return (0, m["_age"], "")
        if m["_date"] and birth is not None:
            return (0, m["_date"][0] - birth, "")
        return (1, 0, m["_date"][1]) if m["_date"] else (2, 0, "")

    out = []
    for m in sorted(memories, key=order):          # stable: at the same age, the file's order
        age, when = m.pop("_age"), m.pop("_date")
        about = "about " if m.pop("_approx") else ""
        if when:
            m["timestamp"] = f"{when[1]}T00:00:00"
        elif age is not None:
            # no date in the file: none is made up, the age stays a note
            m["why_saved"] += f"; happened at {about}age {age:g} (the file gives no date)"
        out.append(m)
    return out


def _consent_scope(identity: dict, manifest: dict) -> list:
    """Uses a real person agreed to, from the file's consent record; an
    expired record counts for nothing."""
    rights = manifest.get("rights") if isinstance(manifest.get("rights"), dict) else {}
    consent = identity.get("consent") if isinstance(identity.get("consent"), dict) else rights.get("consent")
    if not isinstance(consent, dict) or not isinstance(consent.get("scope"), list):
        return []
    expires = consent.get("expires")
    if isinstance(expires, str) and expires[:10] < date.today().isoformat():
        return []
    return [s for s in consent["scope"] if isinstance(s, str)]


def _mentions(value, wanted: str) -> bool:
    if isinstance(value, dict):
        return any(_mentions(v, wanted) for v in value.values())
    if isinstance(value, list):
        return any(_mentions(v, wanted) for v in value)
    return value == wanted


def _importance(salience) -> int:
    """COF salience is 0-100; Mimir importance is 1-10."""
    if isinstance(salience, bool) or not isinstance(salience, (int, float)):
        return 5
    return max(1, min(10, round(salience / 10)))


def _emotion(memory: dict) -> str:
    felt = memory.get("felt_then") or memory.get("felt_now")
    category = felt.get("category") if isinstance(felt, dict) else None
    value = category.get("value") if isinstance(category, dict) else None
    return value.strip().lower() if isinstance(value, str) and value.strip() else "neutral"


def _slots(presets: dict, preset_id: str, seen: tuple = ()) -> dict:
    """What a preset applies, merged over the presets it extends."""
    preset = presets.get(preset_id)
    if not isinstance(preset, dict):
        return {}
    parent = preset.get("extends")
    base = _slots(presets, parent, seen + (preset_id,)) if isinstance(parent, str) and preset_id not in seen else {}
    own = preset.get("slots") if isinstance(preset.get("slots"), dict) else {}
    return {**base, **own}


def _variant(variants: dict, variant_id: str, seen: tuple = ()) -> dict:
    variant = variants.get(variant_id)
    if not isinstance(variant, dict):
        return {}
    parent = variant.get("derives_from")
    base = _variant(variants, parent, seen + (variant_id,)) if isinstance(parent, str) and variant_id not in seen else {}
    return {**base, **variant}


def _read_json(archive: zipfile.ZipFile, path: str):
    try:
        info = archive.getinfo(path)
    except KeyError:
        return None
    if info.file_size > MAX_JSON_BYTES:
        return None
    try:
        return json.loads(archive.read(info).decode("utf-8-sig"))
    except Exception:
        return None


def read_cof(data: bytes, include_secret: bool = False) -> dict:
    """Read a .cof. Returns:
      {name, card (a V2/V3 card dict, or None), description (free-text
       personality, when there is no card), greeting (of a free-text
       preset), avatar_png (bytes or None),
       memories: [{content, emotion, importance, timestamp, why_saved}],
       skipped_secret: int, preset: str, permissions: dict,
       real_person: bool, consent_scope: [str]}
    `real_person` is true unless the file states `fictional: true`: that
    field is the author's statement, and a file that does not make it is
    read as a real person without consent, as the format's own tools do.
    Raises ValueError with a message for the user when the file is not a
    COF file this version can read."""
    if not is_cof(data):
        raise ValueError("Not a COF file (.cof)")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ValueError(f"Not a readable COF file: {e}")
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
        raise ValueError("This COF file is too large to import")
    for info in infos:
        if info.filename != "mimetype" and not _SAFE_PATH.match(info.filename):
            raise ValueError("This COF file contains an unsafe path")

    manifest = _read_json(archive, "manifest.json")
    if not isinstance(manifest, dict):
        raise ValueError("This COF file has no readable manifest")
    if not re.fullmatch(r"1\.\d+", str(manifest.get("cof", ""))):
        raise ValueError(f"COF format {manifest.get('cof')!r} is newer than this version reads")

    presets = manifest.get("presets") if isinstance(manifest.get("presets"), dict) else {}
    identities = manifest.get("identities") if isinstance(manifest.get("identities"), dict) else {}
    identity_id = manifest.get("default_identity") if isinstance(manifest.get("default_identity"), str) else next(iter(identities), None)
    identity = identities.get(identity_id) if isinstance(identities.get(identity_id), dict) else {}
    own = [p for p, v in presets.items()
           if isinstance(v, dict) and (not identity_id or v.get("identity") in (None, identity_id))]
    wanted = identity.get("default_preset") or manifest.get("default_preset")
    preset_id = wanted if wanted in own else (own[0] if own else None)
    if preset_id is None:
        raise ValueError("This COF file has no preset to read")
    slots = _slots(presets, preset_id)
    elements = manifest.get("elements") if isinstance(manifest.get("elements"), dict) else {}

    def variants(category: str) -> dict:
        block = elements.get(category)
        return block["variants"] if isinstance(block, dict) and isinstance(block.get("variants"), dict) else {}

    # ── personality: a card, or free text ──
    card, description, language = None, "", "en"
    applied = [v for v in slots.get("personality") or [] if isinstance(v, str)]
    if applied:
        personality = _variant(variants("personality"), applied[0])
        language = personality.get("language") if isinstance(personality.get("language"), str) else "en"
        if personality.get("kind") == "card" and isinstance(personality.get("card"), str):
            loaded = _read_json(archive, personality["card"])
            if isinstance(loaded, dict):
                card = loaded
        elif isinstance(personality.get("text"), str):
            description = personality["text"]
    # A free-text preset opens with the preset's own greeting (`prompts.greeting`,
    # a map of language -> text), its own or the nearest inherited one.
    greeting, at, seen = "", preset_id, set()
    while not card and isinstance(at, str) and at not in seen and isinstance(presets.get(at), dict):
        seen.add(at)
        prompts = presets[at].get("prompts")
        if isinstance(prompts, dict) and prompts.get("greeting"):
            greeting = _text(prompts["greeting"], language)
            break
        at = presets[at].get("extends")
    name = identity.get("name") or manifest.get("name") or "Imported Character"
    if card:
        inner = card.get("data") if isinstance(card.get("data"), dict) else card
        name = inner.get("name") or name

    # ── memories the preset applies ──
    memories, skipped_secret = [], 0
    for variant_id in slots.get("memories") or []:
        if not isinstance(variant_id, str):
            continue
        variant = _variant(variants("memories"), variant_id)
        memory = _read_json(archive, variant.get("memory")) if isinstance(variant.get("memory"), str) else None
        if not isinstance(memory, dict):
            continue
        if memory.get("disclosure") == "secret" and not include_secret:
            skipped_secret += 1
            continue
        content = _text(memory.get("gist"), language)
        if not content:
            continue
        memories.append({
            "content": content,
            "emotion": _emotion(memory),
            "importance": _importance(memory.get("salience")),
            "timestamp": "",
            "why_saved": "imported from a COF file",
            "_age": _age_years(memory.get("when")),
            "_date": _date_parts(memory.get("when")),
            "_approx": bool(isinstance(memory.get("when"), dict) and memory["when"].get("approx")),
        })
    memories = _date_memories(memories)

    # ── who this is, and whether its picture may be shown ──
    holder = identity if "fictional" in identity else manifest
    real_person = holder.get("fictional") is not True
    scope = _consent_scope(identity, manifest) if real_person else []
    # The thumbnail is derived from one image (its asset's `source`); show it
    # only when the preset being read applies the variant that image belongs to.
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    source = next((a.get("source") for a in assets
                   if isinstance(a, dict) and a.get("path") == THUMBNAIL), None)
    shown = isinstance(source, str) and any(
        _mentions(_variant(variants("appearance"), v), source)
        for v in slots.get("appearance") or [] if isinstance(v, str))
    avatar = None
    if shown and (not real_person or "likeness-image" in scope):
        try:
            info = archive.getinfo(THUMBNAIL)
            if info.file_size <= MAX_JSON_BYTES:
                avatar = archive.read(info)
        except KeyError:
            pass

    rights = identity.get("rights") if isinstance(identity.get("rights"), dict) else manifest.get("rights")
    permissions = rights.get("permissions") if isinstance(rights, dict) and isinstance(rights.get("permissions"), dict) else {}
    return {"name": str(name), "card": card, "description": description, "greeting": greeting,
            "avatar_png": avatar,
            "memories": memories, "skipped_secret": skipped_secret, "preset": preset_id,
            "permissions": permissions, "real_person": real_person, "consent_scope": scope}
