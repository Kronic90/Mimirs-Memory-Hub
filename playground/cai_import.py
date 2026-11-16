"""Import from Character.ai.

Character.ai has no official export; people use the community "CAI Tools"
browser extension (github.com/irsat000/CAI-Tools, v2.1.0). Formats handled,
as that extension's source builds them:

  Characters
    * "Character Card (png)"  -- PNG with a V1-style `chara` tEXt chunk
    * "Character (json)"      -- char_name/char_persona/char_greeting/... plus
                                 name/description/first_mes/... (title is put
                                 in `personality`)
  Chats
    * Tavern chat  (*.jsonl) -- header {user_name, character_name, ...} then
                                one {name, is_user, mes, send_date} per line
    * Offline Chat / History (*.html) -- self-contained page with an embedded
                                {"charPic", "userPic", "history": [{"date"?,
                                "chat": [{"isUser", "name", "message"}]}]};
                                messages are URI-encoded
    * Oobabooga chat (*.json) -- {"internal": [[user, char], ...], ...}
    * "Chat as Definition" / Example (*.txt) -- <START> blocks of
                                {{user}}: / {{char}}: lines

Imported chats become Saved Chats you can carry on, and the meaningful
moments in them become the character's memories (dated, when the export
has dates), so the character arrives already knowing you.
"""
from __future__ import annotations

import base64
import json
import re
from urllib.parse import unquote


def _clean(t) -> str:
    return re.sub(r"\r\n?", "\n", str(t or "")).strip()


def _name_from_filename(filename: str) -> str:
    stem = re.sub(r"\.(jsonl|json|html?|txt)$", "", filename or "", flags=re.I)
    stem = re.sub(r"_(tavern_Chat|oobabooga_Chat|Offline|Example|TavernHistory)$", "", stem, flags=re.I)
    return stem.replace("_", " ").strip()


def is_cai_character(card: dict) -> bool:
    meta = card.get("metadata") or {}
    tool = (meta.get("tool") or {}).get("name", "") if isinstance(meta, dict) else ""
    return "CAI" in str(tool) or "char_greeting" in card or "char_persona" in card


