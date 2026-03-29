"""faster-whisper Speech-to-Text backend for Mimir's Memory Hub.

Dependencies:  pip install faster-whisper
               (faster-whisper bundles CTranslate2; no separate install needed)

Config keys consumed from cfg['stt']:
  enabled    bool  — False disables STT silently
  model_size str   — 'tiny' | 'base' | 'small' | 'medium' | 'large-v3'
  device     str   — 'auto' | 'cpu' | 'cuda'

The browser MediaRecorder produces WebM/Opus by default.
faster-whisper (via ffmpeg) handles WebM, WAV, MP3 etc. transparently.
"""
from __future__ import annotations

import io
import threading


class WhisperSTTBackend:
    """STT via faster-whisper — lazy-loads model on first call."""

    def __init__(self, cfg: dict):
        stt = cfg.get("stt", {})
        self.enabled    = stt.get("enabled", True)
        self.model_size = stt.get("model_size", "base")
        self.device     = stt.get("device", "auto")
        self._model     = None
        self._lock      = threading.Lock()
        self._last_error = ""
        self._deps_ok   = None

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
            "model_size": self.model_size,
        }

    def _check_deps(self):
        try:
            __import__("faster_whisper")
            self._deps_ok = True
            self._last_error = ""
        except ImportError:
            self._deps_ok = False
            self._last_error = "Missing package: faster-whisper. Run: pip install faster-whisper"

    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe raw audio bytes → transcript string (empty string on failure)."""
        if not self.enabled or not audio_bytes:
            return ""
        self._ensure_model()
        buf = io.BytesIO(audio_bytes)
        try:
            segments, _ = self._model.transcribe(buf, beam_size=5)
            return " ".join(seg.text for seg in segments).strip()
        except ImportError as e:
            self._deps_ok = False
            self._last_error = f"Missing package: {e.name}"
            return ""
        except Exception as e:
            self._last_error = str(e)
            return ""

    def unload(self):
        """Release model memory."""
        self._model = None

    # ── Internal ─────────────────────────────────────────────────────────────

    def _ensure_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from faster_whisper import WhisperModel  # pip install faster-whisper
                    device = self.device
                    if device == "auto":
                        try:
                            import torch
                            device = "cuda" if torch.cuda.is_available() else "cpu"
                        except ImportError:
                            device = "cpu"
                    compute = "float16" if device == "cuda" else "int8"
                    self._model = WhisperModel(
                        self.model_size, device=device, compute_type=compute
                    )
