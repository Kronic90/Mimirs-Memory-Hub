"""In-app updates and bringing data over from another copy of the hub.

Two kinds of install:
  * git clone  -> update with `git pull --ff-only` on the current branch.
  * zip / portable (or a downloaded source zip) -> download the latest
    GitHub release's source, replace only the app's code, keep the rest.

Never touched by an update: playground_data/ (memories, characters,
conversations, settings, models) and python_embeded/. Every code item
that gets replaced is backed up first to _update_backups/.

Bringing data from another copy is staged: the old copy's playground_data
is copied to _pending_data_import/ and swapped in on the next start, before
any memory is loaded -- so the running server can't overwrite it with its
own in-memory state on its way out.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from playground.version import __version__

REPO = "Kronic90/Mimirs-Memory-Hub"
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "playground_data"
BACKUP_DIR = ROOT / "_update_backups"
PENDING_IMPORT = ROOT / "_pending_data_import"
INCOMING_BACKUP = ROOT / "_incoming_setup_file"
EXPORT_DIR = ROOT / "_exports"
_UA = {"User-Agent": "Mimirs-Memory-Hub-updater",
       "Accept": "application/vnd.github+json"}

# Code that an update replaces. Everything else in the install is left alone.
_CODE_DIRS = ("playground", "vividmimir", "mimir_modular")
_CODE_FILES = ("requirements.txt", "run.bat", "run.sh", "start.command",
               "install.bat", "README.md", "CHANGELOG.md", "Mimir.py")
_NEVER = {"playground_data", "python_embeded", ".git", "_update_backups",
          "_pending_data_import"}

_lock = threading.Lock()


# ── helpers ──────────────────────────────────────────────────────────

def parse_version(v: str) -> tuple[int, ...]:
    import re
    nums = re.findall(r"\d+", (v or "").split("(")[0])
    return tuple(int(n) for n in nums[:4]) or (0,)


def install_kind() -> str:
    if (ROOT / ".git").exists() and shutil.which("git"):
        return "git"
    if (ROOT / "python_embeded").is_dir():
        return "portable"
    return "source"


def _git(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _ssl_context():
    """The OS certificate store plus certifi's bundle. httpx alone only
    trusts certifi, which fails behind antivirus/corporate HTTPS scanning
    (Norton, Avast, Zscaler...) whose root lives only in the OS store."""
    import ssl
    ctx = ssl.create_default_context()  # loads the Windows/macOS/OpenSSL store
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


def _latest_release() -> dict:
    import httpx
    r = httpx.get(f"https://api.github.com/repos/{REPO}/releases/latest",
                  headers=_UA, timeout=20, follow_redirects=True,
                  verify=_ssl_context())
    r.raise_for_status()
    return r.json()


# ── check ────────────────────────────────────────────────────────────

def check() -> dict:
    kind = install_kind()
    out: dict = {"current": __version__, "kind": kind,
                 "update_available": False}
    try:
        rel = _latest_release()
        out.update({
            "latest": (rel.get("tag_name") or "").lstrip("vV"),
            "latest_name": rel.get("name") or rel.get("tag_name") or "",
            "notes": (rel.get("body") or "")[:6000],
            "url": rel.get("html_url", ""),
            "published": rel.get("published_at", ""),
        })
    except Exception as e:
        out["release_error"] = f"Couldn't reach GitHub: {e}"

    if kind == "git":
        fetch = _git("fetch", "--quiet")
        branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        upstream = _git("rev-parse", "--abbrev-ref", "@{u}")
        dirty = _git("status", "--porcelain", "--untracked-files=no").stdout.strip()
        info: dict = {"branch": branch, "dirty": bool(dirty)}
        if upstream.returncode != 0:
            info["error"] = "This branch doesn't track a remote branch, so there's nothing to pull from."
        elif fetch.returncode != 0:
            info["error"] = "git fetch failed: " + (fetch.stderr.strip() or "unknown error")
        else:
            behind = _git("rev-list", "--count", "HEAD..@{u}").stdout.strip() or "0"
            info["behind"] = int(behind)
            info["upstream"] = upstream.stdout.strip()
            out["update_available"] = int(behind) > 0
        out["git"] = info
    elif out.get("latest"):
        out["update_available"] = parse_version(out["latest"]) > parse_version(__version__)
    return out


# ── apply ────────────────────────────────────────────────────────────

def _pip_install() -> dict:
    req = ROOT / "requirements.txt"
    if not req.is_file():
        return {"ok": True, "output": "no requirements.txt"}
    try:
        p = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req),
             "--disable-pip-version-check", "--quiet"],
            cwd=ROOT, capture_output=True, text=True, timeout=1800,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        tail = (p.stdout + p.stderr).strip()[-1500:]
        return {"ok": p.returncode == 0, "output": tail}
    except Exception as e:
        return {"ok": False, "output": str(e)}


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        if dest != target and dest not in target.parents:
            raise ValueError(f"Unsafe path in update archive: {member.filename}")
    zf.extractall(dest)


def _replace_dir(new: Path, old: Path) -> None:
    """Make `old` match `new`: copy everything over, then remove files the
    new version no longer has (compiled caches left alone)."""
    shutil.copytree(new, old, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    new_files = {p.relative_to(new) for p in new.rglob("*") if p.is_file()}
    for p in sorted(old.rglob("*"), reverse=True):
        rel = p.relative_to(old)
        if "__pycache__" in rel.parts:
            continue
        if p.is_file() and rel not in new_files:
            try:
                p.unlink()
            except OSError:
                pass


def _apply_release(force: bool = False) -> dict:
    import httpx
    rel = _latest_release()
    latest = (rel.get("tag_name") or "").lstrip("vV")
    if not force and parse_version(latest) <= parse_version(__version__):
        return {"ok": False, "error": f"You're already on v{__version__} (latest release is v{latest})."}
    url = rel.get("zipball_url")
    if not url:
        return {"ok": False, "error": "The latest release has no source download."}

    tmp = Path(tempfile.mkdtemp(prefix="mimir_update_", dir=ROOT))
    try:
        zpath = tmp / "release.zip"
        with httpx.stream("GET", url, headers=_UA, timeout=120,
                          follow_redirects=True, verify=_ssl_context()) as r:
            r.raise_for_status()
            with open(zpath, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
        with zipfile.ZipFile(zpath) as zf:
            _safe_extract(zf, tmp / "x")
        tops = [p for p in (tmp / "x").iterdir() if p.is_dir()]
        src = tops[0] if len(tops) == 1 else tmp / "x"
        if not (src / "playground" / "server.py").is_file():
            return {"ok": False, "error": "The downloaded release doesn't look like Mimir's Memory Hub - nothing was changed."}

        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = BACKUP_DIR / f"v{__version__}-{stamp}"
        backup.mkdir(parents=True, exist_ok=True)
        replaced = []
        for name in _CODE_DIRS + _CODE_FILES:
            if name in _NEVER:
                continue
            new, cur = src / name, ROOT / name
            if not new.exists():
                continue
            # Only bring in optional extras this install already has
            if name in ("mimir_modular", "install.bat", "CHANGELOG.md") and not cur.exists():
                continue
            if cur.exists():
                if cur.is_dir():
                    shutil.copytree(cur, backup / name,
                                    ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    shutil.copy2(cur, backup / name)
            if new.is_dir():
                cur.mkdir(exist_ok=True)
                _replace_dir(new, cur)
            else:
                shutil.copy2(new, cur)
            replaced.append(name)
        pip = _pip_install()
        return {"ok": True, "version": latest, "replaced": replaced,
                "backup": str(backup), "pip": pip}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _apply_git() -> dict:
    dirty = _git("status", "--porcelain", "--untracked-files=no").stdout.strip()
    if dirty:
        return {"ok": False, "error": (
            "You have local changes to the hub's code, so git can't update "
            "safely. Commit or stash them (git stash), then try again. "
            "Your memories and characters aren't affected either way.")}
    before = _git("rev-parse", "--short", "HEAD").stdout.strip()
    pull = _git("pull", "--ff-only", timeout=300)
    if pull.returncode != 0:
        return {"ok": False, "error": "git pull failed: " + (pull.stderr.strip() or pull.stdout.strip())}
    after = _git("rev-parse", "--short", "HEAD").stdout.strip()
    pip = _pip_install() if before != after else {"ok": True, "output": ""}
    return {"ok": True, "from": before, "to": after,
            "output": pull.stdout.strip()[-1500:], "pip": pip}


def apply(force: bool = False) -> dict:
    if not _lock.acquire(blocking=False):
        return {"ok": False, "error": "An update is already running."}
    try:
        if install_kind() == "git":
            return _apply_git()
        return _apply_release(force=force)
    except Exception as e:
        return {"ok": False, "error": f"Update failed: {e}. Nothing in playground_data was touched."}
    finally:
        _lock.release()


# ── restart ──────────────────────────────────────────────────────────

def restart(delay: float = 1.0) -> None:
    """Start a fresh hub process, then exit this one so it frees the port."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["MIMIR_NO_BROWSER"] = "1"  # the open page reconnects by itself
    code = ("import time, runpy; time.sleep(3); "
            "runpy.run_module('playground', run_name='__main__', alter_sys=True)")
    kwargs: dict = {"cwd": str(ROOT), "env": env}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    else:
        log = open(DATA_DIR / "hub_restart.log", "ab")
        kwargs.update(start_new_session=True, stdout=log, stderr=log)
    subprocess.Popen([sys.executable, "-c", code], **kwargs)
    threading.Timer(delay, lambda: os._exit(0)).start()


