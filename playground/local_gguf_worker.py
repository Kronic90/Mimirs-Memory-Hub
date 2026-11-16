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

from collections import OrderedDict

# Loaded models, most recently used last. Group chats where characters use
# different local models used to unload/reload a model on EVERY turn; now
# up to MAX_LOADED_MODELS stay in memory when there's enough free RAM.
_models: "OrderedDict[tuple, object]" = OrderedDict()
MAX_LOADED_MODELS = 2
_RAM_HEADROOM = 1.5e9   # leave this much free for the OS, browser and hub


def _free_ram_bytes() -> float:
    try:
        if os.name == "nt":
            import ctypes

            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = _MS()
            st.dwLength = ctypes.sizeof(_MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return float(st.ullAvailPhys)
        return float(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except Exception:
        return 0.0   # unknown -> behave like before (one model at a time)


def _model_bytes(model_path: str, mmproj_path: str) -> float:
    total = 0.0
    for f in (model_path, mmproj_path):
        try:
            if f:
                total += os.path.getsize(f)
        except OSError:
            pass
    return total * 1.2   # weights + context/KV cache overhead

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


def _make_vision_handler(mmproj_path: str):
    """Multimodal chat handler for a projector (mmproj) file.

    llama-cpp-python 0.3.36+ ships MTMDChatHandler: it renders prompts with
    the model's OWN chat template and feeds images *and audio* through
    llama.cpp's mtmd library (which also understands new families like
    Gemma 4). Older versions fall back to the template-fixing handler below.
    """
    try:
        from llama_cpp.llama_chat_format import MTMDChatHandler
        return MTMDChatHandler(clip_model_path=mmproj_path, verbose=False)
    except ImportError:
        return _make_legacy_vision_handler(mmproj_path)


def _make_legacy_vision_handler(mmproj_path: str):
    """Vision chat handler that formats prompts with the MODEL'S OWN chat
    template instead of LLaVA-1.5's.

    llama-cpp-python only ships vision handlers for a few model families,
    and the generic one (Llava15ChatHandler) hard-codes LLaVA's
    "USER: ... ASSISTANT:" format. Used with any other model -- Gemma 3,
    for one -- the model never sees its real turn markers, so it doesn't
    know where its reply ends: it rambles on, writes extra "USER:/ASSISTANT:"
    turns itself and leaks prompt text. Every GGUF carries its own template
    in its metadata, so we render with that, passing images through as
    text placeholders the handler then swaps for the vision embedding.
    LLaVA's format stays as the fallback for models with no template.
    """
    from llama_cpp.llama_chat_format import Llava15ChatHandler

    class ModelTemplateVisionHandler(Llava15ChatHandler):
        _use_model_template = False

        def adopt_model_template(self, llm) -> None:
            template = (getattr(llm, "metadata", None) or {}).get(
                "tokenizer.chat_template", "")
            if template:
                self.CHAT_FORMAT = template
                self.DEFAULT_SYSTEM_MESSAGE = None
                self._use_model_template = True

        @staticmethod
        def get_image_urls(messages):
            urls = []
            for m in messages:
                content = m.get("content") if isinstance(m, dict) else None
                if not isinstance(content, list):
                    continue
                for part in content:
                    if part.get("type") == "image_url":
                        u = part["image_url"]
                        urls.append(u["url"] if isinstance(u, dict) else u)
                    elif part.get("type") == "text" and part.get("_mimir_image"):
                        urls.append(part["text"])
            return urls

        @staticmethod
        def _inline_images(message):
            content = message.get("content")
            if not isinstance(content, list):
                return message
            parts = []
            for part in content:
                if part.get("type") == "image_url":
                    u = part["image_url"]
                    url = u["url"] if isinstance(u, dict) else u
                    # Model templates generally only render text parts; the
                    # URL text is what the handler replaces with the image.
                    parts.append({"type": "text", "text": url, "_mimir_image": True})
                else:
                    parts.append(part)
            return {**message, "content": parts}

        def __call__(self, **kwargs):
            if self._use_model_template:
                original = kwargs["messages"]
                kwargs["messages"] = [self._inline_images(m) for m in original]
                try:
                    return super().__call__(**kwargs)
                except Exception as e:
                    # Template features the vision renderer can't provide
                    # (custom jinja helpers etc.) -> fall back to LLaVA's.
                    if "jinja" not in type(e).__module__:
                        raise
                    self.CHAT_FORMAT = Llava15ChatHandler.CHAT_FORMAT
                    self.DEFAULT_SYSTEM_MESSAGE = Llava15ChatHandler.DEFAULT_SYSTEM_MESSAGE
                    self._use_model_template = False
                    kwargs["messages"] = original
            return super().__call__(**kwargs)

    return ModelTemplateVisionHandler(clip_model_path=mmproj_path, verbose=False)


def _ensure_model(model_path: str, mmproj_path: str, n_gpu_layers: int, n_ctx: int):
    """The requested model, loading it if needed. Keeps recently used
    models loaded while RAM allows; evicts the least recently used first."""
    import gc
    key = (model_path, mmproj_path, n_gpu_layers, n_ctx)
    if key in _models:
        _models.move_to_end(key)
        return _models[key]
    need = _model_bytes(model_path, mmproj_path)
    while _models and (len(_models) >= MAX_LOADED_MODELS
                       or _free_ram_bytes() < need + _RAM_HEADROOM):
        _old_key, old = _models.popitem(last=False)
        del old
        gc.collect()
    llm = _load_model(model_path, mmproj_path, n_gpu_layers, n_ctx)
    _models[key] = llm
    return llm


def _load_model(model_path: str, mmproj_path: str, n_gpu_layers: int, n_ctx: int):
    from llama_cpp import Llama

    kwargs: dict = {
        "model_path": model_path,
        "n_gpu_layers": n_gpu_layers,
        "n_ctx": n_ctx,
        "verbose": False,
    }
    vision_handler = None
    if mmproj_path and pathlib.Path(mmproj_path).is_file():
        # clip_model_path is not a real Llama() parameter in current
        # llama-cpp-python — vision support requires a chat_handler object
        # built from the mmproj file instead.
        vision_handler = _make_vision_handler(mmproj_path)
        kwargs["chat_handler"] = vision_handler

    try:
        llm = Llama(**kwargs)
        if vision_handler is not None and hasattr(vision_handler, "adopt_model_template"):
            vision_handler.adopt_model_template(llm)
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
    return llm


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


def _attach_images(all_messages: list[dict], images: list[str],
                   audio: list[str] | None = None) -> None:
    """Attach images (JPEG b64) and audio clips (16 kHz WAV b64) to the
    latest user turn. llama.cpp's media loader recognises audio from the
    bytes themselves, so both travel as media parts."""
    for i in range(len(all_messages) - 1, -1, -1):
        if all_messages[i]["role"] == "user":
            text = all_messages[i]["content"]
            all_messages[i]["content"] = (
                [{"type": "text", "text": text}]
                + [{"type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img}"}}
                   for img in (images or [])]
                + [{"type": "image_url",
                    "image_url": {"url": f"data:audio/wav;base64,{clip}"}}
                   for clip in (audio or [])]
            )
            break


def _looks_like_template_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(hint in msg for hint in _TEMPLATE_ERROR_HINTS)


def _stream(llm, all_messages: list[dict], temperature: float, max_tokens: int,
            out_q, req_id, has_images: bool = False) -> bool:
    """Stream one attempt. Returns True if at least one token was produced."""
    produced = False
    # A loaded vision model attaches a vision chat handler to the Llama
    # object, and llama-cpp-python then uses it for EVERY request. For a
    # text-only turn use the model's own built-in template directly -- the
    # exact format it was trained on, same as when no vision model is set.
    own_template = (getattr(llm, "_chat_handlers", None) or {}).get(
        "chat_template.default")
    if not has_images and getattr(llm, "chat_handler", None) is not None \
            and own_template is not None:
        chunks = own_template(
            llama=llm, messages=all_messages, temperature=temperature,
            max_tokens=max_tokens, stream=True)
    else:
        chunks = llm.create_chat_completion(
            messages=all_messages, temperature=temperature,
            max_tokens=max_tokens, stream=True)
    for chunk in chunks:
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        token = delta.get("content", "")
        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
        if reasoning:
            out_q.put({"id": req_id, "reasoning": reasoning})
            produced = True
            continue
        if token:
            # Gemma 4 marks its thinking as <|channel>thought ... <channel|>;
            # turn it into the <think> blocks the hub already folds away.
            if "channel" in token:
                token = (token.replace("<|channel>thought", "<think>")
                         .replace("<|channel>", "<think>").replace("<channel|>", "</think>"))
            out_q.put({"id": req_id, "token": token})
            produced = True
    return produced


class _QuietNative:
    """Silence llama.cpp's native stdout/stderr chatter (mtmd prints prompt
    chunks even with verbose off) so it doesn't spill into the hub's console.
    Python exceptions still propagate normally."""
    def __enter__(self):
        self._saved = []
        try:
            self._null = os.open(os.devnull, os.O_WRONLY)
            for fd in (1, 2):
                self._saved.append((fd, os.dup(fd)))
                os.dup2(self._null, fd)
        except OSError:
            pass
        return self

    def __exit__(self, *exc):
        for fd, saved in self._saved:
            try:
                os.dup2(saved, fd)
                os.close(saved)
            except OSError:
                pass
        try:
            os.close(self._null)
        except (OSError, AttributeError):
            pass
        return False


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
            has_images = bool((job.get("images") or job.get("audio")) and job.get("mmproj_path"))
            if has_images:
                _attach_images(all_messages, job.get("images") or [], job.get("audio"))
            try:
                with _QuietNative():
                    _stream(llm, all_messages, job["temperature"], job["max_tokens"],
                            out_q, req_id, has_images=has_images)
            except Exception as e:
                if _looks_like_template_error(e):
                    # The loaded model's chat template rejects a separate
                    # system-role message (e.g. Gemma) — retry once with the
                    # system prompt folded into the first user turn instead.
                    retry_messages = _build_messages(
                        job["system_prompt"], job["messages"], merge_system=True)
                    if has_images:
                        _attach_images(retry_messages, job.get("images") or [], job.get("audio"))
                    with _QuietNative():
                        _stream(llm, retry_messages, job["temperature"],
                                job["max_tokens"], out_q, req_id,
                                has_images=has_images)
                else:
                    raise

            out_q.put({"id": req_id, "done": True})
        except Exception as e:
            msg = str(e)
            if "Failed to load mtmd context" in msg:
                msg = (f"The vision/audio file '{os.path.basename(job.get('mmproj_path', ''))}' doesn't "
                       f"match the model '{os.path.basename(job.get('model_path', ''))}'. Each model needs "
                       f"its own matching file — pick the one made for this model in the vision "
                       f"dropdown (or the character's Advanced tab), or choose 'none'.")
            out_q.put({"id": req_id, "error": msg})
