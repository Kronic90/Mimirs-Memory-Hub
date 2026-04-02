"""Unified LLM backend interface for Mimir's Well.

Supported backends:
    - Ollama        (local, via HTTP)
    - OpenAI        (GPT-4o, etc.)
    - Anthropic     (Claude)
    - Google Gemini
    - OpenRouter    (multi-provider gateway — https://openrouter.ai)
    - vLLM          (remote vLLM server — OpenAI-compatible)
    - OpenAI-compat (any OpenAI-compatible endpoint — LM Studio, text-gen-webui, etc.)
    - Custom        (legacy alias for OpenAI-compatible)
"""
from __future__ import annotations

import json
import asyncio
from abc import ABC, abstractmethod
from typing import AsyncGenerator

import httpx


# ── Abstract base ─────────────────────────────────────────────────────

class LLMBackend(ABC):
    name: str = ""

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Yield tokens as they arrive."""
        yield ""  # pragma: no cover

    @abstractmethod
    async def list_models(self) -> list[dict]:
        """Return [{"id": ..., "name": ..., "size": ...}, ...]"""
        ...

    async def is_available(self) -> bool:
        try:
            models = await self.list_models()
            return True
        except Exception:
            return False


# ── Ollama ────────────────────────────────────────────────────────────

class OllamaBackend(LLMBackend):
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: str = "",
        images: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        formatted = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + messages
        # Attach base64 images to the last user message (Ollama multimodal)
        if images:
            for i in range(len(formatted) - 1, -1, -1):
                if formatted[i]["role"] == "user":
                    formatted[i] = dict(formatted[i])
                    formatted[i]["images"] = images
                    break
        payload = {
            "model": model,
            "messages": formatted,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break

    async def list_models(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            raw = resp.json().get("models", [])
        out = []
        for m in raw:
            out.append({
                "id": m.get("name", ""),
                "name": m.get("name", "").split(":")[0],
                "size": m.get("size", 0),
                "family": m.get("details", {}).get("family", ""),
                "parameters": m.get("details", {}).get("parameter_size", ""),
                "quantization": m.get("details", {}).get("quantization_level", ""),
                "modified": m.get("modified_at", ""),
            })
        return out

    async def pull_model(self, model_name: str) -> AsyncGenerator[dict, None]:
        """Stream pull progress from Ollama."""
        payload = {"name": model_name, "stream": True}
        async with httpx.AsyncClient(timeout=httpx.Timeout(3600.0, connect=10.0)) as client:
            async with client.stream("POST", f"{self.base_url}/api/pull", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        yield json.loads(line)

    async def delete_model(self, model_name: str) -> bool:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(f"{self.base_url}/api/delete", json={"name": model_name})
            return resp.status_code == 200


# ── OpenAI-compatible (works for OpenAI, LM Studio, vLLM, etc.) ──────

class OpenAIBackend(LLMBackend):
    name = "openai"

    def __init__(self, api_key: str = "", base_url: str = "https://api.openai.com/v1",
                 default_model: str = "gpt-4o", extra_headers: dict | None = None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.extra_headers = extra_headers or {}

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: str = "",
        images: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        model = model or self.default_model
        all_messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + [
            dict(m) for m in messages
        ]
        # Attach images to the last user message as multimodal content
        if images:
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
        payload = {
            "model": model,
            "messages": all_messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions",
                                     json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        yield token

    async def list_models(self) -> list[dict]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/models", headers=headers)
            resp.raise_for_status()
            raw = resp.json().get("data", [])
        return [{"id": m["id"], "name": m["id"], "size": 0} for m in raw]


# ── Anthropic (Claude) ────────────────────────────────────────────────

class AnthropicBackend(LLMBackend):
    name = "anthropic"

    def __init__(self, api_key: str = "", default_model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.base_url = "https://api.anthropic.com/v1"
        self.default_model = default_model

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: str = "",
    ) -> AsyncGenerator[str, None]:
        model = model or self.default_model
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "stream": True,
            "messages": messages,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", f"{self.base_url}/messages",
                                     json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data = json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        token = data.get("delta", {}).get("text", "")
                        if token:
                            yield token
                    elif data.get("type") == "message_stop":
                        break

    async def list_models(self) -> list[dict]:
        return [
            {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "size": 0},
            {"id": "claude-opus-4-20250514", "name": "Claude Opus 4", "size": 0},
            {"id": "claude-haiku-3-5-20241022", "name": "Claude 3.5 Haiku", "size": 0},
        ]


# ── Google Gemini ─────────────────────────────────────────────────────

class GoogleBackend(LLMBackend):
    name = "google"

    def __init__(self, api_key: str = "", default_model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.default_model = default_model

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: str = "",
    ) -> AsyncGenerator[str, None]:
        model = model or self.default_model
        # Convert chat format to Gemini
        contents = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:streamGenerateContent?alt=sse&key={self.api_key}"
        )

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data = json.loads(line[6:])
                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    for part in parts:
                        token = part.get("text", "")
                        if token:
                            yield token

    async def list_models(self) -> list[dict]:
        return [
            {"id": "gemini-2.5-pro-preview-05-06", "name": "Gemini 2.5 Pro", "size": 0},
            {"id": "gemini-2.5-flash-preview-05-20", "name": "Gemini 2.5 Flash", "size": 0},
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "size": 0},
        ]


# ── Local GGUF (llama-cpp-python) ─────────────────────────────────────

# VL model filename keywords
_VL_KEYWORDS = {
    "llava", "bakllava", "moondream", "minicpm-v", "cogvlm", "vision",
    "qwen-vl", "yi-vl", "llava-next", "idefics", "internvl", "xgen-mm",
    "llavaphi", "nanollava", "bunny", "vl", "multimodal", "obsidian",
}


def is_vl_model(model_path: str) -> bool:
    """Return True if the model filename suggests it is a vision-language model."""
    import pathlib
    name = pathlib.Path(model_path).stem.lower()
    return any(kw in name for kw in _VL_KEYWORDS)


class LocalGGUFBackend(LLMBackend):
    """Run GGUF models locally via llama-cpp-python."""
    name = "local"

    # Class-level cache: keep ONE model loaded at a time
    _loaded_path: str = ""
    _loaded_mmproj: str = ""
    _llm = None

    def __init__(self, n_gpu_layers: int = -1, n_ctx: int = 8192,
                 mmproj_path: str = ""):
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.mmproj_path = mmproj_path

    def _ensure_model(self, model_path: str):
        """Load model if not already loaded, or swap if path/mmproj changed."""
        mmproj = self.mmproj_path or ""
        if (LocalGGUFBackend._loaded_path == model_path
                and LocalGGUFBackend._loaded_mmproj == mmproj
                and LocalGGUFBackend._llm is not None):
            return LocalGGUFBackend._llm

        # Release old model
        if LocalGGUFBackend._llm is not None:
            try:
                del LocalGGUFBackend._llm
            except Exception:
                pass
            LocalGGUFBackend._llm = None
            LocalGGUFBackend._loaded_path = ""
            LocalGGUFBackend._loaded_mmproj = ""

        import gc
        gc.collect()

        try:
            from llama_cpp import Llama
        except ImportError:
            raise RuntimeError(
                "llama-cpp-python is not installed.\n"
                "To use Local GGUF models, run:\n"
                "  pip install llama-cpp-python\n"
                "Or switch to Ollama (free, no install needed) in the backend selector."
            )

        kwargs: dict = {
            "model_path": model_path,
            "n_gpu_layers": self.n_gpu_layers,
            "n_ctx": self.n_ctx,
            "verbose": False,
        }
        if mmproj:
            import pathlib
            if pathlib.Path(mmproj).is_file():
                kwargs["clip_model_path"] = mmproj
                # Let llama-cpp-python auto-detect the right chat format
                # based on the model's metadata (chatml, llama-3, etc.)

        LocalGGUFBackend._llm = Llama(**kwargs)
        LocalGGUFBackend._loaded_path = model_path
        LocalGGUFBackend._loaded_mmproj = mmproj
        return LocalGGUFBackend._llm

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: str = "",
        images: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        if not model:
            raise ValueError("No model path specified. Select a local GGUF model first.")

        import pathlib
        if not pathlib.Path(model).is_file():
            raise FileNotFoundError(f"Model file not found: {model}")

        # Load model in thread to avoid blocking event loop
        llm = await asyncio.to_thread(self._ensure_model, model)

        all_messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + [
            dict(m) for m in messages
        ]
        # Attach images for LLaVA / VL models (requires mmproj)
        if images and self.mmproj_path:
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

        # Use a queue to bridge sync generator → async generator
        import queue
        q: queue.Queue = queue.Queue()
        _DONE = object()

        def _produce():
            try:
                for chunk in llm.create_chat_completion(
                    messages=all_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                ):
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        q.put(token)
            except Exception as e:
                q.put(e)
            finally:
                q.put(_DONE)

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, _produce)

        while True:
            item = await asyncio.to_thread(q.get)
            if item is _DONE:
                break
            if isinstance(item, Exception):
                raise item
            yield item

    async def list_models(self) -> list[dict]:
        """Return currently loaded model if any."""
        if LocalGGUFBackend._loaded_path:
            import pathlib
            p = pathlib.Path(LocalGGUFBackend._loaded_path)
            return [{
                "id": LocalGGUFBackend._loaded_path,
                "name": p.stem,
                "size": p.stat().st_size if p.exists() else 0,
            }]
        return []


# ── Factory ───────────────────────────────────────────────────────────

# Singleton local backend to preserve model cache across requests
_local_backend: LocalGGUFBackend | None = None


def create_backend(name: str, cfg: dict) -> LLMBackend:
    """Instantiate a backend from config dict."""
    global _local_backend
    backends_cfg = cfg.get("backends", {})
    if name == "local":
        lc = backends_cfg.get("local", {})
        llm_params = cfg.get("llm_params", {})
        new_mmproj = lc.get("mmproj_path", "")
        if _local_backend is None:
            _local_backend = LocalGGUFBackend(
                n_gpu_layers=lc.get("n_gpu_layers", -1),
                n_ctx=llm_params.get("context_length", 8192),
                mmproj_path=new_mmproj,
            )
        elif _local_backend.mmproj_path != new_mmproj:
            # mmproj changed — update and force model reload
            _local_backend.mmproj_path = new_mmproj
            LocalGGUFBackend._llm = None
            LocalGGUFBackend._loaded_path = ""
            LocalGGUFBackend._loaded_mmproj = ""
        return _local_backend
    elif name == "ollama":
        return OllamaBackend(base_url=backends_cfg.get("ollama", {}).get("base_url", "http://localhost:11434"))
    elif name == "openai":
        oc = backends_cfg.get("openai", {})
        return OpenAIBackend(api_key=oc.get("api_key", ""), base_url=oc.get("base_url", "https://api.openai.com/v1"))
    elif name == "anthropic":
        return AnthropicBackend(api_key=backends_cfg.get("anthropic", {}).get("api_key", ""))
    elif name == "google":
        return GoogleBackend(api_key=backends_cfg.get("google", {}).get("api_key", ""))
    elif name == "custom":
        cc = backends_cfg.get("custom", {})
        return OpenAIBackend(api_key=cc.get("api_key", ""), base_url=cc.get("base_url", "http://localhost:1234/v1"))
    elif name == "openrouter":
        rc = backends_cfg.get("openrouter", {})
        return OpenAIBackend(
            api_key=rc.get("api_key", ""),
            base_url="https://openrouter.ai/api/v1",
            extra_headers={
                "HTTP-Referer": rc.get("site_url", "https://github.com/Kronic90/Mimirs-Memory-Hub"),
                "X-Title": rc.get("site_title", "Mimir's Memory Hub"),
            },
        )
    elif name == "vllm":
        vc = backends_cfg.get("vllm", {})
        return OpenAIBackend(
            api_key=vc.get("api_key", ""),
            base_url=vc.get("base_url", "http://localhost:8000/v1"),
        )
    elif name == "openai_compat":
        oc = backends_cfg.get("openai_compat", {})
        return OpenAIBackend(
            api_key=oc.get("api_key", ""),
            base_url=oc.get("base_url", "http://localhost:5000/v1"),
        )
    else:
        return OllamaBackend()
