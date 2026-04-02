"""Model discovery and download management.

Searches HuggingFace for GGUF models, scans local drives, and downloads models.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import AsyncGenerator

import httpx

HF_API = "https://huggingface.co/api"


# ── HuggingFace GGUF search ──────────────────────────────────────────

async def search_huggingface(query: str = "", limit: int = 20) -> list[dict]:
    """Search HuggingFace for GGUF model repos."""
    params = {
        "search": query or "GGUF",
        "filter": "gguf",
        "sort": "downloads",
        "direction": "-1",
        "limit": limit,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{HF_API}/models", params=params)
        resp.raise_for_status()
        models = resp.json()

    results = []
    for m in models:
        results.append({
            "repo_id": m.get("id", ""),
            "name": m.get("id", "").split("/")[-1],
            "author": m.get("id", "").split("/")[0] if "/" in m.get("id", "") else "",
            "downloads": m.get("downloads", 0),
            "likes": m.get("likes", 0),
            "tags": m.get("tags", []),
            "last_modified": m.get("lastModified", ""),
        })
    return results


async def get_repo_files(repo_id: str) -> list[dict]:
    """List GGUF files in a HuggingFace repo with sizes."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{HF_API}/models/{repo_id}",
                                params={"blobs": True})
        resp.raise_for_status()
        data = resp.json()

    siblings = data.get("siblings", [])
    gguf_files = []
    for f in siblings:
        fname = f.get("rfilename", "")
        if fname.lower().endswith(".gguf"):
            gguf_files.append({
                "filename": fname,
                "size": f.get("size", 0),
                "repo_id": repo_id,
                "download_url": f"https://huggingface.co/{repo_id}/resolve/main/{fname}",
            })
    return gguf_files


