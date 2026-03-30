"""FastAPI server for Mimir's Memory Hub."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Ensure Mimir importable
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

# Also export as env var so sub-imports see it
import os as _os
if _root not in _os.environ.get("PYTHONPATH", ""):
    _os.environ["PYTHONPATH"] = _root + _os.pathsep + _os.environ.get("PYTHONPATH", "")

from playground.config import Config
from playground.presets import PRESETS, get_preset
from playground.llm_backends import create_backend, OllamaBackend
from playground.memory_manager import MemoryManager
from playground import model_manager
from playground.character_manager import CharacterManager
from playground.conversation_manager import ConversationManager
from playground.tts_backend import create_tts, EDGE_VOICES
from playground.stt_backend import WhisperSTTBackend

# ── App ───────────────────────────────────────────────────────────────

app = FastAPI(title="Mimir's Memory Hub", version="0.2.0")

_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static)), name="static")


# Prevent browser from caching stale JS/CSS/HTML
@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# ── State ─────────────────────────────────────────────────────────────

_cfg = Config()
_memory: MemoryManager | None = None
_char_memories: dict[str, MemoryManager] = {}   # per-character isolated memories
_download_progress: dict[str, dict] = {}  # filename -> {status, downloaded, total, percent}
_tts = None  # EdgeTTSBackend or MayaTTSBackend
_stt: WhisperSTTBackend | None = None
_conversation: list[dict[str, str]] = []
_current_conv_id: str | None = None     # auto-save tracking
_characters = CharacterManager()
_conversations = ConversationManager()

# History for visualizations (persisted to disk)
_mood_history: list[dict] = []
_chemistry_history: list[dict] = []
_VIZ_HISTORY_FILE = Path(__file__).resolve().parent.parent / "playground_data" / "viz_history.json"


def _load_viz_history():
    """Load mood & chemistry history from disk on startup."""
    global _mood_history, _chemistry_history
    try:
        if _VIZ_HISTORY_FILE.exists():
            data = json.loads(_VIZ_HISTORY_FILE.read_text(encoding="utf-8"))
            _mood_history = data.get("mood", [])
            _chemistry_history = data.get("chemistry", [])
    except Exception:
        pass


def _save_viz_history():
    """Persist mood & chemistry history to disk (keeps last 500 entries)."""
    try:
        _VIZ_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "mood": _mood_history[-500:],
            "chemistry": _chemistry_history[-500:],
        }
        _VIZ_HISTORY_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


_load_viz_history()

# ── Remember-tag parsing ──────────────────────────────────────────────

import re as _re

_REMEMBER_RE = _re.compile(
    r'<remember(?P<attrs>[^>]*)>(?P<content>.*?)</remember>',
    _re.DOTALL | _re.IGNORECASE,
)
_ATTR_RE = _re.compile(r'(\w+)=["\']([^"\']*)["\']')

# Strip <think> / <thinking> blocks from stored conversation history
# Also handles unclosed think tags (model hit max_tokens while still thinking)
_THINK_STRIP_RE = _re.compile(
    r'<(think|thinking)>.*?(?:</(think|thinking)>|$)',
    _re.DOTALL | _re.IGNORECASE,
)

# GPT-OSS / channel-format: strip the entire analysis block from history
_CHANNEL_ANALYSIS_BLOCK_RE = _re.compile(
    r'<\|channel\|>\s*analysis\s*<\|message\|>.*?(?:<\|end\|>|$)',
    _re.DOTALL | _re.IGNORECASE,
)
# Clean remaining channel/start/end markers (keeps final message text)
_CHANNEL_STRIP_RE = _re.compile(
    r'<\|channel\|>\s*(?:analysis|final)\s*<\|message\|>|<\|end\|>|<\|start\|>\s*assistant',
    _re.DOTALL | _re.IGNORECASE,
)

# Extract think block content (for memory-intent fallback)
_THINK_CONTENT_RE = _re.compile(
    r'<(?:think|thinking)>(.*?)(?:</(?:think|thinking)>|$)',
    _re.DOTALL | _re.IGNORECASE,
)
# GPT-OSS analysis channel content
_CHANNEL_CONTENT_RE = _re.compile(
    r'<\|channel\|>\s*analysis\s*<\|message\|>(.*?)(?:<\|end\|>|$)',
    _re.DOTALL | _re.IGNORECASE,
)
# Patterns that indicate memory intent inside think blocks
_MEMORY_INTENT_RE = _re.compile(
    r'(?:I should remember|important to (?:note|remember)|key (?:point|detail|info)|'
    r'worth remembering|need to remember|remember(?:ing)? that)'
    r'[:\s]+(.+?)(?:\.|$)',
    _re.IGNORECASE | _re.MULTILINE,
)

def _parse_remember_tags(text: str) -> list[dict]:
    """Extract all <remember> entries from model output.

    Each entry: { content, emotion, importance, why, source, cherish, anchor }
    """
    entries = []
    for m in _REMEMBER_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(m.group("attrs")))
        importance = int(attrs.get("importance", 5))
        importance = max(1, min(10, importance))
        entries.append({
            "content":    m.group("content").strip(),
            "emotion":    attrs.get("emotion", "neutral"),
            "importance": importance,
            "why":        attrs.get("why", "model-authored memory"),
            "source":     attrs.get("source", "conversation"),
            "cherish":    attrs.get("cherish", "").lower() == "true",
            "anchor":     attrs.get("anchor", "").lower() == "true",
        })
    return entries

def _strip_remember_tags(text: str) -> str:
    """Remove all <remember>…</remember> blocks from text."""
    return _REMEMBER_RE.sub("", text).strip()


# ── Remind-tag parsing ────────────────────────────────────────────────────────

_REMIND_RE = _re.compile(
    r'<remind(?P<attrs>[^>]*)>(?P<content>.*?)</remind>',
    _re.DOTALL | _re.IGNORECASE,
)

# Mapping of weekday names to isoweekday() values (Mon=1)
_WEEKDAY_MAP = {
    "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4,
    "friday": 5, "saturday": 6, "sunday": 7,
}


def _parse_remind_tags(text: str) -> list[dict]:
    """Extract all <remind> entries → [{text, hours}]"""
    import datetime as _dt
    entries = []
    for m in _REMIND_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(m.group("attrs")))
        content = m.group("content").strip()
        hours: float = 24.0  # default

        in_val = attrs.get("in", "")
        if in_val:
            in_val = in_val.lower().strip()
            try:
                if in_val.endswith("d"):
                    hours = float(in_val[:-1]) * 24
                elif in_val.endswith("h"):
                    hours = float(in_val[:-1])
                elif in_val.endswith("m"):
                    hours = float(in_val[:-1]) / 60
            except ValueError:
                hours = 24.0

        date_val = attrs.get("date", "")
        if date_val and not in_val:
            try:
                target = _dt.datetime.strptime(date_val, "%Y-%m-%d")
                now = _dt.datetime.now()
                delta = target - now
                hours = max(0, delta.total_seconds() / 3600)
            except ValueError:
                hours = 24.0

        entries.append({"text": content, "hours": hours})
    return entries


def _strip_remind_tags(text: str) -> str:
    return _REMIND_RE.sub("", text).strip()


# ── Showimage-tag parsing ─────────────────────────────────────────────────────

_SHOWIMAGE_RE = _re.compile(
    r'<showimage\s+hash=["\']([^"\']+)["\'](?:\s*/)?>', _re.IGNORECASE
)


def _parse_showimage_tags(text: str) -> list[str]:
    """Return list of hashes from <showimage hash="..."/> tags."""
    return _SHOWIMAGE_RE.findall(text)


def _strip_showimage_tags(text: str) -> str:
    return _SHOWIMAGE_RE.sub("", text).strip()


# ── Task-tag parsing ─────────────────────────────────────────────────────────
# <task action="start" priority="7">Build the login page</task>
# <task action="complete" id="abc123">Login page done with OAuth</task>
# <task action="fail" id="abc123">Blocked by API limits</task>

_TASK_RE = _re.compile(
    r'<task(?P<attrs>[^>]*)>(?P<content>.*?)</task>',
    _re.DOTALL | _re.IGNORECASE,
)

_SOLUTION_RE = _re.compile(
    r'<solution(?P<attrs>[^>]*)>(?P<content>.*?)</solution>',
    _re.DOTALL | _re.IGNORECASE,
)


def _parse_task_tags(text: str) -> list[dict]:
    """Extract <task> tags → [{action, content, priority, id, project}]"""
    entries = []
    for m in _TASK_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(m.group("attrs")))
        entries.append({
            "action": attrs.get("action", "start").lower(),
            "content": m.group("content").strip(),
            "priority": int(attrs.get("priority", "5")),
            "id": attrs.get("id", ""),
            "project": attrs.get("project", ""),
        })
    return entries


def _strip_task_tags(text: str) -> str:
    return _TASK_RE.sub("", text).strip()


def _parse_solution_tags(text: str) -> list[dict]:
    """Extract <solution> tags → [{problem, content, importance}]"""
    entries = []
    for m in _SOLUTION_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(m.group("attrs")))
        entries.append({
            "problem": attrs.get("problem", ""),
            "content": m.group("content").strip(),
            "importance": int(attrs.get("importance", "5")),
        })
    return entries


def _strip_solution_tags(text: str) -> str:
    return _SOLUTION_RE.sub("", text).strip()


# ── Social impression tag parsing ────────────────────────────────────────────
# <social entity="Scott" emotion="warm" importance="7">He loves hiking</social>

_SOCIAL_RE = _re.compile(
    r'<social(?P<attrs>[^>]*)>(?P<content>.*?)</social>',
    _re.DOTALL | _re.IGNORECASE,
)


def _parse_social_tags(text: str) -> list[dict]:
    """Extract <social> tags → [{entity, content, emotion, importance}]"""
    entries = []
    for m in _SOCIAL_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(m.group("attrs")))
        entity = attrs.get("entity", "").strip()
        if not entity:
            continue
        entries.append({
            "entity": entity,
            "content": m.group("content").strip(),
            "emotion": attrs.get("emotion", "neutral"),
            "importance": int(attrs.get("importance", "5")),
        })
    return entries


def _strip_social_tags(text: str) -> str:
    return _SOCIAL_RE.sub("", text).strip()


# ── Cherish tag parsing (retroactive) ────────────────────────────────────────
# <cherish query="birthday party"/> or <cherish query="first conversation" anchor="true"/>

_CHERISH_RE = _re.compile(
    r'<cherish\s+(?P<attrs>[^>]*?)(?:/>|>\s*</cherish>)',
    _re.DOTALL | _re.IGNORECASE,
)


def _parse_cherish_tags(text: str) -> list[dict]:
    """Extract <cherish> tags → [{query, anchor}]"""
    entries = []
    for m in _CHERISH_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(m.group("attrs")))
        query = attrs.get("query", "").strip()
        if not query:
            continue
        entries.append({
            "query": query,
            "anchor": attrs.get("anchor", "").lower() == "true",
        })
    return entries


def _strip_cherish_tags(text: str) -> str:
    return _CHERISH_RE.sub("", text).strip()


# ── Code block + file saving parsing for Agent mode ──────────────────────────

_CODE_BLOCK_RE = _re.compile(
    r'```(\w+)?\s*\n(.*?)```',
    _re.DOTALL,
)

_SAVE_FILE_RE = _re.compile(
    r'<save_file\s+path=["\']([^"\']+)["\']>\s*(.*?)\s*</save_file>',
    _re.DOTALL | _re.IGNORECASE,
)


def _parse_code_blocks(text: str) -> list[dict]:
    """Extract fenced code blocks → [{language, code}]."""
    blocks = []
    for m in _CODE_BLOCK_RE.finditer(text):
        lang = (m.group(1) or "text").lower()
        code = m.group(2).strip()
        if code and lang in ("python", "py"):
            blocks.append({"language": "python", "code": code})
    return blocks


def _parse_save_file_tags(text: str) -> list[dict]:
    """Extract <save_file path="...">content</save_file> → [{path, content}]."""
    entries = []
    for m in _SAVE_FILE_RE.finditer(text):
        entries.append({"path": m.group(1).strip(), "content": m.group(2)})
    return entries


def _get_agent_files_dir() -> Path:
    """Return the agent_files directory, creating it if needed."""
    d = _cfg.profile_dir.parent.parent / "agent_files"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Heuristic reminder detection ─────────────────────────────────────────────

_HEURISTIC_REMIND_PHRASES = [
    "i need to", "i have to", "i must", "i should", "remind me to",
    "don't forget", "dont forget", "remember to", "i've got to", "i got to",
    "i gotta", "i need", "we need to", "i have an appointment", "i have a meeting",
]


def _heuristic_reminder_from_user(user_text: str) -> list[dict]:
    """
    Scan user message for reminder intent without explicit <remind> tags.
    Returns [{text, hours}] list, or [] if nothing detected.
    """
    import datetime as _dt
    lower = user_text.lower()

    if not any(p in lower for p in _HEURISTIC_REMIND_PHRASES):
        return []

    # Date/time detection
    hours: float = 24.0
    if "tonight" in lower or "this evening" in lower:
        hours = 6.0
    elif "in an hour" in lower or "in 1 hour" in lower:
        hours = 1.0
    elif "in two hours" in lower or "in 2 hours" in lower:
        hours = 2.0
    elif "tomorrow" in lower:
        hours = 24.0
    elif "this week" in lower:
        hours = 5 * 24.0
    elif "next week" in lower:
        hours = 7 * 24.0
    else:
        # Named weekday
        now_iso = _dt.datetime.now().isoweekday()  # Mon=1
        for dayname, iso_day in _WEEKDAY_MAP.items():
            if dayname in lower:
                diff = (iso_day - now_iso) % 7 or 7
                hours = diff * 24.0
                break

    # Cap text length for readability
    reminder_text = user_text[:200].strip()
    return [{"text": reminder_text, "hours": hours}]


def _ensure_memory(char_id: str = "") -> MemoryManager:
    """Return the MemoryManager for the given character (isolated) or global default."""
    global _memory, _char_memories
    if char_id:
        if char_id not in _char_memories:
            preset = get_preset(_cfg.get("active_preset", "companion"))
            char_mem_dir = str(_characters.get_memory_dir(char_id, _cfg.profile_dir))
            _char_memories[char_id] = MemoryManager(
                profile_dir=char_mem_dir,
                chemistry=preset.get("chemistry", True),
            )
        return _char_memories[char_id]
    if _memory is None:
        preset = get_preset(_cfg.get("active_preset", "companion"))
        _memory = MemoryManager(
            profile_dir=str(_cfg.profile_dir),
            chemistry=preset.get("chemistry", True),
        )
    return _memory


def _ensure_tts():
    global _tts
    if _tts is None:
        _tts = create_tts(_cfg.to_dict())
    return _tts


def _reload_tts():
    """Recreate TTS backend after settings change."""
    global _tts
    if _tts is not None:
        _tts.unload()
    _tts = create_tts(_cfg.to_dict())


def _ensure_stt() -> WhisperSTTBackend:
    global _stt
    if _stt is None:
        _stt = WhisperSTTBackend(_cfg.to_dict())
    return _stt


# ── Pages ─────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(str(_static / "index.html"))


# ── Settings API ──────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    data = _cfg.to_dict()
    # Mask API keys for frontend display
    for name in ("openai", "anthropic", "google", "custom"):
        key = data.get("backends", {}).get(name, {}).get("api_key", "")
        if key and len(key) > 8:
            data["backends"][name]["api_key"] = key[:4] + "•" * (len(key) - 8) + key[-4:]
    return JSONResponse(data)


@app.put("/api/settings")
async def update_settings(request: Request):
    global _memory, _char_memories, _tts, _stt
    patch = await request.json()
    # Never overwrite real API keys with masked values from the frontend
    for name in ("openai", "anthropic", "google", "custom"):
        incoming_key = patch.get("backends", {}).get(name, {}).get("api_key")
        if incoming_key is not None and "\u2022" in incoming_key:
            # This is a masked display value — drop it so the real key is preserved
            del patch["backends"][name]["api_key"]
    _cfg.update(patch)
    # Reset memory, TTS, and STT so they re-initialise with new config
    _memory = None
    _char_memories = {}
    _tts = None
    _stt = None
    return JSONResponse({"ok": True})


# ── Presets API ───────────────────────────────────────────────────────

@app.get("/api/presets")
async def list_presets():
    return JSONResponse(PRESETS)


# ── Models API ────────────────────────────────────────────────────────

@app.get("/api/models")
async def get_models():
    """List models for the active backend."""
    backend_name = _cfg.get("active_backend", "ollama")

    # For local backend, return all downloaded models + the active model
    if backend_name == "local":
        models_dir = str(_cfg.profile_dir.parent.parent / "models")
        downloaded = model_manager.list_local_models(models_dir)
        models = [{"id": m["path"], "name": m["filename"], "size": m["size"]}
                  for m in downloaded]
        # Also include the active model if it's outside the models dir
        active = _cfg.get("active_model", "")
        if active:
            from pathlib import Path
            p = Path(active)
            if p.is_file() and not any(m["id"] == active for m in models):
                models.insert(0, {"id": active, "name": p.name,
                                  "size": p.stat().st_size})
        return JSONResponse({"backend": "local", "models": models})

    backend = create_backend(backend_name, _cfg.to_dict())
    try:
        models = await backend.list_models()
        return JSONResponse({"backend": backend_name, "models": models})
    except Exception as e:
        return JSONResponse({"backend": backend_name, "models": [],
                             "error": str(e)}, status_code=200)


@app.get("/api/models/ollama/available")
async def check_ollama():
    """Check if Ollama is running."""
    backend = OllamaBackend(_cfg.to_dict().get("backends", {}).get("ollama", {}).get("base_url", "http://localhost:11434"))
    ok = await backend.is_available()
    return JSONResponse({"available": ok})


@app.get("/api/models/hf/search")
async def search_hf(q: str = "", limit: int = 20):
    try:
        results = await model_manager.search_huggingface(q, limit)
        return JSONResponse(results)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/models/hf/files")
async def hf_files(repo_id: str):
    try:
        files = await model_manager.get_repo_files(repo_id)
        return JSONResponse(files)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/models/local")
async def local_models():
    models_dir = str(_cfg.profile_dir.parent.parent / "models")
    return JSONResponse(model_manager.list_local_models(models_dir))


@app.get("/api/models/scan")
async def scan_models():
    """Scan local drives for GGUF files."""
    custom_dirs = _cfg.get("scan_directories", [])
    try:
        # Custom dirs are scanned in addition to defaults
        all_dirs = model_manager._default_scan_dirs()
        for d in custom_dirs:
            if d not in all_dirs:
                all_dirs.append(d)
        results = await asyncio.to_thread(
            model_manager.scan_for_gguf, all_dirs
        )
        # Cache results so they survive reload
        _cfg.update({"scan_cache": results})
        return JSONResponse(results)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/models/scan/cache")
async def scan_cache():
    """Return cached scan results, filtering out files that no longer exist."""
    cached = _cfg.get("scan_cache", [])
    if not cached:
        return JSONResponse([])
    valid = [m for m in cached if Path(m.get("path", "")).is_file()]
    if len(valid) != len(cached):
        _cfg.update({"scan_cache": valid})
    return JSONResponse(valid)


@app.post("/api/models/scan/dirs")
async def update_scan_dirs(request: Request):
    """Add or set custom scan directories."""
    body = await request.json()
    dirs = body.get("directories", [])
    # Validate paths exist
    valid = [d for d in dirs if Path(d).is_dir()]
    _cfg.update({"scan_directories": valid})
    return JSONResponse({"ok": True, "directories": valid})


@app.post("/api/models/hf/download")
async def download_hf(request: Request):
    """Download a GGUF from HuggingFace."""
    body = await request.json()
    repo_id = body.get("repo_id", "")
    filename = body.get("filename", "")
    if not repo_id or not filename:
        return JSONResponse({"error": "repo_id and filename required"}, status_code=400)

    dest_dir = str(_cfg.profile_dir.parent.parent / "models")
    dest_path = Path(dest_dir) / filename
    if dest_path.exists():
        return JSONResponse({"status": "exists", "path": str(dest_path)})

    # Start download in background, track progress
    _download_progress[filename] = {"status": "starting", "downloaded": 0, "total": 0, "percent": 0}

    async def _do_download():
        try:
            async for prog in model_manager.download_model(repo_id, filename, dest_dir):
                _download_progress[filename] = prog
        except Exception as e:
            _download_progress[filename] = {"status": "error", "error": str(e)}

    asyncio.create_task(_do_download())
    return JSONResponse({"status": "started", "filename": filename, "dest": dest_dir})


@app.get("/api/models/hf/download/status")
async def download_status():
    """Return current download progress for all active downloads."""
    return JSONResponse(_download_progress)


# ── Memory API ────────────────────────────────────────────────────────

@app.get("/api/memory/stats")
async def memory_stats(char_id: str = ""):
    mem = _ensure_memory(char_id=char_id or _cfg.get("active_character_id", ""))
    return JSONResponse(mem.stats())


@app.post("/api/memory/recall")
async def memory_recall(request: Request):
    body = await request.json()
    mem = _ensure_memory()
    results = mem.recall(body.get("context", ""), body.get("limit", 10))
    return JSONResponse(results)


@app.post("/api/memory/sleep")
async def memory_sleep():
    mem = _ensure_memory()
    mem.sleep()
    return JSONResponse({"ok": True})


@app.post("/api/memory/remember")
async def memory_remember(request: Request):
    body = await request.json()
    mem = _ensure_memory()
    result = mem.remember(
        content=body.get("content", ""),
        emotion=body.get("emotion", "neutral"),
        importance=body.get("importance", 5),
        source=body.get("source", "manual"),
        why_saved=body.get("why_saved", ""),
    )
    mem.save()
    return JSONResponse(result)


@app.get("/api/memory/graph")
async def memory_graph():
    """Return all memories with vividness, types, and graph edges for visualization."""
    mem = _ensure_memory()
    return JSONResponse(mem.get_graph())


@app.post("/api/memory/import")
async def memory_import(request: Request):
    """Import memories from uploaded text/JSON/markdown content."""
    body = await request.json()
    mem = _ensure_memory()
    entries = body.get("entries", [])
    imported = []
    for entry in entries:
        result = mem.import_memory(
            content=entry.get("content", ""),
            emotion=entry.get("emotion", "neutral"),
            importance=entry.get("importance", 5),
            source="import",
            why_saved=entry.get("why_saved", "imported from external system"),
            timestamp=entry.get("timestamp", ""),
        )
        imported.append(result)
    mem.save()
    return JSONResponse({"imported": len(imported), "memories": imported})


# ── Agent Tools API ──────────────────────────────────────────────────

_tool_permissions: dict = {}


@app.get("/api/tools/permissions")
async def get_tool_permissions():
    """Get current tool permissions."""
    perms = _cfg.get("tool_permissions", {
        "file_access": False,
        "web_search": False,
        "code_execution": False,
        "allowed_sites": [],
        "allowed_paths": [],
        "allowed_commands": [],
    })
    return JSONResponse(perms)


@app.put("/api/tools/permissions")
async def update_tool_permissions(request: Request):
    """Update tool permissions."""
    body = await request.json()
    perms = _cfg.get("tool_permissions", {})
    perms.update(body)
    _cfg.update({"tool_permissions": perms})
    return JSONResponse({"ok": True, "permissions": perms})


@app.post("/api/tools/execute")
async def execute_tool(request: Request):
    """Execute a tool with sandboxing."""
    body = await request.json()
    tool_name = body.get("tool", "")
    params = body.get("params", {})
    perms = _cfg.get("tool_permissions", {})

    from playground.tool_runner import run_tool
    result = await asyncio.to_thread(run_tool, tool_name, params, perms)
    return JSONResponse(result)


# ── Mood & Chemistry API ─────────────────────────────────────────────

@app.get("/api/memory/mood")
async def memory_mood(char_id: str = ""):
    """Return current mood, PAD vector, and neurochemistry state."""
    mem = _ensure_memory(char_id=char_id or _cfg.get("active_character_id", ""))
    return JSONResponse(mem.get_mood())


@app.post("/api/memory/consolidate")
async def memory_consolidate():
    """Run Muninn consolidation (merge duplicates, prune dead memories)."""
    mem = _ensure_memory()
    result = await asyncio.to_thread(mem.run_consolidation)
    return JSONResponse(result)


@app.post("/api/memory/huginn")
async def memory_huginn():
    """Run Huginn pattern detection (sentiment arcs, theme clusters, open threads)."""
    mem = _ensure_memory()
    result = await asyncio.to_thread(mem.run_huginn)
    return JSONResponse(result)


@app.post("/api/memory/dream")
async def memory_dream():
    """Run Volva dream synthesis (cross-pollinate distant memories)."""
    mem = _ensure_memory()
    result = await asyncio.to_thread(mem.run_dream)
    return JSONResponse(result)


@app.get("/api/memory/emotions")
async def memory_emotions():
    """Return emotion distribution across all memories."""
    mem = _ensure_memory()
    return JSONResponse(mem.emotion_distribution())


@app.get("/api/memory/chemistry")
async def memory_chemistry():
    """Return neurochemistry snapshot."""
    mem = _ensure_memory()
    return JSONResponse(mem.neurochemistry_snapshot())


# ── Memory browse / edit / delete ─────────────────────────────────

@app.get("/api/memory/browse")
async def memory_browse(offset: int = 0, limit: int = 50,
                         sort: str = "recent", emotion: str = "",
                         source: str = "", min_importance: int = 0,
                         char_id: str = ""):
    """Paginated memory browser with filters."""
    mem = _ensure_memory(char_id=char_id or _cfg.get("active_character_id", ""))
    result = mem.browse_memories(
        offset=offset, limit=limit, sort=sort,
        emotion_filter=emotion, source_filter=source,
        min_importance=min_importance,
    )
    return JSONResponse(result)


@app.delete("/api/memory/{index}")
async def memory_delete(index: int):
    """Delete a memory by index."""
    mem = _ensure_memory()
    ok = mem.delete_memory(index)
    if ok:
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "Invalid index"}, status_code=404)


@app.put("/api/memory/{index}")
async def memory_update(index: int, request: Request):
    """Update a memory's editable fields."""
    body = await request.json()
    mem = _ensure_memory()
    result = mem.update_memory(index, body)
    if result is not None:
        return JSONResponse(result)
    return JSONResponse({"error": "Invalid index"}, status_code=404)


