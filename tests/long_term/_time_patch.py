"""Shared helper for audit tests that need REAL simulated-time control over
vividness decay, stability, and consolidation timing.

Why this exists
----------------
`tests/long_term/harness.py`'s `TimeWarp.patched()` only monkeypatches
`time.time`. The entire vividmimir engine (models.py, core.py, write_mixin.py,
recall_mixin.py, neuroscience_mixin.py, yggdrasil_mixin.py, llm_mixin.py,
persistence_mixin.py) computes memory age via `datetime.now()`, which that
patch never touches. See test_audit_timewarp_bug.py for the direct proof.

This module provides a FixedHarness that additionally monkeypatches
`datetime.datetime` (via a subclass whose `.now()` is offset) in every
vividmimir module that imports it, so tests that actually need simulated
aging to take effect (vividness decay, visual fading, stability, Yggdrasil
temporal edges, gist compression, consolidation cadence) can get it.
"""
from __future__ import annotations

import datetime as _dt_module
import sys
import time as _time_module
from contextlib import contextmanager
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_real_datetime = _dt_module.datetime
_real_time = _time_module.time

_PATCHED_MODULES = [
    "vividmimir.core", "vividmimir.models", "vividmimir.helpers",
    "vividmimir.write_mixin", "vividmimir.recall_mixin",
    "vividmimir.neuroscience_mixin", "vividmimir.yggdrasil_mixin",
    "vividmimir.llm_mixin", "vividmimir.persistence_mixin",
]


class _OffsetRef:
    """Mutable box holding the current simulated-day offset."""
    def __init__(self):
        self.days = 0.0


def _make_fake_datetime(ref: _OffsetRef):
    class FakeDateTime(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return _real_datetime.now(tz) + _dt_module.timedelta(days=ref.days)
    return FakeDateTime


class FullTimeWarp:
    """Patches both time.time() and datetime.datetime.now() across every
    vividmimir module, so simulated day advances actually age memories."""

    def __init__(self):
        self.ref = _OffsetRef()
        self._fake_cls = _make_fake_datetime(self.ref)
        self._originals: dict[str, object] = {}
        self._active = False

    def start(self):
        if self._active:
            return
        for modname in _PATCHED_MODULES:
            __import__(modname)
            mod = sys.modules[modname]
            if hasattr(mod, "datetime"):
                self._originals[modname] = mod.datetime
                mod.datetime = self._fake_cls
        ref = self.ref

        def fake_time():
            return _real_time() + ref.days * 86400
        _time_module.time = fake_time
        self._active = True

    def stop(self):
        if not self._active:
            return
        for modname, orig in self._originals.items():
            sys.modules[modname].datetime = orig
        _time_module.time = _real_time
        self._active = False

    def advance_days(self, days: float):
        self.ref.days += days

    @contextmanager
    def active(self):
        self.start()
        try:
            yield self
        finally:
            self.stop()


class FixedHarness:
    """Drop-in replacement for SimulationHarness whose time control actually
    reaches vividness/stability/decay math. Wraps a real MemoryManager built
    while the fake clock is active, so even construction-time timestamps are
    simulated."""

    def __init__(self, test_name: str, preset_name: str = "companion",
                 chemistry: bool = True, llm_fn=None):
        self.warp = FullTimeWarp()
        self.warp.start()
        import tempfile
        import os
        self._tmpdir = tempfile.mkdtemp(prefix=f"mimir_audit_{test_name}_")
        self._profile_dir = os.path.join(self._tmpdir, "profile")
        os.makedirs(self._profile_dir, exist_ok=True)
        from playground.memory_manager import MemoryManager
        from playground.presets import get_preset
        self.preset = get_preset(preset_name)
        self.manager = MemoryManager(
            profile_dir=self._profile_dir, chemistry=chemistry)
        if llm_fn is not None:
            self.manager._mimir._llm_fn = llm_fn

    def advance_days(self, days: float):
        self.warp.advance_days(days)

    def advance_weeks(self, weeks: float):
        self.warp.advance_days(weeks * 7)

    def remember(self, content: str, emotion: str = "neutral",
                 importance: int = 5, source: str = "conversation",
                 why: str = ""):
        return self.manager.remember(
            content=content, emotion=emotion, importance=importance,
            source=source, why_saved=why or "audit test memory")

    def mem_obj(self, idx: int = -1):
        return self.manager._mimir._reflections[idx]

    def recall(self, query: str, limit: int = 10):
        return self.manager.recall(query, limit=limit)

    def close(self):
        self.warp.stop()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
