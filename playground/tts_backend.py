"""Maya1 Text-to-Speech backend for Mimir's Memory Hub.

Two inference modes:
  'hf'           — load Maya1 via HuggingFace Transformers (requires ~6 GB VRAM or runs on CPU)
  'llama_server' — delegate to a llama-server hosting the Maya1 GGUF.
                   Uses /completion with raw token-ID array (avoids Jinja-template garbling).
                   Requires: llama-server running with disable-template flag or /completion endpoint.

Maya1 token constants (same IDs as official reference code):
  CODE_START  128257  — SOS: "start of audio codes"
  CODE_END    128258  — EOS for audio generation
  SOH         128259  — Start of Header
  EOH         128260  — End of Header
  SOA         128261  — Start of Audio
  BOS         128000
  TEXT_EOT    128009
  SNAC range  128266–156937 (28671 codes × 7-token frames)

Prompt format: SOH + BOS + '<description="..."> text' + TEXT_EOT + EOH + SOA + CODE_START
"""
from __future__ import annotations

import io
import re as _re
import threading
from typing import Optional

# ── Maya1 special token IDs ──────────────────────────────────────────────────
_CODE_START  = 128257
_CODE_END    = 128258
_SOH         = 128259
_EOH         = 128260
_SOA         = 128261
_BOS         = 128000
_TEXT_EOT    = 128009
_SNAC_MIN    = 128266
_SNAC_MAX    = 156937
_SNAC_OFFSET = 128266

# llama-server GGUF outputs custom tokens as "<custom_token_N>"
_CUSTOM_TOKEN_RE = _re.compile(r'<custom_token_(\d+)>')

# Strip markdown from TTS text — keep actual words, drop symbols
_MD_RE = _re.compile(
    r'\*{1,3}(.*?)\*{1,3}'      # **bold** / *italic*
    r'|`{1,3}[^`]*`{1,3}'       # `code` / ```block```
    r'|\[([^\]]+)\]\([^\)]+\)'  # [link text](url) → keep display text
    r'|#{1,6}\s+',              # ## headings
    _re.DOTALL,
)


def _strip_markdown(text: str) -> str:
    def _repl(m: _re.Match) -> str:
        return (m.group(1) or m.group(2) or "")
    return _MD_RE.sub(_repl, text).strip()


def _tts_segment(text: str, max_chars: int = 500) -> str:
    """Return an appropriate-length segment for TTS synthesis."""
    if len(text) <= max_chars:
        return text
    # Prefer to break at a sentence boundary
    for punct in (".", "!", "?", "\n"):
        idx = text.rfind(punct, 0, max_chars)
        if idx > max_chars // 3:
            return text[: idx + 1]
    return text[:max_chars]


# ── SNAC decoder (module-level singleton — shared across all instances) ───────
_snac_model     = None
_snac_lock      = threading.Lock()


def _get_snac():
    global _snac_model
    if _snac_model is None:
        with _snac_lock:
            if _snac_model is None:
                import torch
                from snac import SNAC  # pip install snac
                m = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval()
                if torch.cuda.is_available():
                    m = m.to("cuda")
                _snac_model = m
    return _snac_model


def _extract_snac(token_ids: list[int]) -> list[int]:
    """Keep only SNAC-range tokens up to (not including) CODE_END."""
    try:
        eos = token_ids.index(_CODE_END)
    except ValueError:
        eos = len(token_ids)
    return [t for t in token_ids[:eos] if _SNAC_MIN <= t <= _SNAC_MAX]


def _unpack_snac(snac_tokens: list[int]) -> list[list[int]]:
    """Unpack 7-token SNAC frames → three hierarchical codec levels."""
    frames = len(snac_tokens) // 7
    snac_tokens = snac_tokens[: frames * 7]
    l1, l2, l3 = [], [], []
    for i in range(frames):
        s = snac_tokens[i * 7 : (i + 1) * 7]
        l1.append((s[0] - _SNAC_OFFSET) % 4096)
        l2.extend([
            (s[1] - _SNAC_OFFSET) % 4096,
            (s[4] - _SNAC_OFFSET) % 4096,
        ])
        l3.extend([
            (s[2] - _SNAC_OFFSET) % 4096,
            (s[3] - _SNAC_OFFSET) % 4096,
            (s[5] - _SNAC_OFFSET) % 4096,
            (s[6] - _SNAC_OFFSET) % 4096,
        ])
    return [l1, l2, l3]


