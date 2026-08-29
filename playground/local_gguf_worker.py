"""Subprocess worker for local GGUF inference (llama-cpp-python).

Model loading and `create_chat_completion` both hold the GIL for extended
stretches inside llama-cpp-python's C extension — even when called via
`asyncio.to_thread`, that starves the main event loop and freezes the whole
server (every API endpoint, not just chat) for as long as it takes to load
or generate. Running both in a dedicated OS process keeps the main process's
event loop free regardless of how long the C extension holds its own GIL.

This module is intentionally dependency-light (stdlib + llama_cpp only, no
`playground.*` imports) so it starts quickly when spawned as a child process.
"""
from __future__ import annotations

import os
import re
import pathlib
import tempfile
import multiprocessing as mp

_llm = None
_loaded_path = ""
_loaded_mmproj = ""
_loaded_n_gpu_layers: int | None = None
_loaded_n_ctx: int | None = None

# Phrases llama.cpp's chat-template Jinja code raises when a model's template
# doesn't support a separate system role (e.g. Gemma) or otherwise rejects the
# message-role sequence we sent.
_TEMPLATE_ERROR_HINTS = ("alternate", "system role", "system message")

_UNKNOWN_ARCH_RE = re.compile(r"unknown model architecture:\s*'([^']+)'")


def _capture_native_stderr(fn):
    """Run fn() with the OS-level stderr fd redirected to a temp file and
    return (result_or_None, exception_or_None, captured_text).

    llama.cpp logs via native fprintf(stderr, ...), which bypasses Python's
    sys.stderr entirely — only an OS file-descriptor redirect (not
    contextlib.redirect_stderr) actually captures it. Needed only on the
    failure path to recover the specific reason (e.g. an unsupported model
    architecture) that llama-cpp-python's Python-level exception discards.
    """
    stderr_fd = 2
    saved_fd = os.dup(stderr_fd)
    with tempfile.TemporaryFile(mode="w+b") as tmp:
        os.dup2(tmp.fileno(), stderr_fd)
        result, exc = None, None
        try:
            result = fn()
        except Exception as e:
            exc = e
        finally:
            os.dup2(saved_fd, stderr_fd)
            os.close(saved_fd)
        tmp.seek(0)
        captured = tmp.read().decode(errors="replace")
    return result, exc, captured


def _ensure_model(model_path: str, mmproj_path: str, n_gpu_layers: int, n_ctx: int):
    global _llm, _loaded_path, _loaded_mmproj, _loaded_n_gpu_layers, _loaded_n_ctx
    if (_llm is not None and _loaded_path == model_path
            and _loaded_mmproj == mmproj_path
            and _loaded_n_gpu_layers == n_gpu_layers
            and _loaded_n_ctx == n_ctx):
        return _llm

    if _llm is not None:
        try:
            del _llm
        except Exception:
            pass
        _llm = None
        _loaded_path = ""
        _loaded_mmproj = ""
        _loaded_n_gpu_layers = None
        _loaded_n_ctx = None

    import gc
    gc.collect()

    from llama_cpp import Llama

    kwargs: dict = {
        "model_path": model_path,
        "n_gpu_layers": n_gpu_layers,
        "n_ctx": n_ctx,
        "verbose": False,
    }
    if mmproj_path and pathlib.Path(mmproj_path).is_file():
        # clip_model_path is not a real Llama() parameter in current
        # llama-cpp-python — vision support requires a chat_handler object
        # built from the mmproj file instead.
        from llama_cpp.llama_chat_format import Llava15ChatHandler
        kwargs["chat_handler"] = Llava15ChatHandler(
            clip_model_path=mmproj_path, verbose=False)

    try:
        _llm = Llama(**kwargs)
    except Exception as e:
        # Reload with verbose logging captured at the OS fd level, purely to
        # recover the specific native error llama-cpp-python's own exception
        # discards (verbose=False suppresses even error-level native logs,
        # confirmed — the plain exception here is just "Failed to load model
        # from file: PATH" with no detail).
        _, _, captured = _capture_native_stderr(
            lambda: Llama(**{**kwargs, "verbose": True}))
        m = _UNKNOWN_ARCH_RE.search(captured)
        if m:
            import llama_cpp as _lc
            version = getattr(_lc, "__version__", "unknown")
            raise ValueError(
                f"This model uses the '{m.group(1)}' architecture, which "
                f"isn't supported by the installed llama-cpp-python "
                f"({version}). This is common for very new model releases - "
                f"check Settings > Local GGUF for a backend update, or "
                f"try a different model."
            ) from e
        raise

    _loaded_path = model_path
    _loaded_mmproj = mmproj_path
    _loaded_n_gpu_layers = n_gpu_layers
    _loaded_n_ctx = n_ctx
    return _llm