@app.post("/api/memory/{index}/cherish")
async def memory_cherish(index: int):
    """Toggle cherished status."""
    mem = _ensure_memory()
    result = mem.toggle_cherish(index)
    if result is not None:
        return JSONResponse({"cherished": result})
    return JSONResponse({"error": "Invalid index"}, status_code=404)


@app.post("/api/memory/{index}/anchor")
async def memory_anchor(index: int):
    """Toggle anchor status."""
    mem = _ensure_memory()
    result = mem.toggle_anchor(index)
    if result is not None:
        return JSONResponse({"anchored": result})
    return JSONResponse({"error": "Invalid index"}, status_code=404)


@app.get("/api/memory/export")
async def memory_export(char_id: str = ""):
    """Export all memories as JSON."""
    mem = _ensure_memory(char_id=char_id or _cfg.get("active_character_id", ""))
    return JSONResponse(mem.export_all())


@app.get("/api/memory/filters")
async def memory_filters(char_id: str = ""):
    """Return available filter options (unique emotions, sources)."""
    mem = _ensure_memory(char_id=char_id or _cfg.get("active_character_id", ""))
    return JSONResponse({
        "emotions": mem.get_unique_emotions(),
        "sources": mem.get_unique_sources(),
    })


# ── Social Impressions ────────────────────────────────────────────

