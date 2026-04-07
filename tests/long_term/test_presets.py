"""
Preset System Tests
====================
Tests all presets (companion, agent, character, writer, assistant, custom):
- Correct system prompt generation
- Memory context injection per preset
- Chemistry enable/disable per preset
- Emotion weight effects
- Process turn behavior differences
- Context block formatting
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.long_term.harness import SimulationHarness

try:
    from playground.presets import PRESETS, get_preset
    HAS_PRESETS = True
except ImportError:
    HAS_PRESETS = False


def test_all_presets_exist():
    """Test: all expected presets are defined."""
    with SimulationHarness("presets_exist") as h:
        if not HAS_PRESETS:
            h.metrics.record("presets_available", False, "Could not import PRESETS")
            return h.metrics

        expected = ["companion", "agent", "character", "writer", "assistant", "custom"]
        for name in expected:
            preset = get_preset(name)
            h.metrics.record(f"preset_{name}_exists",
                             preset is not None and preset.get("label"),
                             f"Preset '{name}': {preset.get('label', 'MISSING')}")

        return h.metrics


def test_preset_chemistry_settings():
    """Test: chemistry enable/disable matches preset definition."""
    with SimulationHarness("presets_chemistry") as h:
        if not HAS_PRESETS:
            h.metrics.record("presets_available", False, "No presets")
            return h.metrics

        expectations = {
            "companion": True,
            "agent": False,
            "character": True,
            "writer": True,
            "assistant": False,
        }

        for name, expected_chem in expectations.items():
            preset = get_preset(name)
            actual = preset.get("chemistry", None)
            h.metrics.record(f"chem_{name}",
                             actual == expected_chem,
                             f"{name}: chemistry={actual} (expected {expected_chem})")

        return h.metrics


def test_preset_emotion_weights():
    """Test: emotion weights are correct for each preset."""
    with SimulationHarness("presets_weights") as h:
        if not HAS_PRESETS:
            h.metrics.record("presets_available", False, "No presets")
            return h.metrics

        expectations = {
            "companion": 0.8,
            "agent": 0.2,
            "character": 1.0,
            "writer": 0.5,
            "assistant": 0.15,
        }

        for name, expected_weight in expectations.items():
            preset = get_preset(name)
            actual = preset.get("emotion_weight", None)
            h.metrics.record(f"weight_{name}",
                             actual == expected_weight,
                             f"{name}: emotion_weight={actual} (expected {expected_weight})")

        return h.metrics


def test_preset_context_generation():
    """Test: each preset generates valid context blocks."""
    preset_names = ["companion", "agent", "character", "writer", "assistant"]

    with SimulationHarness("presets_context") as h:
        # Seed some memories first
        h.remember("User is a software developer named Scott",
                   emotion="warm", importance=7)
        h.remember("User's partner is named Jamie",
                   emotion="warm", importance=6)
        h.start_task("Write documentation", priority=7, project="TestProject")

        for name in preset_names:
            try:
                preset = get_preset(name) if HAS_PRESETS else {"label": name}
                htest = SimulationHarness(f"ctx_{name}", preset_name=name)
                htest.remember("Test memory for context", emotion="curious",
                               importance=5)

                context = htest.get_context(conversation="testing context",
                                            entity="Scott")
                h.metrics.record(f"context_{name}",
                                 isinstance(context, str),
                                 f"{name} context length: {len(context)} chars")
                htest.cleanup()
            except Exception as e:
                h.metrics.record(f"context_{name}", False, f"Error: {e}")

        return h.metrics


def test_companion_process_turn():
    """Test: companion preset process_turn with high emotion weight."""
    with SimulationHarness("preset_companion_turn",
                           preset_name="companion") as h:
        result = h.process(
            "I'm so excited about my new job!",
            "That's amazing news! Tell me everything!"
        )

        h.metrics.record("companion_emotion",
                         "emotion" in result,
                         f"Detected emotion: {result.get('emotion')}")
        h.metrics.record("companion_importance",
                         "importance" in result,
                         f"Importance: {result.get('importance')}")
        h.metrics.record("companion_mood",
                         result.get("mood_label") is not None,
                         f"Mood: {result.get('mood_label')}")

        return h.metrics


def test_agent_process_turn():
    """Test: agent preset process_turn with low emotion weight."""
    with SimulationHarness("preset_agent_turn",
                           preset_name="agent",
                           chemistry=False) as h:
        result = h.process(
            "Can you help me debug this function?",
            "Sure! Let me analyze it. The issue is in line 42."
        )

        h.metrics.record("agent_result",
                         result is not None,
                         f"Agent result keys: {list(result.keys()) if result else 'None'}")

        return h.metrics


def test_character_high_emotion():
    """Test: character preset with emotion_weight=1.0 amplifies emotions."""
    with SimulationHarness("preset_character_emotion",
                           preset_name="character") as h:
        # Emotional RP scene
        for _ in range(5):
            h.process(
                "*tears streaming down face* I can't believe they're gone.",
                "*pulls you close* I know... I know. Just let it out. I'm here."
            )
            h.advance_hours(0.5)

        mood = h.get_mood()
        h.metrics.record("character_mood_responsive",
                         mood.get("mood_label") is not None,
                         f"Character mood: {mood.get('mood_label')}")

        h.assert_chemistry_stable("character_chemistry")
        return h.metrics


def test_writer_task_support():
    """Test: writer preset supports task tracking."""
    with SimulationHarness("preset_writer_tasks",
                           preset_name="writer") as h:
        h.start_task("Write chapter 1", priority=8, project="Novel")
        h.start_task("Research setting", priority=6, project="Novel")

        try:
            tasks = h.manager.get_active_tasks()
            h.metrics.record("writer_tasks",
                             len(tasks) >= 2,
                             f"Active tasks: {len(tasks)}")
        except Exception as e:
            h.metrics.record("writer_tasks", False, f"Error: {e}")

        return h.metrics


def test_preset_fallback():
    """Test: unknown preset name falls back gracefully."""
    with SimulationHarness("preset_fallback") as h:
        if not HAS_PRESETS:
            h.metrics.record("fallback_test", False, "No presets module")
            return h.metrics

        preset = get_preset("nonexistent_preset_xyz")
        h.metrics.record("fallback_valid",
                         preset is not None and preset.get("label") is not None,
                         f"Fallback preset: {preset.get('label', 'NULL')}")

        return h.metrics


# ═══════════════════════════════════════════════════════════════
#  Collect all tests
# ═══════════════════════════════════════════════════════════════

ALL_PRESET_TESTS = [
    ("All Presets Exist", test_all_presets_exist),
    ("Chemistry Settings", test_preset_chemistry_settings),
    ("Emotion Weights", test_preset_emotion_weights),
    ("Context Generation", test_preset_context_generation),
    ("Companion Process Turn", test_companion_process_turn),
    ("Agent Process Turn", test_agent_process_turn),
    ("Character High Emotion", test_character_high_emotion),
    ("Writer Task Support", test_writer_task_support),
    ("Preset Fallback", test_preset_fallback),
]
