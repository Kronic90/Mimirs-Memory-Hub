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
        self.enabled    = stt.get("enabled", False)
        self.model_size = stt.get("model_size", "base")
        self.device     = stt.get("device", "auto")
        self._model     = None
        self._lock      = threading.Lock()

    # ── Public ───────────────────────────────────────────────────────────────

    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe raw audio bytes → transcript string (empty string on failure)."""
        if not self.enabled or not audio_bytes:
            return ""
        self._ensure_model()
        buf = io.BytesIO(audio_bytes)
        try:
            segments, _ = self._model.transcribe(buf, beam_size=5)
            return " ".join(seg.text for seg in segments).strip()
        except Exception:
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