# ── bring data over from another copy ────────────────────────────────

def _find_data_dir(path: str) -> Path | None:
    p = Path(path.strip().strip('"')).expanduser()
    for cand in (p / "playground_data", p):
        if cand.is_dir() and ((cand / "settings.json").is_file()
                              or (cand / "profiles").is_dir()
                              or (cand / "characters").is_dir()):
            return cand
    return None


def _summarize(d: Path) -> dict:
    """Counts, plus the date of the newest memory or chat (so an import
    can warn before replacing newer data with older data)."""
    import json
    chars = len(list((d / "characters").glob("*.json"))) if (d / "characters").is_dir() else 0
    conv_files = list(d.glob("profiles/*/conversations/*.json"))
    mems = 0
    newest = ""
    for f in d.glob("profiles/**/reflections.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("reflections", [])
            mems += len(items)
            for m in items:
                ts = str(m.get("timestamp", ""))[:19] if isinstance(m, dict) else ""
                if ts > newest:
                    newest = ts
        except Exception:
            pass
    for f in conv_files:
        try:
            ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime))
            if ts > newest:
                newest = ts
        except OSError:
            pass
    return {"characters": chars, "conversations": len(conv_files), "memories": mems,
            "newest": newest}


def _model_refs_inside(d: Path) -> int:
    """How many settings/characters point at model files inside d/models
    (those keep working only while that old folder still exists)."""
    root = str((d / "models").resolve()).lower()
    hits = 0
    files = [d / "settings.json"] + list((d / "characters").glob("*.json"))
    for f in files:
        try:
            if root in f.read_text(encoding="utf-8").replace("\\\\", "\\").lower():
                hits += 1
        except OSError:
            pass
    return hits


