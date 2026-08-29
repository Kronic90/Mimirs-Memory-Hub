"""GPU/local-model-backend diagnostics and guided update helpers.

Local GGUF model loading depends on a llama-cpp-python build that actually
matches the user's GPU — a mismatch (wrong CUDA version, unsupported
architecture, CPU-only build) fails in ways that are hard to diagnose from
the raw error alone. This module answers "what GPU do we have, and can the
installed llama-cpp-python actually use it" so the UI can show that plainly,
and provides a safe, reversible update path for when it can't.

Nothing here runs automatically — every mutating function is opt-in, called
only from an explicit user action in Settings.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


# ── GPU detection ────────────────────────────────────────────────────────

def detect_gpu() -> dict:
    """Report the primary NVIDIA GPU's name, driver version, and compute
    capability via nvidia-smi. Returns {"available": False} on any non-NVIDIA
    or driver-less system — never raises."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,compute_cap",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {"available": False}
        line = result.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            return {"available": False}
        name, driver_version, compute_cap = parts[0], parts[1], parts[2]

        # nvidia-smi's summary table also reports the max CUDA runtime the
        # driver supports (distinct from any separately-installed toolkit).
        driver_cuda_version = ""
        smi_result = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True, timeout=10)
        m = re.search(r"CUDA\s+(?:Version|UMD Version)\s*:\s*([\d.]+)",
                       smi_result.stdout)
        if m:
            driver_cuda_version = m.group(1)

        return {
            "available": True,
            "name": name,
            "driver_version": driver_version,
            "compute_capability": compute_cap,
            "driver_max_cuda_version": driver_cuda_version,
        }
    except Exception:
        return {"available": False}


def detect_llama_cpp_status() -> dict:
    """Report whether llama-cpp-python is importable, its version, and
    whether it actually supports GPU offload. Never raises — a broken or
    missing install is reported as data, not an exception."""
    try:
        import llama_cpp
    except Exception as e:
        return {"installed": False, "error": str(e)}

    version = getattr(llama_cpp, "__version__", "unknown")
    gpu_offload_supported = False
    try:
        from llama_cpp import llama_cpp as _lc
        gpu_offload_supported = bool(_lc.llama_supports_gpu_offload())
    except Exception:
        pass

    return {
        "installed": True,
        "version": version,
        "gpu_offload_supported": gpu_offload_supported,
    }


def backend_status() -> dict:
    """Combined GPU + llama-cpp-python status for the Settings status card."""
    return {
        "gpu": detect_gpu(),
        "llama_cpp": detect_llama_cpp_status(),
    }


# ── Curated compatibility table ──────────────────────────────────────────
# Community-maintained, self-contained (bundled CUDA runtime) wheels, keyed
# by compute-capability family. Best-effort, not guaranteed current — there
# is no single official source covering every GPU generation. Only wheels
# confirmed self-contained (no separate CUDA *toolkit* dependency) belong
# here; a wheel that merely links against a system CUDA install can silently
# fail to load on machines without that exact toolkit version, as happened
# during development of this feature.
COMPATIBLE_WHEELS: dict[str, dict] = {
    # RTX 20-series (Turing)
    "7.5": {
        "label": "Turing (sm_75)",
        "url": ("https://huggingface.co/boneylizardwizard/"
                "llama_cpp_python-0.3.16-cp312-cp312-win_amd64/resolve/main/"
                "llama_cpp_python-0.3.16-cp312-cp312-win_amd64.whl"),
        "version": "0.3.16",
    },
    # RTX 30-series (Ampere)
    "8.6": {
        "label": "Ampere (sm_86)",
        "url": ("https://huggingface.co/boneylizardwizard/"
                "llama_cpp_python-0.3.16-cp312-cp312-win_amd64/resolve/main/"
                "llama_cpp_python-0.3.16-cp312-cp312-win_amd64.whl"),
        "version": "0.3.16",
    },
    # RTX 40-series (Ada Lovelace)
    "8.9": {
        "label": "Ada Lovelace (sm_89)",
        "url": ("https://huggingface.co/boneylizardwizard/"
                "llama_cpp_python-0.3.16-cp312-cp312-win_amd64/resolve/main/"
                "llama_cpp_python-0.3.16-cp312-cp312-win_amd64.whl"),
        "version": "0.3.16",
    },
    # RTX 50-series (Blackwell) — the one confirmed working live during
    # development. Confirmed self-contained; does NOT include qwen35
    # architecture support (llama.cpp version bundled predates it).
    "12.0": {
        "label": "Blackwell (sm_120)",
        "url": ("https://huggingface.co/boneylizardwizard/"
                "llama_cpp_python-0.3.16-cp312-cp312-win_amd64/resolve/main/"
                "llama_cpp_python-0.3.16-cp312-cp312-win_amd64.whl"),
        "version": "0.3.16",
    },
}


