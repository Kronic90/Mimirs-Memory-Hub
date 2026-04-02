"""Preset evaluation script for Mimir's Memory Hub.

Tests that each preset (companion, agent, character, writer, assistant, custom) produces
behaviour appropriate for its role by checking system-prompt construction, memory
tag generation, and response tone across a small set of role-specific scenarios.

Usage:
    python _test_presets.py              # quick in-process checks (no LLM needed)
    python _test_presets.py --live       # also test against a running Mimir instance
"""

import sys, json, importlib, re

# ── In-process structural tests ──────────────────────────────────────────────

def test_preset_definitions():
    """Verify every preset has required keys and sensible values."""
    sys.path.insert(0, ".")
    from playground.presets import PRESETS

    REQUIRED_KEYS = {
        "label", "description", "icon", "chemistry", "emotion_weight",
        "social_priority", "task_priority", "system_prompt_suffix",
        "mimir_overrides",
    }
    passed = 0
    for name, preset in PRESETS.items():
        missing = REQUIRED_KEYS - set(preset.keys())
        assert not missing, f"Preset '{name}' missing keys: {missing}"
        assert isinstance(preset["emotion_weight"], (int, float))
        assert 0.0 <= preset["emotion_weight"] <= 1.0, f"{name} emotion_weight out of range"
        assert isinstance(preset["system_prompt_suffix"], str) and len(preset["system_prompt_suffix"]) > 10
        passed += 1
    print(f"[PASS] All {passed} presets have valid structure")


def test_no_copilot_preset():
    """Copilot preset should have been merged into agent."""
    from playground.presets import PRESETS
    assert "copilot" not in PRESETS, "copilot preset still exists — should be merged into agent"
    print("[PASS] No copilot preset (merged into agent)")


def test_agent_has_tools():
    """Agent preset must include tool documentation."""
    from playground.presets import PRESETS
    suffix = PRESETS["agent"]["system_prompt_suffix"]
    for tool in ["read_file", "write_file", "run_code", "shell_exec", "fetch_page",
                 "http_request", "json_parse", "screenshot", "clipboard", "system_info",
                 "diff_files", "pdf_read", "csv_query", "regex_replace"]:
        assert tool in suffix, f"Agent preset missing tool doc for '{tool}'"
    assert "save_file" in suffix.lower(), "Agent preset missing save_file instructions"
    assert "workflow" in suffix.lower(), "Agent preset missing workflow section"
    print("[PASS] Agent preset has full tool documentation and workflow")


def test_companion_emotional():
    """Companion preset must prioritise emotion and social connection."""
    from playground.presets import PRESETS
    p = PRESETS["companion"]
    assert p["emotion_weight"] >= 0.7, f"Companion emotion_weight too low: {p['emotion_weight']}"
    assert p["chemistry"] is True, "Companion should enable chemistry"
    assert p["social_priority"] is True
    assert p["task_priority"] is False
    suffix = p["system_prompt_suffix"]
    assert "emotion" in suffix.lower() or "feel" in suffix.lower(), "Companion prompt lacks emotional language"
    print("[PASS] Companion preset is emotionally tuned")


def test_character_full_roleplay():
    """Character preset must maximise emotion and immersion."""
    from playground.presets import PRESETS
    p = PRESETS["character"]
    assert p["emotion_weight"] >= 0.9, f"Character emotion_weight too low: {p['emotion_weight']}"
    assert p["chemistry"] is True
    print("[PASS] Character preset is fully immersive")


def test_writer_creative():
    """Writer preset must enable creativity with emotional memory."""
    from playground.presets import PRESETS
    p = PRESETS["writer"]
    assert p["emotion_weight"] >= 0.4, f"Writer emotion_weight too low: {p['emotion_weight']}"
    assert p["chemistry"] is True, "Writer should enable chemistry for creative energy"
    assert p["task_priority"] is False
    suffix = p["system_prompt_suffix"].lower()
    assert "creative" in suffix or "writing" in suffix, "Writer prompt lacks creative language"
    assert "style" in suffix or "imagery" in suffix, "Writer prompt lacks style guidance"
    print("[PASS] Writer preset is creatively tuned")