def preview_import(path: str) -> dict:
    src = _find_data_dir(path)
    if src is None:
        return {"ok": False, "error": "No hub data found there. Pick the folder of the older copy (the one containing playground_data)."}
    if src.resolve() == DATA_DIR.resolve():
        return {"ok": False, "error": "That's this copy's own data."}
    models = src / "models"
    msize = sum(f.stat().st_size for f in models.rglob("*") if f.is_file()) if models.is_dir() else 0
    return {"ok": True, "source": str(src), **_summarize(src),
            "models_gb": round(msize / 1e9, 2),
            "model_refs": _model_refs_inside(src),
            "current": _summarize(DATA_DIR) if DATA_DIR.is_dir() else None}


# ── setup files: your whole setup in one zip ─────────────────────────

_EXPORT_SKIP = {"models", "backend_backups", "__pycache__"}


def _strip_api_keys(settings_text: str) -> str:
    import json
    data = json.loads(settings_text)
    for cfg in (data.get("backends") or {}).values():
        if isinstance(cfg, dict) and cfg.get("api_key"):
            cfg["api_key"] = ""
    return json.dumps(data, indent=2, ensure_ascii=False)


def export_data(include_keys: bool = False) -> Path:
    """Zip this copy's data (memories, characters, chats, settings, your
    presets -- not the big model files) into one file you can keep or load
    into any other copy."""
    import json
    from playground.version import __version__
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    for old in EXPORT_DIR.glob("*.zip"):          # keep just the newest
        old.unlink(missing_ok=True)
    out = EXPORT_DIR / f"mimir-setup-{time.strftime('%Y%m%d-%H%M')}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in DATA_DIR.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(DATA_DIR)
            if rel.parts[0] in _EXPORT_SKIP or "__pycache__" in rel.parts or f.suffix == ".log":
                continue
            arc = "playground_data/" + rel.as_posix()
            if rel.as_posix() == "settings.json" and not include_keys:
                try:
                    z.writestr(arc, _strip_api_keys(f.read_text(encoding="utf-8")))
                    continue
                except Exception:
                    pass
            z.write(f, arc)
        z.writestr("mimir-setup.json", json.dumps({
            "app": "Mimir's Memory Hub", "version": __version__,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "api_keys_included": include_keys}))
    return out