@app.post("/api/memory/social")
async def memory_add_social(request: Request):
    """Add a social impression about a person/entity."""
    body = await request.json()
    mem = _ensure_memory()
    result = mem.add_social(
        entity=body.get("entity", ""),
        content=body.get("content", ""),
        emotion=body.get("emotion", "neutral"),
        importance=body.get("importance", 5),
        why_saved=body.get("why_saved", ""),
    )
    mem.save()
    return JSONResponse(result)


@app.get("/api/memory/social")
async def memory_get_social(entity: str = ""):
    """Get social impressions, optionally filtered by entity."""
    mem = _ensure_memory()
    return JSONResponse(mem.get_social_impressions(entity=entity))


# ── Lessons ──────────────────────────────────────────────────────

@app.get("/api/memory/lessons")
async def memory_get_lessons():
    """Get all active lessons."""
    mem = _ensure_memory()
    return JSONResponse(mem.get_active_lessons())


@app.post("/api/memory/lessons")
async def memory_add_lesson(request: Request):
    """Add a lesson derived from experience."""
    body = await request.json()
    mem = _ensure_memory()
    result = mem.add_lesson(
        topic=body.get("topic", ""),
        context_trigger=body.get("context_trigger", ""),
        strategy=body.get("strategy", ""),
        importance=body.get("importance", 5),
    )
    mem.save()
    return JSONResponse(result)