def find_candidate_wheel(compute_capability: str) -> dict | None:
    """Look up a known-good self-contained wheel for a compute capability.
    Returns None if nothing is known for it — never guesses."""
    return COMPATIBLE_WHEELS.get(compute_capability)


# ── Backup / restore ─────────────────────────────────────────────────────

def _llama_cpp_package_dir() -> Path | None:
    try:
        import llama_cpp
        return Path(llama_cpp.__file__).parent
    except Exception:
        return None


def backup_current_backend(backup_root: Path) -> dict:
    """Copy the currently-installed llama_cpp package directory to a local,
    byte-exact restore point that doesn't depend on any external URL still
    being reachable later. Returns {"ok": bool, "path": str, "version": str}."""
    pkg_dir = _llama_cpp_package_dir()
    if pkg_dir is None or not pkg_dir.is_dir():
        return {"ok": False, "error": "llama_cpp is not currently installed — nothing to back up."}

    status = detect_llama_cpp_status()
    version = status.get("version", "unknown")
    dest = backup_root / f"llama_cpp_{version}_{int(time.time())}"
    try:
        shutil.copytree(pkg_dir, dest)
        return {"ok": True, "path": str(dest), "version": version}
    except Exception as e:
        return {"ok": False, "error": f"Backup failed: {e}"}


def restore_backend(backup_path: str) -> dict:
    """Restore a previously-made backup over the live llama_cpp install."""
    pkg_dir = _llama_cpp_package_dir()
    src = Path(backup_path)
    if not src.is_dir():
        return {"ok": False, "error": f"Backup path does not exist: {backup_path}"}
    try:
        if pkg_dir is not None and pkg_dir.is_dir():
            shutil.rmtree(pkg_dir)
        elif pkg_dir is None:
            # llama_cpp isn't importable right now (e.g. a broken install
            # left no package dir) — restore next to the other site-packages.
            import site
            pkg_dir = Path(site.getsitepackages()[0]) / "llama_cpp"
        shutil.copytree(src, pkg_dir)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"Restore failed: {e}"}


def verify_backend_in_subprocess(python_exe: str = "") -> dict:
    """Import llama_cpp and check GPU offload support in a FRESH subprocess
    — required because Python won't cleanly re-import a native extension
    that failed to load in-process, so testing after an install must not
    reuse the current process's already-loaded (or already-failed) module."""
    py = python_exe or sys.executable
    code = (
        "import json\n"
        "try:\n"
        "    import llama_cpp\n"
        "    from llama_cpp import llama_cpp as _lc\n"
        "    print(json.dumps({'ok': True, "
        "'version': getattr(llama_cpp, '__version__', 'unknown'), "
        "'gpu_offload_supported': bool(_lc.llama_supports_gpu_offload())}))\n"
        "except Exception as e:\n"
        "    print(json.dumps({'ok': False, 'error': str(e)}))\n"
    )
    try:
        result = subprocess.run(
            [py, "-c", code], capture_output=True, text=True, timeout=30)
        import json as _json
        out = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        if out:
            return _json.loads(out)
        return {"ok": False, "error": result.stderr[-500:] or "No output from verification subprocess."}
    except Exception as e:
        return {"ok": False, "error": f"Verification subprocess failed: {e}"}
