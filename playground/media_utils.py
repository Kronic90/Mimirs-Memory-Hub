"""Audio helpers for voice messages, and reading what a GGUF projector
(mmproj) file can do -- see, hear, or both."""
from __future__ import annotations

import base64
import io
import os
import struct
import wave

_CAPS_CACHE: dict[tuple[str, float], dict] = {}


def audio_to_wav16k(data: bytes) -> bytes:
    """Any audio the browser records or a user attaches (WebM/Opus, Ogg,
    MP3, M4A, WAV...) -> 16 kHz mono 16-bit WAV, the format speech models
    (Gemma's audio encoder, Whisper) expect. Uses PyAV, which ships with
    faster-whisper. Raises ValueError if it isn't decodable audio."""
    import av  # noqa: WPS433 (bundled with faster-whisper)
    try:
        container = av.open(io.BytesIO(data))
    except Exception as e:
        raise ValueError(f"Couldn't read that audio: {e}")
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    pcm = bytearray()
    try:
        stream = next(s for s in container.streams if s.type == "audio")
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                pcm += out.to_ndarray().tobytes()
        for out in resampler.resample(None):
            pcm += out.to_ndarray().tobytes()
    except StopIteration:
        raise ValueError("That file has no audio in it")
    finally:
        container.close()
    if not pcm:
        raise ValueError("The recording was empty")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(bytes(pcm))
    return buf.getvalue()


def audio_b64_to_wav_b64(b64: str) -> tuple[str, bytes, float]:
    """(wav_b64, wav_bytes, seconds) from a browser/base64 audio payload."""
    if "," in b64[:100] and b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    wav = audio_to_wav16k(base64.b64decode(b64))
    seconds = (len(wav) - 44) / (16000 * 2)
    return base64.b64encode(wav).decode("ascii"), wav, seconds


# ── GGUF metadata (just enough to read a projector's capabilities) ───────

_GGUF_SCALARS = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i",
                 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}


def _read_gguf_kv(path: str, wanted_prefix: str = "clip.") -> dict:
    """Key/value header of a GGUF file (only keys starting with
    wanted_prefix are kept; arrays are skipped). Reads a few KB, not the
    whole multi-GB file."""
    out: dict = {}
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError("not a GGUF file")
        version = struct.unpack("<I", f.read(4))[0]
        if version < 2:
            raise ValueError("GGUF v1 not supported")
        _n_tensors, n_kv = struct.unpack("<QQ", f.read(16))

        def rstr():
            (n,) = struct.unpack("<Q", f.read(8))
            return f.read(n).decode("utf-8", "replace")

        def skip_value(t):
            if t in _GGUF_SCALARS:
                f.read(struct.calcsize(_GGUF_SCALARS[t]))
            elif t == 8:
                rstr()
            elif t == 9:
                et, = struct.unpack("<I", f.read(4))
                (cnt,) = struct.unpack("<Q", f.read(8))
                for _ in range(cnt):
                    skip_value(et)

        for _ in range(min(n_kv, 10000)):
            key = rstr()
            (t,) = struct.unpack("<I", f.read(4))
            if key.startswith(wanted_prefix) and t in _GGUF_SCALARS:
                (out[key],) = struct.unpack(_GGUF_SCALARS[t], f.read(struct.calcsize(_GGUF_SCALARS[t])))
            elif key.startswith(wanted_prefix) and t == 8:
                out[key] = rstr()
            else:
                skip_value(t)
    return out


def projector_caps(mmproj_path: str) -> dict:
    """{"vision": bool, "audio": bool} for a vision/audio projector file.
    Unknown/old files are assumed vision-only (what they were used for)."""
    if not mmproj_path or not os.path.isfile(mmproj_path):
        return {"vision": False, "audio": False}
    key = (mmproj_path, os.path.getmtime(mmproj_path))
    if key in _CAPS_CACHE:
        return _CAPS_CACHE[key]
    caps = {"vision": True, "audio": False}
    try:
        kv = _read_gguf_kv(mmproj_path)
        if "clip.has_audio_encoder" in kv:
            caps["audio"] = bool(kv["clip.has_audio_encoder"])
        if "clip.has_vision_encoder" in kv:
            caps["vision"] = bool(kv["clip.has_vision_encoder"])
    except Exception:
        pass
    _CAPS_CACHE[key] = caps
    return caps