async def download_model(repo_id: str, filename: str,
                         dest_dir: str) -> AsyncGenerator[dict, None]:
    """Download a GGUF file with progress updates."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    out_path = dest / filename

    url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=15.0),
                                 follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(out_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    yield {
                        "status": "downloading",
                        "filename": filename,
                        "downloaded": downloaded,
                        "total": total,
                        "percent": round(downloaded / total * 100, 1) if total else 0,
                    }

    yield {"status": "complete", "filename": filename, "path": str(out_path)}


# ── Local GGUF scanner ───────────────────────────────────────────────

def _default_scan_dirs() -> list[str]:
    """Return common directories where GGUF models might live."""
    home = Path.home()
    dirs = [
        home / "models",
        home / "Models",
        home / ".cache" / "huggingface",
        home / ".cache" / "lm-studio" / "models",
        home / "AppData" / "Local" / "nomic.ai" / "GPT4All",
        home / "Desktop",
        home / "Downloads",
    ]
    # On Windows, scan likely model folders on other drives (not entire drives)
    if os.name == "nt":
        import string
        model_folder_names = {
            "models", "Models", "AI", "ai",
            "LLM", "llm", "LLMs", "llms", "gguf", "GGUF",
            "huggingface", "lm-studio", "GPT4All", "text-generation-webui",
            "oobabooga", "koboldcpp",
        }
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if not drive.is_dir() or letter == "C":
                continue
            try:
                for entry in drive.iterdir():
                    if entry.name.startswith("$"):
                        continue
                    if entry.is_dir() and entry.name in model_folder_names:
                        dirs.append(entry)
                    # Check for top-level dirs containing .gguf files
                    elif entry.is_dir():
                        try:
                            if any(f.suffix.lower() == ".gguf"
                                   for f in entry.iterdir() if f.is_file()):
                                dirs.append(entry)
                        except (PermissionError, OSError):
                            pass
                    # .gguf directly on drive root — scan the drive itself (shallow)
                    elif entry.is_file() and entry.suffix.lower() == ".gguf":
                        if drive not in dirs:
                            dirs.append(drive)
            except (PermissionError, OSError):
                continue
    return [str(d) for d in dirs]


def scan_for_gguf(directories: list[str] | None = None,
                  max_depth: int = 4) -> list[dict]:
    """Recursively scan directories for .gguf files.

    Args:
        directories: Paths to scan. Uses common defaults if None.
        max_depth: Maximum directory depth to recurse into.

    Returns:
        List of dicts with filename, path, size, parent_dir.
    """
    scan_dirs = directories or _default_scan_dirs()
    results: list[dict] = []
    seen: set[str] = set()

    for base_dir in scan_dirs:
        base = Path(base_dir)
        if not base.exists() or not base.is_dir():
            continue
        try:
            _scan_recursive(base, base, max_depth, 0, results, seen)
        except PermissionError:
            continue

    results.sort(key=lambda x: x["filename"].lower())
    return results


def _scan_recursive(root: Path, current: Path, max_depth: int,
                    depth: int, results: list[dict], seen: set[str]) -> None:
    """Walk directory tree looking for .gguf files."""
    if depth > max_depth:
        return
    try:
        entries = list(current.iterdir())
    except (PermissionError, OSError):
        return

    for entry in entries:
        name = entry.name
        # Skip anything starting with $ (recycle bin, system dirs)
        if name.startswith("$"):
            continue
        if entry.is_file() and entry.suffix.lower() == ".gguf":
            resolved = str(entry.resolve())
            if resolved not in seen:
                seen.add(resolved)
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                results.append({
                    "filename": name,
                    "path": resolved,
                    "size": size,
                    "parent_dir": str(entry.parent),
                })
        elif entry.is_dir() and not name.startswith("."):
            # Skip obvious non-model directories (case-insensitive)
            skip = {"node_modules", "__pycache__", ".git", "venv", "env",
                    "windows", "program files", "program files (x86)",
                    "$recycle.bin", "system volume information",
                    "anaconda3", "anaconda", "miniconda3", "conda",
                    "site-packages", "lib", "libs",
                    "bin", "etc", "share", "include", "scripts",
                    "appdata", "programdata", "recovery",
                    ".conda", ".npm", ".cargo", ".rustup",
                    "python", "pipcache", "tmp"}
            if name.lower() not in skip:
                _scan_recursive(root, entry, max_depth, depth + 1, results, seen)


def list_local_models(models_dir: str) -> list[dict]:
    """List downloaded GGUF files in a specific directory."""
    d = Path(models_dir)
    if not d.exists():
        return []
    results = []
    for f in sorted(d.glob("*.gguf")):
        results.append({
            "filename": f.name,
            "path": str(f),
            "size": f.stat().st_size,
        })
    return results


def delete_local_model(models_dir: str, filename: str) -> bool:
    """Delete a downloaded GGUF file."""
    p = Path(models_dir) / filename
    if p.exists() and p.suffix == ".gguf":
        p.unlink()
        return True
    return False


# ── mmproj / Vision projection file scanner ──────────────────────────

_MMPROJ_KEYWORDS = {"mmproj", "clip-model", "clip_model", "vision-adapter",
                     "visual-encoder", "vision-encoder", "projector",
                     "vision_proj", "mm-projector"}


def scan_for_mmproj(directories: list[str] | None = None,
                    max_depth: int = 4) -> list[dict]:
    """Scan directories for mmproj / CLIP projection GGUF files.

    These are the vision projection files required by LLaVA-style models
    (filenames typically contain 'mmproj' or 'clip').
    """
    scan_dirs = directories or _default_scan_dirs()
    results: list[dict] = []
    seen: set[str] = set()

    for base_dir in scan_dirs:
        base = Path(base_dir)
        if not base.exists() or not base.is_dir():
            continue
        try:
            _scan_mmproj_recursive(base, max_depth, 0, results, seen)
        except PermissionError:
            continue

    results.sort(key=lambda x: x["filename"].lower())
    return results


def _scan_mmproj_recursive(current: Path, max_depth: int, depth: int,
                           results: list[dict], seen: set[str]) -> None:
    """Walk directory tree looking for mmproj/clip projection files."""
    if depth > max_depth:
        return
    try:
        entries = list(current.iterdir())
    except (PermissionError, OSError):
        return

    for entry in entries:
        name = entry.name
        if name.startswith("$") or name.startswith("."):
            continue
        if entry.is_file() and entry.suffix.lower() == ".gguf":
            name_lower = name.lower()
            if any(kw in name_lower for kw in _MMPROJ_KEYWORDS):
                resolved = str(entry.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                    results.append({
                        "filename": name,
                        "path": resolved,
                        "size": size,
                        "parent_dir": str(entry.parent),
                    })
        elif entry.is_dir():
            skip = {"node_modules", "__pycache__", ".git", "venv", "env",
                    "windows", "program files", "program files (x86)",
                    "$recycle.bin", "system volume information",
                    "anaconda3", "anaconda", "miniconda3", "conda",
                    "site-packages", "lib", "libs",
                    "bin", "etc", "share", "include", "scripts",
                    "appdata", "programdata", "recovery",
                    ".conda", ".npm", ".cargo", ".rustup",
                    "python", "pipcache", "tmp"}
            if name.lower() not in skip:
                _scan_mmproj_recursive(entry, max_depth, depth + 1, results, seen)