def _build_messages(system_prompt: str, messages: list[dict],
                     merge_system: bool) -> list[dict]:
    msgs = [dict(m) for m in messages]
    if not system_prompt:
        return msgs
    if not merge_system:
        return [{"role": "system", "content": system_prompt}] + msgs
    # Compatibility mode: fold the system prompt into the first user turn
    # instead of sending a separate system-role message.
    if msgs and msgs[0].get("role") == "user":
        merged = dict(msgs[0])
        merged["content"] = f"{system_prompt}\n\n{merged['content']}"
        return [merged] + msgs[1:]
    return [{"role": "user", "content": system_prompt}] + msgs


def _attach_images(all_messages: list[dict], images: list[str]) -> None:
    for i in range(len(all_messages) - 1, -1, -1):
        if all_messages[i]["role"] == "user":
            text = all_messages[i]["content"]
            all_messages[i]["content"] = (
                [{"type": "text", "text": text}]
                + [{"type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img}"}}
                   for img in images]
            )
            break


def _looks_like_template_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(hint in msg for hint in _TEMPLATE_ERROR_HINTS)


def _stream(llm, all_messages: list[dict], temperature: float, max_tokens: int,
            out_q, req_id) -> bool:
    """Stream one attempt. Returns True if at least one token was produced."""
    produced = False
    for chunk in llm.create_chat_completion(
        messages=all_messages, temperature=temperature,
        max_tokens=max_tokens, stream=True,
    ):
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        token = delta.get("content", "")
        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
        if reasoning:
            out_q.put({"id": req_id, "reasoning": reasoning})
            produced = True
            continue
        if token:
            out_q.put({"id": req_id, "token": token})
            produced = True
    return produced


def run_worker(in_q: "mp.Queue", out_q: "mp.Queue") -> None:
    """Subprocess entrypoint: pulls generate jobs, streams tokens back."""
    while True:
        job = in_q.get()
        if job is None or job.get("cmd") == "shutdown":
            break

        req_id = job["id"]
        try:
            llm = _ensure_model(
                job["model_path"], job.get("mmproj_path", ""),
                job.get("n_gpu_layers", -1), job.get("n_ctx", 8192),
            )

            all_messages = _build_messages(
                job["system_prompt"], job["messages"], merge_system=False)
            if job.get("images") and job.get("mmproj_path"):
                _attach_images(all_messages, job["images"])

            try:
                _stream(llm, all_messages, job["temperature"], job["max_tokens"],
                        out_q, req_id)
            except Exception as e:
                if _looks_like_template_error(e):
                    # The loaded model's chat template rejects a separate
                    # system-role message (e.g. Gemma) — retry once with the
                    # system prompt folded into the first user turn instead.
                    retry_messages = _build_messages(
                        job["system_prompt"], job["messages"], merge_system=True)
                    if job.get("images") and job.get("mmproj_path"):
                        _attach_images(retry_messages, job["images"])
                    _stream(llm, retry_messages, job["temperature"],
                            job["max_tokens"], out_q, req_id)
                else:
                    raise

            out_q.put({"id": req_id, "done": True})
        except Exception as e:
            out_q.put({"id": req_id, "error": str(e)})
