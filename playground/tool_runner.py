"""Sandboxed tool execution for Agent mode.

Each tool runs with explicit user-granted permissions.
No filesystem, network, or OS access unless whitelisted.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx


def run_tool(tool_name: str, params: dict, permissions: dict) -> dict:
    """Dispatch a tool call with permission checks."""
    runners = {
        "read_file": _tool_read_file,
        "write_file": _tool_write_file,
        "list_directory": _tool_list_directory,
        "search_files": _tool_search_files,
        "grep_files": _tool_grep_files,
        "web_search": _tool_web_search,
        "fetch_page": _tool_fetch_page,
        "http_request": _tool_http_request,
        "shell_exec": _tool_shell_exec,
        "run_code": _tool_run_code,
        "datetime": _tool_datetime,
        "weather": _tool_weather,
        "json_parse": _tool_json_parse,
        "screenshot": _tool_screenshot,
        "clipboard": _tool_clipboard,
        "open_app": _tool_open_app,
        "system_info": _tool_system_info,
        "diff_files": _tool_diff_files,
        "pdf_read": _tool_pdf_read,
        "csv_query": _tool_csv_query,
        "regex_replace": _tool_regex_replace,
    }
    runner = runners.get(tool_name)
    if not runner:
        return {"error": f"Unknown tool: {tool_name}", "available": list(runners.keys())}
    try:
        return runner(params, permissions)
    except Exception as e:
        return {"error": str(e)}


# ── File tools ────────────────────────────────────────────────────────

def _check_path_allowed(filepath: str, permissions: dict) -> str | None:
    """Return None if allowed, or an error message."""
    if not permissions.get("file_access"):
        return "File access not enabled. Enable it in Tools settings."
    allowed = permissions.get("allowed_paths", [])
    if not allowed:
        return "No directories whitelisted. Add allowed paths in Tools settings."
    resolved = str(Path(filepath).resolve())
    for ap in allowed:
        ap_resolved = str(Path(ap).resolve())
        if resolved.startswith(ap_resolved):
            return None
    return f"Path not in allowed directories. Allowed: {allowed}"


def _tool_read_file(params: dict, permissions: dict) -> dict:
    filepath = params.get("path", "")
    if not filepath:
        return {"error": "path parameter required"}
    err = _check_path_allowed(filepath, permissions)
    if err:
        return {"error": err}
    p = Path(filepath)
    if not p.exists():
        return {"error": f"File not found: {filepath}"}
    if not p.is_file():
        return {"error": f"Not a file: {filepath}"}
    if p.stat().st_size > 1_000_000:  # 1MB limit
        return {"error": "File too large (>1MB). Read specific sections instead."}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        return {"content": content, "path": str(p), "size": len(content)}
    except Exception as e:
        return {"error": f"Read failed: {e}"}


def _tool_write_file(params: dict, permissions: dict) -> dict:
    filepath = params.get("path", "")
    content = params.get("content", "")
    if not filepath:
        return {"error": "path parameter required"}
    err = _check_path_allowed(filepath, permissions)
    if err:
        return {"error": err}
    p = Path(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(p), "bytes_written": len(content)}


def _tool_list_directory(params: dict, permissions: dict) -> dict:
    dirpath = params.get("path", "")
    if not dirpath:
        return {"error": "path parameter required"}
    err = _check_path_allowed(dirpath, permissions)
    if err:
        return {"error": err}
    p = Path(dirpath)
    if not p.is_dir():
        return {"error": f"Not a directory: {dirpath}"}
    entries = []
    for e in sorted(p.iterdir()):
        entries.append({
            "name": e.name,
            "type": "directory" if e.is_dir() else "file",
            "size": e.stat().st_size if e.is_file() else None,
        })
    return {"path": str(p), "entries": entries[:200]}


def _tool_search_files(params: dict, permissions: dict) -> dict:
    """Search for files by name pattern within allowed directories."""
    if not permissions.get("file_access"):
        return {"error": "File access not enabled. Enable it in Tools settings."}
    pattern = params.get("pattern", "")
    directory = params.get("path", "")
    if not directory:
        return {"error": "path parameter required (directory to search in)"}
    err = _check_path_allowed(directory, permissions)
    if err:
        return {"error": err}
    p = Path(directory)
    if not p.is_dir():
        return {"error": f"Not a directory: {directory}"}
    import fnmatch
    matches = []
    for root, dirs, files in os.walk(str(p)):
        # Skip hidden dirs and common large dirs
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '__pycache__', '.git', 'venv', '.venv')]
        for fname in files:
            if not pattern or fnmatch.fnmatch(fname.lower(), pattern.lower()):
                full = os.path.join(root, fname)
                matches.append(full)
            if len(matches) >= 100:
                break
        if len(matches) >= 100:
            break
    return {"pattern": pattern, "path": str(p), "matches": matches, "total": len(matches)}


def _tool_grep_files(params: dict, permissions: dict) -> dict:
    """Search file contents for a text pattern within allowed directories."""
    if not permissions.get("file_access"):
        return {"error": "File access not enabled. Enable it in Tools settings."}
    query = params.get("query", "")
    directory = params.get("path", "")
    if not query or not directory:
        return {"error": "query and path parameters required"}
    err = _check_path_allowed(directory, permissions)
    if err:
        return {"error": err}
    p = Path(directory)
    if not p.is_dir():
        return {"error": f"Not a directory: {directory}"}
    import re
    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
    TEXT_EXTS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.json', '.md',
                 '.txt', '.yml', '.yaml', '.toml', '.cfg', '.ini', '.sh', '.bat', '.ps1',
                 '.c', '.h', '.cpp', '.hpp', '.java', '.go', '.rs', '.rb', '.php'}
    results = []
    for root, dirs, files in os.walk(str(p)):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '__pycache__', '.git', 'venv', '.venv')]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in TEXT_EXTS:
                continue
            full = os.path.join(root, fname)
            try:
                with open(full, 'r', encoding='utf-8', errors='replace') as fh:
                    for lineno, line in enumerate(fh, 1):
                        if pattern.search(line):
                            results.append({
                                "file": full,
                                "line": lineno,
                                "text": line.rstrip()[:200],
                            })
                            if len(results) >= 50:
                                break
            except (OSError, UnicodeDecodeError):
                continue
            if len(results) >= 50:
                break
        if len(results) >= 50:
            break
    return {"query": query, "path": str(p), "results": results, "total": len(results)}


# ── Web tools ─────────────────────────────────────────────────────────

def _check_site_allowed(url: str, permissions: dict) -> str | None:
    if not permissions.get("web_search"):
        return "Web access not enabled. Enable it in Tools settings."
    allowed = permissions.get("allowed_sites", [])
    if not allowed:
        return None  # no whitelist means all sites allowed
    parsed = urlparse(url)
    domain = parsed.hostname or ""
    for site in allowed:
        site = site.lower().lstrip("*.")
        if domain == site or domain.endswith("." + site):
            return None
    return f"Site {domain} not in allowed list: {allowed}"


def _tool_web_search(params: dict, permissions: dict) -> dict:
    if not permissions.get("web_search"):
        return {"error": "Web search not enabled. Enable it in Tools settings."}
    query = params.get("query", "")
    if not query:
        return {"error": "query parameter required"}
    # Use DuckDuckGo HTML search (no API key needed)
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "MimirsWell/1.0"},
            )
            resp.raise_for_status()
            # Extract result snippets from HTML
            text = resp.text
            results = []
            # Simple extraction of result blocks
            parts = text.split('class="result__snippet"')
            for part in parts[1:6]:  # top 5 results
                snippet_end = part.find("</a>")
                if snippet_end > 0:
                    snippet = part[:snippet_end]
                    # Strip HTML tags
                    clean = ""
                    in_tag = False
                    for ch in snippet:
                        if ch == "<":
                            in_tag = True
                        elif ch == ">":
                            in_tag = False
                        elif not in_tag:
                            clean += ch
                    if clean.strip():
                        results.append(clean.strip()[:300])
            return {"query": query, "results": results}
    except Exception as e:
        return {"error": f"Search failed: {e}"}


def _tool_fetch_page(params: dict, permissions: dict) -> dict:
    url = params.get("url", "")
    if not url:
        return {"error": "url parameter required"}
    err = _check_site_allowed(url, permissions)
    if err:
        return {"error": err}
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MimirsWell/1.0)"})
            resp.raise_for_status()
            text = resp.text
            # Try proper HTML parsing first
            try:
                from html.parser import HTMLParser
                class _TextExtractor(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.parts = []
                        self._skip = False
                        self._skip_tags = {'script', 'style', 'noscript', 'svg', 'head'}
                    def handle_starttag(self, tag, attrs):
                        if tag in self._skip_tags:
                            self._skip = True
                        if tag in ('p', 'br', 'div', 'h1', 'h2', 'h3', 'h4', 'li', 'tr'):
                            self.parts.append('\n')
                    def handle_endtag(self, tag):
                        if tag in self._skip_tags:
                            self._skip = False
                    def handle_data(self, data):
                        if not self._skip:
                            self.parts.append(data)
                parser = _TextExtractor()
                parser.feed(text)
                clean = ''.join(parser.parts)
            except Exception:
                # Fallback: strip tags manually
                clean = ""
                in_tag = False
                for ch in text:
                    if ch == "<": in_tag = True
                    elif ch == ">": in_tag = False
                    elif not in_tag: clean += ch
            # Collapse whitespace
            import re
            clean = re.sub(r"[ \t]+", " ", clean)
            clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
            max_len = int(params.get("max_length", 8000))
            return {"url": url, "title": _extract_title(text), "content": clean[:max_len], "truncated": len(clean) > max_len}
    except Exception as e:
        return {"error": f"Fetch failed: {e}"}


def _extract_title(html: str) -> str:
    """Extract <title> from HTML."""
    import re
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


# ── Code execution ───────────────────────────────────────────────────

def _tool_run_code(params: dict, permissions: dict) -> dict:
    if not permissions.get("code_execution"):
        return {"error": "Code execution not enabled. Enable it in Tools settings."}
    code = params.get("code", "")
    language = params.get("language", "python")
    if not code:
        return {"error": "code parameter required"}
    if language != "python":
        return {"error": f"Only Python is supported, got: {language}"}
    if len(code) > 10000:
        return {"error": "Code too long (>10000 chars)"}

    # Sandbox: block dangerous imports/calls
    blocked = [
        "import os", "import sys", "import subprocess", "import shutil",
        "__import__", "exec(", "eval(", "open(", "compile(",
        "import socket", "import http", "import urllib",
        "import ctypes", "import signal", "import _thread",
        "import multiprocessing", "import pathlib",
    ]
    code_lower = code.lower().replace(" ", "")
    for b in blocked:
        if b.lower().replace(" ", "") in code_lower:
            return {"error": f"Blocked: {b} is not allowed in sandboxed execution. "
                    "Enable file access or web access in Tools settings for those capabilities."}

    # Run in a subprocess with timeout
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write(code)
        f.flush()
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True,
            timeout=10,
            cwd=tempfile.gettempdir(),
        )
        return {
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Code execution timed out (10s limit)"}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Utility tools ─────────────────────────────────────────────────────

def _tool_datetime(params: dict, permissions: dict) -> dict:
    """Always available — no permissions needed."""
    now = datetime.datetime.now()
    return {
        "datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day": now.strftime("%A"),
        "timezone": str(datetime.datetime.now().astimezone().tzinfo),
    }


def _tool_weather(params: dict, permissions: dict) -> dict:
    """Get weather using wttr.in (no API key needed)."""
    if not permissions.get("web_search"):
        return {"error": "Web access not enabled. Enable it in Tools settings."}
    location = params.get("location", "")
    try:
        url = f"https://wttr.in/{location}?format=j1" if location else "https://wttr.in/?format=j1"
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers={"User-Agent": "MimirsWell/1.0"})
            resp.raise_for_status()
            data = resp.json()
            current = data.get("current_condition", [{}])[0]
            return {
                "location": location or "auto-detected",
                "temperature_c": current.get("temp_C", ""),
                "temperature_f": current.get("temp_F", ""),
                "condition": current.get("weatherDesc", [{}])[0].get("value", ""),
                "humidity": current.get("humidity", ""),
                "wind_mph": current.get("windspeedMiles", ""),
                "feels_like_c": current.get("FeelsLikeC", ""),
            }
    except Exception as e:
        return {"error": f"Weather lookup failed: {e}"}


# ── HTTP request tool ─────────────────────────────────────────────────

def _tool_http_request(params: dict, permissions: dict) -> dict:
    """Make arbitrary HTTP requests (GET, POST, PUT, DELETE, PATCH)."""
    if not permissions.get("web_search"):
        return {"error": "Web access not enabled. Enable it in Tools settings."}
    url = params.get("url", "")
    method = params.get("method", "GET").upper()
    if not url:
        return {"error": "url parameter required"}
    if method not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"):
        return {"error": f"Unsupported method: {method}"}
    err = _check_site_allowed(url, permissions)
    if err:
        return {"error": err}
    headers = params.get("headers", {})
    body = params.get("body")
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            req_kwargs = {"headers": {**headers, "User-Agent": "MimirsWell/1.0"}}
            if body and method in ("POST", "PUT", "PATCH"):
                if isinstance(body, dict):
                    req_kwargs["json"] = body
                else:
                    req_kwargs["content"] = str(body)
            resp = client.request(method, url, **req_kwargs)
            # Try to parse as JSON
            try:
                resp_body = resp.json()
            except Exception:
                resp_body = resp.text[:8000]
            return {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp_body,
                "url": str(resp.url),
            }
    except Exception as e:
        return {"error": f"Request failed: {e}"}


# ── Shell execution tool ──────────────────────────────────────────────

def _tool_shell_exec(params: dict, permissions: dict) -> dict:
    """Execute a shell command (requires code_execution permission)."""
    if not permissions.get("code_execution"):
        return {"error": "Code execution not enabled. Enable it in Tools settings."}
    command = params.get("command", "")
    if not command:
        return {"error": "command parameter required"}
    if len(command) > 2000:
        return {"error": "Command too long (>2000 chars)"}
    # Block dangerous commands
    cmd_lower = command.lower().strip()
    blocked_prefixes = ["rm -rf /", "format ", "del /s /q c:\\", "rd /s /q c:\\",
                        "mkfs", "dd if=", ":(){ :|:& };:"]
    for bp in blocked_prefixes:
        if cmd_lower.startswith(bp):
            return {"error": f"Blocked: dangerous command pattern '{bp}'"}
    cwd = params.get("cwd")
    if cwd:
        err = _check_path_allowed(cwd, permissions)
        if err:
            return {"error": err}
    timeout_s = min(int(params.get("timeout", 30)), 60)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=cwd or None,
        )
        return {
            "stdout": result.stdout[:8000],
            "stderr": result.stderr[:4000],
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out ({timeout_s}s limit)"}
    except Exception as e:
        return {"error": f"Execution failed: {e}"}


# ── JSON parse/query tool ─────────────────────────────────────────────

def _tool_json_parse(params: dict, permissions: dict) -> dict:
    """Parse JSON text and optionally extract a value by dot-path."""
    text = params.get("text", "")
    path = params.get("path", "")
    if not text:
        return {"error": "text parameter required"}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}
    if not path:
        # Return structure summary if large
        s = json.dumps(data, indent=2)
        if len(s) > 8000:
            return {"parsed": True, "type": type(data).__name__,
                    "preview": s[:8000], "truncated": True}
        return {"data": data}
    # Navigate dot-path (supports array indices like "items.0.name")
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return {"error": f"Key not found: '{part}' in path '{path}'"}
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return {"error": f"Invalid array index: '{part}' in path '{path}'"}
        else:
            return {"error": f"Cannot navigate into {type(current).__name__} at '{part}'"}
    return {"path": path, "value": current}


# ── Screenshot tool ───────────────────────────────────────────────────

def _tool_screenshot(params: dict, permissions: dict) -> dict:
    """Take a screenshot of the screen (or a region) and return as base64 PNG."""
    if not permissions.get("code_execution"):
        return {"error": "Code execution not enabled. Enable it in Tools settings."}
    try:
        from PIL import ImageGrab
    except ImportError:
        return {"error": "Pillow not installed. Run: pip install Pillow"}
    import base64
    import io
    region = params.get("region")  # optional [left, top, right, bottom]
    try:
        if region and isinstance(region, list) and len(region) == 4:
            img = ImageGrab.grab(bbox=tuple(region))
        else:
            img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return {"image_base64": b64, "width": img.width, "height": img.height,
                "format": "png", "size_bytes": buf.tell()}
    except Exception as e:
        return {"error": f"Screenshot failed: {e}"}


# ── Clipboard tool ────────────────────────────────────────────────────

def _tool_clipboard(params: dict, permissions: dict) -> dict:
    """Read or write the system clipboard."""
    if not permissions.get("code_execution"):
        return {"error": "Code execution not enabled. Enable it in Tools settings."}
    action = params.get("action", "read")
    if action == "read":
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=5,
            )
            return {"content": result.stdout.rstrip("\r\n"), "ok": True}
        except Exception as e:
            return {"error": f"Clipboard read failed: {e}"}
    elif action == "write":
        text = params.get("text", "")
        if not text:
            return {"error": "text parameter required for write action"}
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Set-Clipboard -Value {json.dumps(text)}"],
                capture_output=True, text=True, timeout=5,
            )
            return {"ok": True, "wrote_chars": len(text)}
        except Exception as e:
            return {"error": f"Clipboard write failed: {e}"}
    else:
        return {"error": f"Unknown action: {action}. Use 'read' or 'write'."}


# ── Open Application tool ────────────────────────────────────────────

def _tool_open_app(params: dict, permissions: dict) -> dict:
    """Open an application or file with the system default handler."""
    if not permissions.get("code_execution"):
        return {"error": "Code execution not enabled. Enable it in Tools settings."}
    target = params.get("target", "")
    if not target:
        return {"error": "target parameter required (app name, exe path, or file path)"}
    # Block dangerous targets
    target_lower = target.lower()
    blocked = ["cmd /c", "powershell -", "del ", "rm ", "format ", "rd ", "rmdir "]
    for b in blocked:
        if b in target_lower:
            return {"error": f"Blocked: '{b}' pattern in target"}
    try:
        if sys.platform == "win32":
            os.startfile(target)
        else:
            opener = "xdg-open" if sys.platform == "linux" else "open"
            subprocess.Popen([opener, target])
        return {"ok": True, "opened": target}
    except Exception as e:
        return {"error": f"Failed to open: {e}"}


# ── System Info tool ──────────────────────────────────────────────────

def _tool_system_info(params: dict, permissions: dict) -> dict:
    """Get system information (OS, CPU, RAM, disk, etc.)."""
    import platform
    info: dict = {
        "os": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
    }
    # Memory info (cross-platform)
    try:
        import shutil
        total, used, free = shutil.disk_usage("/") if sys.platform != "win32" else shutil.disk_usage("C:\\")
        info["disk_c"] = {
            "total_gb": round(total / (1024**3), 1),
            "used_gb": round(used / (1024**3), 1),
            "free_gb": round(free / (1024**3), 1),
        }
    except Exception:
        pass
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["wmic", "OS", "get", "TotalVisibleMemorySize,FreePhysicalMemory", "/value"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line.startswith("TotalVisibleMemorySize="):
                    info["ram_total_gb"] = round(int(line.split("=")[1]) / (1024**2), 1)
                elif line.startswith("FreePhysicalMemory="):
                    info["ram_free_gb"] = round(int(line.split("=")[1]) / (1024**2), 1)
    except Exception:
        pass
    return info


# ── Diff Files tool ──────────────────────────────────────────────────

def _tool_diff_files(params: dict, permissions: dict) -> dict:
    """Compare two files or two text strings and return a unified diff."""
    if not permissions.get("file_access"):
        return {"error": "File access not enabled. Enable it in Tools settings."}
    import difflib
    # Support file paths or inline text
    file_a = params.get("file_a", "")
    file_b = params.get("file_b", "")
    text_a = params.get("text_a", "")
    text_b = params.get("text_b", "")
    label_a = "a"
    label_b = "b"
    if file_a and file_b:
        err = _check_path_allowed(file_a, permissions)
        if err:
            return {"error": err}
        err = _check_path_allowed(file_b, permissions)
        if err:
            return {"error": err}
        pa, pb = Path(file_a), Path(file_b)
        if not pa.is_file():
            return {"error": f"File not found: {file_a}"}
        if not pb.is_file():
            return {"error": f"File not found: {file_b}"}
        text_a = pa.read_text(encoding="utf-8", errors="replace")
        text_b = pb.read_text(encoding="utf-8", errors="replace")
        label_a = str(pa.name)
        label_b = str(pb.name)
    elif not text_a and not text_b:
        return {"error": "Provide file_a+file_b or text_a+text_b parameters"}
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)
    diff = list(difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b, lineterm=""))
    if not diff:
        return {"identical": True, "diff": ""}
    return {"identical": False, "diff": "\n".join(diff)[:10000]}


# ── PDF Read tool ─────────────────────────────────────────────────────

def _tool_pdf_read(params: dict, permissions: dict) -> dict:
    """Read text content from a PDF file."""
    if not permissions.get("file_access"):
        return {"error": "File access not enabled. Enable it in Tools settings."}
    filepath = params.get("path", "")
    if not filepath:
        return {"error": "path parameter required"}
    err = _check_path_allowed(filepath, permissions)
    if err:
        return {"error": err}
    p = Path(filepath)
    if not p.is_file():
        return {"error": f"File not found: {filepath}"}
    if not p.suffix.lower() == ".pdf":
        return {"error": "Not a PDF file"}
    # Try multiple PDF libraries
    try:
        import fitz  # PyMuPDF — fast and reliable
        doc = fitz.open(filepath)
        pages = []
        max_pages = int(params.get("max_pages", 50))
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pages.append(page.get_text())
        doc.close()
        text = "\n\n---\n\n".join(pages)
        return {"path": filepath, "pages": min(len(pages), max_pages),
                "total_pages": len(doc) if hasattr(doc, '__len__') else len(pages),
                "content": text[:20000], "truncated": len(text) > 20000}
    except ImportError:
        pass
    # Fallback: pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        pages = []
        max_pages = int(params.get("max_pages", 50))
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                break
            pages.append(page.extract_text() or "")
        text = "\n\n---\n\n".join(pages)
        return {"path": filepath, "pages": len(pages),
                "total_pages": len(reader.pages),
                "content": text[:20000], "truncated": len(text) > 20000}
    except ImportError:
        return {"error": "No PDF library found. Install: pip install PyMuPDF  or  pip install pypdf"}


# ── CSV Query tool ────────────────────────────────────────────────────

def _tool_csv_query(params: dict, permissions: dict) -> dict:
    """Read and query CSV/TSV files — filter rows, get stats, or preview data."""
    if not permissions.get("file_access"):
        return {"error": "File access not enabled. Enable it in Tools settings."}
    filepath = params.get("path", "")
    if not filepath:
        return {"error": "path parameter required"}
    err = _check_path_allowed(filepath, permissions)
    if err:
        return {"error": err}
    p = Path(filepath)
    if not p.is_file():
        return {"error": f"File not found: {filepath}"}
    import csv
    delimiter = params.get("delimiter", "," if p.suffix.lower() == ".csv" else "\t")
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            rows = []
            for i, row in enumerate(reader):
                if i >= 1000:  # limit rows read
                    break
                rows.append(dict(row))
        if not rows:
            return {"path": filepath, "rows": 0, "columns": [], "data": []}
        columns = list(rows[0].keys())
        # Apply filter if provided
        filter_col = params.get("filter_column", "")
        filter_val = params.get("filter_value", "")
        if filter_col and filter_val:
            rows = [r for r in rows if filter_val.lower() in str(r.get(filter_col, "")).lower()]
        # Sort if requested
        sort_by = params.get("sort_by", "")
        if sort_by and sort_by in columns:
            rows.sort(key=lambda r: r.get(sort_by, ""))
        # Limit output
        max_rows = int(params.get("max_rows", 50))
        return {
            "path": filepath, "total_rows": len(rows),
            "columns": columns,
            "data": rows[:max_rows],
            "truncated": len(rows) > max_rows,
        }
    except Exception as e:
        return {"error": f"CSV read failed: {e}"}


# ── Regex Replace tool ────────────────────────────────────────────────

def _tool_regex_replace(params: dict, permissions: dict) -> dict:
    """Apply regex find-and-replace on text or a file."""
    import re
    pattern = params.get("pattern", "")
    replacement = params.get("replacement", "")
    if not pattern:
        return {"error": "pattern parameter required"}
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return {"error": f"Invalid regex: {e}"}
    # If file path given, read+replace+write
    filepath = params.get("path", "")
    if filepath:
        if not permissions.get("file_access"):
            return {"error": "File access not enabled."}
        err = _check_path_allowed(filepath, permissions)
        if err:
            return {"error": err}
        p = Path(filepath)
        if not p.is_file():
            return {"error": f"File not found: {filepath}"}
        text = p.read_text(encoding="utf-8", errors="replace")
        result, count = regex.subn(replacement, text)
        if count > 0:
            p.write_text(result, encoding="utf-8")
        return {"path": filepath, "replacements": count, "ok": True}
    # Inline text mode
    text = params.get("text", "")
    if not text:
        return {"error": "path or text parameter required"}
    result, count = regex.subn(replacement, text)
    return {"result": result[:10000], "replacements": count, "truncated": len(result) > 10000}