@app.post("/api/memory/lessons/{lesson_id}/outcome")
async def memory_record_outcome(lesson_id: str, request: Request):
    """Record an attempt outcome for a lesson."""
    body = await request.json()
    mem = _ensure_memory()
    ok = mem.record_outcome(
        lesson_id=lesson_id,
        action=body.get("action", ""),
        result=body.get("result", ""),
        diagnosis=body.get("diagnosis", ""),
    )
    return JSONResponse({"ok": ok})


# ── Reminders ────────────────────────────────────────────────────

@app.post("/api/memory/reminders")
async def memory_add_reminder(request: Request):
    """Create a timed reminder."""
    body = await request.json()
    mem = _ensure_memory()
    result = mem.set_reminder(
        text=body.get("text", ""),
        hours=float(body.get("hours", 24)),
    )
    mem.save()
    return JSONResponse(result)


@app.get("/api/memory/reminders")
async def memory_get_reminders(include_fired: bool = False):
    """Get all pending reminders."""
    mem = _ensure_memory()
    return JSONResponse(mem.get_reminders(include_fired=include_fired))


# ── Visual Memory API ─────────────────────────────────────────────

@app.get("/api/memory/visual")
async def memory_get_visual():
    """List all visual memories (metadata only, no image bytes)."""
    mem = _ensure_memory()
    return JSONResponse(mem.get_visual_memories())


@app.get("/api/memory/visual/{hash_val}")
async def memory_get_visual_image(hash_val: str):
    """Serve a compressed visual memory image as WebP."""
    import re as _re2
    if not _re2.match(r'^[a-fA-F0-9]+$', hash_val):
        from fastapi.responses import Response
        return Response(status_code=400)
    mem = _ensure_memory()
    data = mem.get_visual_image(hash_val)
    if data is None:
        from fastapi.responses import Response
        return Response(status_code=404)
    from fastapi.responses import Response
    return Response(content=data, media_type="image/webp")


@app.post("/api/memory/visual")
async def memory_save_visual(request: Request):
    """Manually save an image as a visual memory.
    Body: { image_b64: str, description: str, emotion?: str, importance?: int, why_saved?: str }
    """
    import base64
    body = await request.json()
    b64 = body.get("image_b64", "")
    if not b64:
        return JSONResponse({"error": "image_b64 required"}, status_code=400)
    try:
        image_bytes = base64.b64decode(b64)
    except Exception:
        return JSONResponse({"error": "Invalid base64 data"}, status_code=400)
    mem = _ensure_memory()
    result = mem.remember_visual(
        image_bytes=image_bytes,
        description=body.get("description", ""),
        emotion=body.get("emotion", "neutral"),
        importance=int(body.get("importance", 5)),
        why_saved=body.get("why_saved", "manual upload"),
    )
    mem.save()
    return JSONResponse(result)


# ── LLM Reflect & Edit ───────────────────────────────────────────

@app.post("/api/memory/reflect")
async def memory_reflect():
    """Run LLM self-reflection on memories, store as insight."""
    mem = _ensure_memory()
    backend_name = _cfg.get("active_backend", "ollama")
    model_id = _cfg.get("active_model", "")
    backend = create_backend(backend_name, _cfg.to_dict())
    result = await mem.reflect(backend, model=model_id)
    return JSONResponse(result)


@app.post("/api/memory/edit")
async def memory_edit(request: Request):
    """LLM-driven bulk memory curation (promote/demote/forget/update)."""
    body = await request.json()
    mem = _ensure_memory()
    backend_name = _cfg.get("active_backend", "ollama")
    model_id = _cfg.get("active_model", "")
    backend = create_backend(backend_name, _cfg.to_dict())
    instruction = body.get("instruction", "")
    result = await mem.edit_memories(backend, instruction=instruction, model=model_id)
    return JSONResponse(result)


# ── Per-memory advanced ops ───────────────────────────────────────

@app.post("/api/memory/{index}/reframe")
async def memory_reframe(index: int, request: Request):
    """Properly reframe a memory's emotion (logged to audit)."""
    body = await request.json()
    mem = _ensure_memory()
    result = mem.reframe_memory(
        index=index,
        new_emotion=body.get("emotion", "neutral"),
        reason=body.get("reason", ""),
    )
    if result is not None:
        return JSONResponse(result)
    return JSONResponse({"error": "Invalid index"}, status_code=404)


@app.post("/api/memory/{index}/relive")
async def memory_relive(index: int):
    """Mental Time Travel: touch memory and shift current mood."""
    mem = _ensure_memory()
    result = mem.relive_memory(index)
    if result is not None:
        return JSONResponse(result)
    return JSONResponse({"error": "Invalid index"}, status_code=404)


# ── Yggdrasil enrichment ─────────────────────────────────────────

@app.post("/api/memory/enrich")
async def memory_enrich(request: Request):
    """Run LLM-inferred graph enrichment (Yggdrasil edges)."""
    body = await request.json()
    mem = _ensure_memory()
    result = await asyncio.to_thread(
        mem.enrich_yggdrasil, body.get("batch_size", 20)
    )
    return JSONResponse(result)


# ── Task / Project API ───────────────────────────────────────────

@app.get("/api/tasks")
async def list_tasks():
    """List all tasks (active + completed + failed)."""
    mem = _ensure_memory()
    return JSONResponse(mem.get_all_tasks())


@app.get("/api/tasks/active")
async def list_active_tasks():
    """List only active tasks."""
    mem = _ensure_memory()
    return JSONResponse(mem.get_active_tasks())


@app.post("/api/tasks")
async def create_task(request: Request):
    """Create a new task."""
    body = await request.json()
    mem = _ensure_memory()
    result = mem.start_task(
        description=body.get("description", ""),
        priority=body.get("priority", 5),
        project=body.get("project", ""),
    )
    mem.save()
    return JSONResponse(result)


@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: str, request: Request):
    """Mark a task as completed."""
    body = await request.json()
    mem = _ensure_memory()
    ok = mem.complete_task(task_id, body.get("outcome", ""))
    if ok:
        mem.save()
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "Task not found or not active"}, status_code=404)


@app.post("/api/tasks/{task_id}/fail")
async def fail_task(task_id: str, request: Request):
    """Mark a task as failed."""
    body = await request.json()
    mem = _ensure_memory()
    ok = mem.fail_task(task_id, body.get("reason", ""))
    if ok:
        mem.save()
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "Task not found or not active"}, status_code=404)


@app.get("/api/project/overview")
async def project_overview():
    """Get project overview (task counts, solutions, artifacts)."""
    mem = _ensure_memory()
    return JSONResponse(mem.get_project_overview())


@app.post("/api/project/active")
async def set_active_project(request: Request):
    """Set the active project context."""
    body = await request.json()
    mem = _ensure_memory()
    msg = mem.set_active_project(body.get("name", ""))
    return JSONResponse({"message": msg})


@app.post("/api/solutions")
async def record_solution(request: Request):
    """Record a reusable problem → solution pattern."""
    body = await request.json()
    mem = _ensure_memory()
    result = mem.record_solution(
        problem=body.get("problem", ""),
        solution=body.get("solution", ""),
        importance=body.get("importance", 5),
    )
    mem.save()
    return JSONResponse(result)


@app.post("/api/solutions/search")
async def search_solutions(request: Request):
    """Search for matching solution patterns."""
    body = await request.json()
    mem = _ensure_memory()
    results = mem.find_solutions(
        problem=body.get("problem", ""),
        top_k=body.get("top_k", 3),
    )
    return JSONResponse(results)


# ── Conversation history ──────────────────────────────────────────