def parse_chat_file(filename: str, data: bytes) -> dict:
    """-> {"char_name", "user_name", "char_pic": bytes|None,
           "chats": [{"date": str|None, "messages": [{"is_user", "text"}]}]}"""
    text = data.decode("utf-8-sig", errors="replace")
    low = (filename or "").lower()
    stripped = text.lstrip()

    # ── Tavern JSONL ──
    if low.endswith(".jsonl") or (stripped.startswith("{") and "\n{" in stripped and '"mes"' in stripped):
        lines = [ln for ln in text.splitlines() if ln.strip()]
        header, msgs = {}, []
        for ln in lines:
            try:
                o = json.loads(ln)
            except Exception:
                continue
            if "mes" in o:
                msgs.append({"is_user": bool(o.get("is_user")), "text": _clean(o.get("mes"))})
            elif "character_name" in o or "user_name" in o:
                header = o
        if not msgs:
            raise ValueError("No messages found in that chat file")
        return {"char_name": header.get("character_name") or _name_from_filename(filename),
                "user_name": "" if header.get("user_name") in (None, "", "You") else header["user_name"],
                "char_pic": None, "chats": [{"date": None, "messages": msgs}]}

    # ── Offline HTML ──
    if low.endswith((".html", ".htm")) or "<html" in stripped[:500].lower():
        i = text.find('{"charPic"')
        if i < 0:
            m = re.search(r'\{\s*"charPic"', text)
            i = m.start() if m else -1
        if i < 0:
            raise ValueError("This HTML file isn't a CAI Tools offline chat (no embedded chat data found)")
        obj, _ = json.JSONDecoder().raw_decode(text, i)
        chats, char_name, user_name = [], "", ""
        for h in obj.get("history") or []:
            msgs = []
            for m in h.get("chat") or []:
                is_user = bool(m.get("isUser", m.get("isHuman")))
                try:
                    t = unquote(m.get("message", ""))
                except Exception:
                    t = m.get("message", "")
                msgs.append({"is_user": is_user, "text": _clean(t)})
                if is_user and not user_name:
                    user_name = m.get("name", "")
                if not is_user and not char_name:
                    char_name = m.get("name", "")
            if msgs:
                chats.append({"date": h.get("date"), "messages": msgs})
        pic = None
        cp = obj.get("charPic") or ""
        if isinstance(cp, str) and cp.startswith("data:") and "," in cp:
            try:
                pic = base64.b64decode(cp.split(",", 1)[1])
            except Exception:
                pic = None
        # newest-first in the export -> oldest first
        chats.sort(key=lambda c: c["date"] or "")
        if not chats:
            raise ValueError("No messages found in that offline chat")
        return {"char_name": char_name or _name_from_filename(filename),
                "user_name": user_name, "char_pic": pic, "chats": chats}

    # ── Oobabooga JSON ──
    if stripped.startswith("{"):
        obj = json.loads(text)
        if isinstance(obj, dict) and isinstance(obj.get("internal"), list):
            msgs = []
            for pair in obj["internal"]:
                if isinstance(pair, list) and len(pair) == 2:
                    if _clean(pair[0]):
                        msgs.append({"is_user": True, "text": _clean(pair[0])})
                    if _clean(pair[1]):
                        msgs.append({"is_user": False, "text": _clean(pair[1])})
            if not msgs:
                raise ValueError("No messages found in that chat file")
            return {"char_name": _name_from_filename(filename), "user_name": "",
                    "char_pic": None, "chats": [{"date": None, "messages": msgs}]}
        if isinstance(obj, dict) and (obj.get("name") or obj.get("char_name")):
            raise ValueError("That's a character file, not a chat — add it as the character instead")
        raise ValueError("Unrecognised chat JSON")

    # ── Example / definition TXT ──
    if "{{user}}" in text or "{{char}}" in text:
        chats = []
        for block in re.split(r"<START>", text):
            msgs, cur = [], None
            for ln in block.splitlines():
                mm = re.match(r"\s*\{\{(user|char)\}\}\s*:\s*(.*)", ln)
                if mm:
                    cur = {"is_user": mm.group(1) == "user", "text": mm.group(2)}
                    msgs.append(cur)
                elif cur is not None and ln.strip():
                    cur["text"] += "\n" + ln
            msgs = [{"is_user": m["is_user"], "text": _clean(m["text"])} for m in msgs if _clean(m["text"])]
            if msgs:
                chats.append({"date": None, "messages": msgs})
        if chats:
            return {"char_name": _name_from_filename(filename), "user_name": "",
                    "char_pic": None, "chats": chats}
    raise ValueError("Unrecognised chat format — use a CAI Tools Tavern (.jsonl), Offline (.html), "
                     "Oobabooga (.json) or Example (.txt) export")


def exchanges(messages: list[dict]) -> list[tuple[str, str]]:
    """(user text, character's reply) pairs, merging consecutive turns."""
    out, u, c = [], [], []
    for m in messages:
        if m["is_user"]:
            if c and u:
                out.append(("\n".join(u), "\n".join(c)))
                u, c = [], []
            elif c and not u:
                c = []   # character opened the chat (greeting) -- not a memory
            u.append(m["text"])
        else:
            c.append(m["text"])
    if u:
        out.append(("\n".join(u), "\n".join(c)))
    return out


def memories_from_chats(chats: list[dict], user_label: str = "User",
                        max_memories: int = 400) -> list[dict]:
    """The moments worth remembering: each exchange scored with the same
    importance heuristic memory imports use; only the more meaningful
    ones are kept (capped), small talk is left in the saved chat."""
    from playground.memory_manager import estimate_importance, detect_emotions
    cands = []
    for chat in chats:
        for idx, (u, c) in enumerate(exchanges(chat["messages"])):
            if len(u) < 12:
                continue
            imp = estimate_importance(u, c)
            content = f"{user_label} told me: {u[:400]}"
            if c:
                content += f" — I replied: {c[:240]}"
            emo = (detect_emotions(u, top_k=1) or ["neutral"])[0]   # how *you* felt
            cands.append({"content": content, "importance": imp, "emotion": emo,
                          "timestamp": chat.get("date") or "", "_order": (chat.get("date") or "", idx),
                          "why_saved": "imported from Character.ai"})
    # Something personal (importance 6+), or anything said at length; "ok",
    # "lol" and one-liners stay in the saved chat only.
    keep = [m for m in cands if m["importance"] >= 6 or len(m["content"]) >= 120]         or sorted(cands, key=lambda m: -m["importance"])[:40]
    if len(keep) > max_memories:
        keep = sorted(keep, key=lambda m: -m["importance"])[:max_memories]
    keep.sort(key=lambda m: m["_order"])
    for m in keep:
        m.pop("_order", None)
    return keep