def _snac_to_wav(snac_tokens: list[int]) -> bytes:
    """Decode raw SNAC token IDs → 16-bit PCM WAV at 24 kHz."""
    levels = _unpack_snac(snac_tokens)
    if not levels[0]:
        return b""
    import torch
    import soundfile as sf  # pip install soundfile
    snac = _get_snac()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    codes = [
        torch.tensor(lv, dtype=torch.long, device=device).unsqueeze(0)
        for lv in levels
    ]
    with torch.inference_mode():
        z_q = snac.quantizer.from_codes(codes)
        audio = snac.decoder(z_q)[0, 0].cpu().numpy()
    # Trim ~85 ms warmup artefact
    if len(audio) > 2048:
        audio = audio[2048:]
    buf = io.BytesIO()
    sf.write(buf, audio, 24000, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# ── TTS Backend ──────────────────────────────────────────────────────────────

class MayaTTSBackend:
    """Maya1 TTS — lazy-loads model on first call, unloads on demand.

    Config keys consumed from cfg['tts']:
      enabled      bool   — False disables all TTS silently
      mode         str    — 'hf' | 'llama_server'
      model_path   str    — HF repo id or local dir (HF mode)
      server_url   str    — llama-server base URL (GGUF mode)
    """

    def __init__(self, cfg: dict):
        tts = cfg.get("tts", {})
        self.enabled    = tts.get("enabled", True)
        self.mode       = tts.get("mode", "hf")          # "hf" | "llama_server"
        self.model_path = tts.get("model_path", "maya-research/maya1")
        self.server_url = tts.get("server_url", "http://localhost:8081").rstrip("/")
        self._model     = None
        self._tokenizer = None
        self._lock      = threading.Lock()
        self._last_error = ""
        self._deps_ok   = None   # None = unchecked

    # ── Public ───────────────────────────────────────────────────────────────

    @property
    def status(self) -> dict:
        """Return dependency / readiness status."""
        if not self.enabled:
            return {"enabled": False, "ready": False, "error": "Disabled in settings"}
        if self._deps_ok is None:
            self._check_deps()
        return {
            "enabled": True,
            "ready": self._deps_ok,
            "error": self._last_error,
            "mode": self.mode,
        }

    def _check_deps(self):
        missing = []
        for mod in ("torch", "transformers", "snac", "soundfile"):
            try:
                __import__(mod)
            except ImportError:
                missing.append(mod)
        if missing:
            self._deps_ok = False
            self._last_error = f"Missing packages: {', '.join(missing)}. Run: pip install {' '.join(missing)}"
        else:
            self._deps_ok = True
            self._last_error = ""

    def generate_audio(self, text: str, voice_prompt: str = "") -> bytes:
        """Return WAV bytes or b'' (disabled / error / not enough SNAC tokens)."""
        if not self.enabled or not text.strip():
            return b""
        description = voice_prompt.strip() or "Clear, natural conversational voice."
        clean = _strip_markdown(text)
        segment = _tts_segment(clean)
        if not segment:
            return b""
        try:
            if self.mode == "llama_server":
                return self._gen_gguf(segment, description)
            return self._gen_hf(segment, description)
        except ImportError as e:
            self._deps_ok = False
            self._last_error = f"Missing package: {e.name}"
            return b""
        except Exception as e:
            self._last_error = str(e)
            return b""

    def unload(self):
        """Release model memory."""
        self._model = None
        self._tokenizer = None

    # ── HF Transformers mode ─────────────────────────────────────────────────

    def _ensure_hf(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    import torch
                    from transformers import AutoModelForCausalLM, AutoTokenizer
                    self._tokenizer = AutoTokenizer.from_pretrained(
                        self.model_path, trust_remote_code=True
                    )
                    self._model = AutoModelForCausalLM.from_pretrained(
                        self.model_path,
                        torch_dtype=torch.bfloat16,
                        device_map="auto",
                        trust_remote_code=True,
                    ).eval()

    def _build_hf_prompt(self, description: str, text: str) -> str:
        tok = self._tokenizer
        soh = tok.decode([_SOH])
        eoh = tok.decode([_EOH])
        soa = tok.decode([_SOA])
        sos = tok.decode([_CODE_START])
        eot = tok.decode([_TEXT_EOT])
        bos = tok.bos_token
        return soh + bos + f'<description="{description}"> {text}' + eot + eoh + soa + sos

    def _gen_hf(self, text: str, description: str) -> bytes:
        import torch
        self._ensure_hf()
        prompt = self._build_hf_prompt(description, text)
        inputs = self._tokenizer(prompt, return_tensors="pt")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.inference_mode():
            out = self._model.generate(
                **inputs,
                max_new_tokens=2048,
                min_new_tokens=28,
                temperature=0.4,
                top_p=0.9,
                repetition_penalty=1.1,
                do_sample=True,
                eos_token_id=_CODE_END,
                pad_token_id=self._tokenizer.pad_token_id,
            )
        generated = out[0, inputs["input_ids"].shape[1] :].tolist()
        snac_tokens = _extract_snac(generated)
        if len(snac_tokens) < 7:
            return b""
        return _snac_to_wav(snac_tokens)

    # ── llama-server GGUF mode ───────────────────────────────────────────────

    def _build_gguf_token_ids(self, description: str, text: str) -> list[int]:
        """Ask llama-server to tokenize the text portion; prepend/append special IDs."""
        import requests
        formatted = f'<description="{description}"> {text}'
        resp = requests.post(
            f"{self.server_url}/tokenize",
            json={"content": formatted, "add_special": False},
            timeout=15,
        )
        resp.raise_for_status()
        text_ids: list[int] = resp.json().get("tokens", [])
        # Full prompt token sequence: SOH BOS <text_ids> TEXT_EOT EOH SOA CODE_START
        return [_SOH, _BOS] + text_ids + [_TEXT_EOT, _EOH, _SOA, _CODE_START]

    def _gen_gguf(self, text: str, description: str) -> bytes:
        """Generate via llama-server /completion with token-ID prompt array."""
        import requests
        prompt_ids = self._build_gguf_token_ids(description, text)
        payload = {
            "prompt": prompt_ids,   # llama-server accepts int[] as prompt
            "n_predict": 2048,
            "temperature": 0.4,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "stop": [],
        }
        resp = requests.post(
            f"{self.server_url}/completion",
            json=payload,
            timeout=180,
        )
        resp.raise_for_status()
        content: str = resp.json().get("content", "")
        # Parse "<custom_token_N>" → raw token IDs in SNAC range
        snac_tokens = []
        for m in _CUSTOM_TOKEN_RE.finditer(content):
            tid = _SNAC_OFFSET + int(m.group(1))
            if _SNAC_MIN <= tid <= _SNAC_MAX:
                snac_tokens.append(tid)
        if len(snac_tokens) < 7:
            return b""
        return _snac_to_wav(snac_tokens)