def receive_backup(data: bytes) -> dict:
    """Unpack an uploaded setup file next to the hub and preview it. It is
    only applied after you confirm (then it's staged like Bring data)."""
    import io, json
    if INCOMING_BACKUP.exists():
        shutil.rmtree(INCOMING_BACKUP, ignore_errors=True)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return {"ok": False, "error": "That isn't a setup file (it should be a .zip made by Export)."}
    for m in z.infolist():
        parts = Path(m.filename).parts
        if Path(m.filename).is_absolute() or ".." in parts or (parts and ":" in parts[0]):
            return {"ok": False, "error": "That file has unsafe paths in it, so it wasn't opened."}
    INCOMING_BACKUP.mkdir(parents=True)
    z.extractall(INCOMING_BACKUP)
    src = INCOMING_BACKUP / "playground_data"
    if not src.is_dir():
        src = INCOMING_BACKUP
    meta = {}
    try:
        meta = json.loads((INCOMING_BACKUP / "mimir-setup.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    # A file saved without API keys keeps the keys this copy already has
    if (not meta.get("api_keys_included") and (src / "settings.json").is_file()
            and (DATA_DIR / "settings.json").is_file()):
        try:
            new = json.loads((src / "settings.json").read_text(encoding="utf-8"))
            cur = json.loads((DATA_DIR / "settings.json").read_text(encoding="utf-8"))
            for name, cfg in (cur.get("backends") or {}).items():
                key = (cfg or {}).get("api_key") if isinstance(cfg, dict) else ""
                if key:
                    nb = new.setdefault("backends", {}).setdefault(name, {})
                    if isinstance(nb, dict) and not nb.get("api_key"):
                        nb["api_key"] = key
            (src / "settings.json").write_text(json.dumps(new, indent=2, ensure_ascii=False),
                                               encoding="utf-8")
        except Exception:
            pass
    info = preview_import(str(src))
    if info.get("ok"):
        info["file_version"] = meta.get("version", "")
        info["file_created"] = meta.get("created", "")
    return info


def list_backups() -> list[dict]:
    """Earlier copies of this hub's data kept by imports and updates,
    newest first, each with its counts so it can be restored."""
    if not BACKUP_DIR.is_dir():
        return []
    out = []
    for d in sorted(BACKUP_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if d.is_dir() and _find_data_dir(str(d)) == d:
            out.append({"name": d.name, "path": str(d),
                        "saved": time.strftime("%Y-%m-%d %H:%M", time.localtime(d.stat().st_mtime)),
                        **_summarize(d)})
    return out


def stage_import(path: str, include_models: bool = False) -> dict:
    info = preview_import(path)
    if not info.get("ok"):
        return info
    src = Path(info["source"])
    if PENDING_IMPORT.exists():
        shutil.rmtree(PENDING_IMPORT, ignore_errors=True)
    skip = set() if include_models else {"models"}

    def _ignore(d, names):
        if Path(d).resolve() == src.resolve():
            return [n for n in names if n in skip]
        return [n for n in names if n == "__pycache__"]
    shutil.copytree(src, PENDING_IMPORT, ignore=_ignore)
    if INCOMING_BACKUP.exists() and INCOMING_BACKUP.resolve() in (src.resolve(), *src.resolve().parents):
        shutil.rmtree(INCOMING_BACKUP, ignore_errors=True)
    if not include_models and (DATA_DIR / "models").is_dir():
        # keep this copy's own downloaded models
        (PENDING_IMPORT / ".keep_current_models").write_text("1")
    return {**info, "staged": True}


def apply_pending_data_import() -> str | None:
    """Called at startup before anything loads memory. Swaps the staged
    data in, keeping the data it replaces as a backup."""
    if not PENDING_IMPORT.is_dir():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"playground_data-before-import-{stamp}"
    keep_models = (PENDING_IMPORT / ".keep_current_models").exists()
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        if DATA_DIR.exists():
            shutil.move(str(DATA_DIR), str(backup))
        shutil.move(str(PENDING_IMPORT), str(DATA_DIR))
        (DATA_DIR / ".keep_current_models").unlink(missing_ok=True)
        if keep_models and (backup / "models").is_dir() and not (DATA_DIR / "models").exists():
            shutil.move(str(backup / "models"), str(DATA_DIR / "models"))
        (DATA_DIR / "models").mkdir(exist_ok=True)
        return f"Brought in data from the older copy (previous data kept in {backup})"
    except Exception as e:
        return f"Data import failed ({e}); previous data is in {backup}"
