"""Mimir persistence mixin — save, load, JSON I/O, migration."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .constants import (
    _NeuroChemistry, _EmotionalAuditLog, _VividEmbed,
    _Fernet, _PBKDF2, _crypto_hashes,
    FLASHBULB_AROUSAL_THRESHOLD, FLASHBULB_IMPORTANCE_MIN,
)
from .helpers import _emotion_to_vector, _extract_dates
from .models import (
    Memory, Lesson, Reminder, ShortTermFact,
    TaskRecord, ActionRecord, SolutionPattern, ArtifactRecord,
)


class PersistenceMixin:
    """Mixin providing save/load, JSON I/O with optional encryption,
    and VividnessMem migration."""

    # ══════════════════════════════════════════════════════════════════
    #  Migration — import from VividnessMem / Lela
    # ══════════════════════════════════════════════════════════════════

    @classmethod
    def migrate_from_vividnessmem(cls, src_dir: str | Path,
                                  dest_dir: str | Path | None = None
                                  ) -> "PersistenceMixin":
        """Import memories from a VividnessMem data directory."""
        src = Path(src_dir)
        dst = Path(dest_dir) if dest_dir else src

        def _rj(p: Path):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return None

        brief = _rj(src / "brief.json") or {}
        mood_list = brief.get("mood", [0.0, 0.0, 0.0])
        mood_tuple = tuple(mood_list) if isinstance(mood_list, list) else (0.0, 0.0, 0.0)

        raw_mems = _rj(src / "self_memory.json") or []

        raw_social: dict[str, list[dict]] = {}
        social_dir = src / "social"
        if social_dir.exists():
            for fp in social_dir.glob("*.json"):
                data = _rj(fp)
                if isinstance(data, list) and data:
                    entity = data[0].get("entity", fp.stem)
                    raw_social[entity] = data

        raw_chem = _rj(src / "neurochemistry.json")

        def _backfill(d: dict) -> dict:
            if "encoding_mood" not in d:
                d["encoding_mood"] = list(mood_tuple)
            if "emotion_pad" not in d:
                vec = _emotion_to_vector(d.get("emotion", "neutral"))
                d["emotion_pad"] = list(vec) if vec else None
            if "mentioned_dates" not in d:
                d["mentioned_dates"] = _extract_dates(
                    d.get("content", ""))
            if "is_flashbulb" not in d:
                imp = d.get("importance", 5)
                emo = d.get("emotion", "neutral")
                vec = _emotion_to_vector(emo)
                arousal = abs(vec[1]) if vec else 0.0
                d["is_flashbulb"] = (
                    arousal >= FLASHBULB_AROUSAL_THRESHOLD
                    and imp >= FLASHBULB_IMPORTANCE_MIN)
            return d

        backfilled_mems = [_backfill(dict(d)) for d in raw_mems]
        backfilled_social = {
            entity: [_backfill(dict(d)) for d in mems]
            for entity, mems in raw_social.items()
        }

        dst = Path(dst)
        dst.mkdir(parents=True, exist_ok=True)

        def _wj(p: Path, data):
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            tmp.replace(p)

        _wj(dst / "reflections.json", backfilled_mems)

        social_out = dst / "social"
        social_out.mkdir(parents=True, exist_ok=True)
        for entity, mems in backfilled_social.items():
            fname = re.sub(r'[^\w]', '_', entity.lower()) + ".json"
            _wj(social_out / fname, mems)

        _wj(dst / "meta.json", {"mood": list(mood_tuple),
                                "session_count": brief.get("session_count", 0)})

        if raw_chem:
            _wj(dst / "chemistry.json", raw_chem)

        for name in ("lessons.json", "reminders.json", "facts.json"):
            p = dst / name
            if not p.exists():
                _wj(p, [])

        audit_src = src / "emotional_audit.jsonl"
        if audit_src.exists():
            import shutil
            shutil.copy2(audit_src, dst / "emotional_audit.jsonl")

        embed_src = src / "embed_index"
        embed_dst = dst / "embed"
        if embed_src.exists():
            import shutil
            embed_dst.mkdir(parents=True, exist_ok=True)
            for fp in embed_src.glob("*"):
                if fp.is_file():
                    shutil.copy2(fp, embed_dst / fp.name)

        instance = cls(data_dir=str(dst), chemistry=raw_chem is not None)

        if (instance._embed is not None
                and not instance._embed._entries):
            all_dicts = list(backfilled_mems)
            for mems in backfilled_social.values():
                all_dicts.extend(mems)
            try:
                instance._embed.index_from_vividnessmem(all_dicts)
                instance._embed.save()
            except Exception:
                pass

        return instance

    # ──────────────────────────────────────────────────────────────────
    #  Persistence: save
    # ──────────────────────────────────────────────────────────────────

    def save(self):
        """Persist all memory data to disk."""
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._write_json(
            self._data_dir / "reflections.json",
            [m.to_dict() for m in self._reflections])

        social_dir = self._data_dir / "social"
        social_dir.mkdir(exist_ok=True)
        for entity, impressions in self._social.items():
            fname = re.sub(r'[^\w]', '_', entity.lower()) + ".json"
            self._write_json(
                social_dir / fname,
                [m.to_dict() for m in impressions])

        self._write_json(
            self._data_dir / "lessons.json",
            [l.to_dict() for l in self._lessons])

        self._write_json(
            self._data_dir / "reminders.json",
            [r.to_dict() for r in self._reminders])

        self._write_json(
            self._data_dir / "facts.json",
            [f.to_dict() for f in self._facts])

        if self._chemistry.enabled:
            self._write_json(
                self._data_dir / "chemistry.json",
                self._chemistry.to_dict())

        self._write_json(
            self._data_dir / "meta.json",
            {"mood": list(self._mood),
             "session_count": self._session_count,
             "active_project": self._active_project})

        self._write_json(
            self._data_dir / "tasks.json",
            [t.to_dict() for t in self._project_tasks])
        self._write_json(
            self._data_dir / "actions.json",
            [a.to_dict() for a in self._project_actions])
        self._write_json(
            self._data_dir / "solutions.json",
            [s.to_dict() for s in self._solutions])
        self._write_json(
            self._data_dir / "artifacts.json",
            [a.to_dict() for a in self._artifacts])

        if self._inferred_edges:
            edges_serializable = {
                f"{k[0]},{k[1]}": v
                for k, v in self._inferred_edges.items()}
            self._write_json(
                self._data_dir / "inferred_edges.json",
                edges_serializable)

        # ── Memory Attic (archived pruned memories) ──────────────────
        if self._attic:
            self._write_json(
                self._data_dir / "attic.json",
                [m.to_dict() for m in self._attic])

        # ── Persistent mood history ──────────────────────────────────
        if self._mood_history:
            self._write_json(
                self._data_dir / "mood_history.json",
                self._mood_history)

        if self._embed is not None:
            try:
                self._embed.save()
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────────
    #  Persistence: _load
    # ──────────────────────────────────────────────────────────────────

    def _load(self):
        """Load persisted data from disk."""
        rpath = self._data_dir / "reflections.json"
        if rpath.exists():
            data = self._read_json(rpath)
            if isinstance(data, list):
                self._reflections = [Memory.from_dict(d) for d in data]
                self._rebuild_index()

        social_dir = self._data_dir / "social"
        if social_dir.exists():
            for f in social_dir.glob("*.json"):
                data = self._read_json(f)
                if isinstance(data, list) and data:
                    entity = data[0].get("entity", f.stem)
                    self._social[entity] = [
                        Memory.from_dict(d) for d in data]

        lpath = self._data_dir / "lessons.json"
        if lpath.exists():
            data = self._read_json(lpath)
            if isinstance(data, list):
                self._lessons = [Lesson.from_dict(d) for d in data]

        rpath = self._data_dir / "reminders.json"
        if rpath.exists():
            data = self._read_json(rpath)
            if isinstance(data, list):
                self._reminders = [Reminder.from_dict(d) for d in data]

        fpath = self._data_dir / "facts.json"
        if fpath.exists():
            data = self._read_json(fpath)
            if isinstance(data, list):
                self._facts = [ShortTermFact.from_dict(d) for d in data]

        cpath = self._data_dir / "chemistry.json"
        if cpath.exists() and _NeuroChemistry is not None:
            data = self._read_json(cpath)
            if isinstance(data, dict):
                try:
                    self._chemistry = _NeuroChemistry.from_dict(data)
                except Exception:
                    pass

        mpath = self._data_dir / "meta.json"
        if mpath.exists():
            data = self._read_json(mpath)
            if isinstance(data, dict):
                mood = data.get("mood", [0, 0, 0])
                self._mood = tuple(mood)
                self._session_count = data.get("session_count", 0)
                self._active_project = data.get("active_project", "")

        tpath = self._data_dir / "tasks.json"
        if tpath.exists():
            data = self._read_json(tpath)
            if isinstance(data, list):
                self._project_tasks = [TaskRecord.from_dict(d) for d in data]

        apath = self._data_dir / "actions.json"
        if apath.exists():
            data = self._read_json(apath)
            if isinstance(data, list):
                self._project_actions = [ActionRecord.from_dict(d) for d in data]

        spath = self._data_dir / "solutions.json"
        if spath.exists():
            data = self._read_json(spath)
            if isinstance(data, list):
                self._solutions = [SolutionPattern.from_dict(d) for d in data]

        artpath = self._data_dir / "artifacts.json"
        if artpath.exists():
            data = self._read_json(artpath)
            if isinstance(data, list):
                self._artifacts = [ArtifactRecord.from_dict(d) for d in data]

        iepath = self._data_dir / "inferred_edges.json"
        if iepath.exists():
            data = self._read_json(iepath)
            if isinstance(data, dict):
                self._inferred_edges = {}
                for key_str, strength in data.items():
                    parts = key_str.split(",")
                    if len(parts) == 2:
                        try:
                            self._inferred_edges[
                                (int(parts[0]), int(parts[1]))] = float(strength)
                        except ValueError:
                            pass

        # ── Memory Attic ─────────────────────────────────────────
        attic_path = self._data_dir / "attic.json"
        if attic_path.exists():
            data = self._read_json(attic_path)
            if isinstance(data, list):
                self._attic = [Memory.from_dict(d) for d in data]

        # ── Persistent mood history ──────────────────────────────────
        mh_path = self._data_dir / "mood_history.json"
        if mh_path.exists():
            data = self._read_json(mh_path)
            if isinstance(data, list):
                self._mood_history = data

        if len(self._reflections) >= 2:
            self._build_yggdrasil()

    # ──────────────────────────────────────────────────────────────────
    #  Internal: JSON I/O  (with optional encryption at rest)
    # ──────────────────────────────────────────────────────────────────

    def _write_json(self, path: Path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
        if self._fernet is not None:
            raw = self._fernet.encrypt(raw)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                f.write(raw)
            tmp.replace(path)
        else:
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(raw.decode("utf-8"))
            tmp.replace(path)

    def _read_json(self, path: Path):
        try:
            if self._fernet is not None:
                with open(path, "rb") as f:
                    raw = self._fernet.decrypt(f.read())
                return json.loads(raw.decode("utf-8"))
            else:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, Exception):
            return None