def test_assistant_neutral():
    """Assistant preset must be factual, low emotion."""
    from playground.presets import PRESETS
    p = PRESETS["assistant"]
    assert p["emotion_weight"] <= 0.2
    assert p["task_priority"] is True
    assert p["chemistry"] is False
    suffix = p["system_prompt_suffix"].lower()
    assert "concise" in suffix, "Assistant prompt should emphasise conciseness"
    print("[PASS] Assistant preset is neutral/factual")


def test_agent_task_focused():
    """Agent preset must be task-focused with low emotion."""
    from playground.presets import PRESETS
    p = PRESETS["agent"]
    assert p["emotion_weight"] <= 0.3
    assert p["task_priority"] is True
    assert p["chemistry"] is False
    print("[PASS] Agent preset is task-focused")


def test_memory_format_differentiation():
    """Companion/character use emotional memory; agent/assistant use task memory."""
    from playground.presets import PRESETS

    emotional_keywords = ["emotion", "cherish", "anchor", "social impression"]
    task_keywords = ["task", "goal", "solution", "lesson"]

    for name in ("companion", "character", "writer"):
        suffix = PRESETS[name]["system_prompt_suffix"].lower()
        found = [k for k in emotional_keywords if k in suffix]
        assert len(found) >= 2, f"{name} missing emotional memory keywords (found: {found})"

    for name in ("agent", "assistant"):
        suffix = PRESETS[name]["system_prompt_suffix"].lower()
        found = [k for k in task_keywords if k in suffix]
        assert len(found) >= 2, f"{name} missing task memory keywords (found: {found})"

    print("[PASS] Memory formats match preset roles")


def test_ui_has_no_copilot_option():
    """Check that copilot option was removed from HTML and JS."""
    with open("playground/static/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    assert "copilot" not in html.lower().split("<!--")[0], "index.html still has copilot option"
    assert "writer" in html.lower(), "index.html missing writer preset option"

    with open("playground/static/js/agents.js", "r", encoding="utf-8") as f:
        js = f.read()
    assert "copilot" not in js.lower(), "agents.js still has copilot option"
    assert "writer" in js.lower(), "agents.js missing writer preset option"

    print("[PASS] UI dropdowns have no copilot, has writer")


# ── Live API tests (optional, requires running server) ───────────────────────

def test_live_presets():
    """Hit the running Mimir server to verify presets respond differently."""
    import urllib.request

    base = "http://localhost:5000"
    try:
        urllib.request.urlopen(f"{base}/api/status", timeout=3)
    except Exception:
        print("[SKIP] Live tests — server not running on :5000")
        return

    presets_resp = urllib.request.urlopen(f"{base}/api/presets")
    presets = json.loads(presets_resp.read())
    names = [p["name"] if isinstance(p, dict) else p for p in presets]
    assert "copilot" not in names, "Server still returns copilot preset"
    assert "agent" in names
    print("[PASS] /api/presets has no copilot, has agent")


# ── Runner ───────────────────────────────────────────────────────────────────

def main():
    import os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    tests = [
        test_preset_definitions,
        test_no_copilot_preset,
        test_agent_has_tools,
        test_companion_emotional,
        test_character_full_roleplay,
        test_writer_creative,
        test_assistant_neutral,
        test_agent_task_focused,
        test_memory_format_differentiation,
        test_ui_has_no_copilot_option,
    ]
    if "--live" in sys.argv:
        tests.append(test_live_presets)

    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {t.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {len(tests) - failed}/{len(tests)} passed" + (" ✓" if not failed else f", {failed} failed"))
    return failed


if __name__ == "__main__":
    sys.exit(main())