_conversations_dir: Path = _cfg.profile_dir / "conversations"
_conversations_dir.mkdir(parents=True, exist_ok=True)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1.3 tokens per whitespace-delimited word."""
    return max(1, int(len(text.split()) * 1.3))


def _trim_conversation(messages: list[dict], token_budget: int) -> list[dict]:
    """Return a trimmed message list that fits within *token_budget*.

    Strategy: keep the most recent messages as-is.  If the full conversation
    exceeds the budget, compress the oldest messages into a single summary
    message so the model still has context from earlier in the chat.
    """
    if not messages:
        return messages

    # Estimate total tokens
    total = sum(_estimate_tokens(m.get("content", "")) for m in messages)
    if total <= token_budget:
        return messages  # fits fine

    # Always keep at least the last 6 messages (3 turns)
    keep_recent = min(len(messages), 6)
    recent = messages[-keep_recent:]
    recent_tokens = sum(_estimate_tokens(m.get("content", "")) for m in recent)

    # If even recent messages exceed budget, just return them (can't trim further)
    if recent_tokens >= token_budget:
        return recent

    # Compress older messages into a summary
    older = messages[:-keep_recent]
    if not older:
        return recent

    summary_parts = []
    for m in older:
        role = m.get("role", "user")
        content = m.get("content", "")
        # Truncate each old message to key info
        snippet = content[:200] + ("..." if len(content) > 200 else "")
        summary_parts.append(f"{role}: {snippet}")

    summary_text = (
        "[Earlier conversation summary — the following is a compressed "
        "record of the conversation so far. Refer to it for context but "
        "focus on the recent messages.]\n\n"
        + "\n".join(summary_parts)
    )

    # If even the summary is too large, truncate it
    summary_budget = token_budget - recent_tokens - 100
    if _estimate_tokens(summary_text) > summary_budget:
        # Keep only the last N older messages that fit
        trimmed_parts = []
        used = 0
        for part in reversed(summary_parts):
            part_tokens = _estimate_tokens(part)
            if used + part_tokens > summary_budget:
                break
            trimmed_parts.insert(0, part)
            used += part_tokens
        summary_text = (
            "[Conversation compressed — oldest messages dropped to fit "
            "context window.]\n\n" + "\n".join(trimmed_parts)
        )

    return [{"role": "system", "content": summary_text}] + recent


def _auto_save_conversation():
    """Persist the current chat to disk after each turn."""
    global _current_conv_id
    if not _conversation:
        return
    import time as _time
    if _current_conv_id is None:
        _current_conv_id = str(int(_time.time() * 1000))
    first_user = next(
        (m["content"][:60] for m in _conversation if m["role"] == "user"),
        "Untitled",
    )
    path = _conversations_dir / f"{_current_conv_id}.json"
    # Preserve original created time if file exists
    created = _time.strftime("%Y-%m-%dT%H:%M:%S")
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            created = existing.get("created", created)
        except Exception:
            pass
    data = {
        "id": _current_conv_id,
        "title": first_user,
        "created": created,
        "last_modified": _time.strftime("%Y-%m-%dT%H:%M:%S"),
        "preset": _cfg.get("active_preset", "companion"),
        "model": _cfg.get("active_model", ""),
        "agent": _cfg.get("active_character_id", ""),
        "type": "chat",
        "messages": list(_conversation),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@app.get("/api/conversations")
async def list_conversations():
    """List saved conversations (single-agent chats)."""
    convos = []
    for f in sorted(_conversations_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            convos.append({
                "id": f.stem,
                "title": data.get("title", f.stem),
                "created": data.get("created", ""),
                "last_modified": data.get("last_modified", data.get("created", "")),
                "message_count": len(data.get("messages", [])),
                "preset": data.get("preset", ""),
                "agent": data.get("agent", ""),
                "type": "chat",
            })
        except Exception:
            pass
    return JSONResponse(convos)


@app.post("/api/conversations/save")
async def save_conversation(request: Request):
    """Save current conversation."""
    global _conversation
    body = await request.json()
    if not _conversation:
        return JSONResponse({"error": "No conversation to save"}, status_code=400)

    import time as _time
    conv_id = str(int(_time.time() * 1000))
    # Auto-generate title from first user message
    first_user = next((m["content"][:60] for m in _conversation
                       if m["role"] == "user"), "Untitled")
    data = {
        "id": conv_id,
        "title": body.get("title", first_user),
        "created": _time.strftime("%Y-%m-%dT%H:%M:%S"),
        "preset": _cfg.get("active_preset", "companion"),
        "model": _cfg.get("active_model", ""),
        "messages": list(_conversation),
    }
    path = _conversations_dir / f"{conv_id}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return JSONResponse({"id": conv_id, "title": data["title"]})


@app.get("/api/conversations/{conv_id}")
async def load_conversation(conv_id: str):
    """Load a saved conversation."""
    global _conversation, _current_conv_id
    # Sanitize: only allow alphanumeric + underscore
    import re
    if not re.match(r'^[\w]+$', conv_id):
        return JSONResponse({"error": "Invalid ID"}, status_code=400)
    path = _conversations_dir / f"{conv_id}.json"
    if not path.is_file():
        return JSONResponse({"error": "Not found"}, status_code=404)
    data = json.loads(path.read_text(encoding="utf-8"))
    _conversation = data.get("messages", [])
    _current_conv_id = conv_id
    return JSONResponse(data)


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    """Delete a saved conversation."""
    import re
    if not re.match(r'^[\w]+$', conv_id):
        return JSONResponse({"error": "Invalid ID"}, status_code=400)
    path = _conversations_dir / f"{conv_id}.json"
    if path.is_file():
        path.unlink()
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "Not found"}, status_code=404)


# ── Character Management (new multi-agent system) ─────────────────────

@app.get("/api/characters")
async def list_characters():
    """List all characters."""
    chars = _characters.list_characters()
    return JSONResponse({"characters": chars})


@app.get("/api/characters/{char_id}")
async def get_character(char_id: str):
    """Load a character."""
    char = _characters.get_character(char_id)
    if not char:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse(char)


@app.post("/api/characters")
async def create_character(request: Request):
    """Create a new character."""
    body = await request.json()
    name = body.pop("name", "New Character")
    desc = body.pop("description", "")
    char = _characters.create_character(name, desc, **body)
    return JSONResponse(char)


@app.put("/api/characters/{char_id}")
async def update_character(char_id: str, request: Request):
    """Update a character."""
    body = await request.json()
    char = _characters.update_character(char_id, body)
    if not char:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse(char)


@app.delete("/api/characters/{char_id}")
async def delete_character(char_id: str):
    """Delete a character."""
    # If this was the active character, clear active_character_id
    if _cfg.get("active_character_id", "") == char_id:
        global _char_memories
        _cfg.update({"active_character_id": ""})
        _char_memories.pop(char_id, None)
    ok = _characters.delete_character(char_id)
    if ok:
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.post("/api/characters/{char_id}/activate")
async def activate_character(char_id: str):
    """Set a character as the active persona (isolated memory)."""
    char = _characters.get_character(char_id)
    if not char:
        return JSONResponse({"error": "Not found"}, status_code=404)
    global _memory, _char_memories
    _cfg.update({"active_character_id": char_id})
    # Clear global memory so next turn uses character-specific memory
    _memory = None
    return JSONResponse({"ok": True, "character": char})


@app.delete("/api/characters/activate")
async def deactivate_character():
    """Clear the active character — revert to global persona."""
    global _memory
    _cfg.update({"active_character_id": ""})
    _memory = None  # Force re-create with global settings on next turn
    return JSONResponse({"ok": True})


# ── STT endpoint ─────────────────────────────────────────────────────────────

@app.get("/api/tts/status")
async def tts_status():
    """Check TTS readiness and dependency status."""
    tts = _ensure_tts()
    return JSONResponse(tts.status)


@app.get("/api/tts/voices")
async def tts_voices():
    """Return available Edge TTS voices."""
    return JSONResponse({"voices": EDGE_VOICES})


@app.get("/api/stt/status")
async def stt_status():
    """Check STT readiness and dependency status."""
    stt = _ensure_stt()
    return JSONResponse(stt.status)


@app.post("/api/stt")
async def speech_to_text(request: Request):
    """Transcribe uploaded audio (WebM/WAV/MP3) via faster-whisper."""
    stt = _ensure_stt()
    if not stt.enabled:
        return JSONResponse({"error": "STT is disabled"}, status_code=400)
    try:
        form = await request.form()
        audio_file = form.get("audio")
        if audio_file is None:
            return JSONResponse({"error": "No audio field"}, status_code=400)
        audio_bytes: bytes = await audio_file.read()
        transcript = await asyncio.get_event_loop().run_in_executor(
            None, stt.transcribe, audio_bytes
        )
        return JSONResponse({"transcript": transcript})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/characters/import-sillytavern")
async def import_sillytavern(request: Request):
    """Import a SillyTavern character from file."""
    try:
        body = await request.json()
        file_path = body.get("file_path")
        if not file_path:
            return JSONResponse({"error": "No file path provided"}, status_code=400)
        
        char = _characters.import_sillytavern(file_path)
        return JSONResponse({
            "success": True,
            "character": char,
            "message": f"Imported '{char['name']}'",
        })
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"Import failed: {e}"}, status_code=500)


@app.post("/api/characters/bulk-import")
async def bulk_import_folder(request: Request):
    """Bulk import all SillyTavern characters from a folder."""
    try:
        body = await request.json()
        folder_path = body.get("folder_path")
        if not folder_path:
            return JSONResponse({"error": "No folder path provided"}, status_code=400)
        
        result = _characters.bulk_import_folder(folder_path)
        return JSONResponse({
            "success": True,
            **result,
        })
    except NotADirectoryError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": f"Bulk import failed: {e}"}, status_code=500)


# ── Multi-Agent Conversations (new) ────────────────────────────────────

@app.get("/api/multi-conversations")
async def list_multi_conversations():
    """List multi-agent conversations."""
    convs = _conversations.list_conversations()
    return JSONResponse({"conversations": convs})


@app.post("/api/multi-conversations")
async def create_multi_conversation(request: Request):
    """Create a new multi-agent conversation."""
    body = await request.json()
    title = body.get("title", "New Conversation")
    participants = body.get("participants", [])  # [{"type": "user|agent", "name": str, "character_id": str}]
    
    conv_meta = _conversations.create_conversation(title, participants)
    return JSONResponse(conv_meta)


@app.get("/api/multi-conversations/{conv_id}")
async def get_multi_conversation(conv_id: str):
    """Load a multi-agent conversation."""
    conv = _conversations.get_conversation(conv_id)
    if not conv:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse(conv)


@app.put("/api/multi-conversations/{conv_id}")
async def update_multi_conversation(conv_id: str, request: Request):
    """Update conversation metadata."""
    body = await request.json()
    result = _conversations.update_conversation(conv_id, body)
    if not result:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse(result)


@app.delete("/api/multi-conversations/{conv_id}")
async def delete_multi_conversation(conv_id: str):
    """Delete a multi-agent conversation."""
    ok = _conversations.delete_conversation(conv_id)
    if ok:
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.post("/api/multi-conversations/{conv_id}/message")
async def add_message_to_conversation(conv_id: str, request: Request):
    """Add a message to conversation history."""
    body = await request.json()
    speaker = body.get("speaker", "user")
    content = body.get("content", "")
    
    ok = _conversations.add_message(conv_id, {
        "speaker": speaker,
        "content": content,
    })
    
    if ok:
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "Failed to add message"}, status_code=500)


# ── Chat WebSocket ────────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def chat_ws(ws: WebSocket):
    global _conversation
    await ws.accept()

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            if msg.get("type") == "clear":
                _auto_save_conversation()  # save before clearing
                _conversation.clear()
                _current_conv_id = None
                await ws.send_json({"type": "cleared"})
                continue

            if msg.get("type") != "chat":
                continue

            user_text = msg.get("message", "").strip()
            if not user_text:
                continue

            # Image attached by user (base64 string from browser FileReader)
            image_b64: str = msg.get("image", "")
            pending_image_bytes: bytes | None = None
            if image_b64:
                import base64 as _b64
                try:
                    pending_image_bytes = _b64.b64decode(image_b64)
                except Exception:
                    image_b64 = ""
                    pending_image_bytes = None

            backend_name = msg.get("backend") or _cfg.get("active_backend", "ollama")
            model_id = msg.get("model") or _cfg.get("active_model", "")
            preset_name = msg.get("preset") or _cfg.get("active_preset", "companion")

            # ── Active agent/character overrides global settings ───────────
            active_char_id = _cfg.get("active_character_id", "")
            active_char = _characters.get_character(active_char_id) if active_char_id else None

            # Agent can override preset type and model
            if active_char:
                agent_preset = active_char.get("preset_type", "")
                if agent_preset:
                    preset_name = agent_preset
                agent_model = active_char.get("model", "")
                if agent_model:
                    model_id = agent_model

            # Build system prompt — preset-aware
            preset = get_preset(preset_name)
            parts: list[str] = []

            if active_char:
                # Character takes priority over global persona settings
                char_name = active_char.get("name", "")
                char_desc = active_char.get("description", "")
                char_personality = active_char.get("personality", "")
                char_sp = active_char.get("system_prompt", "")
                if char_name:
                    parts.append(f"Your name is {char_name}.")
                combined_desc = "\n".join(filter(None, [char_desc, char_personality]))
                if combined_desc.strip():
                    parts.append(combined_desc.strip())
                if char_sp:
                    parts.append(char_sp)
            else:
                persona_name = _cfg.get("persona_name", "")
                persona_desc = _cfg.get("persona_description", "")
                if persona_name:
                    parts.append(f"Your name is {persona_name}.")
                if persona_desc:
                    parts.append(persona_desc)

                custom_sp = _cfg.get("system_prompt", "")
                if custom_sp:
                    parts.append(custom_sp)

            if preset.get("system_prompt_suffix"):
                parts.append(preset["system_prompt_suffix"])

            # Memory context — uses character-isolated memory if active
            mem = _ensure_memory(char_id=active_char_id)
            memory_enabled = _cfg.get("memory", {}).get("enabled", True)
            if memory_enabled:
                try:
                    entity = active_char.get("name", "") if active_char else _cfg.get("persona_name", "")
                    context_block = mem.get_context_for_preset(
                        preset=preset,
                        conversation_context=user_text,
                        entity=entity,
                    )
                    if context_block:
                        parts.append("## Your Memories\n" + context_block)
                        await ws.send_json({
                            "type": "memory_context",
                            "block": context_block[:2000],
                        })
                except Exception:
                    pass

            # Dynamic mood instruction for character/companion presets
            if preset.get("emotion_weight", 0) >= 0.5 and memory_enabled:
                try:
                    mood_info = mem.get_mood()
                    mood_label = mood_info.get("mood_label", "neutral")
                    if mood_label != "neutral":
                        parts.append(
                            f"## Current Emotional State\n"
                            f"You are currently feeling **{mood_label}**. "
                            f"Let this subtly influence your tone and responses."
                        )
                    chem = mood_info.get("chemistry")
                    if chem and chem.get("description"):
                        parts.append(
                            f"## Internal State\n{chem['description']}"
                        )
                except Exception:
                    pass

            system_prompt = "\n\n".join(parts) if parts else ""

            # Add user message
            _conversation.append({"role": "user", "content": user_text})

            # ── Conversation sliding window with compression ──────
            # Estimate token budget and trim if needed
            llm_params = _cfg.get("llm_params", {})
            context_length = llm_params.get("context_length", 32768)
            max_tokens = llm_params.get("max_tokens", 2048)
            # Reserve space for system prompt + response
            sys_est = len(system_prompt.split()) * 2 if system_prompt else 0
            budget = context_length - max_tokens - sys_est - 200  # safety margin
            send_messages = _trim_conversation(list(_conversation), budget)

            # Stream response
            backend = create_backend(backend_name, _cfg.to_dict())
            full_response = []

            try:
                async for token in backend.generate(
                    messages=send_messages,
                    system_prompt=system_prompt,
                    temperature=llm_params.get("temperature", 0.7),
                    max_tokens=max_tokens,
                    model=model_id,
                    images=[image_b64] if image_b64 else None,
                ):
                    full_response.append(token)
                    await ws.send_json({"type": "token", "content": token})

                response_text = "".join(full_response)

                # ── Model-authored memory (organic) ───────────────────────
                # Parse any <remember> tags the model wrote itself.
                # Strip them from the stored/displayed response.
                # Also strip <think>/<thinking> blocks and GPT-OSS channel tags so they don't pollute history.
                clean_response = _THINK_STRIP_RE.sub("", response_text).strip()
                clean_response = _CHANNEL_ANALYSIS_BLOCK_RE.sub("", clean_response)
                clean_response = _CHANNEL_STRIP_RE.sub("", clean_response).strip()
                clean_response = _strip_remember_tags(clean_response)
                clean_response = _strip_remind_tags(clean_response)
                # Collect showimage hashes before stripping
                showimage_hashes = _parse_showimage_tags(clean_response)
                clean_response = _strip_showimage_tags(clean_response)
                # Strip task/solution tags from displayed response
                clean_response = _strip_task_tags(clean_response)
                clean_response = _strip_solution_tags(clean_response)
                clean_response = _strip_social_tags(clean_response)
                clean_response = _strip_cherish_tags(clean_response)
                remember_tags  = _parse_remember_tags(response_text) if memory_enabled else []
                remind_tags    = _parse_remind_tags(response_text) if memory_enabled else []
                task_tags      = _parse_task_tags(response_text) if memory_enabled else []
                solution_tags  = _parse_solution_tags(response_text) if memory_enabled else []
                social_tags    = _parse_social_tags(response_text) if memory_enabled else []
                cherish_tags   = _parse_cherish_tags(response_text) if memory_enabled else []

                # Parse agent code blocks & file-save tags
                code_blocks = _parse_code_blocks(response_text) if preset_name == "agent" else []
                save_file_tags = _parse_save_file_tags(response_text) if preset_name == "agent" else []

                # Store the clean response (no <remember> tags) in history
                _conversation.append({"role": "assistant", "content": clean_response})

                # Auto-save conversation after each turn
                _auto_save_conversation()

                # ── Think-model memory fallback ───────────────────────────
                # If a think model wrote no <remember> tags, look for memory
                # intent inside the think block itself.
                if not remember_tags and memory_enabled:
                    think_matches = _THINK_CONTENT_RE.findall(response_text)
                    # Also check GPT-OSS analysis channel
                    think_matches += _CHANNEL_CONTENT_RE.findall(response_text)
                    if think_matches:
                        think_text = " ".join(think_matches)
                        for m in _MEMORY_INTENT_RE.finditer(think_text):
                            content = m.group(1).strip()
                            if len(content) > 10:
                                remember_tags.append({
                                    "content": content[:500],
                                    "emotion": "neutral",
                                    "importance": 5,
                                    "why": "extracted from model thinking",
                                    "source": "conversation",
                                })

                # ── Send done immediately so UI unblocks ──────────────────
                await ws.send_json({
                    "type": "done",
                    "memory_saved": len([t for t in remember_tags if isinstance(t, dict)]),
                    "mood": "",
                    "emotion": "",
                    "character": active_char.get("name", "") if active_char else "",
                })

                # Send show_image messages for any <showimage> the model wrote
                for h in showimage_hashes:
                    await ws.send_json({"type": "show_image", "hash": h})

                # ── Background: memory ops + TTS (non-blocking) ───────────
                _bg_remember_tags = list(remember_tags)
                _bg_remind_tags = list(remind_tags)
                _bg_task_tags = list(task_tags)
                _bg_solution_tags = list(solution_tags)
                _bg_social_tags = list(social_tags)
                _bg_cherish_tags = list(cherish_tags)
                _bg_code_blocks = list(code_blocks)
                _bg_save_files = list(save_file_tags)
                _bg_user_text = user_text
                _bg_clean = clean_response
                _bg_preset = dict(preset)
                _bg_pending_img = pending_image_bytes
                _bg_char = dict(active_char) if active_char else None
                _bg_ws = ws

                async def _bg_memory_ops():
                    """Run all memory operations in background so UI stays responsive."""
                    try:
                        if not memory_enabled:
                            return
                        # Save each model-authored memory
                        for entry in _bg_remember_tags:
                            if not isinstance(entry, dict):
                                continue
                            if (entry.get("source") == "visual"
                                    and _bg_pending_img is not None):
                                mem.remember_visual(
                                    image_bytes=_bg_pending_img,
                                    description=entry["content"],
                                    emotion=entry["emotion"],
                                    importance=entry["importance"],
                                    why_saved=entry["why"],
                                )
                            else:
                                result = mem.remember(
                                    content=entry["content"],
                                    emotion=entry["emotion"],
                                    importance=entry["importance"],
                                    source=entry.get("source", "conversation"),
                                    why_saved=entry["why"],
                                )
                                # Apply cherish/anchor if the model requested it
                                if result and (entry.get("cherish") or entry.get("anchor")):
                                    try:
                                        idx = len(mem._mimir._reflections) - 1
                                        if entry.get("cherish"):
                                            mem.toggle_cherish(idx)
                                        if entry.get("anchor"):
                                            mem.toggle_anchor(idx)
                                    except Exception:
                                        pass

                        # Process retroactive cherish/anchor on existing memories
                        for ct in _bg_cherish_tags:
                            try:
                                matches = mem._mimir.recall(ct["query"], top_k=1)
                                if matches:
                                    # Find the index of this memory
                                    target = matches[0]
                                    for idx, m in enumerate(mem._mimir._reflections):
                                        if m is target:
                                            if not getattr(m, '_cherished', False):
                                                mem.toggle_cherish(idx)
                                            if ct.get("anchor") and not getattr(m, '_anchor', False):
                                                mem.toggle_anchor(idx)
                                            break
                            except Exception:
                                pass

                        # Save social impressions
                        for si in _bg_social_tags:
                            try:
                                mem.add_social(
                                    entity=si["entity"],
                                    content=si["content"],
                                    emotion=si["emotion"],
                                    importance=si["importance"],
                                )
                            except Exception:
                                pass

                        # Save model-authored reminders
                        for r in _bg_remind_tags:
                            mem.set_reminder(text=r["text"], hours=r["hours"])

                        # Process model-authored task tags (Agent/Assistant)
                        for t in _bg_task_tags:
                            try:
                                if t["action"] == "start":
                                    result = mem.start_task(
                                        description=t["content"],
                                        priority=t["priority"],
                                        project=t.get("project", ""),
                                    )
                                    await _bg_ws.send_json({
                                        "type": "task_created",
                                        "task_id": result["task_id"],
                                        "description": result["description"],
                                    })
                                elif t["action"] == "complete" and t.get("id"):
                                    mem.complete_task(t["id"], t["content"])
                                    await _bg_ws.send_json({
                                        "type": "task_completed",
                                        "task_id": t["id"],
                                    })
                                elif t["action"] == "fail" and t.get("id"):
                                    mem.fail_task(t["id"], t["content"])
                                    await _bg_ws.send_json({
                                        "type": "task_failed",
                                        "task_id": t["id"],
                                    })
                            except Exception:
                                pass

                        # Process model-authored solution tags (Agent/Assistant)
                        for s in _bg_solution_tags:
                            try:
                                if s["problem"] and s["content"]:
                                    mem.record_solution(
                                        problem=s["problem"],
                                        solution=s["content"],
                                        importance=s["importance"],
                                    )
                                    await _bg_ws.send_json({
                                        "type": "solution_recorded",
                                        "problem": s["problem"][:100],
                                    })
                            except Exception:
                                pass

                        # ── Agent code execution & file saving ────────────
                        agent_dir = _get_agent_files_dir()

                        # Save files the model wrote with <save_file> tags
                        for sf in _bg_save_files:
                            try:
                                # Sanitize path — only allow relative paths inside agent_files
                                rel = sf["path"].replace("\\", "/").lstrip("/")
                                # Block path traversal
                                if ".." in rel:
                                    continue
                                target = agent_dir / rel
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_text(sf["content"], encoding="utf-8")
                                await _bg_ws.send_json({
                                    "type": "agent_file_saved",
                                    "path": str(target),
                                    "filename": rel,
                                })
                            except Exception:
                                pass

                        # Execute Python code blocks in agent mode
                        for cb in _bg_code_blocks:
                            try:
                                from playground.tool_runner import run_tool
                                # Agent auto-grants code_execution + agent_files path
                                agent_perms = {
                                    "code_execution": True,
                                    "file_access": True,
                                    "allowed_paths": [str(agent_dir)],
                                }
                                result = await asyncio.to_thread(
                                    run_tool, "run_code",
                                    {"code": cb["code"], "language": cb["language"]},
                                    agent_perms,
                                )
                                await _bg_ws.send_json({
                                    "type": "agent_code_result",
                                    "language": cb["language"],
                                    "stdout": result.get("stdout", ""),
                                    "stderr": result.get("stderr", ""),
                                    "error": result.get("error", ""),
                                    "exit_code": result.get("exit_code"),
                                })
                            except Exception as e:
                                await _bg_ws.send_json({
                                    "type": "agent_code_result",
                                    "error": str(e),
                                })

                        # Heuristic reminder fallback — only if model wrote no <remind> tags
                        if not _bg_remind_tags:
                            heuristic_reminders = _heuristic_reminder_from_user(_bg_user_text)
                            for r in heuristic_reminders:
                                mem.set_reminder(text=r["text"], hours=r["hours"])
                            if heuristic_reminders:
                                await _bg_ws.send_json({
                                    "type": "reminder_set",
                                    "text": heuristic_reminders[0]["text"],
                                    "hours": heuristic_reminders[0]["hours"],
                                })

                        # Heuristic fallback — task-priority presets only
                        if not _bg_remember_tags and _bg_preset.get("task_priority", False):
                            from playground.memory_manager import (
                                detect_emotions, estimate_importance
                            )
                            combined = _bg_user_text + " " + _bg_clean
                            emotions_fb = detect_emotions(combined)
                            importance_fb = estimate_importance(_bg_user_text, _bg_clean)
                            task_words = {"task", "goal", "deadline", "reminder",
                                          "lesson", "error", "failed", "fixed",
                                          "todo", "action", "need to", "must"}
                            if any(w in combined.lower() for w in task_words):
                                mem.remember(
                                    content=(
                                        f"User: {_bg_user_text[:200]}\n"
                                        f"Response: {_bg_clean[:300]}"
                                    ),
                                    emotion=emotions_fb[0] if emotions_fb else "neutral",
                                    importance=importance_fb,
                                    source="conversation",
                                    why_saved="auto-captured task/goal signal",
                                )

                        # process_turn handles mood/chemistry/huginn/volva/consolidation
                        turn_info = mem.process_turn(
                            _bg_user_text, _bg_clean, _bg_preset, curation=None,
                            skip_save=True,
                        )

                        # Send a mood update so the UI can show it
                        # Send mood + chemistry update to frontend
                        mood_label = turn_info.get("mood_label", "")
                        emotion = turn_info.get("emotion", "")
                        mood_info = mem.get_mood()
                        chem = mood_info.get("chemistry")
                        chem_levels = chem.get("levels", {}) if chem else {}
                        try:
                            await _bg_ws.send_json({
                                "type": "mood_update",
                                "mood": mood_label or "neutral",
                                "emotion": emotion,
                                "chemistry": chem_levels,
                            })
                        except Exception:
                            pass

                        # Background: periodic LLM reflect / edit_memories
                        turn_count = mem._turn_count
                        if turn_count > 0 and turn_count % 20 == 0:
                            async def _bg_reflect():
                                try:
                                    await mem.reflect(backend, model=model_id)
                                except Exception:
                                    pass
                            asyncio.create_task(_bg_reflect())

                        if turn_count > 0 and turn_count % 40 == 0:
                            async def _bg_edit():
                                try:
                                    await mem.edit_memories(backend, model=model_id)
                                except Exception:
                                    pass
                            asyncio.create_task(_bg_edit())

                        # Track mood & chemistry history (persisted)
                        global _mood_history, _chemistry_history
                        try:
                            import time as _t
                            _mood_history.append({
                                "timestamp": _t.time(),
                                "mood_label": mood_info.get("mood_label", ""),
                                "pad": mood_info.get("mood_pad", [0,0,0]),
                                "emotion": emotion,
                            })
                            if chem_levels:
                                _chemistry_history.append({
                                    "timestamp": _t.time(),
                                    "levels": dict(chem_levels),
                                    "description": chem.get("description", "") if chem else "",
                                })
                            _save_viz_history()
                        except Exception:
                            pass
                    except Exception:
                        import traceback
                        traceback.print_exc()

                asyncio.create_task(_bg_memory_ops())

                # ── TTS: generate audio for the response (async background) ──
                tts = _ensure_tts()
                if tts.enabled and clean_response.strip():
                    voice_prompt = active_char.get("voice_prompt", "") if active_char else ""

                    async def _send_tts(resp_text: str, vp: str, _ws: WebSocket):
                        try:
                            audio = await asyncio.get_event_loop().run_in_executor(
                                None, tts.generate_audio, resp_text, vp
                            )
                            if audio:
                                import base64 as _b64
                                # Edge TTS returns MP3, Maya returns WAV
                                fmt = "mp3" if getattr(tts, 'voice', None) else "wav"
                                await _ws.send_json({
                                    "type": "tts_audio",
                                    "audio_b64": _b64.b64encode(audio).decode(),
                                    "format": fmt,
                                })
                            else:
                                print(f"[TTS] generate_audio returned empty bytes")
                                # Tell frontend to use browser fallback
                                error = tts._last_error or "No audio generated (GPU/model issue)"
                                await _ws.send_json({
                                    "type": "tts_fallback",
                                    "text": resp_text,
                                    "error": error,
                                })
                        except Exception as e:
                            print(f"[TTS] Error: {e}")
                            await _ws.send_json({
                                "type": "tts_fallback",
                                "text": resp_text,
                                "error": str(e),
                            })

                    asyncio.create_task(_send_tts(clean_response, voice_prompt, ws))
                elif tts.enabled and not clean_response.strip():
                    pass  # nothing to speak
                elif not tts.enabled:
                    pass  # TTS disabled

            except Exception as e:
                await ws.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ── Multi-Agent WebSocket ─────────────────────────────────────────

@app.websocket("/ws/multi-chat/{conv_id}")
async def multi_chat_ws(ws: WebSocket, conv_id: str):
    """WebSocket for multi-agent conversations with streaming responses."""
    await ws.accept()

    # Load conversation
    conv_data = _conversations.get_conversation(conv_id)
    if not conv_data:
        await ws.send_json({"type": "error", "message": "Conversation not found"})
        await ws.close()
        return

    conv_meta = conv_data["meta"]
    agents = [p for p in conv_meta.get("participants", []) if p.get("type") == "agent"]
    messages = conv_data.get("messages", [])

    # Convert saved messages to chat format
    chat_history = [
        {"role": msg.get("speaker", "user").lower() if msg.get("speaker") != "You" else "user",
         "content": msg.get("content", "")}
        for msg in messages
    ]

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            if msg.get("type") == "settings":
                # Live update conversation settings
                new_settings = msg.get("data", {})
                if "settings" not in conv_meta:
                    conv_meta["settings"] = {}
                conv_meta["settings"].update(new_settings)
                # Reset sequential index if turn order changed
                if "turn_order" in new_settings:
                    conv_meta["_seq_index"] = 0
                # Persist to disk
                _conversations.update_conversation(conv_id, {"settings": conv_meta["settings"]})
                await ws.send_json({"type": "settings_saved", "settings": conv_meta["settings"]})
                continue

            if msg.get("type") == "message":
                user_text = msg.get("content", "").strip()
                chat_history.append({"role": "user", "content": user_text})
                await ws.send_json({
                    "type": "user_message",
                    "speaker": "You",
                    "content": user_text,
                })

                # Save to conversation
                _conversations.add_message(conv_id, {
                    "speaker": "You",
                    "content": user_text,
                })

                # Get agents to respond (based on turn order setting)
                turn_order = conv_meta.get("settings", {}).get("turn_order", conv_meta.get("turn_order", "user_addresses"))
                max_per_round = int(conv_meta.get("settings", {}).get("max_per_round", 3))
                responding_agents = agents  # default

                if turn_order == "user_addresses":
                    mentioned = [a for a in agents if a["name"].lower() in user_text.lower()]
                    responding_agents = mentioned if mentioned else agents[:1]
                elif turn_order == "sequential":
                    # Round-robin: use seq_index tracked in conv_meta
                    if "_seq_index" not in conv_meta:
                        conv_meta["_seq_index"] = 0
                    idx = conv_meta["_seq_index"] % len(agents)
                    responding_agents = [agents[idx]]
                    conv_meta["_seq_index"] = idx + 1
                elif turn_order == "all_respond":
                    responding_agents = agents[:max_per_round]

                # Stream responses from each agent
                for agent in responding_agents:
                    char_id = agent.get("character_id")
                    char = _characters.get_character(char_id) if char_id else None
                    agent_name = agent.get("name", "Agent")

                    # Build system prompt from character
                    parts = [f"You are {agent_name}."]
                    if char:
                        if char.get("description"):
                            parts.append(char["description"])
                        if char.get("personality"):
                            parts.append(f"Personality: {char['personality']}")
                        if char.get("system_prompt"):
                            parts.append(char["system_prompt"])

                    system_prompt = "\n\n".join(parts)

                    # Get backend for this agent (or default)
                    backend_name = agent.get("backend", _cfg.get("active_backend", "ollama"))
                    model_id = agent.get("model", _cfg.get("active_model", ""))

                    backend = create_backend(backend_name, _cfg.to_dict())
                    llm_params = _cfg.get("llm_params", {})
                    full_response = []

                    try:
                        async for token in backend.generate(
                            messages=list(chat_history),
                            system_prompt=system_prompt,
                            temperature=llm_params.get("temperature", 0.7),
                            max_tokens=llm_params.get("max_tokens", 2048),
                            model=model_id,
                        ):
                            full_response.append(token)
                            await ws.send_json({
                                "type": "token",
                                "speaker": agent_name,
                                "content": token,
                            })

                        response_text = "".join(full_response)
                        chat_history.append({"role": "assistant", "content": response_text})

                        # Save to conversation
                        _conversations.add_message(conv_id, {
                            "speaker": agent_name,
                            "content": response_text,
                        })

                        await ws.send_json({
                            "type": "agent_done",
                            "speaker": agent_name,
                            "content": response_text,
                        })

                    except Exception as e:
                        await ws.send_json({
                            "type": "error",
                            "speaker": agent_name,
                            "message": str(e),
                        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except:
            pass


# -- Visualization APIs ---------------------------------------------

@app.get("/api/visualization/mood-history")
async def get_mood_history():
    """Return mood history for timeline visualization."""
    return JSONResponse({"history": _mood_history})


@app.get("/api/visualization/chemistry-history")
async def get_chemistry_history():
    """Return chemistry history for timeline visualization."""
    return JSONResponse({"history": _chemistry_history})


@app.get("/api/visualization/yggdrasil")
async def get_yggdrasil():
    """Return knowledge graph data (Yggdrasil) for 3D visualization."""
    mem = _ensure_memory()
    return JSONResponse(mem.get_graph())


@app.get("/api/visualization/landscape")
async def get_landscape():
    """Return memory landscape data for 3D scatterplot."""
    mem = _ensure_memory()
    graph = mem.get_graph()
    
    # Process nodes for 3D coordinates
    nodes_3d = []
    for i, node in enumerate(graph.get("nodes", [])):
        nodes_3d.append({
            "id": node["id"],
            "content": node["content"],
            "x": node["vividness"],  # Vividness on X
            "y": node["importance"],  # Importance on Y
            "z": node["stability"],   # Stability on Z
            "color": node.get("source", "episodic"),
            "size": node["vividness"],
            "emotion": node["emotion"],
            "timestamp": node["timestamp"],
        })
    
    return JSONResponse({"nodes": nodes_3d, "total": len(nodes_3d)})


@app.get("/api/visualization/cherished")
async def get_cherished_memories():
    """Return cherished memories for wall visualization."""
    mem = _ensure_memory()
    graph = mem.get_graph()
    
    # Filter only cherished memories
    cherished = [
        {
            "id": node["id"],
            "content": node["content"],
            "emotion": node["emotion"],
            "vividness": node["vividness"],
            "importance": node["importance"],
            "timestamp": node["timestamp"],
            "source": node["source"],
        }
        for node in graph.get("nodes", [])
        if node.get("is_cherished")
    ]
    
    return JSONResponse({"memories": cherished, "total": len(cherished)})
