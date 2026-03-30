"""Persistent configuration for Mimir's Well."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

_DEFAULT: dict[str, Any] = {
    "active_backend": "ollama",
    "active_model": "",
    "active_preset": "companion",
    "active_profile": "default",
    "active_character_id": "",
    "backends": {
        "ollama": {"base_url": "http://localhost:11434"},
        "openai": {"api_key": "", "base_url": "https://api.openai.com/v1"},
        "anthropic": {"api_key": ""},
        "google": {"api_key": ""},
        "custom": {"base_url": "", "api_key": "", "label": "Custom (OpenAI-compatible)"},
    },
    "system_prompt": "",
    "persona_name": "",
    "persona_description": "",
    "llm_params": {
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 2048,
        "context_length": 32768,
    },
    "memory": {
        "enabled": True,
        "auto_remember": True,
        "chemistry": True,
    },
    "tts": {
        "enabled": True,
        "mode": "edge",
        "voice": "en-US-JennyNeural",
        "model_path": "maya-research/maya1",
        "server_url": "http://localhost:8081",
    },
    "stt": {
        "enabled": True,
        "model_size": "base",
        "device": "auto",
    },
    "scan_directories": [],
}

_CFG_DIR = Path(__file__).resolve().parent.parent / "playground_data"
_CFG_FILE = _CFG_DIR / "settings.json"


class Config:
    """Thread-safe, auto-persisting settings singleton."""

    _instance: Config | None = None

    def __new__(cls) -> Config:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
            cls._instance._load()
        return cls._instance

    # ── public ────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def update(self, patch: dict) -> None:
        self._deep_merge(self._data, patch)
        self._save()

    def to_dict(self) -> dict:
        return dict(self._data)

    @property
    def profile_dir(self) -> Path:
        p = _CFG_DIR / "profiles" / self._data.get("active_profile", "default")
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ── internal ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if _CFG_FILE.exists():
            with open(_CFG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self._data = dict(_DEFAULT)
            self._deep_merge(self._data, saved)
        else:
            self._data = dict(_DEFAULT)
            self._save()

    def _save(self) -> None:
        _CFG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CFG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _deep_merge(base: dict, overlay: dict) -> None:
        for k, v in overlay.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                Config._deep_merge(base[k], v)
            else:
                base[k] = v
